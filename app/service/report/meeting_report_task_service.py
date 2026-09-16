import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.ws_response import ws_error_event
from app.db.session import SessionLocal
from app.model.enum import MeetingReportStatus
from app.schema.report.ws_event_report_payload import ReportGeneratedPayload
from app.schema.websocket.ws_event import ReportGeneratedWSEvent
from app.service.agent.reflection_scheduler import get_reflection_scheduler
from app.service.report.meeting_report_service import MeetingReportService
from app.service.websocket.connection_manager import RoomConnectionManager, room_ws_manager

logger = get_logger(__name__)

ReflectionDrain = Callable[[UUID], Awaitable[None]]
T = TypeVar("T")


async def _drain_with_scheduler(room_id: UUID) -> None:
    if not settings.REFLECTION_BATCH_ENABLED:
        return
    await get_reflection_scheduler().run_room_until_drained(room_id)


class MeetingReportTaskService:
    """회의 종료 후 BackgroundTasks 로 도는 리포트 생성.

    Image2DGenerationTaskService 와 같이 요청 세션을 쓰지 않고 단계마다 새 세션을 연다.
    DB 작업은 스레드에서, LLM 호출과 WS 전송은 이벤트 루프에서 한다.
    완료 이벤트는 종료를 요청한 사용자에게만 보낸다. 방 전체 전파는 Unity 가 Photon 으로 한다.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        ws_manager: RoomConnectionManager = room_ws_manager,
        report_service: MeetingReportService | None = None,
        reflection_drain: ReflectionDrain = _drain_with_scheduler,
    ) -> None:
        self.session_factory = session_factory
        self.ws_manager = ws_manager
        self.report_service = report_service or MeetingReportService()
        self.reflection_drain = reflection_drain

    async def run(
        self,
        *,
        report_id: UUID,
        room_id: UUID,
        user_id: UUID | None,
        base_url: str | None,
    ) -> None:
        logger.info(
            "[meeting_report_task_started] report_id=%s | room_id=%s | user_id=%s",
            report_id,
            room_id,
            user_id,
        )

        claimed = await self._in_session(
            lambda db: self.report_service.claim_report(db, report_id=report_id)
        )
        if not claimed:
            await self._deliver_existing(
                report_id=report_id,
                room_id=room_id,
                user_id=user_id,
                base_url=base_url,
            )
            return

        try:
            try:
                await self.reflection_drain(room_id)
            except Exception as error:
                # 반영이 덜 됐어도 이미 구조화된 데이터로 리포트는 만들 수 있다.
                logger.exception(
                    "[meeting_report_reflection_drain_failed] report_id=%s | room_id=%s | error=%s",
                    report_id,
                    room_id,
                    str(error),
                )

            inputs = await self._in_session(
                lambda db: self.report_service.load_inputs(db, report_id=report_id)
            )
            inferred, llm_call_count = await self.report_service.infer_missing_decisions(
                inputs
            )
            await self._in_session(
                lambda db: self.report_service.complete_report(
                    db,
                    inputs=inputs,
                    inferred=inferred,
                    llm_call_count=llm_call_count,
                )
            )
        except Exception as error:
            logger.exception(
                "[meeting_report_task_failed] report_id=%s | room_id=%s | error=%s",
                report_id,
                room_id,
                str(error),
            )
            try:
                await self._in_session(
                    lambda db: self.report_service.fail_report(
                        db,
                        report_id=report_id,
                        error_message=f"{type(error).__name__}: {error}",
                    )
                )
            except Exception as record_error:
                logger.exception(
                    "[meeting_report_fail_record_failed] report_id=%s | error=%s",
                    report_id,
                    str(record_error),
                )
            await self._send_error(room_id=room_id, user_id=user_id)
            return

        await self._deliver_existing(
            report_id=report_id,
            room_id=room_id,
            user_id=user_id,
            base_url=base_url,
        )

    async def _deliver_existing(
        self,
        *,
        report_id: UUID,
        room_id: UUID,
        user_id: UUID | None,
        base_url: str | None,
    ) -> None:
        link = await self._in_session(
            lambda db: self.report_service.get_report_link(
                db,
                report_id=report_id,
                base_url=base_url,
            )
        )
        if link is None or link.status != MeetingReportStatus.COMPLETED.value:
            # 다른 작업이 생성 중이다. 그 작업이 끝나면 자기 요청자에게 보낸다.
            logger.info(
                "[meeting_report_task_skipped] report_id=%s | status=%s",
                report_id,
                link.status if link else None,
            )
            return
        if user_id is None:
            # GET /report/{room_id} 로 요청된 생성은 응답에 이미 url 이 실렸다.
            logger.info(
                "[meeting_report_task_completed] report_id=%s | room_id=%s | ws_sent=skipped",
                report_id,
                room_id,
            )
            return

        event = ReportGeneratedWSEvent(
            room_id=room_id,
            user_id=user_id,
            payload=ReportGeneratedPayload(
                report_id=link.report_id,
                report_version=link.report_version,
                report_url=link.report_url,
            ),
        )
        try:
            sent = await self.ws_manager.send_to_user(
                room_id=room_id,
                user_id=user_id,
                message=event.model_dump(mode="json"),
            )
        except Exception as error:
            logger.exception(
                "[meeting_report_ws_failed] report_id=%s | room_id=%s | user_id=%s | error=%s",
                report_id,
                room_id,
                user_id,
                str(error),
            )
            return

        logger.info(
            "[meeting_report_task_completed] report_id=%s | room_id=%s | user_id=%s | ws_sent=%s",
            report_id,
            room_id,
            user_id,
            sent,
        )

    async def _send_error(self, *, room_id: UUID, user_id: UUID | None) -> None:
        if user_id is None:
            return
        try:
            await self.ws_manager.send_to_user(
                room_id=room_id,
                user_id=user_id,
                message=ws_error_event(
                    room_id=room_id,
                    user_id=user_id,
                    code=ResponseCode.REPORT500,
                    failed_event_type="REPORT_GENERATED",
                ),
            )
        except Exception as error:
            logger.exception(
                "[meeting_report_error_ws_failed] room_id=%s | user_id=%s | error=%s",
                room_id,
                user_id,
                str(error),
            )

    async def _in_session(self, work: Callable[[Session], T]) -> T:
        def run() -> T:
            db = self.session_factory()
            try:
                return work(db)
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        return await asyncio.to_thread(run)
