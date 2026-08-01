import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.model.enum import NodeType
from app.repository.graph_repository import GraphRepository
from app.schema.graph.part_node_request import (
    CreatePartNodeRequest,
    DeletePartNodeRequest,
    ModifyPartNodeRequest,
)
from app.service.graph.graph_interaction_service import GraphInteractionService
from app.service.graph.part_node_service import PartNodeService


def test_part_node_router_exposes_only_requested_mutation_paths():
    source_path = Path(__file__).parents[1] / "app/api/part_node.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    routes = []

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            routes.append((decorator.func.attr.upper(), decorator.args[0].value))

    assert routes == [
        ("POST", "/generate"),
        ("PATCH", "/modify"),
        ("DELETE", "/delete"),
    ]
    assert ResponseCode.PART_NODE200.value == "PART_NODE200"
    assert ResponseCode.PART_NODE201.value == "PART_NODE201"
    assert ResponseCode.PART_NODE202.value == "PART_NODE202"


def test_create_part_node_delegates_independent_part_mutation():
    room_id = uuid4()
    node_id = uuid4()
    db = Mock()
    service = PartNodeService()
    service.room_repository.find_room_by_id = Mock(
        return_value=SimpleNamespace(is_active=True),
    )
    created_node = SimpleNamespace(
        room_id=room_id,
        node_id=node_id,
        node_text="robot arm",
    )

    with patch(
        "app.service.graph.part_node_service.GraphInteractionService",
    ) as interaction_service_class:
        interaction_service_class.return_value.create_independent_node.return_value = created_node

        result = service.create_part_node(
            request=CreatePartNodeRequest(
                room_id=room_id,
                text="robot arm",
                position=[1.0, 2.0, 3.0],
            ),
            db=db,
        )

    interaction_service_class.return_value.create_independent_node.assert_called_once_with(
        room_id=room_id,
        user_id=None,
        node_text="robot arm",
        node_type=NodeType.PART,
        position=(1.0, 2.0, 3.0),
    )
    assert result.part_node_id == node_id
    assert result.part_node_text == "robot arm"


def test_modify_rejects_non_part_node_before_mutation():
    room_id = uuid4()
    node_id = uuid4()
    db = Mock()
    service = PartNodeService()
    service.room_repository.find_room_by_id = Mock(
        return_value=SimpleNamespace(is_active=True),
    )
    service.graph_repository.find_active_node_by_id = Mock(
        return_value=SimpleNamespace(node_type=NodeType.PROPERTY),
    )

    with pytest.raises(NotFoundException) as exc_info:
        service.modify_part_node(
            request=ModifyPartNodeRequest(
                room_id=room_id,
                part_node_id=node_id,
                part_node_text="updated",
            ),
            db=db,
        )

    assert exc_info.value.code == ResponseCode.PART_NODE404


def test_delete_part_node_delegates_shared_delete_workflow():
    room_id = uuid4()
    node_id = uuid4()
    db = Mock()
    service = PartNodeService()
    service.room_repository.find_room_by_id = Mock(
        return_value=SimpleNamespace(is_active=True),
    )
    service.graph_repository.find_active_node_by_id = Mock(
        return_value=SimpleNamespace(node_type=NodeType.PART),
    )

    with patch(
        "app.service.graph.part_node_service.GraphInteractionService",
    ) as interaction_service_class:
        result = service.delete_part_node(
            request=DeletePartNodeRequest(
                room_id=room_id,
                part_node_id=node_id,
            ),
            db=db,
        )

    interaction_service_class.return_value.delete_node.assert_called_once_with(
        room_id=room_id,
        user_id=None,
        node_id=node_id,
    )
    assert result.room_id == room_id
    assert result.part_node_id == node_id


