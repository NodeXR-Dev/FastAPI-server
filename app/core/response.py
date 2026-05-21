from typing import Any


def success_response(
    *,
    code: str,
    message: str,
    result: Any = None,
) -> dict:
    return {
        "isSuccess": True,
        "code": code,
        "message": message,
        "result": result,
    }


def error_response(
    *,
    code: str,
    message: str,
    result: Any = None,
) -> dict:
    return {
        "isSuccess": False,
        "code": code,
        "message": message,
        "result": result,
    }