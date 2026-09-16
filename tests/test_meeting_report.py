import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda
from sqlalchemy.dialects import postgresql

from app.agent.node.meeting_report_node import MeetingReportNode
from app.agent.schema.meeting_report_schema import (
    InferredTopicDecision,
    InferredTopicDecisionBundle,
)
from app.api import report as report_api
from app.api import room as room_api
from app.core.config import settings
from app.core.response.code import ResponseCode
from app.core.response.exceptions import NotFoundException
from app.db.session import get_db
from app.model.enum import (
    AssetType,
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    MeetingReportStatus,
    SemanticMemoryType,
)
from app.repository.graph_repository import GraphRepository
from app.repository.meeting_report_repository import MeetingReportRepository
from app.schema.report.meeting_report import MeetingReportData
from app.schema.report.response import MeetingReportLinkResponse
from app.service.agent.reflection_scheduler import ReflectionScheduler
from app.service.report.conclusion_contribution_calculator import (
    ConclusionContributionCalculator,
)
from app.service.report.decision_journey_builder import (
    DecisionJourneyBuilder,
    UtteranceView,
)
from app.service.report.graph_snapshot_layout import layout_graph
from app.service.report.meeting_report_service import (
    MeetingReportPage,
    MeetingReportService,
)
from app.service.report.meeting_report_task_service import MeetingReportTaskService


T0 = datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)


# =========================
# 시나리오 데이터: 의자 등받이 회의
# =========================


class ChairMeeting:
    """곡선형 제안 → 제작 난이도 제약 → 직선형 대안 → 편안함 근거 → 곡선형 결정."""

    def __init__(self):
        self.room_id = uuid4()
        self.topic = SimpleNamespace(
            topic_id=uuid4(),
            summary="의자 등받이 형태",
            centroid_embedding=[0.1] * 3,
            created_at=T0,
        )
        self.users = {name: uuid4() for name in ("민지", "서준", "지우")}
        texts = [
            ("민지", "등받이는 곡선형으로 만들면 좋겠어"),
            ("서준", "곡선 구조는 제작 난이도가 너무 높아"),
            ("서준", "그럼 직선형 등받이로 가는 게 어때"),
            ("지우", "응"),
            ("민지", "장시간 앉으면 허리 지지가 중요하니까 사용자 편안함을 우선해야 해"),
            ("지우", "맞아"),
            ("민지", "등받이를 약 15도 기울인 곡선형으로 확정하자"),
            ("지우", "음"),
        ]
        self.utterances = [
            UtteranceView(
                utterance_id=uuid4(),
                topic_id=self.topic.topic_id,
                user_id=self.users[name],
                nickname=name,
                text=text,
                created_at=T0 + timedelta(minutes=index),
            )
            for index, (name, text) in enumerate(texts)
        ]
        u = self.utterances
        # 배치가 10분 뒤 한꺼번에 저장했다. 저장 순서는 발화 순서와 다르게 섞어 둔다.
        batch_at = T0 + timedelta(minutes=10)
        self.decision_memory = SimpleNamespace(
            semantic_memory_id=uuid4(),
            topic_id=self.topic.topic_id,
            memory_type=SemanticMemoryType.DECISION,
            content="곡선형 등받이를 적용한다.",
            embedding=[0.9, 0.1, 0.0],
            created_at=batch_at,
        )
        self.rationale_memory = SimpleNamespace(
            semantic_memory_id=uuid4(),
            topic_id=self.topic.topic_id,
            memory_type=SemanticMemoryType.RATIONALE,
            content="장시간 사용 시 허리 지지와 사용자 편안함을 우선하기로 했다.",
            embedding=None,
            created_at=batch_at,
        )
        self.decision = self._fact(
            DesignFactType.DECISION,
            "약 15도 기울인 곡선형 등받이로 확정",
            created_at=batch_at,
            memory_id=self.decision_memory.semantic_memory_id,
        )
        self.rationale = self._fact(
            DesignFactType.RATIONALE,
            "장시간 사용 시 허리 지지가 중요하다",
            created_at=batch_at + timedelta(seconds=1),
        )
        self.alternative = self._fact(
            DesignFactType.PROPOSAL,
            "직선형 등받이",
            created_at=batch_at + timedelta(seconds=2),
        )
        self.constraint = self._fact(
            DesignFactType.CONSTRAINT,
            "곡선 구조는 제작 난이도가 높다",
            created_at=batch_at + timedelta(seconds=3),
        )
        self.proposal = self._fact(
            DesignFactType.PROPOSAL,
            "곡선형 등받이",
            created_at=batch_at + timedelta(seconds=4),
        )
        self.facts = [
            self.decision,
            self.rationale,
            self.alternative,
            self.constraint,
            self.proposal,
        ]
        self.links = [
            self._link(self.constraint, self.proposal, DesignFactLinkType.CONSTRAINS),
            self._link(self.alternative, self.proposal, DesignFactLinkType.CONFLICTS_WITH),
            self._link(self.rationale, self.decision, DesignFactLinkType.RATIONALE_OF),
            self._link(self.constraint, self.decision, DesignFactLinkType.CONSTRAINS),
        ]
        self.fact_utterance_ids = {
            self.proposal.design_fact_id: [u[0].utterance_id],
            self.constraint.design_fact_id: [u[1].utterance_id],
            self.alternative.design_fact_id: [u[2].utterance_id],
            self.rationale.design_fact_id: [u[4].utterance_id],
            self.decision.design_fact_id: [u[6].utterance_id],
        }
        # 제약 발화는 결정 문장과 표현이 달라 유사도가 가장 낮다.
        self.similarities = {
            u[0].utterance_id: 0.8,
            u[1].utterance_id: 0.1,
            u[2].utterance_id: 0.3,
            u[3].utterance_id: 0.5,
            u[4].utterance_id: 0.4,
            u[5].utterance_id: 0.45,
            u[6].utterance_id: 0.9,
            u[7].utterance_id: 0.5,
        }

    def _fact(self, fact_type, content, *, created_at, memory_id=None, status=None):
        return SimpleNamespace(
            design_fact_id=uuid4(),
            topic_id=self.topic.topic_id,
            fact_type=fact_type,
            status=status or DesignFactStatus.ACTIVE,
            content=content,
            embedding=[0.8, 0.2, 0.0],
            semantic_memory_id=memory_id,
            created_at=created_at,
            updated_at=None,
        )

    @staticmethod
    def _link(source, target, link_type):
        return SimpleNamespace(
            from_fact_id=source.design_fact_id,
            to_fact_id=target.design_fact_id,
            link_type=link_type,
        )

    def analysis(self):
        return DecisionJourneyBuilder().build(
            topic=self.topic,
            facts=self.facts,
            links=self.links,
            fact_utterance_ids=self.fact_utterance_ids,
            utterance_by_id={item.utterance_id: item for item in self.utterances},
            memories=[self.decision_memory, self.rationale_memory],
        )


