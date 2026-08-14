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
        snapshots = self.graph_repository.find_history_snapshots_by_room_id(
            db=db,
            room_id=room_id,
        )

        history: list[dict[str, Any]] = []

        # 스냅샷을 직접 받으므로 예전의 중복 제거(seen_snapshot_ids)는 필요 없다.
        # 조인 때문에 같은 스냅샷이 이벤트 수만큼 나오던 상황이 사라졌다.
        for graph_snapshot in snapshots:
            snapshot_data = self._parse_snapshot_data(
                graph_snapshot.snapshot_data,
            )

            if snapshot_data is None:
                continue

            history_item = dict(snapshot_data)

            history_item.pop("room_id", None)
            history_item.pop("_generation_context", None)

            if "graph_version" not in history_item:
                # version 은 nullable 이라 비어 있으면 순번으로 채운다.
                # 클라 타임라인이 이 값을 눈금 라벨로 쓰므로 null 이면 안 된다.
                history_item["graph_version"] = (
                    graph_snapshot.version
                    if graph_snapshot.version is not None
                    else len(history) + 1
                )

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
