import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.api import generation
from app.repository.graph_repository import GraphRepository
from app.schema.generation.request import (
    Connection2D,
    Generate2DFeatureRequest,
    Generate2DGraphRequest,
)
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    GeneratedImageBinary,
    StoredObjectInfo,
)
from app.model.enum import GraphEventType
from app.service.history.history_service import HistoryService
from app.service.generation.image_2d_asset_generation_service import (
    Image2DAssetGenerationService,
)
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)
from app.service.generation.prompt_context_builder import PromptContextBuilder


def test_asset_generation_persists_generated_image_and_commits():
    room_id = uuid4()
    graph_snapshot_id = uuid4()
    asset_id = uuid4()
    db = Mock()
    image_client = Mock()
    image_client.generate_image = AsyncMock(
        return_value=GeneratedImageBinary(
            image_bytes=b"image",
            mime_type="image/png",
            width=512,
            height=512,
        ),
    )
    storage = Mock()
    storage.upload_generated_image.return_value = StoredObjectInfo(
        bucket_name="2d-assets",
        object_name="2d/image.png",
        public_url="https://assets.example/2d/image.png",
    )
    repository = Mock()
    repository.create_2d_asset.return_value = SimpleNamespace(asset_id=asset_id)
    graph_repository = Mock()
    updated_snapshot_id = uuid4()
    graph_repository.create_graph_snapshot_from_input_snapshot.return_value = (
        SimpleNamespace(graph_snapshot_id=updated_snapshot_id)
    )
    service = Image2DAssetGenerationService(
        db=db,
        gemini_image_client=image_client,
        minio_asset_storage=storage,
        asset_repository=repository,
        graph_repository=graph_repository,
    )

    result = asyncio.run(
        service.generate(
            room_id=room_id,
            user_id=uuid4(),
            graph_snapshot_id=graph_snapshot_id,
            prompt_text="a clean concept image",
        )
    )

    repository.create_2d_asset.assert_called_once_with(
        db=db,
        room_id=room_id,
        graph_snapshot_id=None,
        file_url="https://assets.example/2d/image.png",
        prompt_text="a clean concept image",
    )
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    storage.delete_uploaded_image.assert_not_called()
    assert result.asset_id == asset_id
    assert result.width == 512
    core_2d_image = (
        graph_repository.create_graph_snapshot_from_input_snapshot.call_args.kwargs[
            "core_2d_image"
        ]
    )
    assert core_2d_image["asset_id"] == str(asset_id)
    assert core_2d_image["image_url"] == "https://assets.example/2d/image.png"
    repository.update_graph_snapshot.assert_called_once_with(
        db=db,
        asset=repository.create_2d_asset.return_value,
        graph_snapshot_id=updated_snapshot_id,
    )
    graph_repository.create_graph_snapshot_from_current_graph.assert_not_called()
    assert (
        graph_repository.create_graph_event.call_args.kwargs["event_type"]
        == GraphEventType.GENERATE_2D
    )
    assert (
        graph_repository.create_graph_event.call_args.kwargs["graph_snapshot_id"]
        == updated_snapshot_id
    )


def test_graph_generation_request_freezes_prompt_context_in_input_snapshot(
    monkeypatch,
):
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    connection = Connection2D(part_node_id=uuid4(), node_id=uuid4())
    request = Generate2DGraphRequest(
        room_id=room_id,
        user_id=user_id,
        job_id=job_id,
        connections=[connection],
    )
    input_snapshot_id = uuid4()
    graph_repository = Mock()
    graph_repository.create_graph_snapshot_from_current_graph.return_value = (
        SimpleNamespace(
            graph_snapshot_id=input_snapshot_id,
            version=5,
        )
    )
    snapshot_context = {
        "topic": "frozen topic",
        "features": ["frozen feature"],
        "connections": [connection.model_dump(mode="json")],
    }
    context_builder = Mock()
    context_builder.capture_snapshot_context.return_value = snapshot_context
    task_service = Mock()
    task_service.generate_from_graph = AsyncMock()
    monkeypatch.setattr(generation, "GraphRepository", Mock(return_value=graph_repository))
    monkeypatch.setattr(generation, "prompt_context_builder", context_builder)
    monkeypatch.setattr(
        generation,
        "image_2d_generation_task_service",
        task_service,
    )
    db = Mock()
    background_tasks = BackgroundTasks()

    result = asyncio.run(
        generation.request_2d_generate(
            request=request,
            background_tasks=background_tasks,
            db=db,
        )
    )

    assert result["isSuccess"] is True
    context_builder.capture_snapshot_context.assert_called_once_with(
        db=db,
        room_id=room_id,
        connections=[connection],
    )
    graph_repository.create_graph_snapshot_from_current_graph.assert_called_once_with(
        db=db,
        room_id=room_id,
        generation_context=snapshot_context,
    )
    db.commit.assert_called_once()
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is task_service.generate_from_graph
    assert task.kwargs["job_id"] == job_id
    assert task.kwargs["graph_snapshot_id"] == input_snapshot_id
    assert result["result"] == {"job_id": str(job_id)}


