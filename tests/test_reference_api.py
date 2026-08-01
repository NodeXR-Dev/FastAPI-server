import asyncio
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api.reference import reference_service, router
from app.core.config import settings
from app.core.response.code import ResponseCode
from app.core.response.exceptions import (
    BadRequestException,
    NotFoundException,
    ServerException,
)
from app.db.session import get_db
from app.model.enum import EdgeType, GraphEventType, NodeType
from app.repository.graph_repository import GraphRepository
from app.schema.generation.generation_result import StoredObjectInfo
from app.schema.graph.reference_request import (
    GenerateReferenceRequest,
    ReferenceMetadataRequest,
)
from app.schema.graph.reference_response import GenerateReferenceResponse
from app.service.graph.graph_interaction_service import GraphInteractionService
from app.service.graph.reference_service import ReferenceService
from app.service.generation.minio_asset_storage import MinioAssetStorage


def make_png(*, width: int = 2, height: int = 3) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def make_request(*, room_id=None, node_id=None) -> GenerateReferenceRequest:
    return GenerateReferenceRequest(
        room_id=room_id or uuid4(),
        node_id=node_id or uuid4(),
        metadata=ReferenceMetadataRequest(
            mime_type="image/png",
            width=2,
            height=3,
        ),
    )


def configured_reference_service(*, request: GenerateReferenceRequest):
    parent = SimpleNamespace(
        node_id=request.node_id,
        node_type=NodeType.PROPERTY,
        sub_graph_id=uuid4(),
        position_x=1.0,
        position_y=2.0,
        position_z=3.0,
    )
    reference_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.REFERENCE,
        room_id=request.room_id,
        sub_graph_id=parent.sub_graph_id,
        parent_node_id=parent.node_id,
    )
    reference = SimpleNamespace(reference_id=uuid4())
    edge = SimpleNamespace(edge_id=uuid4())
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    repository = Mock()
    repository.find_active_node_by_id.return_value = parent
    repository.find_sub_graph_by_id.return_value = SimpleNamespace(
        sub_graph_id=parent.sub_graph_id,
    )
    repository.create_node.return_value = reference_node
    repository.create_reference.return_value = reference
    repository.find_active_edge_between_nodes.return_value = None
    repository.create_edge.return_value = edge
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    storage = Mock()
    storage.upload_reference_image.return_value = StoredObjectInfo(
        bucket_name="nodexr-2d-assets",
        object_name="references/room/reference.png",
        public_url="https://assets.example/references/reference.png",
    )
    service = ReferenceService(
        graph_repository=repository,
        room_repository=room_repository,
        minio_asset_storage=storage,
    )
    return service, repository, room_repository, storage, parent, reference_node, edge


def test_reference_router_preserves_multipart_request_and_response_contract():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = Mock()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    room_id = uuid4()
    reference_node_id = uuid4()
    parent_node_id = uuid4()
    reference_url = "https://assets.example/reference.png"
    original_method = reference_service.generate_reference
    generate_reference_mock = Mock(
        return_value=GenerateReferenceResponse(
            room_id=room_id,
            node_id=reference_node_id,
            reference_url=reference_url,
        )
    )
    reference_service.generate_reference = generate_reference_mock

    try:
        response = TestClient(app).post(
            "/api/references/generate",
            data={
                "room_id": str(room_id),
                "node_id": str(parent_node_id),
                "metadata": json.dumps(
                    {"mime_type": "image/png", "width": 2, "height": 3}
                ),
            },
            files={"file": ("reference.png", make_png(), "image/png")},
        )
    finally:
        reference_service.generate_reference = original_method

    assert response.status_code == 200
    assert response.json() == {
        "isSuccess": True,
        "code": "REFERENCE201",
        "message": "레퍼런스 저장 성공",
        "result": {
            "room_id": str(room_id),
            "node_id": str(reference_node_id),
            "reference_url": reference_url,
        },
    }
    service_call = generate_reference_mock.call_args.kwargs
    assert service_call["db"] is db
    assert service_call["request"].room_id == room_id
    assert service_call["request"].node_id == parent_node_id
    assert service_call["request"].metadata.mime_type == "image/png"
    assert service_call["image_bytes"] == make_png()
    assert service_call["filename"] == "reference.png"
    assert service_call["upload_content_type"] == "image/png"
    assert reference_node_id != parent_node_id