def test_shared_delete_soft_deletes_descendants_edges_and_commits():
    room_id = uuid4()
    root = SimpleNamespace(node_id=uuid4())
    child = SimpleNamespace(node_id=uuid4())
    edge = SimpleNamespace(edge_id=uuid4())
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.find_active_node_by_id.return_value = root
    repository.find_active_child_nodes_recursively.return_value = [child]
    repository.find_active_edges_connected_to_nodes.return_value = [edge]
    repository.find_reference_records_by_node_ids.return_value = []
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    service.graph_repository = repository

    result = service.delete_node(
        room_id=room_id,
        user_id=None,
        node_id=root.node_id,
    )

    repository.soft_delete_nodes.assert_called_once()
    assert repository.soft_delete_nodes.call_args.kwargs["nodes"] == [root, child]
    repository.soft_delete_edges.assert_called_once()
    assert repository.soft_delete_edges.call_args.kwargs["edges"] == [edge]
    repository.create_graph_snapshot_from_current_graph.assert_called_once_with(
        db=db,
        room_id=room_id,
    )
    repository.create_graph_event.assert_called_once()
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert result is root


def test_shared_independent_create_does_not_create_sub_graph_and_rolls_back_on_failure():
    room_id = uuid4()
    node = SimpleNamespace(
        node_id=uuid4(),
        node_text="part",
        node_type=NodeType.PART,
    )
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.create_node.return_value = node
    repository.create_graph_snapshot_from_current_graph.side_effect = RuntimeError(
        "snapshot failed",
    )
    service.graph_repository = repository

    with pytest.raises(RuntimeError, match="snapshot failed"):
        service.create_independent_node(
            room_id=room_id,
            user_id=None,
            node_text="part",
            node_type=NodeType.PART,
            position=(0.0, 0.0, 0.0),
        )

    repository.create_sub_graph.assert_not_called()
    assert repository.create_node.call_args.kwargs["sub_graph_id"] is None
    assert repository.create_node.call_args.kwargs["parent_node_id"] is None
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_keyboard_property_create_without_parent_creates_new_sub_graph():
    room_id = uuid4()
    job_id = uuid4()
    sub_graph_id = uuid4()
    node = SimpleNamespace(
        node_id=uuid4(),
        node_text="material",
        node_type=NodeType.PROPERTY,
    )
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.create_sub_graph.return_value = SimpleNamespace(
        sub_graph_id=sub_graph_id,
    )
    repository.create_node.return_value = node
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    service.graph_repository = repository

    result = asyncio.run(
        service._handle_node_save(
            room_id=room_id,
            user_id=None,
            payload={
                "job_id": str(job_id),
                "parent_node_id": None,
                "sub_graph_id": None,
                "node_text": "material",
                "node_type": NodeType.PROPERTY.value,
                "position": [1.0, 2.0, 3.0],
            },
        )
    )

    repository.create_sub_graph.assert_called_once_with(
        db=db,
        room_id=room_id,
    )
    repository.find_active_node_by_id.assert_not_called()
    assert repository.create_node.call_args.kwargs["sub_graph_id"] == sub_graph_id
    assert repository.create_node.call_args.kwargs["parent_node_id"] is None
    assert repository.create_node.call_args.kwargs["node_type"] == NodeType.PROPERTY
    repository.create_edge.assert_not_called()
    repository.create_graph_snapshot_from_current_graph.assert_called_once_with(
        db=db,
        room_id=room_id,
    )
    repository.create_graph_event.assert_called_once()
    event_payload = repository.create_graph_event.call_args.kwargs["payload"]
    assert event_payload["sub_graph_id"] == str(sub_graph_id)
    db.commit.assert_called_once()
    assert result["result"]["node_id"] == str(node.node_id)


