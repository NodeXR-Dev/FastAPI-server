from typing import Any

from fastapi import WebSocket, status
from pydantic import ValidationError

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BaseCustomException,
    BadRequestException,
    UnauthorizedException,
    NotFoundException,
)
from app.core.response.response import success_response, error_response

logger = get_logger(__name__)


def get_ws_status_code_from_exception(exc: BaseCustomException) -> int:
    if isinstance(exc, BadRequestException):
        return status.HTTP_400_BAD_REQUEST

    if isinstance(exc, UnauthorizedException):
        return status.HTTP_401_UNAUTHORIZED

    if isinstance(exc, NotFoundException):
        return status.HTTP_404_NOT_FOUND

    return status.HTTP_500_INTERNAL_SERVER_ERROR


def serialize_ws_result(result: Any) -> Any:
    if result is None:
        return None

    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")

    return result


async def send_ws_success(
    websocket: WebSocket,
    *,
    code: ResponseCode,
    message: str | None = None,
    result: Any = None,
) -> None:
    await websocket.send_json(
        success_response(
            code=code,
            message=message,
            result=serialize_ws_result(result),
        )
    )


async def send_ws_error(
    websocket: WebSocket,
    *,
    code: ResponseCode,
    message: str | None = None,
    result: Any = None,
) -> None:
    await websocket.send_json(
        error_response(
            code=code,
            message=message,
            result=serialize_ws_result(result),
        )
    )


async def handle_ws_custom_exception(
    websocket: WebSocket,
    *,
    exc: BaseCustomException,
    path: str,
) -> None:
    status_code = get_ws_status_code_from_exception(exc)

    logger.warning(
        "[WSCustomException] path=%s | status=%s | code=%s | message=%s",
        path,
        status_code,
        exc.code,
        exc.message,
    )

    await send_ws_error(
        websocket,
        code=exc.code,
        message=exc.message,
    )


async def handle_ws_validation_exception(
    websocket: WebSocket,
    *,
    exc: ValidationError,
    path: str,
) -> None:
    logger.warning(
        "[WSValidationError] path=%s | errors=%s",
        path,
        exc.errors(),
    )

    await send_ws_error(
        websocket,
        code=ResponseCode.COMMON422,
        message="요청값 검증에 실패했습니다.",
        result=exc.errors(),
    )


async def handle_ws_unhandled_exception(
    websocket: WebSocket,
    *,
    exc: Exception,
    path: str,
) -> None:
    logger.exception(
        "[WSUnhandledException] path=%s | error=%s",
        path,
        str(exc),
    )

    await send_ws_error(
        websocket,
        code=ResponseCode.COMMON500,
        message="서버 오류가 발생했습니다.",
    )