import asyncio
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api import generation
from app.db.session import get_db
from app.model.enum import AssetType
from app.repository.asset_repository import AssetRepository
from app.schema.generation.generation_result import (
    Generated3DAssetResult,
    Generated3DModelBinary,
    StoredObjectInfo,
)
from app.schema.generation.request import Generate3DRequest
from app.service.generation.meshy_client import (
    MeshyClient,
    MeshyClientError,
    MeshyTaskFailedError,
    MeshyTaskTimeoutError,
)
from app.service.generation.minio_asset_storage import MinioAssetStorage
from app.service.generation.model_3d_generation_service import (
    Model3DGenerationService,
)


def make_image(*, image_format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 3), color="blue").save(buffer, format=image_format)
    return buffer.getvalue()


def make_glb() -> bytes:
    return b"glTF" + b"\x02\x00\x00\x00" + b"\x0c\x00\x00\x00"


def configured_service(*, room_id, source_asset_id):
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    source_asset = SimpleNamespace(
        asset_id=source_asset_id,
        room_id=room_id,
        graph_snapshot_id=uuid4(),
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    asset_repository.find_asset_by_id.return_value = source_asset
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    service = Model3DGenerationService(
        room_repository=room_repository,
        asset_repository=asset_repository,
        minio_asset_storage=storage,
        meshy_client=Mock(),
        ws_manager=Mock(),
    )
    return service, room_repository, asset_repository, storage, source_asset


def test_3d_router_returns_exact_202_and_registers_background_task(monkeypatch):
    app = FastAPI()
    app.include_router(generation.router, prefix="/api")
    db = Mock()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    room_id = uuid4()
    source_asset_id = uuid4()
    service = Mock()
    service.run = AsyncMock()
    monkeypatch.setattr(generation, "model_3d_generation_service", service)

    response = TestClient(app).post(
        "/api/3d/generate",
        json={
            "room_id": str(room_id),
            "asset_id": str(source_asset_id),
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "isSuccess": True,
        "code": "3D200",
        "message": "3D 생성 요청 성공",
        "result": {},
    }
    service.validate_request.assert_called_once()
    request = service.validate_request.call_args.kwargs["request"]
    assert request == Generate3DRequest(
        room_id=room_id,
        asset_id=source_asset_id,
    )
    service.run.assert_awaited_once_with(
        room_id=room_id,
        source_asset_id=source_asset_id,
    )


def test_3d_request_openapi_contract_is_json_with_202_response():
    app = FastAPI()
    app.include_router(generation.router, prefix="/api")
    operation = app.openapi()["paths"]["/api/3d/generate"]["post"]

    assert "application/json" in operation["requestBody"]["content"]
    assert "202" in operation["responses"]


def test_3d_validation_accepts_active_room_managed_2d_asset():
    room_id = uuid4()
    source_asset_id = uuid4()
    service, _, _, _, source_asset = configured_service(
        room_id=room_id,
        source_asset_id=source_asset_id,
    )

    result = service.validate_request(
        db=Mock(),
        request=Generate3DRequest(room_id=room_id, asset_id=source_asset_id),
    )

    assert result is source_asset


@pytest.mark.parametrize(
    "asset",
    [
        None,
        SimpleNamespace(
            room_id=uuid4(),
            asset_type=AssetType.IMAGE_2D,
            file_url="https://assets.example/2d/source.png",
        ),
        SimpleNamespace(
            room_id=None,
            asset_type=AssetType.MODEL_3D,
            file_url="https://assets.example/2d/source.png",
        ),
        SimpleNamespace(
            room_id=None,
            asset_type=AssetType.IMAGE_2D,
            file_url="",
        ),
        SimpleNamespace(
            room_id=None,
            asset_type=AssetType.IMAGE_2D,
            file_url="https://assets.example/2d/source.png",
            deleted_at=object(),
        ),
    ],
)
def test_3d_validation_rejects_invalid_source_asset(asset):
    room_id = uuid4()
    source_asset_id = uuid4()
    service, _, asset_repository, storage, _ = configured_service(
        room_id=room_id,
        source_asset_id=source_asset_id,
    )
    if asset is not None and asset.room_id is None:
        asset.room_id = room_id
    asset_repository.find_asset_by_id.return_value = asset
    if asset is not None and not asset.file_url:
        storage.validate_generated_image_url.return_value = False

    with pytest.raises(Exception):
        service.validate_request(
            db=Mock(),
            request=Generate3DRequest(
                room_id=room_id,
                asset_id=source_asset_id,
            ),
        )


def test_meshy_client_sends_data_uri_polls_and_downloads_glb_without_key_leak():
    requests: list[httpx.Request] = []
    poll_count = 0
    source_image = make_image(image_format="JPEG")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        requests.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload["target_formats"] == ["glb"]
            assert payload["image_url"].startswith("data:image/jpeg;base64,")
            assert request.headers["Authorization"] == "Bearer test-key"
            return httpx.Response(200, json={"result": "task-1"})
        if request.url.host == "api.meshy.test":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(
                    200,
                    json={"status": "PENDING", "progress": 0},
                )
            return httpx.Response(
                200,
                json={
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "model_urls": {"glb": "https://cdn.meshy.test/model.glb"},
                },
            )
        assert "Authorization" not in request.headers
        return httpx.Response(
            200,
            content=make_glb(),
            headers={"Content-Type": "model/gltf-binary"},
        )

    client = MeshyClient(
        api_key="test-key",
        base_url="https://api.meshy.test",
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        client.generate_glb(
            image_bytes=source_image,
            mime_type="image/jpeg",
        )
    )

    assert result.task_id == "task-1"
    assert result.model_bytes == make_glb()
    assert [request.method for request in requests] == ["POST", "GET", "GET", "GET"]


@pytest.mark.parametrize("status", ["FAILED", "CANCELED"])
def test_meshy_client_rejects_failed_terminal_status(status):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"result": "task-failed"})
        return httpx.Response(
            200,
            json={
                "status": status,
                "task_error": {"message": "generation failed"},
            },
        )

    client = MeshyClient(
        api_key="test-key",
        base_url="https://api.meshy.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MeshyTaskFailedError, match=status):
        asyncio.run(
            client.generate_glb(
                image_bytes=make_image(),
                mime_type="image/png",
            )
        )


def test_meshy_client_stops_polling_at_timeout():
    current_time = [0.0]

    async def advance_time(delay: float) -> None:
        current_time[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"result": "task-timeout"})
        return httpx.Response(200, json={"status": "IN_PROGRESS", "progress": 50})

    client = MeshyClient(
        api_key="test-key",
        base_url="https://api.meshy.test",
        poll_interval_seconds=0.6,
        poll_timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
        sleep=advance_time,
        monotonic=lambda: current_time[0],
    )

    with pytest.raises(MeshyTaskTimeoutError):
        asyncio.run(
            client.generate_glb(
                image_bytes=make_image(),
                mime_type="image/png",
            )
        )


