from typing import Any
from uuid import UUID

from fastapi import WebSocket

from app.core.response.code import ResponseCode, get_message
from app.service.websocket.connection_manager import room_ws_manager


def ws_success_event(
    *,
    event_type: str,
    room_id: UUID,
    user_id: UUID | None,
    job_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> dict:
    return {
        "event_type": event_type,
        "room_id": str(room_id),
        "user_id": str(user_id) if user_id else None,
        "job_id": str(job_id) if job_id else None,
        "payload": _stringify_uuid(payload or {}),
    }


def ws_error_event(
    *,
    room_id: UUID | None,
    user_id: UUID | None,
    code: ResponseCode,
    job_id: UUID | None = None,
    failed_event_type: str | None = None,
    message: str | None = None,
    detail: str | None = None,
) -> dict:
    payload = {
        "code": code.value,
        "message": message or get_message(code),
    }

    if failed_event_type is not None:
        payload["failed_event_type"] = failed_event_type

    if detail is not None:
        payload["detail"] = detail

    return {
        "event_type": "ERROR",
        "room_id": str(room_id) if room_id else None,
        "user_id": str(user_id) if user_id else None,
        "job_id": str(job_id) if job_id else None,
        "payload": payload,
    }


async def send_ws_success_to_requester(
    *,
    websocket: WebSocket,
    event_type: str,
    room_id: UUID,
    user_id: UUID | None,
    job_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    await room_ws_manager.send_personal_message(
        websocket,
        ws_success_event(
            event_type=event_type,
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            payload=payload,
        ),
    )


async def send_ws_error_to_requester(
    *,
    websocket: WebSocket,
    room_id: UUID | None,
    user_id: UUID | None,
    code: ResponseCode,
    job_id: UUID | None = None,
    failed_event_type: str | None = None,
    message: str | None = None,
    detail: str | None = None,
) -> None:
    await room_ws_manager.send_personal_message(
        websocket,
        ws_error_event(
            room_id=room_id,
            user_id=user_id,
            code=code,
            job_id=job_id,
            failed_event_type=failed_event_type,
            message=message,
            detail=detail,
        ),
    )


def _stringify_uuid(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: _stringify_uuid(value)
            for key, value in data.items()
        }

    if isinstance(data, list):
        return [
            _stringify_uuid(value)
            for value in data
        ]

    if isinstance(data, UUID):
        return str(data)

    return data
