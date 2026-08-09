import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.ws_exception_handler import handle_ws_exception
from app.core.response.ws_exceptions import (
    WSBadRequestException,
    WSConflictException,
    WSNotFoundException,
)
from app.core.response.ws_response import send_ws_success_to_requester
from app.core.ws_utils import (
    extract_user_id,
    get_raw_event_type,
    get_raw_job_id,
    payload_to_dict,
    ws_db_session,
)
from app.schema.websocket.ws_event import WSEvent
from app.service.graph.graph_interaction_service import GraphInteractionService
from app.service.utterance.auto_utterance_service import AutoUtteranceService
from app.service.websocket.connection_manager import room_ws_manager

logger = get_logger(__name__)

router = APIRouter(
    tags=["WebSocket"],
)


GRAPH_INTERACTION_EVENTS = {
    "NODE_CREATE",
    "NODE_MOVE",
    "NODE_TEXT_UPDATE",
    "NODE_DELETE",
    "EDGE_CREATE",
    "EDGE_DELETE",
}

ACK_REQUIRED_EVENTS = {
    "WS_CONNECT",
    "NODE_CREATE",
    "EDGE_CREATE",
}


@router.websocket("/rooms/event")
async def room_event_websocket(
    websocket: WebSocket,
):
    await websocket.accept()

    connected_room_id: UUID | None = None
    connected_user_id: UUID | None = None

    logger.info("[ws_route_entered] /ws/rooms/event")

    try:
        while True:
            raw_data: Any = None
            event: WSEvent | None = None
            current_user_id: UUID | None = connected_user_id
            current_job_id: UUID | None = None
            start_time = time.perf_counter()

            try:
                raw_data = await _receive_ws_json(websocket)
                current_job_id = get_raw_job_id(raw_data)
                event = WSEvent.model_validate(raw_data)

                event_user_id = extract_user_id(event)

                if connected_room_id is None:
                    connected_room_id = event.room_id
                    connected_user_id = event_user_id
                    current_user_id = connected_user_id

                    room_ws_manager.register(
                        room_id=connected_room_id,
                        websocket=websocket,
                        user_id=connected_user_id,
                    )

                    logger.info(
                        "[ws_lazy_registered] room_id=%s | user_id=%s | first_event_type=%s",
                        connected_room_id,
                        connected_user_id,
                        event.event_type,
                    )

                _validate_connection_state(
                    event=event,
                    connected_room_id=connected_room_id,
                    connected_user_id=connected_user_id,
                    event_user_id=event_user_id,
                )

                current_user_id = event_user_id or connected_user_id

                logger.info(
                    "[ws_event_received] room_id=%s | user_id=%s | event_type=%s",
                    event.room_id,
                    current_user_id,
                    event.event_type,
                )

                with ws_db_session() as db:
                    ack_payload, server_events = await route_ws_event(
                        db=db,
                        event=event,
                        user_id=current_user_id,
                    )

                await send_server_events_to_requester(
                    websocket=websocket,
                    server_events=server_events,
                )

                if event.event_type in ACK_REQUIRED_EVENTS and ack_payload is not None:
                    await send_ws_success_to_requester(
                        websocket=websocket,
                        event_type=event.event_type,
                        room_id=event.room_id,
                        user_id=current_user_id,
                        job_id=current_job_id,
                        payload=ack_payload,
                    )

                elapsed_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "[ws_event_done] room_id=%s | user_id=%s | event_type=%s | elapsed_ms=%.2f",
                    event.room_id,
                    current_user_id,
                    event.event_type,
                    elapsed_ms,
                )

            except WebSocketDisconnect:
                raise

            except ValidationError as e:
                await handle_ws_exception(
                    websocket=websocket,
                    exc=e,
                    room_id=connected_room_id,
                    user_id=current_user_id,
                    job_id=current_job_id,
                    failed_event_type=get_raw_event_type(raw_data),
                )

            except Exception as e:
                await handle_ws_exception(
                    websocket=websocket,
                    exc=e,
                    room_id=connected_room_id or (event.room_id if event else None),
                    user_id=current_user_id,
                    job_id=current_job_id,
                    failed_event_type=event.event_type if event else get_raw_event_type(raw_data),
                )

    except WebSocketDisconnect:
        if connected_room_id is not None:
            room_ws_manager.disconnect(
                connected_room_id,
                websocket,
            )

        logger.info(
            "[ws_closed] room_id=%s | user_id=%s",
            connected_room_id,
            connected_user_id,
        )

    except Exception as e:
        if connected_room_id is not None:
            room_ws_manager.disconnect(
                connected_room_id,
                websocket,
            )

        logger.exception(
            "[ws_unexpected_closed] room_id=%s | user_id=%s | error=%s",
            connected_room_id,
            connected_user_id,
            str(e),
        )


