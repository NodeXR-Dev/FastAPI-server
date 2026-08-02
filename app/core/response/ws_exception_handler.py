from uuid import UUID

from fastapi import WebSocket
from pydantic import ValidationError

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BaseCustomException
from app.core.response.ws_exceptions import BaseWSException
from app.core.response.ws_response import send_ws_error_to_requester

logger = get_logger(__name__)


async def handle_ws_exception(
    *,
    websocket: WebSocket,
    exc: Exception,
    room_id: UUID | None,
    user_id: UUID | None,
    job_id: UUID | None = None,
    failed_event_type: str | None = None,
) -> None:
    if isinstance(exc, ValidationError):
        logger.warning(
            "[ws_validation_error] room_id=%s | user_id=%s | event_type=%s | error=%s",
            room_id,
            user_id,
            failed_event_type,
            str(exc),
        )

        await send_ws_error_to_requester(
            websocket=websocket,
            room_id=room_id,
            user_id=user_id,
            code=ResponseCode.WS400,
            job_id=job_id,
            failed_event_type=failed_event_type,
            detail=str(exc),
        )
        return

    if isinstance(exc, BaseWSException):
        logger.warning(
            "[ws_exception] room_id=%s | user_id=%s | event_type=%s | code=%s | detail=%s",
            room_id,
            user_id,
            exc.failed_event_type or failed_event_type,
            exc.code,
            exc.detail,
        )

        await send_ws_error_to_requester(
            websocket=websocket,
            room_id=room_id,
            user_id=user_id,
            code=exc.code,
            job_id=job_id,
            failed_event_type=exc.failed_event_type or failed_event_type,
            message=exc.message,
            detail=exc.detail,
        )
        return

    if isinstance(exc, BaseCustomException):
        logger.warning(
            "[ws_custom_exception] room_id=%s | user_id=%s | event_type=%s | code=%s | message=%s",
            room_id,
            user_id,
            failed_event_type,
            exc.code,
            exc.message,
        )

        await send_ws_error_to_requester(
            websocket=websocket,
            room_id=room_id,
            user_id=user_id,
            code=exc.code,
            job_id=job_id,
            failed_event_type=failed_event_type,
            message=exc.message,
        )
        return

    logger.exception(
        "[ws_unhandled_exception] room_id=%s | user_id=%s | event_type=%s | error=%s",
        room_id,
        user_id,
        failed_event_type,
        str(exc),
    )

    await send_ws_error_to_requester(
        websocket=websocket,
        room_id=room_id,
        user_id=user_id,
        code=ResponseCode.WS500,
        job_id=job_id,
        failed_event_type=failed_event_type,
        detail=str(exc),
    )
