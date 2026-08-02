import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks
from pydantic import ValidationError

from app.ai.prompts.feature_image_prompt import build_feature_image_prompt
from app.api import feature as feature_api
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException
from app.schema.feature.extraction import (
    ExtractedFeature,
    FeatureExtractionResult,
)
from app.schema.feature.request import GenerateFeaturesRequest
from app.schema.feature.response import FeatureInfo, FeatureListResponse
from app.schema.generation.generation_result import (
    FeaturePromptContext,
    Generated2DAssetResult,
)
from app.service.feature.feature_extraction_service import FeatureExtractionService
from app.service.feature.feature_service import FeatureService
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)


@pytest.mark.parametrize("feature_text", [None, "", "   ", "... !!!"])
def test_generate_features_request_rejects_text_without_meaning(feature_text):
    with pytest.raises(ValidationError):
        GenerateFeaturesRequest(
            room_id=uuid4(),
            user_id=uuid4(),
            job_id=uuid4(),
            feature_text=feature_text,
        )


def test_feature_extraction_uses_structured_output_and_deduplicates():
    client = Mock()
    client.chat.completions.parse = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        refusal=None,
                        parsed=FeatureExtractionResult(
                            features=[
                                ExtractedFeature(text="접이식 손잡이"),
                                ExtractedFeature(text="높이 조절 기능"),
                                ExtractedFeature(text="접이식 손잡이"),
                            ]
                        ),
                    )
                )
            ]
        )
    )
    service = FeatureExtractionService(client=client)

    result = asyncio.run(
        service.extract(
            feature_text="손잡이를 접고 높이를 조절할 수 있으면 좋겠어.",
        )
    )

    assert result == ["접이식 손잡이", "높이 조절 기능"]
    request = client.chat.completions.parse.call_args.kwargs
    assert request["response_format"] is FeatureExtractionResult
    assert request["temperature"] == 0.1


def test_feature_extraction_maps_openai_failure_to_feature_error():
    client = Mock()
    client.chat.completions.parse = AsyncMock(side_effect=RuntimeError("timeout"))
    service = FeatureExtractionService(client=client)

    with pytest.raises(ServerException) as exc_info:
        asyncio.run(service.extract(feature_text="접이식 손잡이가 필요해"))

    assert exc_info.value.code == ResponseCode.FEATURE500


def test_feature_extraction_rejects_meaningless_text_before_openai_call():
    client = Mock()
    client.chat.completions.parse = AsyncMock()
    service = FeatureExtractionService(client=client)

    with pytest.raises(BadRequestException) as exc_info:
        asyncio.run(service.extract(feature_text=" ... "))

    assert exc_info.value.code == ResponseCode.FEATURE400
    client.chat.completions.parse.assert_not_awaited()


def test_generate_features_saves_all_extracted_features_in_one_transaction():
    room_id = uuid4()
    db = Mock()
    repository = Mock()
    extraction_service = Mock()
    extraction_service.extract = AsyncMock(
        return_value=["접이식 손잡이", "높이 조절 기능", "이동용 바퀴"]
    )

    def assign_ids(*, db, features):
        for feature in features:
            feature.feature_id = uuid4()
        return features

    repository.save_features.side_effect = assign_ids
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    service = FeatureService(
        feature_repository=repository,
        room_repository=room_repository,
        feature_extraction_service=extraction_service,
    )
    request = GenerateFeaturesRequest(
        room_id=room_id,
        user_id=uuid4(),
        job_id=uuid4(),
        feature_text="전체 기능 대화 내용",
    )

    result = asyncio.run(service.generate_features(request=request, db=db))

    extraction_service.extract.assert_awaited_once_with(
        feature_text="전체 기능 대화 내용",
    )
    saved = repository.save_features.call_args.kwargs["features"]
    assert [feature.feature_text for feature in saved] == [
        "접이식 손잡이",
        "높이 조절 기능",
        "이동용 바퀴",
    ]
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert [feature.feature_text for feature in result.features] == [
        "접이식 손잡이",
        "높이 조절 기능",
        "이동용 바퀴",
    ]


