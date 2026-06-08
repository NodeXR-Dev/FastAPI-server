# app/api/routes/ws_room_event.py

import time
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.logger import get_logger
from app.schema.websocket.ws_event import WSEventRequest, WSErrorResponse
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
    """
    회의실 단위 WebSocket 연결.

    최종 정책:
    - 노드/엣지 조작 성공: 응답 없음
    - 노드/엣지 조작 실패: 요청자에게 ERROR
    - AGENT_GUIDE: room 전체 broadcast
    - GRAPH_UPDATED: room 전체 broadcast
    - 2D_GENERATED / 3D_GENERATED: 생성 API background task에서 room 전체 broadcast
    """

    await room_ws_manager.connect(
        room_id=room_id,
        websocket=websocket,
        user_id=user_id,
    )

    await room_ws_manager.send_personal_message(
        websocket,
        {
            "isSuccess": True,
            "code": "WS200",
            "message": "회의실 웹소켓 연결 성공",
            "result": {
                "room_id": str(room_id),
                "user_id": str(user_id) if user_id else None,
            },
        },
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
                event = WSEventRequest.model_validate(raw_data)
            except ValidationError as e:
                logger.warning(
                    "[ws_invalid_schema] room_id=%s | user_id=%s | error=%s",
                    room_id,
                    user_id,
                    str(e),
                )

                await room_ws_manager.send_personal_message(
                    websocket,
                    {
                        "event_type": "ERROR",
                        "room_id": str(room_id),
                        "payload": {
                            "code": "WS400",
                            "message": "WebSocket 요청 형식이 올바르지 않습니다.",
                            "detail": str(e),
                            "failed_event_type": raw_data.get("event_type"),
                        },
                    },
                )
                continue

            if event.room_id != room_id:
                await _send_ws_error(
                    websocket=websocket,
                    room_id=room_id,
                    failed_event_type=event.event_type,
                    code="WS_ROOM_MISMATCH",
                    message="URL의 room_id와 body의 room_id가 일치하지 않습니다.",
                )
                continue

            logger.info(
                "[ws_event_received] room_id=%s | user_id=%s | event_type=%s",
                event.room_id,
                event.user_id,
                event.event_type,
            )

            try:
                await _route_ws_event(
                    websocket=websocket,
                    db=db,
                    event=event,
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
                    code="WS500",
                    message="WebSocket 이벤트 처리 중 서버 오류가 발생했습니다.",
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
    event: WSEventRequest,
):
    """
    event_type에 따라 서비스 클래스로 routing.
    """

    if event.event_type == "UTTERANCE_CREATE":
        await _handle_utterance_create(
            websocket=websocket,
            db=db,
            event=event,
        )
        return

    if event.event_type in GRAPH_INTERACTION_EVENTS:
        await _handle_graph_interaction(
            websocket=websocket,
            db=db,
            event=event,
        )
        return

    if event.event_type == "AGENT_GUIDE":
        await _handle_agent_guide(
            websocket=websocket,
            db=db,
            event=event,
        )
        return

    await _send_ws_error(
        websocket=websocket,
        room_id=event.room_id,
        failed_event_type=event.event_type,
        code="WS404",
        message=f"지원하지 않는 event_type입니다: {event.event_type}",
    )


async def _handle_graph_interaction(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEventRequest,
):
    """
    노드 이동/수정/삭제, 엣지 생성/삭제 처리.

    정책:
    - Unity는 이미 로컬 반영 + Photon 동기화
    - FastAPI는 DB 저장만 수행
    - 성공 시 WS 응답 없음
    - 실패 시 상위 try-except에서 요청자에게 ERROR 전송
    """

    service = GraphInteractionService(db)

    await service.handle_graph_interaction(
        event_type=event.event_type,
        room_id=event.room_id,
        user_id=event.user_id,
        payload=event.payload,
    )

    logger.info(
        "[graph_interaction_saved] room_id=%s | user_id=%s | event_type=%s",
        event.room_id,
        event.user_id,
        event.event_type,
    )

    # 성공 응답 없음.
    # Photon이 조작 UI 동기화를 담당한다.


async def _handle_utterance_create(
    *,
    websocket: WebSocket,
    db: Session,
    event: WSEventRequest,
):
    """
    자동 발화 처리.

    AutoUtteranceService가 반환할 수 있는 이벤트 예시:
    - GRAPH_UPDATED
    - AGENT_GUIDE
    - UTTERANCE_CREATED

    정책:
    - GRAPH_UPDATED: room 전체 broadcast
    - AGENT_GUIDE: room 전체 broadcast
    - UTTERANCE_CREATED: 필요하면 room 전체 broadcast
    """

    service = AutoUtteranceService(db)

    ws_events = await service.handle_auto_utterance(
        room_id=event.room_id,
        user_id=event.user_id,
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
    event: WSEventRequest,
):
    """
    발화 가이드 생성 요청 처리.

    정책:
    - AGENT_GUIDE는 모든 사용자가 같은 근거 데이터를 봐야 하므로 room 전체 broadcast
    """

    guide_type = event.payload.get("guide_type")

    if not guide_type:
        await _send_ws_error(
            websocket=websocket,
            room_id=event.room_id,
            failed_event_type=event.event_type,
            code="GUIDE400",
            message="guide_type이 필요합니다.",
        )
        return

    service = AgentGuideService(db)

    guide_event = await service.create_guide(
        guide_type=guide_type,
        room_id=event.room_id,
        user_id=event.user_id,
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
    """
    서버에서 생성된 이벤트를 전송한다.

    최종 정책:
    - GRAPH_UPDATED: room broadcast
    - AGENT_GUIDE: room broadcast
    - 2D_GENERATED: room broadcast
    - 3D_GENERATED: room broadcast
    - 그 외 서버 이벤트도 기본적으로 room broadcast

    단, 노드/엣지 조작 성공 이벤트는 여기로 오지 않게 한다.
    """

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
    code: str,
    message: str,
    detail: str | None = None,
):
    """
    요청자에게만 ERROR 전송.
    """

    error = WSErrorResponse(
        room_id=room_id,
        payload={
            "code": code,
            "message": message,
            "detail": detail,
            "failed_event_type": failed_event_type,
        },
    )

    await room_ws_manager.send_personal_message(
        websocket,
        _stringify_uuid(error.model_dump()),
    )


def _stringify_uuid(data):
    """
    UUID가 섞인 dict를 JSON 전송 가능한 형태로 변환한다.
    """
    if isinstance(data, dict):
        return {k: _stringify_uuid(v) for k, v in data.items()}

    if isinstance(data, list):
        return [_stringify_uuid(v) for v in data]

    if isinstance(data, UUID):
        return str(data)

    return data