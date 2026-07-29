import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

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
    graph_repository.create_graph_snapshot_from_current_graph.return_value = (
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
        graph_snapshot_id=graph_snapshot_id,
        file_url="https://assets.example/2d/image.png",
        prompt_text="a clean concept image",
    )
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    storage.delete_uploaded_image.assert_not_called()
    assert result.asset_id == asset_id
    assert result.width == 512
    core_2d_image = (
        graph_repository.create_graph_snapshot_from_current_graph.call_args.kwargs[
            "core_2d_image"
        ]
    )
    assert core_2d_image["asset_id"] == str(asset_id)
    assert core_2d_image["image_url"] == "https://assets.example/2d/image.png"
    assert (
        graph_repository.create_graph_event.call_args.kwargs["event_type"]
        == GraphEventType.GENERATE_2D
    )
    assert (
        graph_repository.create_graph_event.call_args.kwargs["graph_snapshot_id"]
        == updated_snapshot_id
    )


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
            graph_snapshot_id=None,
            generation_call=generation_call,
        )
    )

    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message["event_type"] == "2D_GENERATED"
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

    asyncio.run(
        service._run(
            room_id=uuid4(),
            user_id=uuid4(),
            graph_snapshot_id=None,
            generation_call=generation_call,
        )
    )

    db.rollback.assert_called_once()
    db.close.assert_called_once()
    ws_manager.send_to_user.assert_not_awaited()


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
