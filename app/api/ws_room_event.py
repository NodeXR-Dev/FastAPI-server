# app/api/routes/ws_room_event.py

import time
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.logger import get_logger
from app.core.response.code import ResponseCode, get_message
from app.schema.websocket.ws_event import (
    WSEvent,
    WSErrorPayload,
    WSErrorWSEvent,
    WSConnectSuccessResponse,
    WSConnectSuccessResult,
)
from app.websocket.connection_manager import room_ws_manager

from app.service.utterance.auto_utterance_service import AutoUtteranceService
from app.service.graph.graph_interaction_service import GraphInteractionService
from app.service.agent.agent_guide_service import AgentGuideService

logger = get_logger(__name__)

router = APIRouter()


GRAPH_INTERACTION_EVENTS = {
    "NODE_MOVE",
    "NODE_TEXT_UPDATE",
    "NODE_DELETE",
    "EDGE_CREATE",
    "EDGE_DELETE",
}


@router.websocket("/ws/rooms/{room_id}/event")
async def room_event_websocket(
    websocket: WebSocket,
    room_id: UUID,
    user_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    await room_ws_manager.connect(
        room_id=room_id,
        websocket=websocket,
        user_id=user_id,
    )

    connect_response = WSConnectSuccessResponse(
        result=WSConnectSuccessResult(
            room_id=room_id,
            user_id=user_id,
        )
    )

    await room_ws_manager.send_personal_message(
        websocket,
        connect_response.model_dump(mode="json"),
    )

    logger.info(
        "[ws_open] room_id=%s | user_id=%s",
        room_id,
        user_id,
    )

    try:
        while True:
            raw_data = await websocket.receive_json()
            start_time = time.perf_counter()

            try:
                event = WSEvent.model_validate(raw_data)

            except ValidationError as e:
                logger.warning(
                    "[ws_invalid_schema] room_id=%s | user_id=%s | error=%s",
                    room_id,
                    user_id,
                    str(e),
                )

                await _send_ws_error(
                    websocket=websocket,
                    room_id=room_id,
                    failed_event_type=raw_data.get("event_type"),
                    code=ResponseCode.WS400,
                    detail=str(e),
                )
                continue

            if event.room_id != room_id:
                await _send_ws_error(
                    websocket=websocket,
                    room_id=room_id,
                    failed_event_type=event.event_type,
                    code=ResponseCode.WS409,
                )
                continue

            logger.info(
                "[ws_event_received] room_id=%s | user_id=%s | event_type=%s",
                event.room_id,
                user_id,
                event.event_type,
            )

            try:
                await _route_ws_event(
                    websocket=websocket,
                    db=db,
                    event=event,
                    user_id=user_id,
                )

                elapsed_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "[ws_event_done] room_id=%s | event_type=%s | elapsed_ms=%.2f",
                    event.room_id,
                    event.event_type,
                    elapsed_ms,
                )

            except Exception as e:
                logger.exception(
                    "[ws_event_failed] room_id=%s | event_type=%s | error=%s",
                    event.room_id,
                    event.event_type,
                    str(e),
                )

                await _send_ws_error(
                    websocket=websocket,
                    room_id=event.room_id,
                    failed_event_type=event.event_type,
                    code=ResponseCode.WS500,
                    detail=str(e),
                )

    except WebSocketDisconnect:
        room_ws_manager.disconnect(room_id, websocket)

        logger.info(
            "[ws_closed] room_id=%s | user_id=%s",
            room_id,
            user_id,
        )

    except Exception as e:
        room_ws_manager.disconnect(room_id, websocket)

        logger.exception(
            "[ws_unexpected_closed] room_id=%s | user_id=%s | error=%s",
            room_id,
            user_id,
            str(e),
        )


async def _route_ws_event(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
):
    if event.event_type == "UTTERANCE_CREATE":
        await _handle_utterance_create(
            websocket=websocket,
            db=db,
            event=event,
            user_id=user_id,
        )
        return

    if event.event_type in GRAPH_INTERACTION_EVENTS:
        await _handle_graph_interaction(
            websocket=websocket,
            db=db,
            event=event,
            user_id=user_id,
        )
        return

    if event.event_type == "AGENT_GUIDE":
        await _handle_agent_guide(
            websocket=websocket,
            db=db,
            event=event,
            user_id=user_id,
        )
        return

    await _send_ws_error(
        websocket=websocket,
        room_id=event.room_id,
        failed_event_type=event.event_type,
        code=ResponseCode.WS404,
        detail=f"unsupported event_type={event.event_type}",
    )


async def _handle_graph_interaction(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
):
    service = GraphInteractionService(db)

    await service.handle_graph_interaction(
        event_type=event.event_type,
        room_id=event.room_id,
        user_id=user_id,
        payload=event.payload,
    )

    logger.info(
        "[graph_interaction_saved] room_id=%s | user_id=%s | event_type=%s",
        event.room_id,
        user_id,
        event.event_type,
    )


async def _handle_utterance_create(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
):
    service = AutoUtteranceService(db)

    ws_events = await service.handle_auto_utterance(
        room_id=event.room_id,
        user_id=user_id,
        payload=event.payload,
    )

    for ws_event in ws_events:
        await _dispatch_server_event(
            room_id=event.room_id,
            ws_event=ws_event,
        )


async def _handle_agent_guide(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
):
    guide_type = event.payload.get("guide_type")

    if not guide_type:
        await _send_ws_error(
            websocket=websocket,
            room_id=event.room_id,
            failed_event_type=event.event_type,
            code=ResponseCode.GUIDE400,
            detail="guide_type is required",
        )
        return

    service = AgentGuideService(db)

    guide_event = await service.create_guide(
        guide_type=guide_type,
        room_id=event.room_id,
        user_id=user_id,
        payload=event.payload,
    )

    await _dispatch_server_event(
        room_id=event.room_id,
        ws_event=guide_event,
    )


async def _dispatch_server_event(
    *,
    room_id: UUID,
    ws_event: dict,
):
    ws_event = _stringify_uuid(ws_event)
    event_type = ws_event.get("event_type")

    logger.info(
        "[ws_dispatch_server_event] room_id=%s | event_type=%s",
        room_id,
        event_type,
    )

    await room_ws_manager.broadcast_to_room(
        room_id=room_id,
        message=ws_event,
    )


async def _send_ws_error(
    *,
    websocket: WebSocket,
    room_id: UUID,
    failed_event_type: str | None,
    code: ResponseCode,
    detail: str | None = None,
    message: str | None = None,
):
    error_event = WSErrorWSEvent(
        room_id=room_id,
        payload=WSErrorPayload(
            code=code,
            message=message or get_message(code),
            detail=detail,
            failed_event_type=failed_event_type,
        ),
    )

    await room_ws_manager.send_personal_message(
        websocket,
        error_event.model_dump(mode="json"),
    )


def _stringify_uuid(data):
    if isinstance(data, dict):
        return {k: _stringify_uuid(v) for k, v in data.items()}

    if isinstance(data, list):
        return [_stringify_uuid(v) for v in data]

    if isinstance(data, UUID):
        return str(data)

    return data