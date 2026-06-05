from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.response.exceptions import (
    BaseCustomException,
    BadRequestException,
    UnauthorizedException,
    NotFoundException,
)
from app.core.response.response import error_response
from app.core.response.code import ResponseCode
from app.core.logger import get_logger

logger = get_logger(__name__)


async def custom_exception_handler(
    request: Request,
    exc: BaseCustomException,
):
    if isinstance(exc, BadRequestException):
        status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, UnauthorizedException):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, NotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    logger.warning(
        "[CustomException] path=%s | status=%s | code=%s | message=%s",
        request.url.path,
        status_code,
        exc.code,
        exc.message,
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response(
            code=exc.code,
            message=exc.message,
        ),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    logger.warning(
        "[ValidationError] path=%s | errors=%s",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(
            code=ResponseCode.COMMON422,
            message="요청값 검증에 실패했습니다.",
            result=exc.errors(),
        ),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception(
        "[UnhandledException] path=%s | error=%s",
        request.url.path,
        str(exc),
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            code=ResponseCode.COMMON500,
            message="서버 오류가 발생했습니다.",
        ),
    )