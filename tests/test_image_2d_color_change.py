import asyncio
import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.api import generation
from app.ai.prompts.color_change_prompt import COLOR_CHANGE_PROMPT
from app.core.response.exceptions import BadRequestException, NotFoundException
from app.db.session import get_db
from app.model.enum import AssetType, GraphEventType
from app.schema.generation.color_change_request import ColorChangeMetadataRequest
from app.schema.generation.generation_result import (
    Generated2DAssetResult,
    GeneratedImageBinary,
    StoredObjectInfo,
)
from app.service.generation.gemini_image_client import GeminiImageClient
from app.service.generation.image_2d_asset_generation_service import (
    Image2DAssetGenerationService,
)
from app.service.generation.image_2d_color_change_service import (
    Image2DColorChangeService,
)
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)


def make_image(
    *,
    width: int = 4,
    height: int = 3,
    image_format: str = "PNG",
) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color="red").save(
        buffer,
        format=image_format,
    )
    return buffer.getvalue()


def configured_validation_service(
    *,
    room_id,
    asset_id,
    source_image: bytes | None = None,
):
    source_image = source_image or make_image()
    snapshot_id = uuid4()
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        asset_id=asset_id,
        room_id=room_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
        graph_snapshot_id=snapshot_id,
    )
    graph_repository = Mock()
    graph_repository.find_latest_graph_snapshot_by_room_id.return_value = (
        SimpleNamespace(graph_snapshot_id=snapshot_id)
    )
    graph_repository.find_graph_snapshot_by_id.return_value = SimpleNamespace(
        graph_snapshot_id=snapshot_id
    )
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = source_image
    image_client = Mock()
    image_client.inspect_image.side_effect = lambda *, image_bytes: (
        GeminiImageClient.inspect_image(image_bytes=image_bytes)
    )
    service = Image2DColorChangeService(
        room_repository=room_repository,
        asset_repository=asset_repository,
        graph_repository=graph_repository,
        minio_asset_storage=storage,
        gemini_image_client=image_client,
    )
    return (
        service,
        room_repository,
        asset_repository,
        graph_repository,
        storage,
        snapshot_id,
    )


def test_color_change_router_returns_exact_202_contract_and_copies_upload_bytes(
    monkeypatch,
):
    app = FastAPI()
    app.include_router(generation.router, prefix="/api")
    request_db = Mock()

    def override_db():
        yield request_db

    app.dependency_overrides[get_db] = override_db
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    source_asset_id = uuid4()
    input_snapshot_id = uuid4()
    guide_image = make_image()
    validation_service = Mock()
    validation_service.validate_request.return_value = input_snapshot_id
    task_service = Mock()
    task_service.generate_color_change = AsyncMock()
    monkeypatch.setattr(
        generation,
        "image_2d_color_change_service",
        validation_service,
    )
    monkeypatch.setattr(
        generation,
        "image_2d_generation_task_service",
        task_service,
    )

    response = TestClient(app).post(
        "/api/2d/color_change",
        data={
            "room_id": str(room_id),
            "user_id": str(user_id),
            "job_id": str(job_id),
            "asset_id": str(source_asset_id),
            "metadata": json.dumps(
                {"mime_type": "image/png", "width": 4, "height": 3}
            ),
        },
        files={"file": ("guide.png", guide_image, "image/png")},
    )

    assert response.status_code == 202
    assert response.json() == {
        "isSuccess": True,
        "code": "2D201",
        "message": "2D 색상 변경 요청 성공",
        "result": {"job_id": str(job_id)},
    }
    validation_call = validation_service.validate_request.call_args.kwargs
    assert validation_call["db"] is request_db
    assert validation_call["guide_image_bytes"] == guide_image
    task_call = task_service.generate_color_change.call_args.kwargs
    assert task_call == {
        "room_id": room_id,
        "user_id": user_id,
        "job_id": job_id,
        "source_asset_id": source_asset_id,
        "graph_snapshot_id": input_snapshot_id,
        "guide_image_bytes": guide_image,
        "metadata": ColorChangeMetadataRequest(
            mime_type="image/png",
            width=4,
            height=3,
        ),
    }
    assert "request_id" not in response.json()
    assert "asset_id" not in response.json()["result"]