# =========================
# Decision Journey
# =========================


def test_journey_uses_existing_decision_memory_and_orders_by_utterance_time():
    meeting = ChairMeeting()

    analysis = meeting.analysis()

    assert analysis.final_decision.content == "곡선형 등받이를 적용한다."
    assert analysis.final_decision.source == "SEMANTIC_MEMORY"
    assert analysis.final_decision.design_fact_id == meeting.decision.design_fact_id
    assert analysis.decision_embedding == [0.9, 0.1, 0.0]
    assert analysis.decision_rationale == meeting.rationale_memory.content
    assert [step.type for step in analysis.journey] == [
        "PROPOSAL",
        "CONSTRAINT",
        "ALTERNATIVE",
        "RATIONALE",
        "DECISION",
    ]
    constraint_step = analysis.journey[1]
    assert constraint_step.utterance_id == meeting.utterances[1].utterance_id
    assert constraint_step.nickname == "서준"
    assert constraint_step.timestamp == meeting.utterances[1].created_at
    assert analysis.needs_inference is False


def test_decision_evidence_follows_existing_fact_links_without_join_table():
    meeting = ChairMeeting()

    evidence = meeting.analysis().evidence

    assert evidence.supporting_design_fact_ids[0] == meeting.decision.design_fact_id
    assert set(evidence.supporting_design_fact_ids) == {
        meeting.decision.design_fact_id,
        meeting.rationale.design_fact_id,
        meeting.constraint.design_fact_id,
    }
    assert set(evidence.supporting_utterance_ids) == {
        meeting.utterances[6].utterance_id,
        meeting.utterances[4].utterance_id,
        meeting.utterances[1].utterance_id,
    }
    assert evidence.supporting_semantic_memory_ids == [
        meeting.decision_memory.semantic_memory_id,
        meeting.rationale_memory.semantic_memory_id,
    ]


def test_rationale_falls_back_to_linked_rationale_facts_without_memory():
    meeting = ChairMeeting()

    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=meeting.facts,
        links=meeting.links,
        fact_utterance_ids=meeting.fact_utterance_ids,
        utterance_by_id={item.utterance_id: item for item in meeting.utterances},
        memories=[],
    )

    assert analysis.final_decision.source == "DESIGN_FACT"
    assert analysis.final_decision.content == meeting.decision.content
    assert analysis.decision_rationale == "장시간 사용 시 허리 지지가 중요하다"


def test_superseded_decision_is_not_selected_as_final():
    meeting = ChairMeeting()
    old_decision = meeting._fact(
        DesignFactType.DECISION,
        "직선형으로 확정",
        created_at=T0 + timedelta(minutes=30),
        status=DesignFactStatus.SUPERSEDED,
    )

    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=[*meeting.facts, old_decision],
        links=meeting.links,
        fact_utterance_ids=meeting.fact_utterance_ids,
        utterance_by_id={item.utterance_id: item for item in meeting.utterances},
        memories=[],
    )

    assert analysis.final_decision.design_fact_id == meeting.decision.design_fact_id
    assert analysis.journey[-1].design_fact_id == meeting.decision.design_fact_id


# =========================
# Case 4: Final Decision 이 없는 Topic
# =========================


def test_topic_without_decision_is_marked_for_inference_not_failure():
    meeting = ChairMeeting()
    facts = [meeting.proposal, meeting.constraint]

    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=facts,
        links=meeting.links,
        fact_utterance_ids=meeting.fact_utterance_ids,
        utterance_by_id={item.utterance_id: item for item in meeting.utterances},
        memories=[],
    )

    assert analysis.final_decision.content is None
    assert analysis.final_decision.source == "NONE"
    assert analysis.decision_rationale is None
    assert analysis.needs_inference is True
    assert analysis.evidence.supporting_design_fact_ids == []


def test_topic_without_any_structure_does_not_request_inference():
    meeting = ChairMeeting()

    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=[],
        links=[],
        fact_utterance_ids={},
        utterance_by_id={},
        memories=[],
    )

    assert analysis.needs_inference is False
    assert analysis.journey == []


def test_inference_failure_keeps_report_without_decision():
    service = MeetingReportService(report_node=Mock(infer_decisions=AsyncMock(side_effect=RuntimeError("timeout"))))
    inputs = SimpleNamespace(
        report_id=uuid4(),
        inference_contexts=[SimpleNamespace(topic_id=uuid4())],
    )

    inferred, call_count = asyncio.run(service.infer_missing_decisions(inputs))

    assert inferred == {}
    assert call_count == 1


