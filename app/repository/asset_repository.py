from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logger import get_logger
from app.model.asset import Asset
from app.model.enum import AssetType

logger = get_logger(__name__)


class AssetRepository:
    def find_asset_by_id(
        self,
        db: Session,
        *,
        asset_id: UUID,
    ) -> Asset | None:
        return (
            db.query(Asset)
            .filter(Asset.asset_id == asset_id)
            .first()
        )

    def create_2d_asset(
        self,
        db: Session,
        *,
        room_id: UUID,
        graph_snapshot_id: UUID | None=None,
        file_url: str,
        prompt_text: str,
    ) -> Asset:
        logger.info(
            "[create_2d_asset_started] room_id=%s | graph_snapshot_id=%s",
            room_id,
            graph_snapshot_id,
        )

        asset = Asset(
            room_id=room_id,
            graph_snapshot_id=graph_snapshot_id,
            asset_type=AssetType.IMAGE_2D,
            file_url=file_url,
            prompt_text=prompt_text,
        )

        db.add(asset)
        db.flush()

        logger.info(
            "[create_2d_asset_completed] room_id=%s | asset_id=%s",
            room_id,
            asset.asset_id,
        )

        return asset

    def create_3d_asset(
        self,
        db: Session,
        *,
        room_id: UUID,
        graph_snapshot_id: UUID | None,
        file_url: str,
    ) -> Asset:
        asset = Asset(
            room_id=room_id,
            graph_snapshot_id=graph_snapshot_id,
            asset_type=AssetType.MODEL_3D,
            file_url=file_url,
            prompt_text=None,
        )
        db.add(asset)
        db.flush()

        logger.info(
            "[create_3d_asset_completed] room_id=%s | asset_id=%s | graph_snapshot_id=%s",
            room_id,
            asset.asset_id,
            graph_snapshot_id,
        )
        return asset

    def update_graph_snapshot(
        self,
        db: Session,
        *,
        asset: Asset,
        graph_snapshot_id: UUID,
    ) -> Asset:
        asset.graph_snapshot_id = graph_snapshot_id
        db.flush()
        return asset