def test_color_change_openapi_renders_metadata_as_text_form_field():
    app = FastAPI()
    app.include_router(generation.router, prefix="/api")
    schema = app.openapi()
    operation = schema["paths"]["/api/2d/color_change"]["post"]
    body_ref = operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]["$ref"]
    body_name = body_ref.rsplit("/", 1)[-1]
    metadata_schema = schema["components"]["schemas"][body_name]["properties"][
        "metadata"
    ]

    assert metadata_schema["type"] == "string"
    assert "contentMediaType" not in metadata_schema


@pytest.mark.parametrize(
    ("metadata", "guide_image", "content_type"),
    [
        (
            ColorChangeMetadataRequest(
                mime_type="image/jpeg",
                width=4,
                height=3,
            ),
            make_image(),
            "image/png",
        ),
        (
            ColorChangeMetadataRequest(
                mime_type="image/png",
                width=5,
                height=3,
            ),
            make_image(),
            "image/png",
        ),
        (
            ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=2,
            ),
            make_image(),
            "image/png",
        ),
        (
            ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
            b"not-an-image",
            "image/png",
        ),
        (
            ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
            b"",
            "image/png",
        ),
    ],
)
def test_color_change_rejects_invalid_guide_metadata_or_image(
    metadata,
    guide_image,
    content_type,
):
    room_id = uuid4()
    source_asset_id = uuid4()
    service, *_ = configured_validation_service(
        room_id=room_id,
        asset_id=source_asset_id,
    )

    with pytest.raises(BadRequestException):
        service._validate_guide_image(
            image_bytes=guide_image,
            metadata=metadata,
            upload_content_type=content_type,
        )


def test_color_change_metadata_rejects_non_positive_dimensions():
    with pytest.raises(ValidationError):
        ColorChangeMetadataRequest(
            mime_type="image/png",
            width=0,
            height=3,
        )


def test_color_change_validation_fixes_input_snapshot_and_checks_source_dimensions():
    room_id = uuid4()
    source_asset_id = uuid4()
    service, _, _, graph_repository, storage, snapshot_id = (
        configured_validation_service(
            room_id=room_id,
            asset_id=source_asset_id,
        )
    )
    request = SimpleNamespace(
        room_id=room_id,
        asset_id=source_asset_id,
        metadata=ColorChangeMetadataRequest(
            mime_type="image/png",
            width=4,
            height=3,
        ),
    )

    result = service.validate_request(
        db=Mock(),
        request=request,
        guide_image_bytes=make_image(),
        upload_content_type="image/png",
    )

    assert result == snapshot_id
    storage.download_generated_image.assert_called_once()
    graph_repository.find_graph_snapshot_by_id.assert_called_once()
    snapshot_lookup = graph_repository.find_graph_snapshot_by_id.call_args.kwargs
    assert snapshot_lookup["room_id"] == room_id
    assert snapshot_lookup["graph_snapshot_id"] == snapshot_id
    graph_repository.find_latest_graph_snapshot_by_room_id.assert_not_called()

    storage.download_generated_image.return_value = make_image(width=5, height=3)
    with pytest.raises(BadRequestException):
        service.validate_request(
            db=Mock(),
            request=request,
            guide_image_bytes=make_image(),
            upload_content_type="image/png",
        )


def test_color_change_rejects_missing_room_asset_wrong_room_deleted_or_non_2d():
    room_id = uuid4()
    asset_id = uuid4()
    service, room_repository, asset_repository, _, storage, _ = (
        configured_validation_service(room_id=room_id, asset_id=asset_id)
    )
    db = Mock()

    room_repository.find_room_by_id.return_value = None
    with pytest.raises(NotFoundException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)

    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository.find_asset_by_id.return_value = None
    with pytest.raises(NotFoundException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)

    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=uuid4(),
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    with pytest.raises(NotFoundException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)

    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
        deleted_at=object(),
    )
    with pytest.raises(NotFoundException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)

    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        asset_type=AssetType.MODEL_3D,
        file_url="https://assets.example/2d/source.png",
    )
    with pytest.raises(BadRequestException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)

    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://unmanaged.example/source.png",
    )
    storage.validate_generated_image_url.return_value = False
    with pytest.raises(BadRequestException):
        service._validate_entities(db=db, room_id=room_id, asset_id=asset_id)


