import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.prompts.color_change_prompt import COLOR_CHANGE_PROMPT
from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.db.session import SessionLocal
from app.model.asset import Asset
from app.model.enum import AssetType
from app.repository.asset_repository import AssetRepository
from app.repository.graph_repository import GraphRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.color_change_request import (
    ColorChangeMetadataRequest,
    ColorChangeRequest,
)
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    ImageBinaryInfo,
)
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.image_2d_asset_generation_service import (
    Image2DAssetGenerationService,
)
from app.service.generation.minio_asset_storage import MinioAssetStorage

logger = get_logger(__name__)


class Image2DColorChangeService:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        room_repository: RoomRepository | None = None,
        asset_repository: AssetRepository | None = None,
        graph_repository: GraphRepository | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
        gemini_image_client: GeminiImageClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.room_repository = room_repository or RoomRepository()
        self.asset_repository = asset_repository or AssetRepository()
        self.graph_repository = graph_repository or GraphRepository()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()
        self.gemini_image_client = gemini_image_client or GeminiImageClient()

    def validate_request(
        self,
        *,
        db: Session,
        request: ColorChangeRequest,
        guide_image_bytes: bytes,
        upload_content_type: str | None,
    ) -> UUID:
        source_asset = self._validate_entities(
            db=db,
            room_id=request.room_id,
            asset_id=request.asset_id,
        )
        guide_info = self._validate_guide_image(
            image_bytes=guide_image_bytes,
            metadata=request.metadata,
            upload_content_type=upload_content_type,
        )
        source_image_bytes = self.minio_asset_storage.download_generated_image(
            image_url=source_asset.file_url,
        )
        source_info = self._inspect_image(image_bytes=source_image_bytes)
        self._validate_matching_dimensions(
            source_info=source_info,
            guide_info=guide_info,
        )

        graph_snapshot = None
        if source_asset.graph_snapshot_id is not None:
            graph_snapshot = self.graph_repository.find_graph_snapshot_by_id(
                db=db,
                room_id=request.room_id,
                graph_snapshot_id=source_asset.graph_snapshot_id,
            )
            if graph_snapshot is None:
                raise BadRequestException(
                    code=ResponseCode.COLOR_CHANGE400,
                    message="원본 Asset의 Graph Snapshot이 유효하지 않습니다.",
                )
        else:
            graph_snapshot = self.graph_repository.find_latest_graph_snapshot_by_room_id(
                db=db,
                room_id=request.room_id,
            )
        if graph_snapshot is None:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="색상 변경에 사용할 Graph Snapshot이 없습니다.",
            )

        return graph_snapshot.graph_snapshot_id

    async def generate(
        self,
        *,
        room_id: UUID,
        source_asset_id: UUID,
        graph_snapshot_id: UUID,
        guide_image_bytes: bytes,
        metadata: ColorChangeMetadataRequest,
    ) -> Generated2DAssetResult:
        lookup_db = self.session_factory()

        try:
            source_asset = self._validate_entities(
                db=lookup_db,
                room_id=room_id,
                asset_id=source_asset_id,
            )
            source_asset_url = source_asset.file_url

            if self.graph_repository.find_graph_snapshot_by_id(
                db=lookup_db,
                room_id=room_id,
                graph_snapshot_id=graph_snapshot_id,
            ) is None:
                raise BadRequestException(
                    code=ResponseCode.COLOR_CHANGE400,
                    message="색상 변경에 사용할 Graph Snapshot이 유효하지 않습니다.",
                )
        finally:
            lookup_db.close()

        source_image_bytes = await asyncio.to_thread(
            self.minio_asset_storage.download_generated_image,
            image_url=source_asset_url,
        )
        source_info, guide_info = await asyncio.gather(
            asyncio.to_thread(
                self._inspect_image,
                image_bytes=source_image_bytes,
            ),
            asyncio.to_thread(
                self._validate_guide_image,
                image_bytes=guide_image_bytes,
                metadata=metadata,
                upload_content_type=metadata.mime_type,
            ),
        )
        self._validate_matching_dimensions(
            source_info=source_info,
            guide_info=guide_info,
        )

        generated_image = await self.gemini_image_client.edit_image_colors(
            prompt_text=COLOR_CHANGE_PROMPT,
            source_image_bytes=source_image_bytes,
            source_mime_type=source_info.mime_type,
            guide_image_bytes=guide_image_bytes,
            guide_mime_type=guide_info.mime_type,
        )

        if generated_image.width is None or generated_image.height is None:
            raise ValueError("Gemini 결과 이미지 크기를 확인할 수 없습니다.")
        if (
            generated_image.width * source_info.height
            != generated_image.height * source_info.width
        ):
            raise ValueError("Gemini 결과 이미지의 aspect ratio가 원본과 다릅니다.")

        persistence_db = self.session_factory()

        try:
            persistence_service = Image2DAssetGenerationService(
                db=persistence_db,
                gemini_image_client=self.gemini_image_client,
                minio_asset_storage=self.minio_asset_storage,
                asset_repository=self.asset_repository,
                graph_repository=self.graph_repository,
            )
            return await persistence_service.persist_generated_image(
                room_id=room_id,
                user_id=None,
                graph_snapshot_id=graph_snapshot_id,
                prompt_text=COLOR_CHANGE_PROMPT,
                generated_image=generated_image,
                event_payload_extra={
                    "source_asset_id": str(source_asset_id),
                    "generation_type": "COLOR_CHANGE",
                },
            )
        finally:
            persistence_db.close()

    def _validate_entities(
        self,
        *,
        db: Session,
        room_id: UUID,
        asset_id: UUID,
    ) -> Asset:
        room = self.room_repository.find_room_by_id(db=db, room_id=room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="비활성화된 회의실에서는 색상을 변경할 수 없습니다.",
            )

        asset = self.asset_repository.find_asset_by_id(db=db, asset_id=asset_id)
        if asset is None:
            raise NotFoundException(code=ResponseCode.COLOR_CHANGE404)
        if asset.room_id != room_id:
            raise NotFoundException(code=ResponseCode.COLOR_CHANGE404)
        if getattr(asset, "deleted_at", None) is not None:
            raise NotFoundException(code=ResponseCode.COLOR_CHANGE404)

        asset_type = (
            asset.asset_type.value
            if hasattr(asset.asset_type, "value")
            else str(asset.asset_type)
        )
        if asset_type != AssetType.IMAGE_2D.value:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="2D 이미지 Asset만 색상을 변경할 수 있습니다.",
            )
        if not self.minio_asset_storage.validate_generated_image_url(
            image_url=asset.file_url,
        ):
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="원본 Asset URL이 유효하지 않습니다.",
            )

        return asset

    def _validate_guide_image(
        self,
        *,
        image_bytes: bytes,
        metadata: ColorChangeMetadataRequest,
        upload_content_type: str | None,
    ) -> ImageBinaryInfo:
        if not image_bytes:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="색상 가이드 이미지가 비어 있습니다.",
            )

        normalized_content_type = (
            (upload_content_type or "")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if (
            normalized_content_type
            and normalized_content_type != "application/octet-stream"
            and normalized_content_type != metadata.mime_type
        ):
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="metadata.mime_type과 파일 Content-Type이 일치하지 않습니다.",
            )

        image_info = self._inspect_image(image_bytes=image_bytes)
        if image_info.mime_type != metadata.mime_type:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="metadata.mime_type과 실제 이미지 형식이 일치하지 않습니다.",
            )
        if image_info.width != metadata.width or image_info.height != metadata.height:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="metadata의 이미지 크기와 실제 이미지 크기가 일치하지 않습니다.",
            )
        return image_info

    def _inspect_image(self, *, image_bytes: bytes) -> ImageBinaryInfo:
        try:
            mime_type, width, height = self.gemini_image_client.inspect_image(
                image_bytes=image_bytes,
            )
        except ValueError as exc:
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="유효한 이미지 파일이 아닙니다.",
            ) from exc

        return ImageBinaryInfo(
            mime_type=mime_type,
            width=width,
            height=height,
        )

    @staticmethod
    def _validate_matching_dimensions(
        *,
        source_info: ImageBinaryInfo,
        guide_info: ImageBinaryInfo,
    ) -> None:
        if (
            source_info.width != guide_info.width
            or source_info.height != guide_info.height
        ):
            raise BadRequestException(
                code=ResponseCode.COLOR_CHANGE400,
                message="원본 Asset과 색상 가이드 이미지의 크기가 일치하지 않습니다.",
            )
