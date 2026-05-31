# app/core/response.py

from typing import Any
from app.core.response.code import ResponseCode, get_message


def success_response(
    *,
    code: ResponseCode,
    message: str | None = None,
    result: Any = None,
) -> dict:
    return {
        "isSuccess": True,
        "code": code.value,
        "message": message or get_message(code),
        "result": result,
    }


def error_response(
    *,
    code: ResponseCode,
    message: str | None = None,
    result: Any = None,
) -> dict:
    return {
        "isSuccess": False,
        "code": code.value,
        "message": message or get_message(code),
        "result": result,
    }