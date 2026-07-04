import time
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode, get_message
from app.db.session import SessionLocal
from app.schema.websocket.ws_event import WSEvent
from app.service.agent.agent_guide_service import AgentGuideService
from app.service.generation.image_2d_generation_service import Image2DGenerationService
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
            raw_data = None
            db: Session | None = None

            try:
                raw_data = await websocket.receive_json()
                start_time = time.perf_counter()
                event = WSEvent.model_validate(raw_data)

            except WebSocketDisconnect:
                raise

            except ValidationError as e:
                logger.warning(
                    "[ws_invalid_schema] room_id=%s | user_id=%s | error=%s",
                    connected_room_id,
                    connected_user_id,
                    str(e),
                )

                await _send_ws_error(
                    websocket=websocket,
                    room_id=connected_room_id,
                    failed_event_type=_get_raw_event_type(raw_data),
                    code=ResponseCode.WS400,
                    detail=str(e),
                )
                continue

            except Exception as e:
                logger.warning(
                    "[ws_receive_failed] room_id=%s | user_id=%s | error=%s",
                    connected_room_id,
                    connected_user_id,
                    str(e),
                )

                await _send_ws_error(
                    websocket=websocket,
                    room_id=connected_room_id,
                    failed_event_type=_get_raw_event_type(raw_data),
                    code=ResponseCode.WS400,
                    detail=str(e),
                )
                continue

            if connected_room_id is None:
                connected_room_id = event.room_id
                connected_user_id = event.user_id

                room_ws_manager.register(
                    room_id=connected_room_id,
                    websocket=websocket,
                    user_id=connected_user_id,
                )

                await room_ws_manager.send_personal_message(
                    websocket,
                    {
                        "event_type": "WS_CONNECT",
                        "room_id": str(connected_room_id),
                        "payload": {
                            "user_id": str(connected_user_id)
                            if connected_user_id
                            else None
                        },
                    },
                )

                logger.info(
                    "[ws_room_event] connect_done | room_id=%s | user_id=%s",
                    connected_room_id,
                    connected_user_id,
                )

            if event.room_id != connected_room_id:
                await _send_ws_error(
                    websocket=websocket,
                    room_id=connected_room_id,
                    failed_event_type=event.event_type,
                    code=ResponseCode.WS409,
                    detail="room_id cannot be changed after websocket connection",
                )
                continue

            if (
                connected_user_id is not None
                and event.user_id is not None
                and event.user_id != connected_user_id
            ):
                await _send_ws_error(
                    websocket=websocket,
                    room_id=connected_room_id,
                    failed_event_type=event.event_type,
                    code=ResponseCode.WS409,
                    detail="user_id cannot be changed after websocket connection",
                )
                continue

            current_user_id = event.user_id or connected_user_id

            logger.info(
                "[ws_event_received] room_id=%s | user_id=%s | event_type=%s",
                event.room_id,
                current_user_id,
                event.event_type,
            )

            db = SessionLocal()

            try:
                await _route_ws_event(
                    websocket=websocket,
                    db=db,
                    event=event,
                    user_id=current_user_id,
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

            finally:
                if db is not None:
                    db.close()

    except WebSocketDisconnect:
        if connected_room_id is not None:
            room_ws_manager.disconnect(connected_room_id, websocket)

        logger.info(
            "[ws_closed] room_id=%s | user_id=%s",
            connected_room_id,
            connected_user_id,
        )

    except Exception as e:
        if connected_room_id is not None:
            room_ws_manager.disconnect(connected_room_id, websocket)

        logger.exception(
            "[ws_unexpected_closed] room_id=%s | user_id=%s | error=%s",
            connected_room_id,
            connected_user_id,
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
    
    if event.event_type == "2D_GENERATED":
        await _handle_2d_generate(
            websocket=websocket,
            db=db,
            event=event,
        )

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

async def _handle_2d_generate(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEvent
):
    service = Image2DGenerationService(db)
    


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
    room_id: UUID | None,
    failed_event_type: str | None,
    code: ResponseCode,
    detail: str | None = None,
    message: str | None = None,
):
    error_event = {
        "event_type": "ERROR",
        "room_id": str(room_id) if room_id else None,
        "payload": {
            "code": code,
            "message": message or get_message(code),
            "detail": detail,
            "failed_event_type": failed_event_type,
        },
    }

    await room_ws_manager.send_personal_message(
        websocket,
        error_event,
    )


def _extract_connect_user_id(event: WSEvent) -> UUID | None:
    if event.user_id is not None:
        return event.user_id

    user_id = event.payload.get("user_id")

    if user_id is None:
        return None

    if isinstance(user_id, UUID):
        return user_id

    return UUID(str(user_id))


def _get_raw_event_type(raw_data) -> str | None:
    if isinstance(raw_data, dict):
        return raw_data.get("event_type")

    return None


def _stringify_uuid(data):
    if isinstance(data, dict):
        return {k: _stringify_uuid(v) for k, v in data.items()}

    if isinstance(data, list):
        return [_stringify_uuid(v) for v in data]

    if isinstance(data, UUID):
        return str(data)

    return data