def test_feature_2d_request_returns_job_id_and_passes_it_to_background_task(
    monkeypatch,
):
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    request = Generate2DFeatureRequest(
        room_id=room_id,
        user_id=user_id,
        job_id=job_id,
    )
    task_service = Mock()
    task_service.generate_from_features = AsyncMock()
    monkeypatch.setattr(
        generation,
        "image_2d_generation_task_service",
        task_service,
    )
    background_tasks = BackgroundTasks()

    result = asyncio.run(
        generation.request_2d_generate_by_feature(
            request=request,
            background_tasks=background_tasks,
        )
    )

    assert result["result"] == {"job_id": str(job_id)}
    task = background_tasks.tasks[0]
    assert task.func is task_service.generate_from_features
    assert task.kwargs == {
        "room_id": room_id,
        "user_id": user_id,
        "job_id": job_id,
    }


def test_result_snapshot_copies_input_graph_and_replaces_only_core_image():
    room_id = uuid4()
    input_snapshot_id = uuid4()
    sub_graph_id = uuid4()
    node_id = uuid4()
    input_data = {
        "graph_version": 4,
        "core_2d_image": {"asset_id": str(uuid4()), "image_url": "old"},
        "sub_graphs": [
            {
                "sub_graph_id": str(sub_graph_id),
                "root_node_id": str(node_id),
                "nodes": [{"node_id": str(node_id), "node_text": "frozen"}],
                "edges": [],
            }
        ],
        "_generation_context": {
            "topic": "frozen topic",
            "features": ["frozen feature"],
            "connections": [],
        },
    }
    input_snapshot = SimpleNamespace(snapshot_data=json.dumps(input_data))
    db = Mock()
    repository = GraphRepository()
    repository.find_graph_snapshot_by_id = Mock(return_value=input_snapshot)
    repository.get_next_graph_version = Mock(return_value=9)
    new_core_image = {
        "asset_id": str(uuid4()),
        "image_url": "new",
        "mime_type": "image/png",
        "width": 4,
        "height": 3,
    }

    result = repository.create_graph_snapshot_from_input_snapshot(
        db=db,
        room_id=room_id,
        input_graph_snapshot_id=input_snapshot_id,
        core_2d_image=new_core_image,
    )
    result_data = json.loads(result.snapshot_data)

    assert result_data["graph_version"] == 9
    assert result_data["core_2d_image"] == new_core_image
    assert result_data["sub_graphs"] == input_data["sub_graphs"]
    assert result_data["_generation_context"] == input_data["_generation_context"]
    assert input_data["core_2d_image"]["image_url"] == "old"
    db.add.assert_called_once_with(result)
    db.flush.assert_called_once()


def test_prompt_context_is_built_only_from_generation_input_snapshot():
    room_id = uuid4()
    input_snapshot_id = uuid4()
    sub_graph_id = uuid4()
    root_id = uuid4()
    selected_id = uuid4()
    part_id = uuid4()
    connection = Connection2D(part_node_id=part_id, node_id=selected_id)
    snapshot_data = {
        "graph_version": 3,
        "core_2d_image": None,
        "_generation_context": {
            "topic": "snapshot topic",
            "features": ["snapshot feature"],
            "connections": [connection.model_dump(mode="json")],
        },
        "sub_graphs": [
            {
                "sub_graph_id": str(sub_graph_id),
                "root_node_id": str(root_id),
                "nodes": [
                    {
                        "node_id": str(root_id),
                        "node_text": "root from snapshot",
                        "parent_node_id": None,
                    },
                    {
                        "node_id": str(selected_id),
                        "node_text": "selected from snapshot",
                        "parent_node_id": str(root_id),
                    },
                    {
                        "node_id": str(part_id),
                        "node_text": "part from snapshot",
                        "parent_node_id": None,
                    },
                ],
                "edges": [],
            }
        ],
    }
    graph_repository = Mock()
    graph_repository.find_graph_snapshot_by_id.return_value = SimpleNamespace()
    graph_repository.load_snapshot_data.return_value = snapshot_data
    room_repository = Mock()
    feature_repository = Mock()
    builder = PromptContextBuilder(
        graph_repository=graph_repository,
        room_repository=room_repository,
        feature_repository=feature_repository,
    )

    context = builder.build_from_snapshot(
        db=Mock(),
        room_id=room_id,
        graph_snapshot_id=input_snapshot_id,
        expected_connections=[connection],
    )

    assert context.topic == "snapshot topic"
    assert context.features == ["snapshot feature"]
    prompt_connection = context.grouped_connections[sub_graph_id][0]
    assert prompt_connection.part_node_text == "part from snapshot"
    assert prompt_connection.node_chain_texts == [
        "root from snapshot",
        "selected from snapshot",
    ]
    room_repository.find_room_topic.assert_not_called()
    feature_repository.find_feature_texts.assert_not_called()
    graph_repository.find_active_node_by_id.assert_not_called()
    graph_repository.find_active_ancestor_chain_to_root.assert_not_called()