def test_inference_ignores_null_and_unknown_topics():
    known_topic = uuid4()
    converged_topic = uuid4()
    llm = Mock()
    llm.with_structured_output.return_value = RunnableLambda(
        lambda _prompt: InferredTopicDecisionBundle(
            decisions=[
                InferredTopicDecision(topic_id=known_topic, decision=None),
                InferredTopicDecision(topic_id=converged_topic, decision="목재로 가는 방향으로 모였다"),
                InferredTopicDecision(topic_id=uuid4(), decision="엉뚱한 topic"),
            ]
        )
    )
    service = MeetingReportService(report_node=MeetingReportNode(llm=llm))
    inputs = SimpleNamespace(
        report_id=uuid4(),
        inference_contexts=[
            SimpleNamespace(topic_id=known_topic, model_dump=lambda mode: {}),
            SimpleNamespace(topic_id=converged_topic, model_dump=lambda mode: {}),
        ],
    )

    inferred, call_count = asyncio.run(service.infer_missing_decisions(inputs))

    assert call_count == 1
    assert list(inferred) == [converged_topic]


def test_no_llm_call_when_every_topic_has_explicit_decision():
    node = Mock(infer_decisions=AsyncMock())
    service = MeetingReportService(report_node=node)
    inputs = SimpleNamespace(report_id=uuid4(), inference_contexts=[])

    inferred, call_count = asyncio.run(service.infer_missing_decisions(inputs))

    assert (inferred, call_count) == ({}, 0)
    node.infer_decisions.assert_not_called()


# =========================
# Case 5, 6: 기여도
# =========================


def _scores(meeting, analysis, *, similarities=None):
    return ConclusionContributionCalculator().score_utterances(
        utterances=meeting.utterances,
        similarities=similarities or meeting.similarities,
        utterance_roles=analysis.utterance_roles,
        dialogue_moves={},
        has_decision=analysis.has_decision,
    )


def test_filler_utterances_barely_affect_contribution():
    meeting = ChairMeeting()
    calculator = ConclusionContributionCalculator()
    scores = _scores(meeting, meeting.analysis())

    by_text = {item.utterance.text: item for item in scores}
    assert by_text["음"].score == 0.0
    assert by_text["응"].score < 0.05
    assert by_text["맞아"].score < 0.05

    contributions = {
        item.nickname: item for item in calculator.aggregate_contributions(scores)
    }
    # 지우는 발화 수로는 민지와 같지만(3회) 결론 형성 기여는 거의 없다.
    assert contributions["지우"].utterance_count == 3
    assert contributions["지우"].contribution_percent < 5.0
    assert contributions["지우"].contributions == []
    assert sum(item.contribution_percent for item in contributions.values()) == pytest.approx(100.0)


def test_low_similarity_constraint_is_kept_in_meaningful_utterances_and_contribution():
    meeting = ChairMeeting()
    calculator = ConclusionContributionCalculator()
    scores = _scores(meeting, meeting.analysis())

    meaningful = calculator.select_meaningful(scores)
    constraint = next(
        item for item in meaningful if item.utterance_id == meeting.utterances[1].utterance_id
    )
    assert constraint.conclusion_relevance == 0.1
    assert constraint.roles == ["CONSTRAINT"]
    assert constraint.score > 0.5
    assert all(item.text not in {"응", "맞아", "음"} for item in meaningful)

    contributions = {
        item.nickname: item for item in calculator.aggregate_contributions(scores)
    }
    assert contributions["서준"].contribution_percent > 20.0
    assert "제약 조건 제시: 곡선 구조는 제작 난이도가 높다" in contributions["서준"].contributions
    assert contributions["민지"].contribution_percent > contributions["서준"].contribution_percent


def test_similarity_alone_does_not_make_agreement_meaningful():
    meeting = ChairMeeting()
    calculator = ConclusionContributionCalculator()
    similarities = {key: 0.95 for key in meeting.similarities}
    scores = _scores(meeting, meeting.analysis(), similarities=similarities)

    agreement = next(item for item in scores if item.utterance.text == "맞아")
    constraint = next(
        item for item in scores if item.utterance.utterance_id == meeting.utterances[1].utterance_id
    )
    assert agreement.score < constraint.score / 5


def test_contribution_normalization_sums_to_exactly_hundred():
    user_ids = [uuid4() for _ in range(3)]

    percents = ConclusionContributionCalculator._normalize_to_hundred(
        {user_ids[0]: 1.0, user_ids[1]: 1.0, user_ids[2]: 1.0}
    )

    assert sum(percents.values()) == pytest.approx(100.0)
    assert sorted(percents.values()) == [33.3, 33.3, 33.4]


def test_contribution_is_zero_when_topic_has_only_noise():
    user_id = uuid4()
    utterance = UtteranceView(
        utterance_id=uuid4(),
        topic_id=uuid4(),
        user_id=user_id,
        nickname="민지",
        text="음",
        created_at=T0,
    )
    calculator = ConclusionContributionCalculator()

    scores = calculator.score_utterances(
        utterances=[utterance],
        similarities={utterance.utterance_id: 0.9},
        utterance_roles={},
        dialogue_moves={},
        has_decision=False,
    )

    [contribution] = calculator.aggregate_contributions(scores)
    assert contribution.contribution_percent == 0.0


# =========================
# Case 1, 2, 3: 리포트 조립과 최종 결과물
# =========================