def test_color_change_uses_separate_sessions_and_common_atomic_persistence():
    room_id = uuid4()
    source_asset_id = uuid4()
    input_snapshot_id = uuid4()
    generated_asset_id = uuid4()
    post_snapshot_id = uuid4()
    lookup_db = Mock()
    persistence_db = Mock()
    session_factory = Mock(side_effect=[lookup_db, persistence_db])
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    source_asset = SimpleNamespace(
        asset_id=source_asset_id,
        room_id=room_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
        graph_snapshot_id=input_snapshot_id,
    )
    asset_repository.find_asset_by_id.return_value = source_asset
    asset_repository.create_2d_asset.return_value = SimpleNamespace(
        asset_id=generated_asset_id
    )
    graph_repository = Mock()
    graph_repository.find_graph_snapshot_by_id.return_value = SimpleNamespace(
        graph_snapshot_id=input_snapshot_id
    )
    graph_repository.create_graph_snapshot_from_input_snapshot.return_value = (
        SimpleNamespace(graph_snapshot_id=post_snapshot_id)
    )
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = make_image()
    storage.upload_generated_image.return_value = StoredObjectInfo(
        bucket_name="2d-assets",
        object_name="2d/result.png",
        public_url="https://assets.example/2d/result.png",
    )
    image_client = Mock()
    image_client.inspect_image.side_effect = lambda *, image_bytes: (
        GeminiImageClient.inspect_image(image_bytes=image_bytes)
    )
    result_image = make_image()
    image_client.edit_image_colors = AsyncMock(
        return_value=GeneratedImageBinary(
            image_bytes=result_image,
            mime_type="image/png",
            width=4,
            height=3,
        )
    )
    service = Image2DColorChangeService(
        session_factory=session_factory,
        room_repository=room_repository,
        asset_repository=asset_repository,
        graph_repository=graph_repository,
        minio_asset_storage=storage,
        gemini_image_client=image_client,
    )

    result = asyncio.run(
        service.generate(
            room_id=room_id,
            source_asset_id=source_asset_id,
            graph_snapshot_id=input_snapshot_id,
            guide_image_bytes=make_image(),
            metadata=ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
        )
    )

    assert session_factory.call_count == 2
    lookup_db.close.assert_called_once()
    lookup_db.commit.assert_not_called()
    persistence_db.close.assert_called_once()
    persistence_db.commit.assert_called_once()
    image_client.edit_image_colors.assert_awaited_once_with(
        prompt_text=COLOR_CHANGE_PROMPT,
        source_image_bytes=make_image(),
        source_mime_type="image/png",
        guide_image_bytes=make_image(),
        guide_mime_type="image/png",
    )
    asset_repository.create_2d_asset.assert_called_once_with(
        db=persistence_db,
        room_id=room_id,
        graph_snapshot_id=None,
        file_url="https://assets.example/2d/result.png",
        prompt_text=COLOR_CHANGE_PROMPT,
    )
    graph_repository.create_graph_snapshot_from_input_snapshot.assert_called_once_with(
        db=persistence_db,
        room_id=room_id,
        input_graph_snapshot_id=input_snapshot_id,
        core_2d_image={
            "asset_id": str(generated_asset_id),
            "image_url": "https://assets.example/2d/result.png",
            "mime_type": "image/png",
            "width": 4,
            "height": 3,
        },
    )
    asset_repository.update_graph_snapshot.assert_called_once_with(
        db=persistence_db,
        asset=asset_repository.create_2d_asset.return_value,
        graph_snapshot_id=post_snapshot_id,
    )
    graph_repository.create_graph_snapshot_from_current_graph.assert_not_called()
    graph_repository.create_graph_event.assert_called_once()
    event_call = graph_repository.create_graph_event.call_args.kwargs
    assert event_call["event_type"] == GraphEventType.GENERATE_2D
    assert event_call["graph_snapshot_id"] == post_snapshot_id
    assert event_call["payload"]["source_asset_id"] == str(source_asset_id)
    assert event_call["payload"]["generated_asset_id"] == str(generated_asset_id)
    assert (
        event_call["payload"]["generated_asset_url"]
        == "https://assets.example/2d/result.png"
    )
    assert event_call["payload"]["generation_type"] == "COLOR_CHANGE"
    assert result.asset_id == generated_asset_id
    assert source_asset.file_url == "https://assets.example/2d/source.png"


