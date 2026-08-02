import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api import graph
from app.core.response.exceptions import NotFoundException
from app.db.session import get_db
from app.model.enum import NodeType
from app.repository.graph_repository import GraphRepository
from app.repository.graph_restore_repository import GraphRestoreRepository
from app.service.graph.graph_restore_service import GraphRestoreService


def _node(
    *,
    sub_graph_id: UUID,
    node_type: NodeType,
    node_text: str,
    parent_node_id: UUID | None = None,
    is_active: bool = True,
):
    return SimpleNamespace(
        node_id=uuid4(),
        sub_graph_id=sub_graph_id,
        parent_node_id=parent_node_id,
        node_type=node_type,
        node_text=node_text,
        position_x=1.0,
        position_y=None,
        position_z=3.0,
        is_active=is_active,
        deleted_at=None,
    )


def _configured_restore_service():
    room_id = uuid4()
    sub_graph_id = uuid4()
    empty_sub_graph_id = uuid4()
    part = _node(
        sub_graph_id=sub_graph_id,
        node_type=NodeType.PART,
        node_text="armrest",
    )
    inactive_property = _node(
        sub_graph_id=sub_graph_id,
        node_type=NodeType.PROPERTY,
        node_text="material",
        parent_node_id=part.node_id,
        is_active=False,
    )
    reference_node = _node(
        sub_graph_id=sub_graph_id,
        node_type=NodeType.REFERENCE,
        node_text="reference.png",
        parent_node_id=part.node_id,
    )
    edge = SimpleNamespace(
        edge_id=uuid4(),
        room_id=room_id,
        sub_graph_id=sub_graph_id,
        from_node_id=part.node_id,
        to_node_id=inactive_property.node_id,
        label="has_property",
        deleted_at=None,
    )
    reference = SimpleNamespace(
        reference_id=uuid4(),
        image_url="https://assets.example/reference.png",
        mime_type="image/png",
        width=1024,
        height=768,
    )
    core_asset_id = uuid4()
    snapshot_data = {
        "graph_version": 12,
        "core_2d_image": {
            "asset_id": str(core_asset_id),
            "image_url": "https://assets.example/core.png",
            "mime_type": "image/png",
            "width": 1280,
            "height": 720,
        },
        "sub_graphs": [
            {
                "sub_graph_id": str(sub_graph_id),
                "root_node_id": str(part.node_id),
                "nodes": [
                    {
                        "node_id": str(part.node_id),
                        "used_in_generation": True,
                    },
                    {
                        "node_id": str(inactive_property.node_id),
                        "used_in_generation": False,
                    },
                    {
                        "node_id": str(reference_node.node_id),
                        "used_in_generation": False,
                    },
                ],
                "edges": [
                    {
                        "edge_id": str(edge.edge_id),
                        "used_in_generation": False,
                    }
                ],
            }
        ],
    }

    restore_repository = Mock(spec=GraphRestoreRepository)
    restore_repository.find_non_deleted_sub_graphs_by_room_id.return_value = [
        SimpleNamespace(sub_graph_id=sub_graph_id, deleted_at=None),
        SimpleNamespace(sub_graph_id=empty_sub_graph_id, deleted_at=None),
    ]
    restore_repository.find_non_deleted_nodes_by_sub_graph_ids.return_value = [
        part,
        inactive_property,
        reference_node,
    ]
    restore_repository.find_non_deleted_edges_by_sub_graph_ids.return_value = [edge]

    graph_repository = Mock(spec=GraphRepository)
    latest_snapshot = SimpleNamespace(
        graph_snapshot_id=uuid4(),
        snapshot_data=json.dumps(snapshot_data),
        version=12,
    )
    graph_repository.find_latest_graph_snapshot_by_room_id.return_value = latest_snapshot
    graph_repository.load_snapshot_data.return_value = snapshot_data
    graph_repository.get_latest_graph_version.return_value = 12
    graph_repository.find_references_by_node_ids.return_value = {
        reference_node.node_id: reference,
    }

    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=False)

    service = GraphRestoreService(
        restore_repository=restore_repository,
        graph_repository=graph_repository,
        room_repository=room_repository,
    )
    return (
        service,
        room_id,
        sub_graph_id,
        empty_sub_graph_id,
        part,
        inactive_property,
        reference_node,
        edge,
        reference,
        core_asset_id,
        graph_repository,
    )


