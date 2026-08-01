from io import BytesIO
from pathlib import Path
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    BaseCustomException,
    NotFoundException,
    ServerException,
)
from app.model.enum import EdgeType, GraphEventType, NodeType
from app.model.graph import Node
from app.repository.graph_repository import GraphRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.generation_result import StoredObjectInfo
from app.schema.graph.reference_request import GenerateReferenceRequest
from app.schema.graph.reference_response import GenerateReferenceResponse
from app.service.generation.minio_asset_storage import MinioAssetStorage

logger = get_logger(__name__)


class ReferenceService:
    ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
    MIME_TYPE_BY_FORMAT = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }

    def __init__(
        self,
        *,
        graph_repository: GraphRepository | None = None,
        room_repository: RoomRepository | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
    ) -> None:
        self.graph_repository = graph_repository or GraphRepository()
        self.room_repository = room_repository or RoomRepository()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()

    def generate_reference(
        self,
        *,
        db: Session,
        request: GenerateReferenceRequest,
        image_bytes: bytes,
        filename: str | None,
        upload_content_type: str | None,
    ) -> GenerateReferenceResponse:
        stored_object: StoredObjectInfo | None = None

        try:
            parent_node = self._validate_request(
                db=db,
                request=request,
                image_bytes=image_bytes,
                upload_content_type=upload_content_type,
            )

            stored_object = self.minio_asset_storage.upload_reference_image(
                room_id=request.room_id,
                image_bytes=image_bytes,
                mime_type=request.metadata.mime_type,
            )

            reference_node = self.graph_repository.create_node(
                db=db,
                room_id=request.room_id,
                sub_graph_id=parent_node.sub_graph_id,
                parent_node_id=parent_node.node_id,
                node_type=NodeType.REFERENCE,
                node_text=self._resolve_node_text(filename=filename),
                position_x=parent_node.position_x,
                position_y=parent_node.position_y,
                position_z=parent_node.position_z,
            )

            reference = self.graph_repository.create_reference(
                db=db,
                room_id=request.room_id,
                node_id=reference_node.node_id,
                image_url=stored_object.public_url,
                mime_type=request.metadata.mime_type,
                width=request.metadata.width,
                height=request.metadata.height,
            )

            existing_edge = self.graph_repository.find_active_edge_between_nodes(
                db=db,
                room_id=request.room_id,
                from_node_id=parent_node.node_id,
                to_node_id=reference_node.node_id,
            )
            if existing_edge is not None:
                raise BadRequestException(
                    code=ResponseCode.REFERENCE400,
                    message="이미 연결된 레퍼런스 노드입니다.",
                )

            edge = self.graph_repository.create_edge(
                db=db,
                room_id=request.room_id,
                sub_graph_id=parent_node.sub_graph_id,
                from_node_id=parent_node.node_id,
                to_node_id=reference_node.node_id,
                label=EdgeType.PROPERTY_REFERENCE.value,
            )

            graph_snapshot = self.graph_repository.create_graph_snapshot_from_current_graph(
                db=db,
                room_id=request.room_id,
            )

            self.graph_repository.create_graph_event(
                db=db,
                room_id=request.room_id,
                user_id=None,
                node_id=reference_node.node_id,
                edge_id=edge.edge_id,
                graph_snapshot_id=graph_snapshot.graph_snapshot_id,
                event_type=GraphEventType.NODE_CREATE,
                payload={
                    "interaction_type": GraphEventType.NODE_CREATE.value,
                    "sub_graph_id": str(reference_node.sub_graph_id),
                    "parent_node_id": str(parent_node.node_id),
                    "reference_node_id": str(reference_node.node_id),
                    "reference_id": str(reference.reference_id),
                    "edge_id": str(edge.edge_id),
                    "reference_url": stored_object.public_url,
                    "node_type": NodeType.REFERENCE.value,
                    "edge_type": EdgeType.PROPERTY_REFERENCE.value,
                    "graph_snapshot_id": str(graph_snapshot.graph_snapshot_id),
                },
            )

            result = GenerateReferenceResponse(
                room_id=request.room_id,
                node_id=reference_node.node_id,
                reference_url=stored_object.public_url,
            )
            reference_id = reference.reference_id
            edge_id = edge.edge_id
            graph_snapshot_id = graph_snapshot.graph_snapshot_id
            db.commit()

            logger.info(
                "[reference_generate_saved] room_id=%s | parent_node_id=%s | reference_node_id=%s | reference_id=%s | edge_id=%s | graph_snapshot_id=%s",
                request.room_id,
                request.node_id,
                result.node_id,
                reference_id,
                edge_id,
                graph_snapshot_id,
            )

            return result

        except BaseCustomException:
            db.rollback()
            self._compensate_uploaded_object(
                room_id=request.room_id,
                stored_object=stored_object,
            )
            raise
        except Exception as exc:
            db.rollback()
            logger.exception(
                "[reference_generate_failed] room_id=%s | parent_node_id=%s",
                request.room_id,
                request.node_id,
            )
            self._compensate_uploaded_object(
                room_id=request.room_id,
                stored_object=stored_object,
            )
            raise ServerException(code=ResponseCode.REFERENCE500) from exc

    def _validate_request(
        self,
        *,
        db: Session,
        request: GenerateReferenceRequest,
        image_bytes: bytes,
        upload_content_type: str | None,
    ) -> Node:
        room = self.room_repository.find_room_by_id(
            db=db,
            room_id=request.room_id,
        )
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="비활성화된 회의실에는 레퍼런스를 추가할 수 없습니다.",
            )

        parent_node = self.graph_repository.find_active_node_by_id(
            db=db,
            room_id=request.room_id,
            node_id=request.node_id,
        )
        if parent_node is None:
            raise NotFoundException(code=ResponseCode.NODE404)

        if parent_node.sub_graph_id is None:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="부모 노드가 유효한 서브 그래프에 속하지 않습니다.",
            )

        sub_graph = self.graph_repository.find_sub_graph_by_id(
            db=db,
            room_id=request.room_id,
            sub_graph_id=parent_node.sub_graph_id,
        )
        if sub_graph is None:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="부모 노드의 서브 그래프가 유효하지 않습니다.",
            )

        self._validate_image(
            image_bytes=image_bytes,
            metadata_mime_type=request.metadata.mime_type,
            upload_content_type=upload_content_type,
            expected_width=request.metadata.width,
            expected_height=request.metadata.height,
        )
        return parent_node

    def _validate_image(
        self,
        *,
        image_bytes: bytes,
        metadata_mime_type: str,
        upload_content_type: str | None,
        expected_width: int,
        expected_height: int,
    ) -> None:
        if not image_bytes:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="이미지 파일이 비어 있습니다.",
            )

        normalized_mime_type = metadata_mime_type.strip().lower()
        if normalized_mime_type not in self.ALLOWED_MIME_TYPES:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="지원하지 않는 이미지 MIME Type입니다.",
            )

        normalized_upload_type = (
            (upload_content_type or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if (
            normalized_upload_type
            and normalized_upload_type != "application/octet-stream"
            and normalized_upload_type != normalized_mime_type
        ):
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="metadata.mime_type과 파일 Content-Type이 일치하지 않습니다.",
            )

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                actual_mime_type = self.MIME_TYPE_BY_FORMAT.get(image.format or "")
                actual_width, actual_height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="유효한 이미지 파일이 아닙니다.",
            ) from exc

        if actual_mime_type != normalized_mime_type:
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="metadata.mime_type과 실제 이미지 형식이 일치하지 않습니다.",
            )
        if (actual_width, actual_height) != (expected_width, expected_height):
            raise BadRequestException(
                code=ResponseCode.REFERENCE400,
                message="metadata의 이미지 크기와 실제 이미지 크기가 일치하지 않습니다.",
            )

    def _compensate_uploaded_object(
        self,
        *,
        room_id: UUID,
        stored_object: StoredObjectInfo | None,
    ) -> None:
        if stored_object is None:
            return

        try:
            self.minio_asset_storage.delete_uploaded_image(
                bucket_name=stored_object.bucket_name,
                object_name=stored_object.object_name,
            )
        except Exception as cleanup_error:
            logger.exception(
                "[reference_generate_cleanup_failed] room_id=%s | object_name=%s | error=%s",
                room_id,
                stored_object.object_name,
                str(cleanup_error),
            )

    @staticmethod
    def _resolve_node_text(*, filename: str | None) -> str:
        safe_filename = Path(filename or "").name.strip()
        return safe_filename or "reference_image"