def test_color_change_rejects_generated_image_with_different_aspect_ratio():
    room_id = uuid4()
    source_asset_id = uuid4()
    input_snapshot_id = uuid4()
    lookup_db = Mock()
    session_factory = Mock(return_value=lookup_db)
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    asset_repository = Mock()
    asset_repository.find_asset_by_id.return_value = SimpleNamespace(
        room_id=room_id,
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/2d/source.png",
    )
    graph_repository = Mock()
    graph_repository.find_graph_snapshot_by_id.return_value = SimpleNamespace()
    storage = Mock()
    storage.validate_generated_image_url.return_value = True
    storage.download_generated_image.return_value = make_image()
    image_client = Mock()
    image_client.inspect_image.side_effect = lambda *, image_bytes: (
        GeminiImageClient.inspect_image(image_bytes=image_bytes)
    )
    image_client.edit_image_colors = AsyncMock(
        return_value=GeneratedImageBinary(
            image_bytes=make_image(width=4, height=4),
            mime_type="image/png",
            width=4,
            height=4,
        )
    )
    service = Image2DColorChangeService(
        session_factory=session_factory,
        room_repository=room_repository,
        asset_repository=asset_repository,
        graph_repository=graph_repository,
        minio_asset_storage=storage,
        gemini_image_client=image_client,
    )

    with pytest.raises(ValueError, match="aspect ratio"):
        asyncio.run(
            service.generate(
                room_id=room_id,
                source_asset_id=source_asset_id,
                graph_snapshot_id=input_snapshot_id,
                guide_image_bytes=make_image(),
                metadata=ColorChangeMetadataRequest(
                    mime_type="image/png",
                    width=4,
                    height=3,
                ),
            )
        )

    session_factory.assert_called_once()
    storage.upload_generated_image.assert_not_called()
    asset_repository.create_2d_asset.assert_not_called()


def test_gemini_color_change_sends_prompt_source_then_guide_and_decodes_result():
    source = make_image()
    guide = make_image()
    output = make_image(width=8, height=6, image_format="JPEG")
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            inline_data=SimpleNamespace(data=output),
                        )
                    ]
                )
            )
        ]
    )
    client = GeminiImageClient.__new__(GeminiImageClient)
    client._generate_content = AsyncMock(return_value=response)

    result = asyncio.run(
        client.edit_image_colors(
            prompt_text=COLOR_CHANGE_PROMPT,
            source_image_bytes=source,
            source_mime_type="image/png",
            guide_image_bytes=guide,
            guide_mime_type="image/png",
        )
    )

    contents = client._generate_content.call_args.kwargs["contents"]
    assert contents[0] == COLOR_CHANGE_PROMPT
    assert contents[1].inline_data.data == source
    assert contents[2].inline_data.data == guide
    assert result.mime_type == "image/jpeg"
    assert result.width == 8
    assert result.height == 6


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(candidates=[]),
        SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                inline_data=SimpleNamespace(data=b"invalid"),
                            )
                        ]
                    )
                )
            ]
        ),
    ],
)
def test_gemini_color_change_rejects_missing_or_undecodable_output(response):
    client = GeminiImageClient.__new__(GeminiImageClient)
    client._generate_content = AsyncMock(return_value=response)

    with pytest.raises(ValueError):
        asyncio.run(
            client.edit_image_colors(
                prompt_text=COLOR_CHANGE_PROMPT,
                source_image_bytes=make_image(),
                source_mime_type="image/png",
                guide_image_bytes=make_image(),
                guide_mime_type="image/png",
            )
        )