def test_keyboard_property_create_without_parent_rolls_back_new_sub_graph_on_failure():
    room_id = uuid4()
    sub_graph_id = uuid4()
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.create_sub_graph.return_value = SimpleNamespace(
        sub_graph_id=sub_graph_id,
    )
    repository.create_node.side_effect = RuntimeError("node create failed")
    service.graph_repository = repository

    with pytest.raises(RuntimeError, match="node create failed"):
        asyncio.run(
            service.handle_graph_interaction(
                event_type="NODE_CREATE",
                room_id=room_id,
                user_id=None,
                payload={
                    "job_id": str(uuid4()),
                    "parent_node_id": None,
                    "node_text": "material",
                    "node_type": NodeType.PROPERTY.value,
                    "position": [1.0, 2.0, 3.0],
                },
            )
        )

    repository.create_sub_graph.assert_called_once_with(
        db=db,
        room_id=room_id,
    )
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_keyboard_property_create_with_parent_inherits_parent_sub_graph():
    room_id = uuid4()
    parent_node = SimpleNamespace(
        node_id=uuid4(),
        sub_graph_id=uuid4(),
    )
    node = SimpleNamespace(
        node_id=uuid4(),
        node_text="material",
        node_type=NodeType.PROPERTY,
    )
    edge = SimpleNamespace(edge_id=uuid4())
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.find_active_node_by_id.return_value = parent_node
    repository.create_node.return_value = node
    repository.create_edge.return_value = edge
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    service.graph_repository = repository

    asyncio.run(
        service._handle_node_save(
            room_id=room_id,
            user_id=None,
            payload={
                "job_id": str(uuid4()),
                "parent_node_id": str(parent_node.node_id),
                "node_text": "material",
                "node_type": NodeType.PROPERTY.value,
                "position": [1.0, 2.0, 3.0],
            },
        )
    )

    repository.create_sub_graph.assert_not_called()
    assert (
        repository.create_node.call_args.kwargs["sub_graph_id"]
        == parent_node.sub_graph_id
    )
    assert (
        repository.create_edge.call_args.kwargs["sub_graph_id"]
        == parent_node.sub_graph_id
    )
    db.commit.assert_called_once()


def test_part_property_edge_assigns_part_to_property_sub_graph():
    room_id = uuid4()
    part_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.PART,
        sub_graph_id=None,
    )
    property_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.PROPERTY,
        sub_graph_id=uuid4(),
    )
    edge = SimpleNamespace(edge_id=uuid4(), label=None)
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.find_active_node_by_id.side_effect = [part_node, property_node]
    repository.find_active_edge_between_nodes.return_value = None
    repository.create_edge.return_value = edge
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    repository.update_node_sub_graph.side_effect = (
        lambda *, node, sub_graph_id: setattr(node, "sub_graph_id", sub_graph_id) or node
    )
    service.graph_repository = repository

    asyncio.run(
        service._handle_edge_create(
            room_id=room_id,
            user_id=None,
            payload={
                "job_id": str(uuid4()),
                "from_node_id": str(part_node.node_id),
                "to_node_id": str(property_node.node_id),
            },
        )
    )

    repository.update_node_sub_graph.assert_called_once_with(
        node=part_node,
        sub_graph_id=property_node.sub_graph_id,
    )
    assert repository.create_edge.call_args.kwargs["sub_graph_id"] == property_node.sub_graph_id
    db.commit.assert_called_once()


def test_deleting_last_part_property_edge_makes_part_independent_again():
    room_id = uuid4()
    sub_graph_id = uuid4()
    part_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.PART,
        sub_graph_id=sub_graph_id,
    )
    property_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.PROPERTY,
        sub_graph_id=sub_graph_id,
    )
    edge = SimpleNamespace(
        edge_id=uuid4(),
        from_node_id=part_node.node_id,
        to_node_id=property_node.node_id,
        label=None,
    )
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    service = GraphInteractionService(db)
    repository = Mock()
    repository.find_active_edge_by_id.return_value = edge
    repository.find_active_node_by_id.side_effect = [part_node, property_node]
    repository.find_active_edges_connected_to_node.return_value = []
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    repository.update_node_sub_graph.side_effect = (
        lambda *, node, sub_graph_id: setattr(node, "sub_graph_id", sub_graph_id) or node
    )
    service.graph_repository = repository

    asyncio.run(
        service._handle_edge_delete(
            room_id=room_id,
            user_id=None,
            payload={"edge_id": str(edge.edge_id)},
        )
    )

    repository.update_node_sub_graph.assert_called_once_with(
        node=part_node,
        sub_graph_id=None,
    )
    db.commit.assert_called_once()


def test_attached_part_is_not_selected_as_property_sub_graph_root():
    repository = GraphRepository()
    attached_part = SimpleNamespace(
        node_id=uuid4(),
        parent_node_id=None,
    )
    existing_root = SimpleNamespace(
        node_id=uuid4(),
        parent_node_id=None,
    )

    root_node_id = repository._resolve_root_node_id(
        nodes=[attached_part, existing_root],
        excluded_root_node_ids={attached_part.node_id},
    )

    assert root_node_id == str(existing_root.node_id)