def test_reference_openapi_renders_metadata_as_text_form_field():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    schema = app.openapi()
    operation = schema["paths"]["/api/references/generate"]["post"]
    body_schema_ref = operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"]
    body_schema_name = body_schema_ref.rsplit("/", 1)[-1]
    metadata_schema = schema["components"]["schemas"][body_schema_name][
        "properties"
    ]["metadata"]

    assert metadata_schema["type"] == "string"
    assert "contentMediaType" not in metadata_schema


def test_reference_generate_persists_node_reference_edge_snapshot_and_one_event():
    request = make_request()
    service, repository, _, storage, parent, reference_node, edge = (
        configured_reference_service(request=request)
    )
    db = Mock()

    result = service.generate_reference(
        db=db,
        request=request,
        image_bytes=make_png(),
        filename="reference.png",
        upload_content_type="image/png",
    )

    storage.upload_reference_image.assert_called_once_with(
        room_id=request.room_id,
        image_bytes=make_png(),
        mime_type="image/png",
    )
    node_call = repository.create_node.call_args.kwargs
    assert node_call["node_type"] == NodeType.REFERENCE
    assert node_call["parent_node_id"] == request.node_id
    assert node_call["sub_graph_id"] == parent.sub_graph_id
    reference_call = repository.create_reference.call_args.kwargs
    assert reference_call["node_id"] == reference_node.node_id
    assert reference_call["image_url"] == result.reference_url
    edge_call = repository.create_edge.call_args.kwargs
    assert edge_call["from_node_id"] == parent.node_id
    assert edge_call["to_node_id"] == reference_node.node_id
    assert edge_call["label"] == EdgeType.PROPERTY_REFERENCE.value
    repository.create_graph_snapshot_from_current_graph.assert_called_once()
    repository.create_graph_event.assert_called_once()
    event_call = repository.create_graph_event.call_args.kwargs
    assert event_call["event_type"] == GraphEventType.NODE_CREATE
    assert event_call["edge_id"] == edge.edge_id
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert result.node_id == reference_node.node_id
    assert result.node_id != request.node_id


def test_reference_model_write_uses_null_query_text_and_new_node_id():
    repository = GraphRepository()
    db = Mock()
    node_id = uuid4()

    reference = repository.create_reference(
        db=db,
        room_id=uuid4(),
        node_id=node_id,
        image_url="https://assets.example/reference.png",
        mime_type="image/png",
        width=2,
        height=3,
    )

    assert reference.query_text is None
    assert reference.node_id == node_id
    db.add.assert_called_once_with(reference)
    db.flush.assert_called_once()


@pytest.mark.parametrize(
    ("room", "parent", "sub_graph", "expected_code"),
    [
        (None, None, None, ResponseCode.ROOM404),
        (SimpleNamespace(is_active=True), None, None, ResponseCode.NODE404),
        (
            SimpleNamespace(is_active=True),
            SimpleNamespace(node_id=uuid4(), sub_graph_id=None),
            None,
            ResponseCode.REFERENCE400,
        ),
    ],
)
def test_reference_generate_rejects_invalid_room_parent_or_sub_graph(
    room,
    parent,
    sub_graph,
    expected_code,
):
    request = make_request()
    repository = Mock()
    repository.find_active_node_by_id.return_value = parent
    repository.find_sub_graph_by_id.return_value = sub_graph
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = room
    storage = Mock()
    service = ReferenceService(
        graph_repository=repository,
        room_repository=room_repository,
        minio_asset_storage=storage,
    )
    db = Mock()

    with pytest.raises((NotFoundException, BadRequestException)) as exc_info:
        service.generate_reference(
            db=db,
            request=request,
            image_bytes=make_png(),
            filename="reference.png",
            upload_content_type="image/png",
        )

    assert exc_info.value.code == expected_code
    storage.upload_reference_image.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    ("image_bytes", "metadata", "content_type"),
    [
        (b"", ReferenceMetadataRequest(mime_type="image/png", width=2, height=3), "image/png"),
        (make_png(), ReferenceMetadataRequest(mime_type="image/webp", width=2, height=3), "image/webp"),
        (make_png(), ReferenceMetadataRequest(mime_type="image/png", width=2, height=3), "image/jpeg"),
        (make_png(), ReferenceMetadataRequest(mime_type="image/png", width=5, height=5), "image/png"),
    ],
)
def test_reference_generate_rejects_empty_or_mismatched_image(
    image_bytes,
    metadata,
    content_type,
):
    request = GenerateReferenceRequest(
        room_id=uuid4(),
        node_id=uuid4(),
        metadata=metadata,
    )
    service, _, _, storage, _, _, _ = configured_reference_service(request=request)
    db = Mock()

    with pytest.raises(BadRequestException) as exc_info:
        service.generate_reference(
            db=db,
            request=request,
            image_bytes=image_bytes,
            filename="reference.png",
            upload_content_type=content_type,
        )

    assert exc_info.value.code == ResponseCode.REFERENCE400
    storage.upload_reference_image.assert_not_called()


