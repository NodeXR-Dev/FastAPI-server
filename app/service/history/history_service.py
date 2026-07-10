import json
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

            snapshot_data = self._parse_snapshot_data(
                graph_snapshot.snapshot_data,
            )

            if snapshot_data is None:
                continue

            history_item = dict(snapshot_data)

            history_item.pop("room_id", None)

            if "graph_version" not in history_item:
                history_item["graph_version"] = graph_snapshot.version

            history_item.setdefault("core_2d_image", None)
            history_item.setdefault("sub_graphs", [])

            history.append(history_item)

        return {
            "room_id": room_id,
            "history": history,
        }

    def _parse_snapshot_data(
        self,
        snapshot_data: Any,
    ) -> dict[str, Any] | None:
        if snapshot_data is None:
            return None

        if isinstance(snapshot_data, dict):
            return snapshot_data

        if isinstance(snapshot_data, str):
            try:
                parsed = json.loads(snapshot_data)
            except json.JSONDecodeError:
                return None

            if isinstance(parsed, dict):
                return parsed

        return None