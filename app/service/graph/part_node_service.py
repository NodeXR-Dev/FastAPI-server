from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.model.enum import NodeType
from app.model.graph import Node
from app.repository.graph_repository import GraphRepository
from app.repository.room_repository import RoomRepository
from app.schema.graph.part_node_request import (
    CreatePartNodeRequest,
    DeletePartNodeRequest,
    ModifyPartNodeRequest,
)
from app.schema.graph.part_node_response import (
    DeletePartNodeResponse,
    PartNodeResponse,
)
from app.service.graph.graph_interaction_service import GraphInteractionService

logger = get_logger(__name__)


class PartNodeService:
    def __init__(self):
        self.room_repository = RoomRepository()
        self.graph_repository = GraphRepository()

    def create_part_node(
        self,
        *,
        request: CreatePartNodeRequest,
        db: Session,
    ) -> PartNodeResponse:
        self._validate_active_room(db=db, room_id=request.room_id)

        logger.info(
            "[part_node_create_start] room_id=%s | text_length=%s | position=%s",
            request.room_id,
            len(request.text),
            request.position,
        )

        node = GraphInteractionService(db).create_independent_node(
            room_id=request.room_id,
            user_id=None,
            node_text=request.text,
            node_type=NodeType.PART,
            position=request.position,
        )

        logger.info(
            "[part_node_create_success] room_id=%s | part_node_id=%s",
            request.room_id,
            node.node_id,
        )

        return self._to_part_node_response(node=node)

    def modify_part_node(
        self,
        *,
        request: ModifyPartNodeRequest,
        db: Session,
    ) -> PartNodeResponse:
        self._validate_active_room(db=db, room_id=request.room_id)
        self._get_active_part_node_or_404(
            db=db,
            room_id=request.room_id,
            part_node_id=request.part_node_id,
        )

        node = GraphInteractionService(db).update_node_text(
            room_id=request.room_id,
            user_id=None,
            node_id=request.part_node_id,
            text=request.part_node_text,
        )

        logger.info(
            "[part_node_modify_success] room_id=%s | part_node_id=%s",
            request.room_id,
            request.part_node_id,
        )

        return self._to_part_node_response(node=node)

    def delete_part_node(
        self,
        *,
        request: DeletePartNodeRequest,
        db: Session,
    ) -> DeletePartNodeResponse:
        self._validate_active_room(db=db, room_id=request.room_id)
        self._get_active_part_node_or_404(
            db=db,
            room_id=request.room_id,
            part_node_id=request.part_node_id,
        )

        GraphInteractionService(db).delete_node(
            room_id=request.room_id,
            user_id=None,
            node_id=request.part_node_id,
        )

        logger.info(
            "[part_node_delete_success] room_id=%s | part_node_id=%s",
            request.room_id,
            request.part_node_id,
        )

        return DeletePartNodeResponse(
            room_id=request.room_id,
            part_node_id=request.part_node_id,
        )

    def _validate_active_room(self, *, db: Session, room_id: UUID) -> None:
        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=room_id,
        )

        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)

        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.PART_NODE400,
                message="비활성화된 회의실에서는 파트 노드를 변경할 수 없습니다.",
            )

    def _get_active_part_node_or_404(
        self,
        *,
        db: Session,
        room_id: UUID,
        part_node_id: UUID,
    ) -> Node:
        node = self.graph_repository.find_active_node_by_id(
            db=db,
            room_id=room_id,
            node_id=part_node_id,
        )

        if node is None or self._node_type_value(node) != NodeType.PART.value:
            raise NotFoundException(code=ResponseCode.PART_NODE404)

        return node

    def _to_part_node_response(self, *, node: Node) -> PartNodeResponse:
        return PartNodeResponse(
            room_id=node.room_id,
            part_node_id=node.node_id,
            part_node_text=node.node_text,
        )

    def _node_type_value(self, node: Node) -> str:
        return (
            node.node_type.value
            if hasattr(node.node_type, "value")
            else str(node.node_type)
        )
