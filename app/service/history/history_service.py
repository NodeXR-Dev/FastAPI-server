from uuid import UUID
from typing import Any

from sqlalchemy.orm import Session

from app.repository.graph_repository import GraphRepository


class HistoryService:
    def __init__(
        self,
        graph_repository: GraphRepository,
    ):
        self.graph_repository = graph_repository

    def get_graph_history(
        self,
        *,
        db: Session,
        room_id: UUID,
    ) -> dict[str, Any]:
        rows = self.graph_repository.find_history_snapshots_by_room_id(
            db=db,
            room_id=room_id,
        )

        history: list[dict[str, Any]] = []
        seen_snapshot_ids: set[UUID] = set()

        for graph_event, graph_snapshot in rows:
            if graph_snapshot.graph_snapshot_id in seen_snapshot_ids:
                continue

            seen_snapshot_ids.add(graph_snapshot.graph_snapshot_id)

            snapshot_data = graph_snapshot.snapshot_data or {}

            if not isinstance(snapshot_data, dict):
                continue

            history_item = dict(snapshot_data)

            # snapshot_data 안에 room_id가 들어있더라도 응답 구조상 result.room_id로만 내려주기
            history_item.pop("room_id", None)

            # graph_version은 snapshot_data에 없으면 graph_snapshots 컬럼에서 보강
            if "graph_version" not in history_item:
                history_item["graph_version"] = graph_snapshot.graph_version

            # 응답 예시 구조를 안정적으로 맞추기 위한 기본값
            history_item.setdefault("core_2d_image", None)
            history_item.setdefault("sub_graphs", [])

            history.append(history_item)

        return {
            "room_id": room_id,
            "history": history,
        }