def test_restore_returns_all_non_deleted_types_and_false_generation_flags():
    (
        service,
        room_id,
        sub_graph_id,
        empty_sub_graph_id,
        part,
        inactive_property,
        reference_node,
        edge,
        reference,
        core_asset_id,
        graph_repository,
    ) = _configured_restore_service()

    result = service.get_room_graph(db=Mock(), room_id=room_id).model_dump(mode="json")

    assert result["room_id"] == str(room_id)
    assert result["graph_version"] == 12
    assert result["core_2d_image"]["asset_id"] == str(core_asset_id)
    assert [item["sub_graph_id"] for item in result["sub_graphs"]] == [
        str(sub_graph_id),
        str(empty_sub_graph_id),
    ]

    populated = result["sub_graphs"][0]
    assert populated["root_node_id"] == str(part.node_id)
    assert {node["type"] for node in populated["nodes"]} == {
        NodeType.PART.value,
        NodeType.PROPERTY.value,
        NodeType.REFERENCE.value,
    }
    property_result = next(
        node for node in populated["nodes"] if node["node_id"] == str(inactive_property.node_id)
    )
    assert property_result["used_in_generation"] is False
    assert property_result["position"] == [1.0, 0.0, 3.0]
    reference_result = next(
        node for node in populated["nodes"] if node["node_id"] == str(reference_node.node_id)
    )
    assert reference_result["used_in_generation"] is False
    assert reference_result["data"] == {
        "asset_id": str(reference.reference_id),
        "mime_type": "image/png",
        "width": 1024,
        "height": 768,
        "reference_image_url": "https://assets.example/reference.png",
    }
    assert populated["edges"] == [
        {
            "edge_id": str(edge.edge_id),
            "from_node_id": str(part.node_id),
            "to_node_id": str(inactive_property.node_id),
            "label": "has_property",
            "used_in_generation": False,
        }
    ]
    assert result["sub_graphs"][1]["nodes"] == []
    assert result["sub_graphs"][1]["edges"] == []
    graph_repository.build_snapshot_data.assert_not_called()
    graph_repository.create_graph_snapshot_from_current_graph.assert_not_called()


@pytest.mark.parametrize(
    ("repository_method", "expected_table"),
    [
        ("find_non_deleted_sub_graphs_by_room_id", "sub_graphs.deleted_at IS NULL"),
        ("find_non_deleted_nodes_by_sub_graph_ids", "nodes.deleted_at IS NULL"),
        ("find_non_deleted_edges_by_sub_graph_ids", "edges.deleted_at IS NULL"),
    ],
)
def test_restore_repository_filters_only_soft_deleted_rows(
    repository_method,
    expected_table,
):
    repository = GraphRestoreRepository()
    db = Mock()
    db.scalars.return_value.all.return_value = []
    kwargs = {"db": db, "room_id": uuid4()}
    if repository_method != "find_non_deleted_sub_graphs_by_room_id":
        kwargs["sub_graph_ids"] = [uuid4()]

    getattr(repository, repository_method)(**kwargs)

    stmt = db.scalars.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    where_sql = str(stmt.whereclause.compile(dialect=postgresql.dialect()))
    assert expected_table in sql
    assert "is_active" not in where_sql
    assert "status" not in where_sql
    assert "node_type" not in where_sql
    assert "label" not in where_sql


def test_restore_rejects_nonexistent_room():
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = None
    service = GraphRestoreService(
        restore_repository=Mock(spec=GraphRestoreRepository),
        graph_repository=Mock(spec=GraphRepository),
        room_repository=room_repository,
    )

    with pytest.raises(NotFoundException):
        service.get_room_graph(db=Mock(), room_id=uuid4())


def test_restore_allows_missing_core_2d_image_and_snapshot():
    room_id = uuid4()
    restore_repository = Mock(spec=GraphRestoreRepository)
    restore_repository.find_non_deleted_sub_graphs_by_room_id.return_value = []
    restore_repository.find_non_deleted_nodes_by_sub_graph_ids.return_value = []
    restore_repository.find_non_deleted_edges_by_sub_graph_ids.return_value = []
    graph_repository = Mock(spec=GraphRepository)
    graph_repository.find_latest_graph_snapshot_by_room_id.return_value = None
    graph_repository.get_latest_graph_version.return_value = 0
    graph_repository.find_references_by_node_ids.return_value = {}
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    service = GraphRestoreService(
        restore_repository=restore_repository,
        graph_repository=graph_repository,
        room_repository=room_repository,
    )

    result = service.get_room_graph(db=Mock(), room_id=room_id)

    assert result.graph_version == 0
    assert result.core_2d_image is None
    assert result.sub_graphs == []
    graph_repository.load_snapshot_data.assert_not_called()


def test_get_graph_endpoint_uses_graph200_contract(monkeypatch):
    service, room_id, *_ = _configured_restore_service()
    monkeypatch.setattr(graph, "graph_restore_service", service)
    app = FastAPI()
    app.include_router(graph.router, prefix="/api")
    db = Mock()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db

    response = TestClient(app).get(
        "/api/graph",
        params={"room_id": str(room_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["isSuccess"] is True
    assert body["code"] == "GRAPH200"
    assert body["message"] == "노드 그래프 조회 성공"
    assert body["result"]["room_id"] == str(room_id)


def test_existing_snapshot_builder_generation_flags_are_unchanged():
    repository = GraphRepository()
    sub_graph_id = uuid4()
    part = _node(
        sub_graph_id=sub_graph_id,
        node_type=NodeType.PART,
        node_text="part",
    )
    property_node = _node(
        sub_graph_id=sub_graph_id,
        node_type=NodeType.PROPERTY,
        node_text="property",
    )
    edge = SimpleNamespace(
        edge_id=uuid4(),
        sub_graph_id=sub_graph_id,
        from_node_id=part.node_id,
        to_node_id=property_node.node_id,
        label=None,
    )

    snapshot = repository.build_snapshot_data(
        version=1,
        nodes=[part, property_node],
        edges=[edge],
    )

    restored_nodes = snapshot["sub_graphs"][0]["nodes"]
    assert all(node["used_in_generation"] is True for node in restored_nodes)
    assert snapshot["sub_graphs"][0]["edges"][0]["used_in_generation"] is True