def _snapshot(version, *, node_texts):
    snapshot_id = uuid4()
    root_id = str(uuid4())
    nodes = [
        {
            "node_id": root_id,
            "type": "PROPERTY",
            "node_text": node_texts[0],
            "parent_node_id": None,
            "used_in_generation": True,
        }
    ]
    edges = []
    for text in node_texts[1:]:
        child_id = str(uuid4())
        nodes.append(
            {
                "node_id": child_id,
                "type": "PROPERTY",
                "node_text": text,
                "parent_node_id": root_id,
                "used_in_generation": False,
            }
        )
        edges.append(
            {
                "edge_id": str(uuid4()),
                "from_node_id": root_id,
                "to_node_id": child_id,
                "label": None,
                "used_in_generation": False,
            }
        )
    return SimpleNamespace(
        graph_snapshot_id=snapshot_id,
        version=version,
        created_at=T0 + timedelta(minutes=version),
        snapshot_data=json.dumps(
            {
                "graph_version": version,
                "part_nodes": [],
                "sub_graphs": [{"sub_graph_id": str(uuid4()), "nodes": nodes, "edges": edges}],
            }
        ),
    )


def _outcome_service(meeting):
    """v12 로 이미지 생성 → 결과 사본 v13 → 이후 그래프 수정 v14."""
    source = _snapshot(12, node_texts=["의자", "곡선 등받이"])
    result = _snapshot(13, node_texts=["의자", "곡선 등받이"])
    latest = _snapshot(14, node_texts=["의자", "곡선 등받이", "팔걸이", "바퀴"])
    snapshots = {item.graph_snapshot_id: item for item in (source, result, latest)}
    asset = SimpleNamespace(
        asset_id=uuid4(),
        asset_type=AssetType.IMAGE_2D,
        file_url="https://assets.example/final.png",
        graph_snapshot_id=result.graph_snapshot_id,
        created_at=T0 + timedelta(minutes=13),
    )
    asset_repository = Mock()
    asset_repository.find_latest_ws_sent_2d_asset.return_value = asset
    graph_repository = Mock()
    graph_repository.find_graph_snapshot_by_id.side_effect = (
        lambda db, room_id, graph_snapshot_id: snapshots.get(graph_snapshot_id)
    )
    graph_repository.find_latest_graph_snapshot_by_room_id.return_value = latest
    graph_repository.find_generation_source_snapshot_id.return_value = source.graph_snapshot_id
    graph_repository.load_snapshot_data.side_effect = (
        lambda graph_snapshot: json.loads(graph_snapshot.snapshot_data)
    )
    return asset, source, result, graph_repository, asset_repository


def test_final_outcome_uses_snapshot_that_was_input_to_the_image_not_latest():
    meeting = ChairMeeting()
    asset, source, result, graph_repository, asset_repository = _outcome_service(meeting)
    service = MeetingReportService(
        graph_repository=graph_repository,
        asset_repository=asset_repository,
    )

    outcome = service._build_final_outcome(
        Mock(),
        room_id=meeting.room_id,
        ended_at=T0 + timedelta(hours=1),
    )

    assert outcome.asset_id == asset.asset_id
    assert outcome.image_url == "https://assets.example/final.png"
    assert outcome.graph_snapshot_id == source.graph_snapshot_id
    assert outcome.graph_snapshot_version == 12
    assert outcome.result_graph_snapshot_id == result.graph_snapshot_id
    assert outcome.result_graph_snapshot_version == 13
    assert sorted(node.node_text for node in outcome.nodes) == ["곡선 등받이", "의자"]
    assert len(outcome.edges) == 1
    graph_repository.find_latest_graph_snapshot_by_room_id.assert_not_called()
    assert graph_repository.find_generation_source_snapshot_id.call_args.kwargs == {
        "room_id": meeting.room_id,
        "result_graph_snapshot_id": result.graph_snapshot_id,
    }


def test_final_outcome_uses_result_snapshot_when_generation_had_no_input_snapshot():
    meeting = ChairMeeting()
    asset, _source, result, graph_repository, asset_repository = _outcome_service(meeting)
    graph_repository.find_generation_source_snapshot_id.return_value = None
    service = MeetingReportService(
        graph_repository=graph_repository,
        asset_repository=asset_repository,
    )

    outcome = service._build_final_outcome(Mock(), room_id=meeting.room_id, ended_at=T0)

    assert outcome.graph_snapshot_id == result.graph_snapshot_id
    assert outcome.graph_snapshot_version == 13


def test_final_outcome_is_none_without_delivered_2d_image():
    asset_repository = Mock()
    asset_repository.find_latest_ws_sent_2d_asset.return_value = None
    service = MeetingReportService(asset_repository=asset_repository, graph_repository=Mock())

    assert service._build_final_outcome(Mock(), room_id=uuid4(), ended_at=T0) is None