def test_reference_generate_compensates_minio_when_database_work_fails():
    request = make_request()
    service, repository, _, storage, _, _, _ = configured_reference_service(request=request)
    repository.create_reference.side_effect = RuntimeError("reference insert failed")
    db = Mock()

    with pytest.raises(ServerException) as exc_info:
        service.generate_reference(
            db=db,
            request=request,
            image_bytes=make_png(),
            filename="reference.png",
            upload_content_type="image/png",
        )

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    storage.delete_uploaded_image.assert_called_once_with(
        bucket_name="nodexr-2d-assets",
        object_name="references/room/reference.png",
    )


def test_compensation_failure_does_not_replace_original_database_failure():
    request = make_request()
    service, repository, _, storage, _, _, _ = configured_reference_service(request=request)
    database_error = RuntimeError("edge insert failed")
    repository.create_edge.side_effect = database_error
    storage.delete_uploaded_image.side_effect = RuntimeError("cleanup failed")

    with pytest.raises(ServerException) as exc_info:
        service.generate_reference(
            db=Mock(),
            request=request,
            image_bytes=make_png(),
            filename="reference.png",
            upload_content_type="image/png",
        )

    assert exc_info.value.__cause__ is database_error


def test_minio_upload_failure_leaves_database_unmodified():
    request = make_request()
    service, repository, _, storage, _, _, _ = configured_reference_service(request=request)
    upload_error = RuntimeError("minio unavailable")
    storage.upload_reference_image.side_effect = upload_error
    db = Mock()

    with pytest.raises(ServerException) as exc_info:
        service.generate_reference(
            db=db,
            request=request,
            image_bytes=make_png(),
            filename="reference.png",
            upload_content_type="image/png",
        )

    assert exc_info.value.__cause__ is upload_error
    repository.create_node.assert_not_called()
    storage.delete_uploaded_image.assert_not_called()
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_reference_parent_can_itself_be_reference_when_sub_graph_is_valid():
    request = make_request()
    service, _, _, _, parent, _, _ = configured_reference_service(request=request)
    parent.node_type = NodeType.REFERENCE

    result = service.generate_reference(
        db=Mock(),
        request=request,
        image_bytes=make_png(),
        filename="nested.png",
        upload_content_type="image/png",
    )

    assert result.node_id is not None


def test_snapshot_keeps_common_edge_shape_and_adds_reference_data_to_node():
    repository = GraphRepository()
    sub_graph_id = uuid4()
    parent = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.PROPERTY,
        node_text="material",
        sub_graph_id=sub_graph_id,
        parent_node_id=None,
        position_x=0.0,
        position_y=0.0,
        position_z=0.0,
    )
    reference_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.REFERENCE,
        node_text="reference.png",
        sub_graph_id=sub_graph_id,
        parent_node_id=parent.node_id,
        position_x=0.0,
        position_y=0.0,
        position_z=0.0,
    )
    edge = SimpleNamespace(
        edge_id=uuid4(),
        sub_graph_id=sub_graph_id,
        from_node_id=parent.node_id,
        to_node_id=reference_node.node_id,
        label=EdgeType.PROPERTY_REFERENCE.value,
    )
    reference = SimpleNamespace(
        image_url="https://assets.example/reference.png",
        mime_type="image/png",
        width=2,
        height=3,
    )

    snapshot = repository.build_snapshot_data(
        version=1,
        nodes=[parent, reference_node],
        edges=[edge],
        reference_by_node_id={reference_node.node_id: reference},
    )

    sub_graph = snapshot["sub_graphs"][0]
    reference_snapshot = next(
        node for node in sub_graph["nodes"] if node["type"] == NodeType.REFERENCE.value
    )
    edge_snapshot = sub_graph["edges"][0]
    assert reference_snapshot["data"] == {
        "reference_url": reference.image_url,
        "mime_type": "image/png",
        "width": 2,
        "height": 3,
    }
    assert edge_snapshot == {
        "edge_id": str(edge.edge_id),
        "from_node_id": str(parent.node_id),
        "to_node_id": str(reference_node.node_id),
        "label": EdgeType.PROPERTY_REFERENCE.value,
        "used_in_generation": True,
    }


