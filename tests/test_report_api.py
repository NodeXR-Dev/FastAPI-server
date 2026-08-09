import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api import report
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.db.session import get_db
from app.model.enum import AssetType
from app.repository.asset_repository import AssetRepository
from app.repository.report_repository import ReportRepository
from app.schema.generation.color_change_request import ColorChangeMetadataRequest
from app.schema.report.response import ParticipantRatioResponse, ReportResponse
from app.schema.generation.generation_result import Generated2DAssetResult
from app.schema.generation.request import Generate2DGraphRequest
from app.service.generation.image_2d_generation_task_service import (
    Image2DGenerationTaskService,
)
from app.service.report.report_service import ReportService


def test_report_router_returns_requested_contract():
    room_id = uuid4()
    user_id = uuid4()
    db = Mock()
    service = Mock()
    service.get_report.return_value = ReportResponse(
        topic="XR 협업 의자",
        participants=["민지"],
        participants_ratio=[
            ParticipantRatioResponse(
                user_id=user_id,
                nickname="민지",
                ratio=100.0,
            )
        ],
        final_2D_image="https://assets.example/final.png",
    )
    app = FastAPI()
    app.include_router(report.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[report.get_report_service] = lambda: service

    response = TestClient(app).get(f"/report/{room_id}")

    assert response.status_code == 200
    assert response.json() == {
        "isSuccess": True,
        "code": "REPORT200",
        "message": "팀 프로젝트 레포트 생성 성공",
        "result": {
            "topic": "XR 협업 의자",
            "participants": ["민지"],
            "participants_ratio": [
                {
                    "user_id": str(user_id),
                    "nickname": "민지",
                    "ratio": 100.0,
                }
            ],
            "final_2D_image": "https://assets.example/final.png",
        },
    }
    service.get_report.assert_called_once_with(db=db, room_id=room_id)


def test_report_openapi_uses_room_id_path_parameter_without_request_body():
    app = FastAPI()
    app.include_router(report.router)

    operation = app.openapi()["paths"]["/report/{room_id}"]["get"]

    assert "requestBody" not in operation
    assert operation["parameters"] == [
        {
            "name": "room_id",
            "in": "path",
            "required": True,
            "schema": {
                "type": "string",
                "format": "uuid",
                "title": "Room Id",
            },
        }
    ]


def test_report_service_calculates_count_based_ratios_for_all_participants():
    room_id = uuid4()
    started_at = datetime(2026, 8, 9, 1, tzinfo=timezone.utc)
    requested_at = started_at + timedelta(hours=2)
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(
        topic="모듈형 의자",
        created_at=started_at,
    )
    participant_counts = [
        (uuid4(), "민지", 2),
        (uuid4(), "서준", 1),
        (uuid4(), "지우", 0),
    ]
    report_repository = Mock()
    report_repository.find_participant_utterance_counts.return_value = (
        participant_counts
    )
    asset_repository = Mock()
    asset_repository.find_latest_ws_sent_2d_asset.return_value = SimpleNamespace(
        asset_id=uuid4(),
        file_url="https://assets.example/latest.png",
    )
    service = ReportService(
        room_repository=room_repository,
        report_repository=report_repository,
        asset_repository=asset_repository,
    )
    db = Mock()

    result = service.get_report(
        db=db,
        room_id=room_id,
        requested_at=requested_at,
    )

    assert result.topic == "모듈형 의자"
    assert result.participants == ["민지", "서준", "지우"]
    assert [item.ratio for item in result.participants_ratio] == [66.67, 33.33, 0.0]
    report_repository.find_participant_utterance_counts.assert_called_once_with(
        db=db,
        room_id=room_id,
        started_at=started_at,
        requested_at=requested_at,
    )
    asset_repository.find_latest_ws_sent_2d_asset.assert_called_once_with(
        db=db,
        room_id=room_id,
        requested_at=requested_at,
    )


def test_report_service_returns_zero_ratios_when_there_are_no_utterances():
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(
        topic="주제",
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    report_repository = Mock()
    report_repository.find_participant_utterance_counts.return_value = [
        (uuid4(), "민지", 0),
        (uuid4(), "서준", 0),
    ]
    asset_repository = Mock()
    asset_repository.find_latest_ws_sent_2d_asset.return_value = SimpleNamespace(
        asset_id=uuid4(),
        file_url="https://assets.example/latest.png",
    )
    service = ReportService(
        room_repository=room_repository,
        report_repository=report_repository,
        asset_repository=asset_repository,
    )

    result = service.get_report(db=Mock(), room_id=uuid4())

    assert [item.ratio for item in result.participants_ratio] == [0.0, 0.0]


def test_report_service_rejects_missing_room():
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = None
    report_repository = Mock()
    report_repository.find_participant_utterance_counts.return_value = []
    asset_repository = Mock()
    service = ReportService(
        room_repository=room_repository,
        report_repository=report_repository,
        asset_repository=asset_repository,
    )

    with pytest.raises(NotFoundException) as exc_info:
        service.get_report(db=Mock(), room_id=uuid4())

    assert exc_info.value.code == ResponseCode.ROOM404


def test_report_service_returns_null_when_final_image_does_not_exist():
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(
        topic="주제",
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    report_repository = Mock()
    report_repository.find_participant_utterance_counts.return_value = []
    asset_repository = Mock()
    asset_repository.find_latest_ws_sent_2d_asset.return_value = None
    service = ReportService(
        room_repository=room_repository,
        report_repository=report_repository,
        asset_repository=asset_repository,
    )

    result = service.get_report(db=Mock(), room_id=uuid4())

    assert result.final_2D_image is None


def test_seed_2d_generation_json_matches_request_schema_and_seed_ids():
    fixture_path = (
        Path(__file__).parent / "fixtures" / "seed_generate_2d_request.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    request = Generate2DGraphRequest.model_validate(payload)

    assert str(request.room_id) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert str(request.user_id) == "11111111-1111-1111-1111-111111111111"
    assert len(request.connections) == 4


def test_report_repository_counts_utterances_in_meeting_window_with_left_join():
    repository = ReportRepository()
    db = Mock()
    db.execute.return_value.all.return_value = []
    room_id = uuid4()
    started_at = datetime(2026, 8, 9, tzinfo=timezone.utc)
    requested_at = started_at + timedelta(hours=1)

    repository.find_participant_utterance_counts(
        db=db,
        room_id=room_id,
        started_at=started_at,
        requested_at=requested_at,
    )

    stmt = db.execute.call_args.args[0]
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "LEFT OUTER JOIN utterances" in sql
    assert "utterances.created_at >=" in sql
    assert "utterances.created_at <=" in sql
    assert "room_members.state" not in sql


def test_latest_report_asset_requires_successful_ws_delivery():
    repository = AssetRepository()
    db = Mock()
    db.scalar.return_value = None

    repository.find_latest_ws_sent_2d_asset(
        db=db,
        room_id=uuid4(),
        requested_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    stmt = db.scalar.call_args.args[0]
    where_sql = str(stmt.whereclause.compile(dialect=postgresql.dialect()))
    order_sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "assets.asset_type" in where_sql
    assert AssetType.IMAGE_2D.value in str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "assets.ws_sent_at IS NOT NULL" in where_sql
    assert "assets.ws_sent_at DESC" in order_sql


@pytest.mark.parametrize(("sent", "expected_mark_count"), [(True, 1), (False, 0)])
def test_2d_task_records_delivery_only_when_websocket_send_succeeds(
    sent,
    expected_mark_count,
):
    room_id = uuid4()
    user_id = uuid4()
    asset_id = uuid4()
    db = Mock()
    ws_manager = Mock()
    ws_manager.send_to_user = Mock()

    async def send_to_user(**_kwargs):
        return sent

    ws_manager.send_to_user.side_effect = send_to_user
    asset_repository = Mock()
    asset_repository.mark_2d_asset_ws_sent.return_value = SimpleNamespace(
        asset_id=asset_id
    )
    service = Image2DGenerationTaskService(
        session_factory=Mock(return_value=db),
        ws_manager=ws_manager,
        asset_repository=asset_repository,
    )

    async def generation_call(_db):
        return Generated2DAssetResult(
            asset_id=asset_id,
            mime_type="image/png",
            width=1280,
            height=720,
            img_url="https://assets.example/final.png",
        )

    asyncio.run(
        service._run(
            room_id=room_id,
            user_id=user_id,
            job_id=uuid4(),
            graph_snapshot_id=None,
            generation_call=generation_call,
        )
    )

    assert asset_repository.mark_2d_asset_ws_sent.call_count == expected_mark_count


def test_color_change_task_records_successful_websocket_delivery():
    room_id = uuid4()
    user_id = uuid4()
    asset_id = uuid4()
    result = Generated2DAssetResult(
        asset_id=asset_id,
        mime_type="image/png",
        width=1280,
        height=720,
        img_url="https://assets.example/color-changed.png",
    )
    color_change_service = Mock()

    async def generate(**_kwargs):
        return result

    color_change_service.generate.side_effect = generate
    ws_manager = Mock()

    async def send_to_user(**_kwargs):
        return True

    ws_manager.send_to_user.side_effect = send_to_user
    delivery_db = Mock()
    session_factory = Mock(return_value=delivery_db)
    asset_repository = Mock()
    asset_repository.mark_2d_asset_ws_sent.return_value = SimpleNamespace(
        asset_id=asset_id
    )
    service = Image2DGenerationTaskService(
        session_factory=session_factory,
        ws_manager=ws_manager,
        color_change_service=color_change_service,
        asset_repository=asset_repository,
    )

    asyncio.run(
        service.generate_color_change(
            room_id=room_id,
            user_id=user_id,
            job_id=uuid4(),
            source_asset_id=uuid4(),
            graph_snapshot_id=uuid4(),
            guide_image_bytes=b"guide",
            metadata=ColorChangeMetadataRequest(
                mime_type="image/png",
                width=1280,
                height=720,
            ),
        )
    )

    asset_repository.mark_2d_asset_ws_sent.assert_called_once()
    delivery_db.commit.assert_called_once()
    delivery_db.close.assert_called_once()