def test_generation_source_snapshot_is_read_from_generate_2d_event_payload():
    source_id = uuid4()
    db = Mock()
    db.scalar.return_value = json.dumps({"source_graph_snapshot_id": str(source_id)})

    found = GraphRepository().find_generation_source_snapshot_id(
        db,
        room_id=uuid4(),
        result_graph_snapshot_id=uuid4(),
    )

    assert found == source_id
    sql = str(db.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "graph_events.graph_snapshot_id" in sql
    assert "graph_events.event_type" in sql


def test_generation_source_snapshot_tolerates_missing_or_broken_payload():
    db = Mock()
    for payload in (None, "not-json", json.dumps({"source_graph_snapshot_id": None})):
        db.scalar.return_value = payload
        assert (
            GraphRepository().find_generation_source_snapshot_id(
                db,
                room_id=uuid4(),
                result_graph_snapshot_id=uuid4(),
            )
            is None
        )


def _inputs_for(meeting, *, extra_analyses=None, final_outcome=None):
    analysis = meeting.analysis()
    return SimpleNamespace(
        report_id=uuid4(),
        room_id=meeting.room_id,
        report_version=1,
        room_topic="XR 협업 의자",
        started_at=T0,
        ended_at=T0 + timedelta(hours=1),
        last_utterance_at=T0 + timedelta(minutes=7),
        participant_counts=[
            (meeting.users["민지"], "민지", 3),
            (meeting.users["서준"], "서준", 2),
            (meeting.users["지우"], "지우", 3),
        ],
        final_outcome=final_outcome,
        utterances_by_topic={meeting.topic.topic_id: meeting.utterances},
        analyses=[analysis, *(extra_analyses or [])],
        topic_centroids={meeting.topic.topic_id: [0.1, 0.1, 0.1]},
        dialogue_moves={},
        inference_contexts=[],
    )


def test_report_data_contains_topics_decisions_and_separate_participation():
    meeting = ChairMeeting()
    second_topic = ChairMeeting()
    repository = Mock()
    repository.find_utterance_similarities.side_effect = (
        lambda db, utterance_ids, embedding: {
            key: value
            for key, value in {**meeting.similarities, **second_topic.similarities}.items()
            if key in utterance_ids
        }
    )
    service = MeetingReportService(meeting_report_repository=repository)
    inputs = _inputs_for(meeting, extra_analyses=[second_topic.analysis()])
    inputs.utterances_by_topic[second_topic.topic.topic_id] = second_topic.utterances

    data = service.build_report_data(
        Mock(),
        inputs=inputs,
        inferred={},
        llm_call_count=0,
        generated_at=T0 + timedelta(hours=1),
    )

    assert data.overview.topic_count == 2
    assert data.overview.duration_seconds == 7 * 60
    assert data.overview.total_utterance_count == 8
    assert [topic.final_decision.content for topic in data.topics] == [
        "곡선형 등받이를 적용한다.",
        "곡선형 등받이를 적용한다.",
    ]
    first = data.topics[0]
    assert first.meaningful_utterances
    assert first.decision_contributions
    # 전체 참여도는 발화 횟수라 지우(3회)가 서준(2회)보다 높지만,
    # 결론 형성 기여도에서는 반대다.
    participation = {item.nickname: item for item in data.overall_participation}
    contribution = {item.nickname: item for item in first.decision_contributions}
    assert participation["지우"].ratio > participation["서준"].ratio
    assert contribution["지우"].contribution_percent < contribution["서준"].contribution_percent
    repository.find_utterance_similarities.assert_any_call(
        repository.find_utterance_similarities.call_args_list[0].args[0],
        utterance_ids=[item.utterance_id for item in meeting.utterances],
        embedding=[0.9, 0.1, 0.0],
    )
    # JSON 으로 저장했다가 다시 읽어도 같은 구조다.
    assert MeetingReportData.model_validate_json(data.model_dump_json()) == data


def test_inferred_decision_is_labelled_and_embedded_for_relevance():
    meeting = ChairMeeting()
    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=[meeting.proposal, meeting.constraint],
        links=meeting.links,
        fact_utterance_ids=meeting.fact_utterance_ids,
        utterance_by_id={item.utterance_id: item for item in meeting.utterances},
        memories=[],
    )
    repository = Mock()
    repository.find_utterance_similarities.return_value = {}
    embedding_service = Mock()
    embedding_service.embed_text.return_value = [0.3, 0.3, 0.3]
    service = MeetingReportService(
        meeting_report_repository=repository,
        embedding_service=embedding_service,
    )
    inputs = _inputs_for(meeting)
    inputs.analyses = [analysis]

    data = service.build_report_data(
        Mock(),
        inputs=inputs,
        inferred={
            meeting.topic.topic_id: InferredTopicDecision(
                topic_id=meeting.topic.topic_id,
                decision="곡선형을 유지하되 제작 방법을 더 알아보는 방향으로 모였다",
                rationale="편안함을 우선했다",
            )
        },
        llm_call_count=1,
        generated_at=T0,
    )

    topic = data.topics[0]
    assert topic.final_decision.source == "LLM_INFERRED"
    assert topic.decision_rationale == "편안함을 우선했다"
    assert data.llm_call_count == 1
    embedding_service.embed_text.assert_called_once()
    assert repository.find_utterance_similarities.call_args.kwargs["embedding"] == [0.3, 0.3, 0.3]


def test_topic_without_decision_uses_topic_centroid_and_still_completes():
    meeting = ChairMeeting()
    analysis = DecisionJourneyBuilder().build(
        topic=meeting.topic,
        facts=[],
        links=[],
        fact_utterance_ids={},
        utterance_by_id={},
        memories=[],
    )
    repository = Mock()
    repository.find_utterance_similarities.return_value = {}
    service = MeetingReportService(meeting_report_repository=repository)
    inputs = _inputs_for(meeting)
    inputs.analyses = [analysis]

    data = service.build_report_data(Mock(), inputs=inputs, inferred={}, llm_call_count=0, generated_at=T0)

    assert data.topics[0].final_decision.content is None
    assert repository.find_utterance_similarities.call_args.kwargs["embedding"] == [0.1, 0.1, 0.1]


def test_complete_report_persists_json_and_commits():
    meeting = ChairMeeting()
    report = SimpleNamespace(meeting_report_id=uuid4())
    repository = Mock()
    repository.find_utterance_similarities.return_value = meeting.similarities
    repository.find_by_id.return_value = report
    service = MeetingReportService(meeting_report_repository=repository)
    db = Mock()
    outcome = _outcome_service(meeting)
    final_outcome = MeetingReportService(
        graph_repository=outcome[3],
        asset_repository=outcome[4],
    )._build_final_outcome(Mock(), room_id=meeting.room_id, ended_at=T0)

    data = service.complete_report(
        db,
        inputs=_inputs_for(meeting, final_outcome=final_outcome),
        inferred={},
        llm_call_count=0,
    )

    kwargs = repository.mark_completed.call_args.kwargs
    assert kwargs["final_asset_id"] == outcome[0].asset_id
    assert kwargs["final_graph_snapshot_id"] == outcome[1].graph_snapshot_id
    assert MeetingReportData.model_validate_json(kwargs["report_data"]) == data
    db.commit.assert_called_once()