async def _receive_ws_json(
    websocket: WebSocket,
) -> Any:
    try:
        return await websocket.receive_json()

    except WebSocketDisconnect:
        raise

    except Exception as e:
        raise WSBadRequestException(
            detail=str(e),
        )


def _validate_connection_state(
    *,
    event: WSEvent,
    connected_room_id: UUID,
    connected_user_id: UUID | None,
    event_user_id: UUID | None,
) -> None:
    if event.room_id != connected_room_id:
        raise WSConflictException(
            detail="room_id cannot be changed after websocket connection",
            failed_event_type=event.event_type,
        )

    if (
        connected_user_id is not None
        and event_user_id is not None
        and event_user_id != connected_user_id
    ):
        raise WSConflictException(
            detail="user_id cannot be changed after websocket connection",
            failed_event_type=event.event_type,
        )


async def route_ws_event(
    *,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
) -> tuple[dict | None, list[Any]]:
    if event.event_type == "WS_CONNECT":
        return {"connected": True}, []

    if event.event_type == "UTTERANCE_CREATE":
        server_events = await handle_utterance_create(
            db=db,
            event=event,
            user_id=user_id,
        )
        return None, server_events

    if event.event_type in GRAPH_INTERACTION_EVENTS:
        ack_payload = await handle_graph_interaction(
            db=db,
            event=event,
            user_id=user_id,
        )
        return ack_payload, []

    raise WSNotFoundException(
        detail=f"unsupported event_type={event.event_type}",
        failed_event_type=event.event_type,
    )


async def handle_graph_interaction(
    *,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
) -> dict | None:
    service = GraphInteractionService(db)
    payload = payload_to_dict(event.payload)
    if event.job_id is not None and "job_id" not in payload:
        payload["job_id"] = event.job_id

    ack_payload = await service.handle_graph_interaction(
        event_type=event.event_type,
        room_id=event.room_id,
        user_id=user_id,
        payload=payload,
    )

    logger.info(
        "[graph_interaction_saved] room_id=%s | user_id=%s | event_type=%s",
        event.room_id,
        user_id,
        event.event_type,
    )

    return ack_payload


async def handle_utterance_create(
    *,
    db: Session,
    event: WSEvent,
    user_id: UUID | None,
) -> list[Any]:
    service = AutoUtteranceService(db)

    ws_events = await service.handle_auto_utterance(
        room_id=event.room_id,
        user_id=user_id,
        payload=payload_to_dict(event.payload),
    )

    logger.info(
        "[utterance_saved] room_id=%s | user_id=%s",
        event.room_id,
        user_id,
    )

    return ws_events or []


async def send_server_events_to_requester(
    *,
    websocket: WebSocket,
    server_events: list[Any],
) -> None:
    for server_event in server_events:
        try:
            await room_ws_manager.send_personal_message(
                websocket,
                server_event,
            )
        except Exception as send_error:
            logger.exception(
                "[ws_server_event_send_failed] event_type=%s | error=%s",
                server_event.get("event_type"),
                str(send_error),
            )