def test_generate_features_rolls_back_complete_batch_when_persistence_fails():
    repository = Mock()
    repository.save_features.side_effect = RuntimeError("insert failed")
    extraction_service = Mock()
    extraction_service.extract = AsyncMock(return_value=["기능 1", "기능 2"])
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    service = FeatureService(
        feature_repository=repository,
        room_repository=room_repository,
        feature_extraction_service=extraction_service,
    )

    with pytest.raises(ServerException) as exc_info:
        asyncio.run(
            service.generate_features(
                request=GenerateFeaturesRequest(
                    room_id=uuid4(),
                    user_id=uuid4(),
                    job_id=uuid4(),
                    feature_text="두 기능에 관한 대화",
                ),
                db=Mock(),
            )
        )

    db = repository.save_features.call_args.kwargs["db"]
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    assert exc_info.value.code == ResponseCode.FEATURE500


def test_generate_features_rejects_inactive_room_before_openai_call():
    extraction_service = Mock()
    extraction_service.extract = AsyncMock()
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=False)
    service = FeatureService(
        feature_repository=Mock(),
        room_repository=room_repository,
        feature_extraction_service=extraction_service,
    )

    with pytest.raises(BadRequestException) as exc_info:
        asyncio.run(
            service.generate_features(
                request=GenerateFeaturesRequest(
                    room_id=uuid4(),
                    user_id=uuid4(),
                    job_id=uuid4(),
                    feature_text="접이식 손잡이 기능",
                ),
                db=Mock(),
            )
        )

    assert exc_info.value.code == ResponseCode.FEATURE400
    extraction_service.extract.assert_not_awaited()


def test_feature_api_registers_existing_2d_feature_generation_after_save(monkeypatch):
    room_id = uuid4()
    user_id = uuid4()
    job_id = uuid4()
    feature_id = uuid4()
    request = GenerateFeaturesRequest(
        room_id=room_id,
        user_id=user_id,
        job_id=job_id,
        feature_text="접이식 손잡이가 필요해",
    )
    result = FeatureListResponse(
        room_id=room_id,
        features=[
            FeatureInfo(
                feature_id=feature_id,
                feature_text="접이식 손잡이",
            )
        ],
    )
    feature_service = Mock()
    feature_service.generate_features = AsyncMock(return_value=result)
    task_service = Mock()
    task_service.generate_from_features = AsyncMock()
    monkeypatch.setattr(feature_api, "feature_service", feature_service)
    monkeypatch.setattr(
        feature_api,
        "image_2d_generation_task_service",
        task_service,
    )
    background_tasks = BackgroundTasks()

    response = asyncio.run(
        feature_api.generate_features(
            request=request,
            background_tasks=background_tasks,
            db=Mock(),
        )
    )

    assert response["code"] == ResponseCode.FEATURE200.value
    assert response["result"]["features"][0]["feature_text"] == "접이식 손잡이"
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is task_service.generate_from_features
    assert task.kwargs == {
        "room_id": room_id,
        "user_id": user_id,
        "job_id": job_id,
    }
    assert response["result"]["job_id"] == str(job_id)


def test_feature_image_prompt_contains_db_feature_context_as_product_requirements():
    context = FeaturePromptContext(
        room_id=uuid4(),
        topic="이동식 작업대",
        features=["접이식 손잡이", "높이 조절 기능", "바퀴 고정 기능"],
    )

    prompt = build_feature_image_prompt(context.to_text())

    assert "이동식 작업대" in prompt
    assert "접이식 손잡이" in prompt
    assert "높이 조절 기능" in prompt
    assert "바퀴 고정 기능" in prompt
    assert "actual product design" in prompt


def test_feature_generation_sends_completion_only_to_requester():
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
        return Generated2DAssetResult(
            asset_id=asset_id,
            mime_type="image/png",
            width=512,
            height=512,
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

    ws_manager.send_to_user.assert_awaited_once()
    assert ws_manager.send_to_user.call_args.kwargs["user_id"] == user_id
    message = ws_manager.send_to_user.call_args.kwargs["message"]
    assert message["event_type"] == "2D_GENERATED"
    assert message["user_id"] == str(user_id)
    assert message["job_id"] == str(job_id)
    assert message["payload"]["asset_id"] == str(asset_id)
