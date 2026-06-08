from uuid import UUID
from sqlalchemy.orm import Session
from app.core.logger import get_logger

logger = get_logger(__name__)


class GraphInteractionService:
    """
    노드/엣지 조작 이벤트 처리 서비스.

    최종 정책:
    - 성공 시 WS 응답 없음
    - 실패 시 exception 발생
    - router에서 exception을 잡아 요청자에게 ERROR 전송
    """

    def __init__(self, db: Session):
        self.db = db

    async def handle_graph_interaction(
        self,
        *,
        event_type: str,
        room_id: UUID,
        user_id: UUID | None,
        request_id: UUID | None,
        payload: dict,
    ) -> None:
        logger.info(
            "[graph_interaction] event_type=%s | room_id=%s | user_id=%s | request_id=%s",
            event_type,
            room_id,
            user_id,
            request_id,
        )

        if event_type == "NODE_MOVE":
            await self._handle_node_move(room_id, user_id, payload)
            return

        if event_type == "NODE_TEXT_UPDATE":
            await self._handle_node_text_update(room_id, user_id, payload)
            return

        if event_type == "NODE_DELETE":
            await self._handle_node_delete(room_id, user_id, payload)
            return

        if event_type == "EDGE_CREATE":
            await self._handle_edge_create(room_id, user_id, payload)
            return

        if event_type == "EDGE_DELETE":
            await self._handle_edge_delete(room_id, user_id, payload)
            return

        raise ValueError(f"Unsupported graph interaction event_type: {event_type}")

    async def _handle_node_move(
        self,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = payload["node_id"]
        position = payload["position"]

        # TODO:
        # 1. node_id가 해당 room_id에 존재하는지 확인
        # 2. nodes.position_x/y/z 업데이트
        # 3. graph_events 저장
        # 4. commit

        logger.info(
            "[node_move_saved] room_id=%s | node_id=%s | position=%s",
            room_id,
            node_id,
            position,
        )

    async def _handle_node_text_update(
        self,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = payload["node_id"]
        text = payload["text"]

        # TODO:
        # nodes.node_text 업데이트
        # graph_events 저장
        # commit

        logger.info(
            "[node_text_update_saved] room_id=%s | node_id=%s",
            room_id,
            node_id,
        )

    async def _handle_node_delete(
        self,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        node_id = payload["node_id"]

        # TODO:
        # 1. node 삭제 또는 soft delete
        # 2. 관련 edge 삭제
        # 3. graph_events 저장
        # 4. commit

        logger.info(
            "[node_delete_saved] room_id=%s | node_id=%s",
            room_id,
            node_id,
        )

    async def _handle_edge_create(
        self,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        from_node_id = payload["from_node_id"]
        to_node_id = payload["to_node_id"]
        label = payload.get("label")

        # TODO:
        # 1. from_node_id, to_node_id가 같은 room의 node인지 검증
        # 2. edges insert
        # 3. graph_events 저장
        # 4. commit

        logger.info(
            "[edge_create_saved] room_id=%s | from_node_id=%s | to_node_id=%s | label=%s",
            room_id,
            from_node_id,
            to_node_id,
            label,
        )

    async def _handle_edge_delete(
        self,
        room_id: UUID,
        user_id: UUID | None,
        payload: dict,
    ) -> None:
        edge_id = payload["edge_id"]

        # TODO:
        # 1. edge_id가 해당 room의 edge인지 검증
        # 2. edges delete
        # 3. graph_events 저장
        # 4. commit

        logger.info(
            "[edge_delete_saved] room_id=%s | edge_id=%s",
            room_id,
            edge_id,
        )