def test_meshy_client_rejects_success_without_glb_url():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"result": "task-no-glb"})
        return httpx.Response(
            200,
            json={"status": "SUCCEEDED", "model_urls": {}},
        )

    client = MeshyClient(
        api_key="test-key",
        base_url="https://api.meshy.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MeshyClientError, match="GLB URL"):
        asyncio.run(
            client.generate_glb(
                image_bytes=make_image(),
                mime_type="image/png",
            )
        )


@pytest.mark.parametrize(
    ("mime_type", "image_bytes"),
    [
        ("image/webp", b"image"),
        ("image/png", b""),
    ],
)
def test_meshy_client_rejects_unsupported_or_empty_input(mime_type, image_bytes):
    client = MeshyClient(api_key="test-key")

    with pytest.raises(MeshyClientError):
        asyncio.run(
            client.generate_glb(
                image_bytes=image_bytes,
                mime_type=mime_type,
            )
        )


def test_3d_generation_uses_separate_sessions_and_persists_new_asset():
    room_id = uuid4()
    source_asset_id = uuid4()
    graph_snapshot_id = uuid4()
    generated_asset_id = uuid4()
    lookup_db = Mock()
    persistence_db = Mock()
    session_factory = Mock(side_effect=[lookup_db, persistence_db])
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    source_asset = SimpleNamespace(
        asset_id=source_asset_id,
        room_id=room_id,
        graph_snapshot_id=graph_snapshot_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    asset_repository.find_asset_by_id.return_value = source_asset
    asset_repository.create_3d_asset.return_value = SimpleNamespace(
        asset_id=generated_asset_id
    )
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = make_image()
    storage.upload_generated_model.return_value = StoredObjectInfo(
        bucket_name="nodexr-2d-assets",
        object_name="3d/room/source/model.glb",
        public_url="https://assets.example/3d/model.glb",
    )
    meshy_client = Mock()
    meshy_client.generate_glb = AsyncMock(
        return_value=Generated3DModelBinary(
            task_id="task-1",
            model_bytes=make_glb(),
        )
    )
    service = Model3DGenerationService(
        session_factory=session_factory,
        room_repository=room_repository,
        asset_repository=asset_repository,
        minio_asset_storage=storage,
        meshy_client=meshy_client,
        ws_manager=Mock(),
    )

    result = asyncio.run(
        service.generate(room_id=room_id, source_asset_id=source_asset_id)
    )

    assert session_factory.call_count == 2
    lookup_db.close.assert_called_once()
    persistence_db.close.assert_called_once()
    persistence_db.commit.assert_called_once()
    meshy_client.generate_glb.assert_awaited_once_with(
        image_bytes=make_image(),
        mime_type="image/png",
    )
    storage.upload_generated_model.assert_called_once_with(
        room_id=room_id,
        source_asset_id=source_asset_id,
        model_bytes=make_glb(),
    )
    asset_repository.create_3d_asset.assert_called_once_with(
        db=persistence_db,
        room_id=room_id,
        graph_snapshot_id=graph_snapshot_id,
        file_url="https://assets.example/3d/model.glb",
    )
    assert result.asset_id == generated_asset_id
    assert result.mime_type == "model/gltf-binary"
    assert result.model_url == "https://assets.example/3d/model.glb"
    assert generated_asset_id != source_asset_id


def test_3d_generation_removes_minio_object_when_db_fails():
    room_id = uuid4()
    source_asset_id = uuid4()
    lookup_db = Mock()
    persistence_db = Mock()
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        graph_snapshot_id=None,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    asset_repository.create_3d_asset.side_effect = RuntimeError("database failed")
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = make_image()
    stored = StoredObjectInfo(
        bucket_name="nodexr-2d-assets",
        object_name="3d/orphan.glb",
        public_url="https://assets.example/3d/orphan.glb",
    )
    storage.upload_generated_model.return_value = stored
    meshy_client = Mock()
    meshy_client.generate_glb = AsyncMock(
        return_value=Generated3DModelBinary(
            task_id="task-1",
            model_bytes=make_glb(),
        )
    )
    service = Model3DGenerationService(
        session_factory=Mock(side_effect=[lookup_db, persistence_db]),
        room_repository=room_repository,
        asset_repository=asset_repository,
        minio_asset_storage=storage,
        meshy_client=meshy_client,
    )

    with pytest.raises(RuntimeError, match="database failed"):
        asyncio.run(
            service.generate(room_id=room_id, source_asset_id=source_asset_id)
        )

    persistence_db.rollback.assert_called_once()
    persistence_db.commit.assert_not_called()
    storage.delete_uploaded_model.assert_called_once_with(
        bucket_name=stored.bucket_name,
        object_name=stored.object_name,
    )


def test_3d_cleanup_failure_does_not_replace_database_error():
    room_id = uuid4()
    source_asset_id = uuid4()
    lookup_db = Mock()
    persistence_db = Mock()
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        graph_snapshot_id=None,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    asset_repository.create_3d_asset.side_effect = RuntimeError("database failed")
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = make_image()
    storage.upload_generated_model.return_value = StoredObjectInfo(
        bucket_name="nodexr-2d-assets",
        object_name="3d/orphan.glb",
        public_url="https://assets.example/3d/orphan.glb",
    )
    storage.delete_uploaded_model.side_effect = RuntimeError("cleanup failed")
    meshy_client = Mock()
    meshy_client.generate_glb = AsyncMock(
        return_value=Generated3DModelBinary(
            task_id="task-1",
            model_bytes=make_glb(),
        )
    )
    service = Model3DGenerationService(
        session_factory=Mock(side_effect=[lookup_db, persistence_db]),
        room_repository=room_repository,
        asset_repository=asset_repository,
        minio_asset_storage=storage,
        meshy_client=meshy_client,
    )

    with pytest.raises(RuntimeError, match="database failed"):
        asyncio.run(
            service.generate(room_id=room_id, source_asset_id=source_asset_id)
        )

    persistence_db.rollback.assert_called_once()
    storage.delete_uploaded_model.assert_called_once()


def test_3d_success_broadcasts_exact_event_after_generate_returns():
    room_id = uuid4()
    result = Generated3DAssetResult(
        asset_id=uuid4(),
        mime_type="model/gltf-binary",
        model_url="https://assets.example/3d/model.glb",
    )
    ws_manager = Mock()
    ws_manager.broadcast_to_room = AsyncMock(return_value=2)
    service = Model3DGenerationService(ws_manager=ws_manager)
    service.generate = AsyncMock(return_value=result)

    asyncio.run(service.run(room_id=room_id, source_asset_id=uuid4()))

    ws_manager.broadcast_to_room.assert_awaited_once_with(
        room_id=room_id,
        message={
            "event_type": "3D_GENERATED",
            "room_id": str(room_id),
            "payload": {
                "asset_id": str(result.asset_id),
                "mime_type": "model/gltf-binary",
                "model_url": "https://assets.example/3d/model.glb",
            },
        },
    )


def test_3d_failure_does_not_broadcast_success_event():
    ws_manager = Mock()
    ws_manager.broadcast_to_room = AsyncMock()
    service = Model3DGenerationService(ws_manager=ws_manager)
    service.generate = AsyncMock(side_effect=RuntimeError("generation failed"))

    asyncio.run(service.run(room_id=uuid4(), source_asset_id=uuid4()))

    ws_manager.broadcast_to_room.assert_not_awaited()


def test_3d_websocket_failure_does_not_retry_or_rollback_generation():
    result = Generated3DAssetResult(
        asset_id=uuid4(),
        mime_type="model/gltf-binary",
        model_url="https://assets.example/3d/model.glb",
    )
    ws_manager = Mock()
    ws_manager.broadcast_to_room = AsyncMock(side_effect=RuntimeError("ws failed"))
    service = Model3DGenerationService(ws_manager=ws_manager)
    service.generate = AsyncMock(return_value=result)

    asyncio.run(service.run(room_id=uuid4(), source_asset_id=uuid4()))

    service.generate.assert_awaited_once()
    ws_manager.broadcast_to_room.assert_awaited_once()


def test_model_storage_reuses_bucket_and_writes_glb_content_type():
    manager = Mock()
    manager.build_public_url.return_value = "https://assets.example/3d/model.glb"
    storage = MinioAssetStorage(minio_manager=manager)
    room_id = uuid4()
    source_asset_id = uuid4()

    result = storage.upload_generated_model(
        room_id=room_id,
        source_asset_id=source_asset_id,
        model_bytes=make_glb(),
    )

    upload = manager.upload_bytes.call_args.kwargs
    assert upload["bucket_name"] == "nodexr-2d-assets"
    assert upload["object_name"].startswith(f"3d/{room_id}/{source_asset_id}/")
    assert upload["object_name"].endswith(".glb")
    assert upload["content_type"] == "model/gltf-binary"
    assert result.public_url == "https://assets.example/3d/model.glb"


def test_asset_repository_creates_model_3d_row_with_minio_url():
    db = Mock()
    room_id = uuid4()
    snapshot_id = uuid4()
    repository = AssetRepository()

    asset = repository.create_3d_asset(
        db=db,
        room_id=room_id,
        graph_snapshot_id=snapshot_id,
        file_url="https://assets.example/3d/model.glb",
    )

    assert asset.room_id == room_id
    assert asset.graph_snapshot_id == snapshot_id
    assert asset.asset_type == AssetType.MODEL_3D
    assert asset.file_url == "https://assets.example/3d/model.glb"
    assert asset.prompt_text is None
    db.add.assert_called_once_with(asset)
    db.flush.assert_called_once()
