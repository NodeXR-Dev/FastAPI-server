from datetime import datetime
from uuid import UUID

from sqlalchemy import select
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

    def find_latest_ws_sent_2d_asset(
        self,
        db: Session,
        *,
        room_id: UUID,
        requested_at: datetime,
    ) -> Asset | None:
        stmt = (
            select(Asset)
            .where(
                Asset.room_id == room_id,
                Asset.asset_type == AssetType.IMAGE_2D,
                Asset.ws_sent_at.is_not(None),
                Asset.ws_sent_at <= requested_at,
            )
            .order_by(
                Asset.ws_sent_at.desc(),
                Asset.created_at.desc(),
                Asset.asset_id.desc(),
            )
            .limit(1)
        )
        return db.scalar(stmt)

    def mark_2d_asset_ws_sent(
        self,
        db: Session,
        *,
        room_id: UUID,
        asset_id: UUID,
        ws_sent_at: datetime,
    ) -> Asset | None:
        stmt = select(Asset).where(
            Asset.room_id == room_id,
            Asset.asset_id == asset_id,
            Asset.asset_type == AssetType.IMAGE_2D,
        )
        asset = db.scalar(stmt)
        if asset is None:
            return None

        asset.ws_sent_at = ws_sent_at
        db.flush()
        return asset

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

    def find_latest_3d_asset(
        self,
        db: Session,
        *,
        room_id: UUID,
    ) -> Asset | None:
        """방의 가장 최근 3D 모델을 돌려준다.

        3D 생성은 Meshy 때문에 1~2분이 걸리는데, 그 사이 클라이언트의 WS 가
        끊기면 완료 이벤트를 보낼 곳이 없어 결과가 그대로 사라진다.
        (실측 2026-08-15: 완료 6초 전에 ws_closed → ws_send_to_user_skip)
        생성물은 DB 에 남아 있으므로, 클라이언트가 방에 들어올 때 이걸로
        따라잡게 한다. 앱을 다시 켠 경우와 늦게 합류한 참가자도 같이 해결된다.
        """
        stmt = (
            select(Asset)
            .where(
                Asset.room_id == room_id,
                Asset.asset_type == AssetType.MODEL_3D,
            )
            .order_by(
                Asset.created_at.desc(),
                Asset.asset_id.desc(),
            )
            .limit(1)
        )
        return db.scalar(stmt)

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