def test_asset_generation_removes_uploaded_object_when_db_persistence_fails():
    db = Mock()
    image_client = Mock()
    image_client.generate_image = AsyncMock(
        return_value=GeneratedImageBinary(
            image_bytes=b"image",
            mime_type="image/png",
        ),
    )
    storage = Mock()
    storage.upload_generated_image.return_value = StoredObjectInfo(
        bucket_name="2d-assets",
        object_name="2d/orphan.png",
        public_url="https://assets.example/2d/orphan.png",
    )
    repository = Mock()
    repository.create_2d_asset.side_effect = RuntimeError("database failed")
    graph_repository = Mock()
    service = Image2DAssetGenerationService(
        db=db,
        gemini_image_client=image_client,
        minio_asset_storage=storage,
        asset_repository=repository,
        graph_repository=graph_repository,
    )

    with pytest.raises(RuntimeError, match="database failed"):
        asyncio.run(
            service.generate(
                room_id=uuid4(),
                user_id=uuid4(),
                graph_snapshot_id=None,
                prompt_text="prompt",
            )
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    storage.delete_uploaded_image.assert_called_once_with(
        bucket_name="2d-assets",
        object_name="2d/orphan.png",
    )


def test_background_task_sends_generated_event_and_closes_session():
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    asset_id = uuid4()
    db = Mock()
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock(return_value=True)
    service = Image2DGenerationTaskService(
        session_factory=Mock(return_value=db),
        ws_manager=ws_manager,
    )

    async def generation_call(_db):
        assert _db is db
        return Generated2DAssetResult(
            asset_id=asset_id,
            mime_type="image/png",
            width=1024,
            height=1024,
            img_url="https://assets.example/generated.png",
        )

    asyncio.run(
        service._run(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            graph_snapshot_id=None,
            generation_call=generation_call,
        )
    )

    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message["event_type"] == "2D_GENERATED"
    assert message["job_id"] == str(job_id)
    assert message["payload"]["asset_id"] == str(asset_id)
    db.close.assert_called_once()


def test_background_task_does_not_send_success_event_when_generation_fails():
    db = Mock()
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock()
    service = Image2DGenerationTaskService(
        session_factory=Mock(return_value=db),
        ws_manager=ws_manager,
    )

    async def generation_call(_db):
        raise RuntimeError("generation failed")

    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    asyncio.run(
        service._run(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            graph_snapshot_id=None,
            generation_call=generation_call,
        )
    )

    db.rollback.assert_called_once()
    db.close.assert_called_once()
    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message["event_type"] == "ERROR"
    assert message["job_id"] == str(job_id)
    assert message["payload"]["failed_event_type"] == "2D_GENERATED"


def test_generate_2d_snapshot_is_included_in_graph_history():
    room_id = uuid4()
    snapshot_id = uuid4()
    asset_id = uuid4()
    repository = Mock()
    repository.find_history_snapshots_by_room_id.return_value = [
        (
            SimpleNamespace(event_type=GraphEventType.GENERATE_2D),
            SimpleNamespace(
                graph_snapshot_id=snapshot_id,
                version=7,
                snapshot_data={
                    "graph_version": 7,
                    "_generation_context": {
                        "topic": "internal",
                        "features": [],
                        "connections": [],
                    },
                    "core_2d_image": {
                        "asset_id": str(asset_id),
                        "image_url": "https://assets.example/generated.png",
                        "mime_type": "image/png",
                        "width": 1024,
                        "height": 1024,
                    },
                    "sub_graphs": [],
                },
            ),
        )
    ]
    service = HistoryService(graph_repository=repository)

    result = service.get_graph_history(
        db=Mock(),
        room_id=room_id,
    )

    assert len(result["history"]) == 1
    assert result["history"][0]["graph_version"] == 7
    assert result["history"][0]["core_2d_image"]["asset_id"] == str(asset_id)
    assert "_generation_context" not in result["history"][0]
