import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.db.session import SessionLocal
from app.model.asset import Asset
from app.model.enum import AssetType
from app.repository.asset_repository import AssetRepository
from app.repository.room_repository import RoomRepository
from app.schema.generation.generation_result import (
    Generated3DAssetResult,
    StoredObjectInfo,
)
from app.schema.generation.request import Generate3DRequest
from app.schema.generation.ws_event_generation_payload import Model3DAssetPayload
from app.schema.websocket.ws_event import Model3DGeneratedWSEvent
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.meshy_client import MeshyClient, MeshyClientError
from app.service.generation.minio_asset_storage import MinioAssetStorage
from app.service.websocket.connection_manager import RoomConnectionManager, room_ws_manager

logger = get_logger(__name__)


class Model3DGenerationService:
    MODEL_MIME_TYPE = "model/gltf-binary"

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        room_repository: RoomRepository | None = None,
        asset_repository: AssetRepository | None = None,
        minio_asset_storage: MinioAssetStorage | None = None,
        meshy_client: MeshyClient | None = None,
        ws_manager: RoomConnectionManager = room_ws_manager,
    ) -> None:
        self.session_factory = session_factory
        self.room_repository = room_repository or RoomRepository()
        self.asset_repository = asset_repository or AssetRepository()
        self.minio_asset_storage = minio_asset_storage or MinioAssetStorage()
        self.meshy_client = meshy_client or MeshyClient()
        self.ws_manager = ws_manager

    def validate_request(
        self,
        *,
        db: Session,
        request: Generate3DRequest,
    ) -> Asset:
        return self._get_valid_source_asset(
            db=db,
            room_id=request.room_id,
            source_asset_id=request.asset_id,
        )

    async def run(
        self,
        *,
        room_id: UUID,
        source_asset_id: UUID,
    ) -> None:
        logger.info(
            "[3d_generation_started] room_id=%s | source_asset_id=%s",
            room_id,
            source_asset_id,
        )
        try:
            result = await self.generate(
                room_id=room_id,
                source_asset_id=source_asset_id,
            )
        except Exception as error:
            logger.exception(
                "[3d_generation_failed] room_id=%s | source_asset_id=%s | error=%s",
                room_id,
                source_asset_id,
                str(error),
            )
            return

        event = Model3DGeneratedWSEvent(
            room_id=room_id,
            payload=Model3DAssetPayload(
                asset_id=result.asset_id,
                mime_type=result.mime_type,
                model_url=result.model_url,
            ),
        )
        try:
            await self.ws_manager.broadcast_to_room(
                room_id=room_id,
                message=event.model_dump(mode="json"),
            )
        except Exception as error:
            logger.exception(
                "[3d_generation_ws_failed_after_commit] room_id=%s | asset_id=%s | error=%s",
                room_id,
                result.asset_id,
                str(error),
            )
            return

        logger.info(
            "[3d_generation_completed] room_id=%s | source_asset_id=%s | asset_id=%s",
            room_id,
            source_asset_id,
            result.asset_id,
        )

    async def generate(
        self,
        *,
        room_id: UUID,
        source_asset_id: UUID,
    ) -> Generated3DAssetResult:
        lookup_db = self.session_factory()
        try:
            source_asset = self._get_valid_source_asset(
                db=lookup_db,
                room_id=room_id,
                source_asset_id=source_asset_id,
            )
            source_image_url = source_asset.file_url
            graph_snapshot_id = source_asset.graph_snapshot_id
        finally:
            lookup_db.close()

        image_bytes = await asyncio.to_thread(
            self.minio_asset_storage.download_generated_image,
            image_url=source_image_url,
        )
        try:
            source_mime_type, _, _ = await asyncio.to_thread(
                GeminiImageClient.inspect_image,
                image_bytes=image_bytes,
            )
        except ValueError as exc:
            raise MeshyClientError("원본 Asset이 유효한 이미지가 아닙니다.") from exc

        generated_model = await self.meshy_client.generate_glb(
            image_bytes=image_bytes,
            mime_type=source_mime_type,
        )
        stored_object: StoredObjectInfo | None = None
        persistence_db = self.session_factory()

        try:
            stored_object = await asyncio.to_thread(
                self.minio_asset_storage.upload_generated_model,
                room_id=room_id,
                source_asset_id=source_asset_id,
                model_bytes=generated_model.model_bytes,
            )
            self._get_valid_source_asset(
                db=persistence_db,
                room_id=room_id,
                source_asset_id=source_asset_id,
            )
            generated_asset = self.asset_repository.create_3d_asset(
                db=persistence_db,
                room_id=room_id,
                graph_snapshot_id=graph_snapshot_id,
                file_url=stored_object.public_url,
            )
            result = Generated3DAssetResult(
                asset_id=generated_asset.asset_id,
                mime_type=self.MODEL_MIME_TYPE,
                model_url=stored_object.public_url,
            )
            persistence_db.commit()
            return result
        except Exception:
            persistence_db.rollback()
            if stored_object is not None:
                try:
                    await asyncio.to_thread(
                        self.minio_asset_storage.delete_uploaded_model,
                        bucket_name=stored_object.bucket_name,
                        object_name=stored_object.object_name,
                    )
                except Exception as cleanup_error:
                    logger.exception(
                        "[3d_model_cleanup_failed] room_id=%s | object_name=%s | error=%s",
                        room_id,
                        stored_object.object_name,
                        str(cleanup_error),
                    )
            raise
        finally:
            persistence_db.close()

    def _get_valid_source_asset(
        self,
        *,
        db: Session,
        room_id: UUID,
        source_asset_id: UUID,
    ) -> Asset:
        room = self.room_repository.find_room_by_id(db=db, room_id=room_id)
        if room is None:
            raise NotFoundException(code=ResponseCode.ROOM404)
        if not room.is_active:
            raise BadRequestException(
                code=ResponseCode.MODEL_3D400,
                message="비활성화된 회의실에서는 3D를 생성할 수 없습니다.",
            )

        asset = self.asset_repository.find_asset_by_id(
            db=db,
            asset_id=source_asset_id,
        )
        if asset is None or asset.room_id != room_id:
            raise NotFoundException(code=ResponseCode.MODEL_3D404)
        if getattr(asset, "deleted_at", None) is not None:
            raise NotFoundException(code=ResponseCode.MODEL_3D404)
        if asset.asset_type != AssetType.IMAGE_2D:
            raise BadRequestException(
                code=ResponseCode.MODEL_3D400,
                message="2D 이미지 Asset만 3D로 변환할 수 있습니다.",
            )
        if not asset.file_url or not self.minio_asset_storage.validate_generated_image_url(
            image_url=asset.file_url,
        ):
            raise BadRequestException(
                code=ResponseCode.MODEL_3D400,
                message="원본 2D Asset URL이 유효하지 않습니다.",
            )
        return asset