def test_generic_node_create_and_text_update_reject_reference_policy():
    room_id = uuid4()
    db = Mock()
    service = GraphInteractionService(db, minio_asset_storage=Mock())
    repository = Mock()
    service.graph_repository = repository

    with pytest.raises(ValueError, match="POST /api/references/generate"):
        asyncio.run(
            service._handle_node_save(
                room_id=room_id,
                user_id=None,
                payload={
                    "job_id": str(uuid4()),
                    "node_text": "invalid",
                    "node_type": NodeType.REFERENCE.value,
                    "position": [0, 0, 0],
                },
            )
        )
    repository.create_node.assert_not_called()

    reference_node = SimpleNamespace(
        node_id=uuid4(),
        node_type=NodeType.REFERENCE,
        node_text="reference.png",
    )
    repository.find_active_node_by_id.return_value = reference_node
    with pytest.raises(ValueError, match="reference workflow"):
        service.update_node_text(
            room_id=room_id,
            user_id=None,
            node_id=reference_node.node_id,
            text="changed",
        )
    repository.update_node_text.assert_not_called()


def test_direct_reference_node_delete_uses_one_snapshot_event_and_cleans_image():
    room_id = uuid4()
    reference_node = SimpleNamespace(node_id=uuid4(), node_type=NodeType.REFERENCE)
    edge = SimpleNamespace(edge_id=uuid4())
    reference = SimpleNamespace(
        reference_id=uuid4(),
        image_url="http://localhost:9000/nodexr-2d-assets/references/ref.png",
    )
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    storage = Mock()
    service = GraphInteractionService(db, minio_asset_storage=storage)
    repository = Mock()
    repository.find_active_node_by_id.return_value = reference_node
    repository.find_active_child_nodes_recursively.return_value = []
    repository.find_active_edges_connected_to_nodes.return_value = [edge]
    repository.find_reference_records_by_node_ids.return_value = [reference]
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    service.graph_repository = repository

    service.delete_node(
        room_id=room_id,
        user_id=None,
        node_id=reference_node.node_id,
    )

    repository.delete_references.assert_called_once_with(
        db=db,
        references=[reference],
    )
    repository.soft_delete_nodes.assert_called_once()
    repository.soft_delete_edges.assert_called_once()
    repository.create_graph_snapshot_from_current_graph.assert_called_once()
    repository.create_graph_event.assert_called_once()
    db.commit.assert_called_once()
    storage.delete_reference_image.assert_called_once_with(
        image_url=reference.image_url,
    )


def test_parent_node_delete_cleans_descendant_references_in_one_mutation():
    room_id = uuid4()
    parent = SimpleNamespace(node_id=uuid4(), node_type=NodeType.PROPERTY)
    first_reference_node = SimpleNamespace(node_id=uuid4(), node_type=NodeType.REFERENCE)
    second_reference_node = SimpleNamespace(node_id=uuid4(), node_type=NodeType.REFERENCE)
    references = [
        SimpleNamespace(reference_id=uuid4(), image_url="https://assets/ref-1.png"),
        SimpleNamespace(reference_id=uuid4(), image_url="https://assets/ref-2.png"),
    ]
    edges = [SimpleNamespace(edge_id=uuid4()), SimpleNamespace(edge_id=uuid4())]
    repository = Mock()
    repository.find_active_node_by_id.return_value = parent
    repository.find_active_child_nodes_recursively.return_value = [
        first_reference_node,
        second_reference_node,
    ]
    repository.find_active_edges_connected_to_nodes.return_value = edges
    repository.find_reference_records_by_node_ids.return_value = references
    repository.create_graph_snapshot_from_current_graph.return_value = SimpleNamespace(
        graph_snapshot_id=uuid4()
    )
    storage = Mock()
    service = GraphInteractionService(Mock(), minio_asset_storage=storage)
    service.graph_repository = repository

    service.delete_node(
        room_id=room_id,
        user_id=None,
        node_id=parent.node_id,
    )

    assert repository.soft_delete_nodes.call_args.kwargs["nodes"] == [
        parent,
        first_reference_node,
        second_reference_node,
    ]
    repository.delete_references.assert_called_once()
    repository.create_graph_snapshot_from_current_graph.assert_called_once()
    repository.create_graph_event.assert_called_once()
    assert storage.delete_reference_image.call_count == 2