# =========================
# Case 7: 중복 종료 요청
# =========================


def _request_service(*, latest, has_activity=False):
    user_id = uuid4()
    room = SimpleNamespace(
        room_id=uuid4(),
        created_at=T0,
        members=[SimpleNamespace(user_id=user_id)],
    )
    topic_repository = Mock()
    topic_repository.lock_room.return_value = room
    repository = Mock()
    repository.find_latest_by_room.return_value = latest
    repository.has_activity_after.return_value = has_activity
    repository.create.side_effect = lambda db, **kwargs: SimpleNamespace(
        meeting_report_id=uuid4(),
        room_id=kwargs["room_id"],
        report_version=kwargs["report_version"],
        status=MeetingReportStatus.PENDING,
    )
    repository.reset_to_pending.side_effect = lambda db, report, requested_by_user_id: (
        setattr(report, "status", MeetingReportStatus.PENDING) or report
    )
    service = MeetingReportService(
        meeting_report_repository=repository,
        topic_repository=topic_repository,
    )
    return service, repository, room, user_id


def _existing_report(room_status):
    return SimpleNamespace(
        meeting_report_id=uuid4(),
        room_id=uuid4(),
        report_version=1,
        status=room_status,
        meeting_ended_at=T0,
    )


def test_first_end_request_creates_version_one(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://nodexr.example")
    service, repository, room, user_id = _request_service(latest=None)
    db = Mock()

    result = service.request_report(db, room_id=room.room_id, user_id=user_id, base_url="http://internal:8000/")

    assert result.report_version == 1
    assert result.status == "PENDING"
    assert result.report_url == f"https://nodexr.example/reports/{result.report_id}"
    assert repository.create.call_args.kwargs["meeting_started_at"] == T0
    db.commit.assert_called_once()


@pytest.mark.parametrize(
    "status",
    [MeetingReportStatus.PENDING, MeetingReportStatus.GENERATING, MeetingReportStatus.COMPLETED],
)
def test_repeated_end_request_reuses_existing_report(status):
    latest = _existing_report(status)
    service, repository, room, user_id = _request_service(latest=latest)

    result = service.request_report(Mock(), room_id=room.room_id, user_id=user_id, base_url=None)

    assert result.report_id == latest.meeting_report_id
    repository.create.assert_not_called()
    repository.reset_to_pending.assert_not_called()


def test_end_request_after_failure_retries_same_report_url():
    latest = _existing_report(MeetingReportStatus.FAILED)
    service, repository, room, user_id = _request_service(latest=latest)

    result = service.request_report(Mock(), room_id=room.room_id, user_id=user_id, base_url=None)

    assert result.report_id == latest.meeting_report_id
    assert result.status == "PENDING"
    repository.create.assert_not_called()


def test_end_request_after_meeting_resumed_creates_next_version():
    latest = _existing_report(MeetingReportStatus.COMPLETED)
    service, repository, room, user_id = _request_service(latest=latest, has_activity=True)

    result = service.request_report(Mock(), room_id=room.room_id, user_id=user_id, base_url=None)

    assert result.report_version == 2
    assert result.report_id != latest.meeting_report_id


def test_end_request_rejects_unknown_room_and_non_member():
    service, _repository, room, _user_id = _request_service(latest=None)
    with pytest.raises(NotFoundException) as exc:
        service.request_report(Mock(), room_id=room.room_id, user_id=uuid4(), base_url=None)
    assert exc.value.code == ResponseCode.ROOM_MEMBER404

    service.topic_repository.lock_room.return_value = None
    with pytest.raises(NotFoundException) as exc:
        service.request_report(Mock(), room_id=room.room_id, user_id=uuid4(), base_url=None)
    assert exc.value.code == ResponseCode.ROOM404


def test_claim_is_a_single_conditional_update():
    db = Mock()
    db.execute.return_value = SimpleNamespace(rowcount=1)

    claimed = MeetingReportRepository().claim_for_generation(
        db,
        report_id=uuid4(),
        stale_before=T0,
    )

    assert claimed is True
    sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert sql.startswith("UPDATE meeting_reports SET status=")
    assert "meeting_reports.status = %(status_1)s" in sql
    assert "meeting_reports.updated_at <" in sql


def test_report_url_does_not_hardcode_host(monkeypatch):
    report_id = uuid4()
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", None)
    assert (
        MeetingReportService.build_report_url(report_id=report_id, base_url="https://a.example/")
        == f"https://a.example/reports/{report_id}"
    )
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://b.example/")
    assert (
        MeetingReportService.build_report_url(report_id=report_id, base_url="https://a.example/")
        == f"https://b.example/reports/{report_id}"
    )


# =========================
# Case 7, 9: 백그라운드 작업과 WebSocket
# =========================


def _task_service(*, claimed=True, status="COMPLETED", complete_error=None):
    report_id = uuid4()
    link = MeetingReportLinkResponse(
        report_id=report_id,
        room_id=uuid4(),
        report_version=1,
        status=status,
        report_url=f"https://nodexr.example/reports/{report_id}",
    )
    report_service = Mock()
    report_service.claim_report.return_value = claimed
    report_service.load_inputs.return_value = SimpleNamespace()
    report_service.infer_missing_decisions = AsyncMock(return_value=({}, 0))
    report_service.complete_report.side_effect = complete_error
    report_service.get_report_link.return_value = link
    ws_manager = Mock()
    ws_manager.send_to_user = AsyncMock(return_value=True)
    drain = AsyncMock()
    service = MeetingReportTaskService(
        session_factory=Mock,
        ws_manager=ws_manager,
        report_service=report_service,
        reflection_drain=drain,
    )
    return service, report_service, ws_manager, drain, link


def test_task_generates_report_and_sends_report_url_only_to_requester():
    service, report_service, ws_manager, drain, link = _task_service()
    room_id = uuid4()
    user_id = uuid4()

    asyncio.run(
        service.run(report_id=link.report_id, room_id=room_id, user_id=user_id, base_url=None)
    )

    drain.assert_awaited_once_with(room_id)
    report_service.complete_report.assert_called_once()
    ws_manager.send_to_user.assert_awaited_once()
    kwargs = ws_manager.send_to_user.await_args.kwargs
    assert kwargs["room_id"] == room_id
    assert kwargs["user_id"] == user_id
    assert kwargs["message"] == {
        "event_type": "REPORT_GENERATED",
        "room_id": str(room_id),
        "user_id": str(user_id),
        "job_id": None,
        "payload": {
            "report_id": str(link.report_id),
            "report_version": 1,
            "report_url": link.report_url,
        },
    }
    ws_manager.broadcast.assert_not_called()


def test_duplicate_task_does_not_regenerate_but_delivers_completed_report():
    service, report_service, ws_manager, drain, link = _task_service(claimed=False)

    asyncio.run(service.run(report_id=link.report_id, room_id=uuid4(), user_id=uuid4(), base_url=None))

    drain.assert_not_awaited()
    report_service.load_inputs.assert_not_called()
    report_service.complete_report.assert_not_called()
    ws_manager.send_to_user.assert_awaited_once()


def test_duplicate_task_while_other_worker_generates_does_nothing():
    service, report_service, ws_manager, _drain, link = _task_service(
        claimed=False,
        status="GENERATING",
    )

    asyncio.run(service.run(report_id=link.report_id, room_id=uuid4(), user_id=uuid4(), base_url=None))

    report_service.complete_report.assert_not_called()
    ws_manager.send_to_user.assert_not_awaited()


def test_task_failure_marks_report_failed_and_sends_ws_error():
    service, report_service, ws_manager, _drain, link = _task_service(
        complete_error=RuntimeError("db down"),
    )
    user_id = uuid4()

    asyncio.run(service.run(report_id=link.report_id, room_id=uuid4(), user_id=user_id, base_url=None))

    report_service.fail_report.assert_called_once()
    assert "db down" in report_service.fail_report.call_args.kwargs["error_message"]
    message = ws_manager.send_to_user.await_args.kwargs["message"]
    assert message["event_type"] == "ERROR"
    assert message["payload"]["code"] == "REPORT500"
    assert message["payload"]["failed_event_type"] == "REPORT_GENERATED"


def test_reflection_drain_failure_does_not_block_report():
    service, report_service, ws_manager, drain, link = _task_service()
    drain.side_effect = RuntimeError("batch llm timeout")

    asyncio.run(service.run(report_id=link.report_id, room_id=uuid4(), user_id=uuid4(), base_url=None))

    report_service.complete_report.assert_called_once()
    assert ws_manager.send_to_user.await_args.kwargs["message"]["event_type"] == "REPORT_GENERATED"


def test_scheduler_drains_room_until_no_pending_utterances():
    room_id = uuid4()
    service = Mock()
    service.find_pending_room_ids.side_effect = [[room_id], [room_id], []]
    scheduler = ReflectionScheduler(
        service=service,
        graph=Mock(),
        lock_repository=Mock(),
        interval_seconds=1,
    )
    scheduler._run_room = AsyncMock()

    asyncio.run(scheduler.run_room_until_drained(room_id, retry_delay_seconds=0))

    assert scheduler._run_room.await_count == 2


def test_scheduler_drain_stops_after_batch_failure():
    room_id = uuid4()
    service = Mock()
    service.find_pending_room_ids.return_value = [room_id]
    scheduler = ReflectionScheduler(
        service=service,
        graph=Mock(),
        lock_repository=Mock(),
        interval_seconds=1,
    )

    async def failing_run(target_room_id):
        scheduler._record_failure(target_room_id)

    scheduler._run_room = AsyncMock(side_effect=failing_run)

    asyncio.run(scheduler.run_room_until_drained(room_id, retry_delay_seconds=0))

    assert scheduler._run_room.await_count == 1


# =========================
# Case 8: HTML, API
# =========================


def _completed_page(meeting):
    repository = Mock()
    repository.find_utterance_similarities.return_value = meeting.similarities
    outcome = _outcome_service(meeting)
    final_outcome = MeetingReportService(
        graph_repository=outcome[3],
        asset_repository=outcome[4],
    )._build_final_outcome(Mock(), room_id=meeting.room_id, ended_at=T0)
    data = MeetingReportService(meeting_report_repository=repository).build_report_data(
        Mock(),
        inputs=_inputs_for(meeting, final_outcome=final_outcome),
        inferred={},
        llm_call_count=0,
        generated_at=T0 + timedelta(hours=1),
    )
    report = SimpleNamespace(
        meeting_report_id=data.report_id,
        report_version=1,
        status=MeetingReportStatus.COMPLETED,
        report_data=data.model_dump_json(),
    )
    return report, data


def _report_client(page):
    service = Mock()
    service.find_report_page.return_value = page
    app = FastAPI()
    app.include_router(report_api.router)
    app.dependency_overrides[get_db] = lambda: Mock()
    app.dependency_overrides[report_api.get_meeting_report_service] = lambda: service
    return TestClient(app)


def test_report_page_renders_final_outcome_topics_and_participation():
    meeting = ChairMeeting()
    meeting.utterances[0] = UtteranceView(
        **{**meeting.utterances[0].__dict__, "text": "<script>alert(1)</script> 곡선형으로 만들자"}
    )
    report, _data = _completed_page(meeting)
    repository = Mock()
    repository.find_by_id.return_value = report
    page = MeetingReportService(meeting_report_repository=repository).find_report_page(
        Mock(),
        report_id=report.meeting_report_id,
        base_url="https://nodexr.example/",
    )

    response = _report_client(page).get(f"/reports/{report.meeting_report_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    html = response.text
    assert "NodeXR Meeting Report" in html
    assert "Graph Snapshot v12" in html
    assert "https://assets.example/final.png" in html
    assert "<svg" in html
    assert "곡선형 등받이를 적용한다." in html
    assert "Decision Journey" in html
    assert "곡선 구조는 제작 난이도가 높다" in html
    assert "결론 형성 기여도" in html
    assert "전체 회의 참여도" in html
    assert "<script>alert(1)</script>" not in html
    assert html.index("최종 결과물") < html.index("Topic 1") < html.index("전체 회의 참여도")


def test_report_page_shows_progress_while_generating():
    page = MeetingReportPage(
        report=SimpleNamespace(report_version=1, status=MeetingReportStatus.GENERATING),
        report_url="https://nodexr.example/reports/x",
        data=None,
        graph_layout=None,
    )

    response = _report_client(page).get(f"/reports/{uuid4()}")

    assert response.status_code == 200
    assert "리포트를 만드는 중입니다" in response.text
    assert 'http-equiv="refresh"' in response.text


def test_report_page_returns_html_404_for_unknown_report():
    response = _report_client(None).get(f"/reports/{uuid4()}")

    assert response.status_code == 404
    assert "리포트를 찾을 수 없습니다" in response.text


def test_end_meeting_api_returns_report_contract_and_schedules_generation(monkeypatch):
    from app.service.report.report_service import ReportResult
    from app.schema.report.response import ParticipantRatioResponse, ReportResponse

    room_id = uuid4()
    user_id = uuid4()
    report_id = uuid4()
    service = Mock()
    service.get_report.return_value = ReportResult(
        response=ReportResponse(
            topic="XR 협업 의자",
            participants=["민지"],
            participants_ratio=[
                ParticipantRatioResponse(user_id=user_id, nickname="민지", ratio=100.0)
            ],
            final_2D_image=None,
            url=f"https://nodexr.example/reports/{report_id}",
        ),
        report_id=report_id,
    )
    task_service = Mock()
    task_service.run = AsyncMock()
    monkeypatch.setattr(room_api, "report_service", service)
    monkeypatch.setattr(room_api, "meeting_report_task_service", task_service)
    app = FastAPI()
    app.include_router(room_api.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: Mock()

    response = TestClient(app).post(
        f"/api/rooms/{room_id}/end",
        json={"user_id": str(user_id)},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["code"] == "REPORT200"
    assert body["message"] == "팀 프로젝트 레포트 생성 성공"
    assert set(body["result"]) == {
        "topic",
        "participants",
        "participants_ratio",
        "final_2D_image",
        "url",
    }
    assert set(body["result"]["participants_ratio"][0]) == {"user_id", "nickname", "ratio"}
    assert body["result"]["url"] == f"https://nodexr.example/reports/{report_id}"
    assert service.get_report.call_args.kwargs["user_id"] == user_id
    task_service.run.assert_awaited_once()
    assert task_service.run.await_args.kwargs["report_id"] == report_id
    assert task_service.run.await_args.kwargs["user_id"] == user_id


def test_report_request_without_user_skips_member_check():
    service, repository, room, _user_id = _request_service(latest=None)

    result = service.request_report(Mock(), room_id=room.room_id, user_id=None, base_url=None)

    assert result.report_version == 1
    assert repository.create.call_args.kwargs["requested_by_user_id"] is None


def test_task_without_requester_completes_without_websocket():
    service, report_service, ws_manager, _drain, link = _task_service()

    asyncio.run(service.run(report_id=link.report_id, room_id=uuid4(), user_id=None, base_url=None))

    report_service.complete_report.assert_called_once()
    ws_manager.send_to_user.assert_not_awaited()


def test_graph_layout_places_children_right_of_parent_and_survives_cycles():
    from app.schema.report.meeting_report import ReportGraphEdge, ReportGraphNode

    nodes = [
        ReportGraphNode(node_id="a", node_type="PROPERTY", node_text="의자", parent_node_id=None),
        ReportGraphNode(node_id="b", node_type="PROPERTY", node_text="등받이", parent_node_id="a"),
        ReportGraphNode(node_id="c", node_type="PROPERTY", node_text="순환1", parent_node_id="d"),
        ReportGraphNode(node_id="d", node_type="PROPERTY", node_text="순환2", parent_node_id="c"),
    ]
    edges = [
        ReportGraphEdge(edge_id="e1", from_node_id="a", to_node_id="b"),
        ReportGraphEdge(edge_id="e2", from_node_id="a", to_node_id="missing"),
    ]

    layout = layout_graph(nodes=nodes, edges=edges)

    positions = {node.node_id: node for node in layout.nodes}
    assert positions["b"].x > positions["a"].x
    assert set(positions) == {"a", "b", "c", "d"}
    assert [edge.edge_id for edge in layout.edges] == ["e1"]


def test_overall_participation_query_can_exclude_agent_commands():
    from app.repository.report_repository import ReportRepository

    db = Mock()
    db.execute.return_value.all.return_value = []

    ReportRepository().find_participant_utterance_counts(
        db,
        room_id=uuid4(),
        started_at=T0,
        requested_at=T0,
        exclude_agent_commands=True,
    )
    with_skip_filter = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    ReportRepository().find_participant_utterance_counts(
        db,
        room_id=uuid4(),
        started_at=T0,
        requested_at=T0,
    )
    default_sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))

    assert "utterances.state !=" in with_skip_filter
    assert "utterances.state" not in default_sql
