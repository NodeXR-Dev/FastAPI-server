import asyncio
import time
from collections.abc import Callable
from functools import lru_cache
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

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
            await self._run_room(room_id)

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
            state = await self.graph.ainvoke(
                room_id=room_id,
                batch_run_id=batch_run_id,
            )
            result = state.get("persistence_result")
            analysis = state.get("analysis_result")
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


@lru_cache(maxsize=1)
def get_reflection_scheduler() -> ReflectionScheduler:
    return ReflectionScheduler()