def test_property_reference_edge_delete_deletes_target_without_recursive_side_effects():
    room_id = uuid4()
    parent = SimpleNamespace(node_id=uuid4(), node_type=NodeType.PROPERTY)
    target = SimpleNamespace(node_id=uuid4(), node_type=NodeType.REFERENCE)
    edge = SimpleNamespace(
        edge_id=uuid4(),
        from_node_id=parent.node_id,
        to_node_id=target.node_id,
        label=EdgeType.PROPERTY_REFERENCE.value,
    )
    reference = SimpleNamespace(reference_id=uuid4(), image_url="https://assets/ref.png")
    snapshot = SimpleNamespace(graph_snapshot_id=uuid4())
    db = Mock()
    storage = Mock()
    service = GraphInteractionService(db, minio_asset_storage=storage)
    repository = Mock()
    repository.find_active_edge_by_id.return_value = edge
    repository.find_active_node_by_id.side_effect = [parent, target]
    repository.find_active_child_nodes_recursively.return_value = []
    repository.find_active_edges_connected_to_nodes.return_value = [edge]
    repository.find_reference_records_by_node_ids.return_value = [reference]
    repository.create_graph_snapshot_from_current_graph.return_value = snapshot
    service.graph_repository = repository

    asyncio.run(
        service._handle_edge_delete(
            room_id=room_id,
            user_id=None,
            payload={"edge_id": str(edge.edge_id)},
        )
    )

    repository.soft_delete_edge.assert_not_called()
    repository.soft_delete_edges.assert_called_once_with(
        edges=[edge],
        deleted_at=repository.soft_delete_edges.call_args.kwargs["deleted_at"],
    )
    repository.create_graph_snapshot_from_current_graph.assert_called_once()
    repository.create_graph_event.assert_called_once()
    assert (
        repository.create_graph_event.call_args.kwargs["event_type"]
        == GraphEventType.EDGE_DELETE
    )
    db.commit.assert_called_once()
    storage.delete_reference_image.assert_called_once_with(image_url=reference.image_url)


@pytest.mark.parametrize(
    "edge_label",
    ["HAS_DETAIL", EdgeType.PROPERTY_REFERENCE.value],
)
def test_normal_edge_delete_does_not_delete_connected_node_or_reference(edge_label):
    room_id = uuid4()
    parent = SimpleNamespace(node_id=uuid4(), node_type=NodeType.PROPERTY, sub_graph_id=uuid4())
    target = SimpleNamespace(node_id=uuid4(), node_type=NodeType.PROPERTY, sub_graph_id=parent.sub_graph_id)
    edge = SimpleNamespace(
        edge_id=uuid4(),
        from_node_id=parent.node_id,
        to_node_id=target.node_id,
        label=edge_label,
    )
    repository = Mock()
    repository.find_active_edge_by_id.return_value = edge
    repository.find_active_node_by_id.side_effect = [parent, target]
    repository.create_graph_snapshot_from_current_graph.return_value = SimpleNamespace(
        graph_snapshot_id=uuid4()
    )
    service = GraphInteractionService(Mock(), minio_asset_storage=Mock())
    service.graph_repository = repository

    asyncio.run(
        service._handle_edge_delete(
            room_id=room_id,
            user_id=None,
            payload={"edge_id": str(edge.edge_id)},
        )
    )

    repository.soft_delete_edge.assert_called_once()
    repository.soft_delete_nodes.assert_not_called()
    repository.delete_references.assert_not_called()


def test_reference_storage_deletes_only_urls_managed_by_configured_minio():
    manager = Mock()
    storage = MinioAssetStorage(minio_manager=manager)
    managed_url = (
        f"{settings.MINIO_PUBLIC_BASE_URL.rstrip('/')}"
        f"/{settings.MINIO_BUCKET_2D_ASSETS}/references/room-id/reference.png"
    )

    assert storage.delete_reference_image(image_url=managed_url) is True
    manager.remove_object.assert_called_once_with(
        bucket_name=settings.MINIO_BUCKET_2D_ASSETS,
        object_name="references/room-id/reference.png",
    )

    manager.reset_mock()
    assert (
        storage.delete_reference_image(
            image_url="https://external.example/reference.png",
        )
        is False
    )
    manager.remove_object.assert_not_called()
