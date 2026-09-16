import asyncio
import time
from collections.abc import Callable
from functools import lru_cache
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from langsmith import trace

from app.agent.graph.reflection_batch_graph import (
    ReflectionBatchGraph,
)
from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import SessionLocal
from app.repository.reflection_batch_repository import ReflectionBatchRepository
from app.service.agent.reflection_batch_service import ReflectionBatchService

logger = get_logger(__name__)


class ReflectionScheduler:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        lock_repository: ReflectionBatchRepository | None = None,
        service: ReflectionBatchService | None = None,
        graph: ReflectionBatchGraph | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.lock_repository = lock_repository or ReflectionBatchRepository()
        self.service = service or ReflectionBatchService(
            session_factory=session_factory,
        )
        self.graph = graph or ReflectionBatchGraph(service=self.service)
        self.interval_seconds = (
            settings.REFLECTION_BATCH_INTERVAL_SECONDS
            if interval_seconds is None
            else interval_seconds
        )
        self.max_consecutive_failures = (
            settings.REFLECTION_BATCH_MAX_CONSECUTIVE_FAILURES
        )
        self._failure_counts: dict[UUID, int] = {}
        self._retry_after: dict[UUID, float] = {}
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if not settings.REFLECTION_BATCH_ENABLED:
            logger.info("[reflection_scheduler_disabled]")
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run_loop(),
            name="reflection-batch-scheduler",
        )
        logger.info(
            "[reflection_scheduler_started] interval_seconds=%s",
            self.interval_seconds,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
        logger.info("[reflection_scheduler_stopped]")

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
                continue
            except TimeoutError:
                pass
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.exception(
                    "[reflection_scheduler_iteration_failed] error=%s",
                    str(error),
                )

    async def run_once(self) -> None:
        room_ids = await asyncio.to_thread(self.service.find_pending_room_ids)
        for room_id in room_ids:
            if self._is_backing_off(room_id):
                continue
            await self._run_room(room_id)

    async def run_room_until_drained(
        self,
        room_id: UUID,
        *,
        max_runs: int = 5,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        """한 방의 미처리 발화·그래프 이벤트를 주기를 기다리지 않고 반영한다.

        회의 종료 리포트는 마지막 몇 분의 발화까지 design_fact 로 구조화된 뒤에 만들어야
        한다. 주기 실행과 같은 advisory lock 을 쓰므로 둘이 겹쳐 돌지 않는다. 주기 실행이
        이 방을 잡고 있으면 잠시 기다렸다 다시 확인한다. 배치가 실패하면 더 돌지 않는다.
        """
        for attempt in range(max_runs):
            pending_room_ids = await asyncio.to_thread(self.service.find_pending_room_ids)
            if room_id not in pending_room_ids:
                return
            if self._is_backing_off(room_id):
                return
            failures_before = self._failure_counts.get(room_id, 0)
            await self._run_room(room_id)
            if self._failure_counts.get(room_id, 0) > failures_before:
                logger.warning(
                    "[reflection_drain_stopped_on_failure] room_id=%s | attempt=%s",
                    room_id,
                    attempt + 1,
                )
                return
            await asyncio.sleep(retry_delay_seconds)
        logger.warning(
            "[reflection_drain_incomplete] room_id=%s | max_runs=%s",
            room_id,
            max_runs,
        )

    async def _run_room(self, room_id: UUID) -> None:
        lock_db = self.session_factory()
        acquired = False
        batch_run_id = uuid4()
        started_at = time.perf_counter()
        try:
            acquired = self.lock_repository.try_acquire_room_lock(
                lock_db,
                room_id=room_id,
            )
            if not acquired:
                logger.info(
                    "[reflection_batch_skipped_locked] room_id=%s | batch_run_id=%s",
                    room_id,
                    batch_run_id,
                )
                return
            logger.info(
                "[reflection_batch_started] room_id=%s | batch_run_id=%s",
                room_id,
                batch_run_id,
            )
            with trace(
                name="ReflectionBatchRun",
                run_type="chain",
                inputs={
                    "room_id": str(room_id),
                    "batch_run_id": str(batch_run_id),
                },
                tags=["reflection-batch", "cold-path"],
                metadata={"room_id": str(room_id), "batch_run_id": str(batch_run_id)},
            ) as batch_trace:
                state = await self.graph.ainvoke(
                    room_id=room_id,
                    batch_run_id=batch_run_id,
                )
                result = state.get("persistence_result")
                analysis = state.get("analysis_result")
                if batch_trace is not None:
                    batch_trace.end(
                        outputs={
                            "utterance_count": len(state.get("utterances", [])),
                            "graph_event_count": len(state.get("graph_events", [])),
                            "topic_count": len(state.get("topic_ids", [])),
                            "retrieved_fact_count": len(state.get("existing_facts", [])),
                            "retrieved_memory_count": len(state.get("semantic_memories", [])),
                            "generated_fact_count": len(analysis.facts) if analysis is not None else 0,
                            "generated_link_count": len(analysis.links) if analysis is not None else 0,
                            "persistence_result": result.model_dump() if result is not None else None,
                        }
                    )
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "[reflection_batch_succeeded] room_id=%s | batch_run_id=%s "
                "| utterance_count=%s | graph_event_count=%s | topic_count=%s "
                "| retrieved_fact_count=%s | retrieved_memory_count=%s "
                "| generated_fact_count=%s | generated_link_count=%s "
                "| result=%s | elapsed_ms=%.2f",
                room_id,
                batch_run_id,
                len(state.get("utterances", [])),
                len(state.get("graph_events", [])),
                len(state.get("topic_ids", [])),
                len(state.get("existing_facts", [])),
                len(state.get("semantic_memories", [])),
                len(analysis.facts) if analysis is not None else 0,
                len(analysis.links) if analysis is not None else 0,
                result.model_dump() if result is not None else None,
                elapsed_ms,
            )
            self._clear_failure(room_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.exception(
                "[reflection_batch_failed] room_id=%s | batch_run_id=%s | elapsed_ms=%.2f | error=%s",
                room_id,
                batch_run_id,
                elapsed_ms,
                str(error),
            )
            self._record_failure(room_id)
        finally:
            if acquired:
                try:
                    self.lock_repository.release_room_lock(
                        lock_db,
                        room_id=room_id,
                    )
                except Exception as unlock_error:
                    logger.exception(
                        "[reflection_batch_unlock_failed] room_id=%s | batch_run_id=%s | error=%s",
                        room_id,
                        batch_run_id,
                        str(unlock_error),
                    )
            lock_db.close()

    def _is_backing_off(self, room_id: UUID) -> bool:
        retry_after = self._retry_after.get(room_id)
        if retry_after is None:
            return False
        remaining_seconds = retry_after - time.monotonic()
        if remaining_seconds <= 0:
            return False
        logger.info(
            "[reflection_batch_skipped_backoff] room_id=%s | failure_count=%s "
            "| retry_in_seconds=%.1f",
            room_id,
            self._failure_counts.get(room_id, 0),
            remaining_seconds,
        )
        return True

    def _record_failure(self, room_id: UUID) -> None:
        failure_count = self._failure_counts.get(room_id, 0) + 1
        self._failure_counts[room_id] = failure_count
        if failure_count < self.max_consecutive_failures:
            return
        exponent = min(failure_count - self.max_consecutive_failures + 1, 16)
        backoff_cycles = min(
            float(2**exponent),
            settings.REFLECTION_BATCH_MAX_BACKOFF_CYCLES,
        )
        delay_seconds = self.interval_seconds * backoff_cycles
        self._retry_after[room_id] = time.monotonic() + delay_seconds
        logger.warning(
            "[reflection_batch_backoff_applied] room_id=%s | failure_count=%s "
            "| delay_seconds=%.1f",
            room_id,
            failure_count,
            delay_seconds,
        )

    def _clear_failure(self, room_id: UUID) -> None:
        if self._failure_counts.pop(room_id, None) is not None:
            logger.info(
                "[reflection_batch_backoff_cleared] room_id=%s",
                room_id,
            )
        self._retry_after.pop(room_id, None)


@lru_cache(maxsize=1)
def get_reflection_scheduler() -> ReflectionScheduler:
    return ReflectionScheduler()