def test_color_change_task_sends_exact_payload_only_to_requester_after_persistence():
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    result = Generated2DAssetResult(
        asset_id=uuid4(),
        mime_type="image/webp",
        width=1280,
        height=720,
        img_url="https://assets.example/2d/result.webp",
    )
    color_service = Mock()
    color_service.generate = AsyncMock(return_value=result)
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock(return_value=True)
    task_service = Image2DGenerationTaskService(
        ws_manager=ws_manager,
        color_change_service=color_service,
    )

    asyncio.run(
        task_service.generate_color_change(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            source_asset_id=uuid4(),
            graph_snapshot_id=uuid4(),
            guide_image_bytes=make_image(),
            metadata=ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
        )
    )

    ws_manager.send_to_user.assert_awaited_once()
    assert ws_manager.send_to_user.call_args.kwargs["user_id"] == user_id
    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message == {
        "event_type": "2D_COLOR_CHANGED",
        "room_id": str(room_id),
        "job_id": str(job_id),
        "payload": {
            "asset_id": str(result.asset_id),
            "mime_type": "image/webp",
            "width": 1280,
            "height": 720,
            "img_url": "https://assets.example/2d/result.webp",
        },
    }
    assert "request_id" not in message
    assert "source_asset_id" not in message["payload"]
    assert "graph_snapshot_id" not in message["payload"]


def test_websocket_failure_after_color_change_does_not_touch_database_session():
    color_service = Mock()
    color_service.generate = AsyncMock(
        return_value=Generated2DAssetResult(
            asset_id=uuid4(),
            mime_type="image/png",
            width=4,
            height=3,
            img_url="https://assets.example/2d/result.png",
        )
    )
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock(side_effect=RuntimeError("ws failed"))
    session_factory = Mock()
    task_service = Image2DGenerationTaskService(
        session_factory=session_factory,
        ws_manager=ws_manager,
        color_change_service=color_service,
    )

    asyncio.run(
        task_service.generate_color_change(
            room_id=uuid4(),
            user_id=uuid4(),
            job_id=uuid4(),
            source_asset_id=uuid4(),
            graph_snapshot_id=uuid4(),
            guide_image_bytes=make_image(),
            metadata=ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
        )
    )

    color_service.generate.assert_awaited_once()
    session_factory.assert_not_called()


def test_color_change_failure_sends_correlated_error_only_to_requester():
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    color_service = Mock()
    color_service.generate = AsyncMock(side_effect=RuntimeError("generation failed"))
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock(return_value=True)
    task_service = Image2DGenerationTaskService(
        ws_manager=ws_manager,
        color_change_service=color_service,
    )

    asyncio.run(
        task_service.generate_color_change(
            room_id=room_id,
            user_id=user_id,
            job_id=job_id,
            source_asset_id=uuid4(),
            graph_snapshot_id=uuid4(),
            guide_image_bytes=make_image(),
            metadata=ColorChangeMetadataRequest(
                mime_type="image/png",
                width=4,
                height=3,
            ),
        )
    )

    ws_manager.send_to_user.assert_awaited_once()
    assert ws_manager.send_to_user.call_args.kwargs["user_id"] == user_id
    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message["event_type"] == "ERROR"
    assert message["job_id"] == str(job_id)
    assert message["payload"]["failed_event_type"] == "2D_COLOR_CHANGED"


def test_persistence_cleanup_failure_does_not_replace_database_error():
    db = Mock()
    storage = Mock()
    storage.upload_generated_image.return_value = StoredObjectInfo(
        bucket_name="2d-assets",
        object_name="2d/orphan.png",
        public_url="https://assets.example/2d/orphan.png",
    )
    storage.delete_uploaded_image.side_effect = RuntimeError("cleanup failed")
    asset_repository = Mock()
    asset_repository.create_2d_asset.side_effect = RuntimeError("database failed")
    service = Image2DAssetGenerationService(
        db=db,
        gemini_image_client=Mock(),
        minio_asset_storage=storage,
        asset_repository=asset_repository,
        graph_repository=Mock(),
    )

    with pytest.raises(RuntimeError, match="database failed"):
        asyncio.run(
            service.persist_generated_image(
                room_id=uuid4(),
                user_id=None,
                graph_snapshot_id=uuid4(),
                prompt_text=COLOR_CHANGE_PROMPT,
                generated_image=GeneratedImageBinary(
                    image_bytes=make_image(),
                    mime_type="image/png",
                    width=4,
                    height=3,
                ),
            )
        )

    db.rollback.assert_called_once()
    storage.delete_uploaded_image.assert_called_once()
