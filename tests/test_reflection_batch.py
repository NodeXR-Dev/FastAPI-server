import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableLambda
from sqlalchemy.dialects import postgresql

from app.agent.node.reflection_batch_node import ReflectionBatchNode
from app.agent.graph.reflection_batch_graph import ReflectionBatchGraph
from app.agent.schema.reflection_batch_schema import (
    BatchAnalysisResult,
    BatchContext,
    BatchMemoryRecord,
    BatchTopicRecord,
    BatchUtteranceRecord,
    FactCandidate,
    FactDedupDecision,
    FactDedupJudgeResult,
    FactLinkCandidate,
    FactReference,
    PreparedFactDecision,
    PreparedReflection,
    ReflectionPersistenceResult,
    SemanticMemoryProposal,
    SemanticMemoryProposalBundle,
    TopicResegmentAssignment,
    TopicResegmentResult,
    TopicSummaryProposal,
    TopicSummaryProposalBundle,
)
from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    SemanticMemoryType,
    TopicStatus,
    UtteranceState,
)
from app.repository.graph_repository import GraphRepository
from app.repository.utterance_repository import UtteranceRepository
from app.service.agent.reflection_batch_service import (
    InvalidFactRelationshipError,
    ReflectionBatchService,
)
from app.service.agent.reflection_scheduler import ReflectionScheduler


class SchemaFakeLLM:
    def __init__(self, responses):
        self.responses = responses

    def with_structured_output(self, schema):
        return RunnableLambda(lambda _prompt: self.responses[schema])


def _context(*, utterances=None) -> BatchContext:
    return BatchContext(
        room_id=uuid4(),
        utterances=utterances or [],
    )


def _reflection_service() -> ReflectionBatchService:
    return ReflectionBatchService(
        session_factory=Mock(),
        utterance_repository=Mock(),
        graph_repository=Mock(),
        topic_repository=Mock(),
        memory_repository=Mock(),
        embedding_service=Mock(),
    )


def _invalid_relationship_case():
    topic_id = uuid4()
    proposal_source = uuid4()
    rationale_source = uuid4()
    context = _context(
        utterances=[
            BatchUtteranceRecord(
                utterance_id=proposal_source,
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="접이식 손잡이를 제안합니다.",
            ),
            BatchUtteranceRecord(
                utterance_id=rationale_source,
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="보관 공간을 줄일 수 있기 때문입니다.",
            ),
        ]
    )
    facts = [
        FactCandidate(
            temp_id="proposal-1",
            topic_id=topic_id,
            fact_type=DesignFactType.PROPOSAL,
            content="접이식 손잡이를 적용한다.",
            source_utterance_ids=[proposal_source],
            confidence=0.95,
        ),
        FactCandidate(
            temp_id="rationale-1",
            topic_id=topic_id,
            fact_type=DesignFactType.RATIONALE,
            content="보관 공간을 줄일 수 있다.",
            source_utterance_ids=[rationale_source],
            confidence=0.92,
        ),
    ]
    invalid_analysis = BatchAnalysisResult(
        facts=facts,
        links=[
            FactLinkCandidate(
                source=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="proposal-1",
                ),
                target=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="rationale-1",
                ),
                link_type=DesignFactLinkType.SUPPORTS,
                confidence=0.9,
            )
        ],
    )
    repaired_analysis = BatchAnalysisResult(
        facts=facts,
        links=[
            FactLinkCandidate(
                source=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="rationale-1",
                ),
                target=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="proposal-1",
                ),
                link_type=DesignFactLinkType.RATIONALE_OF,
                confidence=0.9,
            )
        ],
    )
    return context, facts, invalid_analysis, repaired_analysis


def _validate_with_graph(*, context, analysis, repair_result):
    node = Mock()
    node.repair_analysis_relationships = AsyncMock(
        side_effect=repair_result
        if isinstance(repair_result, Exception)
        else None,
        return_value=None
        if isinstance(repair_result, Exception)
        else repair_result,
    )
    graph = ReflectionBatchGraph(service=_reflection_service(), node=node)
    result = asyncio.run(
        graph.validate_analysis(
            {
                "room_id": context.room_id,
                "batch_context": context,
                "analysis_result": analysis,
            }
        )
    )["analysis_result"]
    return result, node


def test_unprocessed_utterance_query_is_state_based_not_five_minute_based():
    db = Mock()
    db.scalars.return_value.all.return_value = []
    repository = UtteranceRepository()

    repository.find_unprocessed_by_room(
        db,
        room_id=uuid4(),
        limit=100,
    )

    stmt = db.scalars.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "utterances.state" in sql
    assert "utterances.created_at >=" not in sql
    assert "utterances.created_at >" not in sql


def test_unprocessed_graph_event_query_uses_processed_at_cursor():
    db = Mock()
    db.scalars.return_value.all.return_value = []

    GraphRepository().find_unprocessed_events_by_room(
        db,
        room_id=uuid4(),
        limit=100,
    )

    stmt = db.scalars.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "graph_events.processed_at IS NULL" in sql
    assert "graph_events.created_at >=" not in sql


def test_old_pending_utterance_remains_valid_batch_input():
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    record = BatchUtteranceRecord(
        utterance_id=uuid4(),
        user_id=uuid4(),
        topic_id=uuid4(),
        normalized_text="10분 전 미처리 발화",
        created_at=old,
    )
    assert record.created_at == old
    assert UtteranceState.NOREFLECT != UtteranceState.REFLECT


def test_batch_routes_preexisting_topicless_utterance_before_analysis():
    room_id = uuid4()
    topic_id = uuid4()
    utterance = SimpleNamespace(
        utterance_id=uuid4(),
        user_id=uuid4(),
        room_id=room_id,
        topic_id=None,
        original_text="버튼으로 입력한 발화",
        normalized_text=None,
        embedding=None,
        created_at=datetime.now(timezone.utc),
    )
    db = Mock()
    utterance_repository = Mock()
    utterance_repository.find_unprocessed_by_room.return_value = [utterance]
    graph_repository = Mock()
    graph_repository.find_unprocessed_events_by_room.return_value = []
    topic_routing_service = Mock()

    def assign_topic(*_args, **_kwargs):
        utterance.topic_id = topic_id
        return topic_id

    topic_routing_service.route_topic.side_effect = assign_topic
    service = ReflectionBatchService(
        session_factory=Mock(return_value=db),
        utterance_repository=utterance_repository,
        graph_repository=graph_repository,
        topic_repository=Mock(),
        memory_repository=Mock(),
        embedding_service=Mock(embed_text=Mock(return_value=[0.1, 0.2])),
        topic_routing_service=topic_routing_service,
    )

    records, _events, topic_ids = service.load_batch_data(room_id=room_id)

    assert records[0].topic_id == topic_id
    assert topic_ids == [topic_id]
    topic_routing_service.route_topic.assert_called_once()
    db.commit.assert_called_once()


def test_scheduler_skips_room_when_advisory_lock_is_held():
    lock_db = Mock()
    lock_repository = Mock()
    lock_repository.try_acquire_room_lock.return_value = False
    graph = Mock()
    graph.ainvoke = AsyncMock()
    scheduler = ReflectionScheduler(
        session_factory=Mock(return_value=lock_db),
        lock_repository=lock_repository,
        service=Mock(),
        graph=graph,
        interval_seconds=300,
    )

    asyncio.run(scheduler._run_room(uuid4()))

    graph.ainvoke.assert_not_awaited()
    lock_repository.release_room_lock.assert_not_called()
    lock_db.close.assert_called_once()


def test_batch_analyzer_returns_structured_facts_links_and_provenance():
    topic_id = uuid4()
    proposal_source = uuid4()
    rationale_source = uuid4()
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="proposal-1",
                topic_id=topic_id,
                fact_type=DesignFactType.PROPOSAL,
                content="의자는 알루미늄으로 제작한다.",
                source_utterance_ids=[proposal_source],
                confidence=0.95,
            ),
            FactCandidate(
                temp_id="rationale-1",
                topic_id=topic_id,
                fact_type=DesignFactType.RATIONALE,
                content="가볍고 재활용하기 쉽다.",
                source_utterance_ids=[rationale_source],
                confidence=0.93,
            ),
        ],
        links=[
            FactLinkCandidate(
                source=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="rationale-1",
                ),
                target=FactReference(
                    reference_type="CANDIDATE",
                    reference_id="proposal-1",
                ),
                link_type=DesignFactLinkType.RATIONALE_OF,
                confidence=0.9,
            )
        ],
    )
    fake_llm = SchemaFakeLLM(
        {
            BatchAnalysisResult: analysis,
            FactDedupJudgeResult: FactDedupJudgeResult(),
            SemanticMemoryProposalBundle: SemanticMemoryProposalBundle(),
            TopicSummaryProposalBundle: TopicSummaryProposalBundle(),
        }
    )
    node = ReflectionBatchNode(llm=fake_llm)
    context = _context(
        utterances=[
            BatchUtteranceRecord(
                utterance_id=proposal_source,
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="의자는 알루미늄으로 만들죠.",
            ),
            BatchUtteranceRecord(
                utterance_id=rationale_source,
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="가볍고 재활용하기 좋으니까요.",
            ),
        ]
    )

    result = asyncio.run(node.analyze(context))
    validated = ReflectionBatchService(
        session_factory=Mock(),
        utterance_repository=Mock(),
        graph_repository=Mock(),
        topic_repository=Mock(),
        memory_repository=Mock(),
        embedding_service=Mock(),
    ).validate_analysis(context=context, analysis=result)

    assert {item.fact_type for item in validated.facts} == {
        DesignFactType.PROPOSAL,
        DesignFactType.RATIONALE,
    }
    assert validated.links[0].link_type == DesignFactLinkType.RATIONALE_OF
    assert validated.facts[0].source_utterance_ids == [proposal_source]


def test_validation_drops_fact_without_batch_provenance():
    topic_id = uuid4()
    context = _context(
        utterances=[
            BatchUtteranceRecord(
                utterance_id=uuid4(),
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="예산은 15만원을 넘으면 안 됩니다.",
            )
        ]
    )
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="constraint-1",
                topic_id=topic_id,
                fact_type=DesignFactType.CONSTRAINT,
                content="예산은 15만원 이하이다.",
                source_utterance_ids=[uuid4()],
                confidence=0.95,
            )
        ]
    )
    service = ReflectionBatchService(
        session_factory=Mock(),
        utterance_repository=Mock(),
        graph_repository=Mock(),
        topic_repository=Mock(),
        memory_repository=Mock(),
        embedding_service=Mock(),
    )

    # 출처가 배치 안에 하나도 없으면 그 fact만 버리고 배치는 계속한다.
    validated = service.validate_analysis(context=context, analysis=analysis)

    assert validated.facts == []


def test_invalid_fact_relationship_triggers_one_repair_and_accepts_correction():
    context, facts, invalid_analysis, repaired_analysis = (
        _invalid_relationship_case()
    )
    result, node = _validate_with_graph(
        context=context,
        analysis=invalid_analysis,
        repair_result=repaired_analysis,
    )

    node.repair_analysis_relationships.assert_awaited_once()
    assert result.facts == facts
    assert len(result.links) == 1
    assert result.links[0].link_type == DesignFactLinkType.RATIONALE_OF
    assert result.links[0].source.reference_id == "rationale-1"


def test_invalid_relationship_is_discarded_when_single_repair_is_still_invalid():
    context, facts, invalid_analysis, _ = _invalid_relationship_case()
    result, node = _validate_with_graph(
        context=context,
        analysis=invalid_analysis,
        repair_result=invalid_analysis,
    )

    node.repair_analysis_relationships.assert_awaited_once()
    assert result.facts == facts
    assert result.links == []


def test_invalid_relationship_is_discarded_when_repair_call_fails():
    context, facts, invalid_analysis, _ = _invalid_relationship_case()
    result, node = _validate_with_graph(
        context=context,
        analysis=invalid_analysis,
        repair_result=RuntimeError("repair timeout"),
    )

    node.repair_analysis_relationships.assert_awaited_once()
    assert result.facts == facts
    assert result.links == []


def test_invalid_relationship_uses_specific_validation_error():
    context, _, invalid_analysis, _ = _invalid_relationship_case()

    with pytest.raises(
        InvalidFactRelationshipError,
        match="PROPOSAL -SUPPORTS-> RATIONALE",
    ):
        _reflection_service().validate_analysis(
            context=context,
            analysis=invalid_analysis,
        )


def test_vector_exact_match_prevents_duplicate_constraint():
    room_id = uuid4()
    topic_id = uuid4()
    existing_id = uuid4()
    db = Mock()
    memory_repository = Mock()
    memory_repository.find_similar_facts.return_value = [
        (
            SimpleNamespace(
                design_fact_id=existing_id,
                topic_id=topic_id,
                fact_type=DesignFactType.CONSTRAINT,
                status=DesignFactStatus.ACTIVE,
                content="제품은 500g 이하이다.",
            ),
            0.99,
        )
    ]
    service = ReflectionBatchService(
        session_factory=Mock(return_value=db),
        utterance_repository=Mock(),
        graph_repository=Mock(),
        topic_repository=Mock(),
        memory_repository=memory_repository,
        embedding_service=Mock(embed_text=Mock(return_value=[0.1, 0.2])),
    )
    fact = FactCandidate(
        temp_id="constraint-1",
        topic_id=topic_id,
        fact_type=DesignFactType.CONSTRAINT,
        content="제품은 500g 이하이다.",
        source_utterance_ids=[uuid4()],
        confidence=0.95,
    )

    decisions, comparisons, _embeddings = service._build_dedup_inputs(
        room_id=room_id,
        facts=[fact],
    )

    assert comparisons == []
    assert decisions[0].action == "KEEP_EXISTING"
    assert decisions[0].existing_fact_id == existing_id


def test_persistence_failure_rolls_back_without_marking_utterance_reflected():
    room_id = uuid4()
    topic_id = uuid4()
    utterance_id = uuid4()
    created_fact_id = uuid4()
    db = Mock()
    utterance_repository = Mock()
    utterance_repository.lock_unprocessed_by_ids.return_value = [
        SimpleNamespace(utterance_id=utterance_id)
    ]
    graph_repository = Mock()
    graph_repository.lock_unprocessed_events_by_ids.return_value = []
    topic_repository = Mock()
    topic_repository.lock_room.return_value = SimpleNamespace()
    topic_repository.find_by_ids.return_value = [
        SimpleNamespace(topic_id=topic_id)
    ]
    memory_repository = Mock()
    memory_repository.find_fact_entities_by_ids.return_value = []
    memory_repository.create_fact.return_value = SimpleNamespace(
        design_fact_id=created_fact_id,
        topic_id=topic_id,
    )
    memory_repository.ensure_fact_utterance_link.return_value = True
    memory_repository.upsert_semantic_memory.side_effect = RuntimeError(
        "forced memory failure"
    )
    service = ReflectionBatchService(
        session_factory=Mock(return_value=db),
        utterance_repository=utterance_repository,
        graph_repository=graph_repository,
        topic_repository=topic_repository,
        memory_repository=memory_repository,
        embedding_service=Mock(embed_text=Mock(return_value=[0.1, 0.2])),
    )
    candidate = FactCandidate(
        temp_id="decision-1",
        topic_id=topic_id,
        fact_type=DesignFactType.DECISION,
        content="색상은 검은색으로 결정한다.",
        source_utterance_ids=[utterance_id],
        confidence=0.95,
    )
    prepared = PreparedReflection(
        facts=[candidate],
        decisions=[
            PreparedFactDecision(
                temp_id=candidate.temp_id,
                action="CREATE",
                confidence=1.0,
                embedding=[0.1, 0.2],
            )
        ],
        changed_topic_ids=[topic_id],
    )
    memories = [
        SemanticMemoryProposal(
            topic_id=topic_id,
            memory_type=SemanticMemoryType.DECISION,
            content="색상은 검은색이다.",
            source_fact_refs=[
                FactReference(
                    reference_type="CANDIDATE",
                    reference_id=candidate.temp_id,
                )
            ],
        )
    ]

    with pytest.raises(RuntimeError, match="forced memory failure"):
        service.persist_reflection(
            room_id=room_id,
            utterance_ids=[utterance_id],
            graph_event_ids=[],
            prepared=prepared,
            memory_updates=memories,
            topic_updates=[
                TopicSummaryProposal(topic_id=topic_id, summary="색상 결정")
            ],
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    utterance_repository.mark_reflected.assert_not_called()


def test_success_marks_inputs_only_after_all_domain_writes():
    room_id = uuid4()
    topic_id = uuid4()
    utterance_id = uuid4()
    graph_event_id = uuid4()
    fact_id = uuid4()
    calls = []
    db = Mock()
    db.commit.side_effect = lambda: calls.append("commit")
    utterance_repository = Mock()
    utterance_repository.lock_unprocessed_by_ids.return_value = [
        SimpleNamespace(utterance_id=utterance_id)
    ]
    utterance_repository.mark_reflected.side_effect = lambda _items: calls.append(
        "mark_utterances"
    )
    graph_repository = Mock()
    graph_repository.lock_unprocessed_events_by_ids.return_value = [
        SimpleNamespace(graph_event_id=graph_event_id)
    ]
    graph_repository.mark_events_processed.side_effect = lambda *_args, **_kwargs: calls.append(
        "mark_events"
    )
    topic_repository = Mock()
    topic_repository.lock_room.return_value = SimpleNamespace()
    topic_repository.find_by_ids.return_value = [
        SimpleNamespace(topic_id=topic_id)
    ]
    topic_repository.find_utterance_embeddings.return_value = [[0.2, 0.4]]
    topic_repository.update_summary_and_centroid.side_effect = (
        lambda *_args, **_kwargs: calls.append("update_topic")
    )
    memory_repository = Mock()
    memory_repository.find_fact_entities_by_ids.return_value = []
    memory_repository.create_fact.return_value = SimpleNamespace(
        design_fact_id=fact_id,
        topic_id=topic_id,
    )
    memory_repository.ensure_fact_utterance_link.return_value = True
    service = ReflectionBatchService(
        session_factory=Mock(return_value=db),
        utterance_repository=utterance_repository,
        graph_repository=graph_repository,
        topic_repository=topic_repository,
        memory_repository=memory_repository,
        embedding_service=Mock(),
    )
    candidate = FactCandidate(
        temp_id="proposal-1",
        topic_id=topic_id,
        fact_type=DesignFactType.PROPOSAL,
        content="재활용 알루미늄을 사용한다.",
        source_utterance_ids=[utterance_id],
        confidence=0.9,
    )
    prepared = PreparedReflection(
        facts=[candidate],
        decisions=[
            PreparedFactDecision(
                temp_id=candidate.temp_id,
                action="CREATE",
                confidence=1.0,
                embedding=[0.2, 0.4],
            )
        ],
        changed_topic_ids=[topic_id],
    )

    result = service.persist_reflection(
        room_id=room_id,
        utterance_ids=[utterance_id],
        graph_event_ids=[graph_event_id],
        prepared=prepared,
        memory_updates=[],
        topic_updates=[
            TopicSummaryProposal(topic_id=topic_id, summary="재료 제안")
        ],
    )

    assert isinstance(result, ReflectionPersistenceResult)
    assert calls == ["update_topic", "mark_events", "mark_utterances", "commit"]
    assert result.reflected_utterance_count == 1
    assert result.processed_graph_event_count == 1


def test_supersede_marks_old_fact_and_creates_new_active_fact():
    room_id = uuid4()
    topic_id = uuid4()
    utterance_id = uuid4()
    old_fact_id = uuid4()
    new_fact_id = uuid4()
    db = Mock()
    utterance_repository = Mock()
    utterance_repository.lock_unprocessed_by_ids.return_value = [
        SimpleNamespace(utterance_id=utterance_id)
    ]
    graph_repository = Mock()
    graph_repository.lock_unprocessed_events_by_ids.return_value = []
    topic_repository = Mock()
    topic_repository.lock_room.return_value = SimpleNamespace()
    topic_repository.find_by_ids.return_value = [
        SimpleNamespace(topic_id=topic_id)
    ]
    old_fact = SimpleNamespace(
        design_fact_id=old_fact_id,
        topic_id=topic_id,
        status=DesignFactStatus.ACTIVE,
    )
    memory_repository = Mock()
    memory_repository.find_fact_entities_by_ids.return_value = [old_fact]
    memory_repository.create_fact.return_value = SimpleNamespace(
        design_fact_id=new_fact_id,
        topic_id=topic_id,
    )
    memory_repository.ensure_fact_utterance_link.return_value = True
    service = ReflectionBatchService(
        session_factory=Mock(return_value=db),
        utterance_repository=utterance_repository,
        graph_repository=graph_repository,
        topic_repository=topic_repository,
        memory_repository=memory_repository,
        embedding_service=Mock(),
    )
    candidate = FactCandidate(
        temp_id="decision-black",
        topic_id=topic_id,
        fact_type=DesignFactType.DECISION,
        content="최종 색상은 검은색이다.",
        source_utterance_ids=[utterance_id],
        confidence=0.97,
    )
    prepared = PreparedReflection(
        facts=[candidate],
        decisions=[
            PreparedFactDecision(
                temp_id=candidate.temp_id,
                action="SUPERSEDE_EXISTING",
                existing_fact_id=old_fact_id,
                confidence=0.95,
                embedding=[0.1, 0.2],
            )
        ],
        changed_topic_ids=[topic_id],
    )

    result = service.persist_reflection(
        room_id=room_id,
        utterance_ids=[utterance_id],
        graph_event_ids=[],
        prepared=prepared,
        memory_updates=[],
        topic_updates=[],
    )

    memory_repository.mark_fact_superseded.assert_called_once_with(old_fact)
    memory_repository.create_fact.assert_called_once()
    assert result.created_fact_count == 1
    assert result.superseded_fact_count == 1


def test_forced_second_persistence_attempt_stops_before_duplicate_writes():
    room_id = uuid4()
    topic_id = uuid4()
    utterance_id = uuid4()
    db_first = Mock()
    db_second = Mock()
    utterance_repository = Mock()
    utterance_repository.lock_unprocessed_by_ids.side_effect = [
        [SimpleNamespace(utterance_id=utterance_id)],
        [],
    ]
    graph_repository = Mock()
    graph_repository.lock_unprocessed_events_by_ids.return_value = []
    topic_repository = Mock()
    topic_repository.lock_room.return_value = SimpleNamespace()
    topic_repository.find_by_ids.return_value = [
        SimpleNamespace(topic_id=topic_id)
    ]
    memory_repository = Mock()
    memory_repository.find_fact_entities_by_ids.return_value = []
    memory_repository.create_fact.return_value = SimpleNamespace(
        design_fact_id=uuid4(),
        topic_id=topic_id,
    )
    memory_repository.ensure_fact_utterance_link.return_value = True
    service = ReflectionBatchService(
        session_factory=Mock(side_effect=[db_first, db_second]),
        utterance_repository=utterance_repository,
        graph_repository=graph_repository,
        topic_repository=topic_repository,
        memory_repository=memory_repository,
        embedding_service=Mock(),
    )
    candidate = FactCandidate(
        temp_id="constraint-1",
        topic_id=topic_id,
        fact_type=DesignFactType.CONSTRAINT,
        content="제품 무게는 500g 이하이다.",
        source_utterance_ids=[utterance_id],
        confidence=0.95,
    )
    prepared = PreparedReflection(
        facts=[candidate],
        decisions=[
            PreparedFactDecision(
                temp_id=candidate.temp_id,
                action="CREATE",
                confidence=1.0,
                embedding=[0.1, 0.2],
            )
        ],
        changed_topic_ids=[topic_id],
    )
    kwargs = dict(
        room_id=room_id,
        utterance_ids=[utterance_id],
        graph_event_ids=[],
        prepared=prepared,
        memory_updates=[],
        topic_updates=[],
    )

    service.persist_reflection(**kwargs)
    with pytest.raises(ValueError, match="already reflected"):
        service.persist_reflection(**kwargs)

    memory_repository.create_fact.assert_called_once()
    db_second.rollback.assert_called_once()


def test_reflection_graph_runs_without_langsmith_export_when_tracing_is_disabled():
    room_id = uuid4()
    topic_id = uuid4()
    utterance = BatchUtteranceRecord(
        utterance_id=uuid4(),
        user_id=uuid4(),
        topic_id=topic_id,
        normalized_text="일반적인 회의 발화",
    )
    context = BatchContext(room_id=room_id, utterances=[utterance])
    prepared = PreparedReflection()
    persistence = ReflectionPersistenceResult(reflected_utterance_count=1)
    service = Mock()
    service.load_batch_data.return_value = ([utterance], [], [topic_id])
    service.retrieve_related_context.return_value = ([], [], [])
    service.build_context.return_value = context
    service.validate_analysis.return_value = BatchAnalysisResult()
    service.deduplicate_facts = AsyncMock(return_value=prepared)
    service.validate_memory_updates.return_value = []
    service.persist_reflection.return_value = persistence
    node = Mock()
    node.analyze = AsyncMock(return_value=BatchAnalysisResult())
    node.generate_memories = AsyncMock(
        return_value=SemanticMemoryProposalBundle()
    )
    graph = ReflectionBatchGraph(service=service, node=node)

    result = asyncio.run(graph.ainvoke(room_id=room_id))

    assert result["persistence_result"] == persistence
    service.persist_reflection.assert_called_once()


def test_memory_proposals_are_dropped_instead_of_failing_the_batch():
    topic_id = uuid4()
    other_topic_id = uuid4()
    utterance_id = uuid4()
    service = ReflectionBatchService(session_factory=Mock())

    decision = FactCandidate(
        temp_id="decision-1",
        topic_id=topic_id,
        fact_type=DesignFactType.DECISION,
        content="모터는 쓰지 않기로 한다.",
        source_utterance_ids=[utterance_id],
        confidence=0.9,
    )
    proposal = FactCandidate(
        temp_id="proposal-1",
        topic_id=topic_id,
        fact_type=DesignFactType.PROPOSAL,
        content="송풍기를 넣는다.",
        source_utterance_ids=[utterance_id],
        confidence=0.9,
    )
    prepared = PreparedReflection(
        facts=[decision, proposal],
        changed_topic_ids=[topic_id],
    )
    context = BatchContext(room_id=uuid4())

    def ref(temp_id):
        return FactReference(reference_type="CANDIDATE", reference_id=temp_id)

    grounded = SemanticMemoryProposal(
        topic_id=topic_id,
        memory_type=SemanticMemoryType.DECISION,
        content="모터를 쓰지 않기로 결정했다.",
        source_fact_refs=[ref("decision-1")],
    )
    # CONFLICT 메모리인데 근거가 PROPOSAL뿐이라 규칙에 어긋난다.
    ungrounded = SemanticMemoryProposal(
        topic_id=topic_id,
        memory_type=SemanticMemoryType.CONFLICT,
        content="송풍기 도입을 두고 충돌이 있었다.",
        source_fact_refs=[ref("proposal-1")],
    )
    unchanged_topic = SemanticMemoryProposal(
        topic_id=other_topic_id,
        memory_type=SemanticMemoryType.SUMMARY,
        content="이번 batch에서 바뀌지 않은 topic 요약",
        source_fact_refs=[ref("decision-1")],
    )
    unknown_fact = SemanticMemoryProposal(
        topic_id=topic_id,
        memory_type=SemanticMemoryType.RATIONALE,
        content="존재하지 않는 fact를 근거로 든 메모리",
        source_fact_refs=[ref("does-not-exist")],
    )

    accepted = service.validate_memory_updates(
        context=context,
        prepared=prepared,
        proposals=[grounded, ungrounded, unchanged_topic, unknown_fact],
    )

    # 어긋난 제안만 버리고, 정상 제안과 나머지 batch는 살린다.
    assert accepted == [grounded]


def test_duplicate_memory_proposal_for_same_topic_and_type_is_dropped():
    topic_id = uuid4()
    service = ReflectionBatchService(session_factory=Mock())
    candidate = FactCandidate(
        temp_id="constraint-1",
        topic_id=topic_id,
        fact_type=DesignFactType.CONSTRAINT,
        content="전기 부품을 쓰지 않는다.",
        source_utterance_ids=[uuid4()],
        confidence=0.9,
    )
    prepared = PreparedReflection(facts=[candidate], changed_topic_ids=[topic_id])

    def proposal(content):
        return SemanticMemoryProposal(
            topic_id=topic_id,
            memory_type=SemanticMemoryType.CONSTRAINT,
            content=content,
            source_fact_refs=[
                FactReference(reference_type="CANDIDATE", reference_id="constraint-1")
            ],
        )

    accepted = service.validate_memory_updates(
        context=BatchContext(room_id=uuid4()),
        prepared=prepared,
        proposals=[proposal("첫 번째"), proposal("두 번째")],
    )

    assert [item.content for item in accepted] == ["첫 번째"]


def test_memory_generation_marks_replaceable_existing_memories():
    """덮어쓰기 대상 메모리를 LLM 입력에 명시해 병합을 유도한다."""
    changed_topic = uuid4()
    other_topic = uuid4()
    captured: dict[str, str] = {}

    class CapturingLLM(SchemaFakeLLM):
        def with_structured_output(self, schema):
            def _run(prompt):
                captured["text"] = prompt.to_string()
                return self.responses[schema]

            return RunnableLambda(_run)

    node = ReflectionBatchNode(
        llm=CapturingLLM(
            {SemanticMemoryProposalBundle: SemanticMemoryProposalBundle()},
        )
    )
    context = BatchContext(
        room_id=uuid4(),
        semantic_memories=[
            BatchMemoryRecord(
                semantic_memory_id=uuid4(),
                topic_id=changed_topic,
                memory_type=SemanticMemoryType.SUMMARY,
                content="기존 요약: 우산 물기 제거기를 만들기로 했다.",
            ),
            BatchMemoryRecord(
                semantic_memory_id=uuid4(),
                topic_id=other_topic,
                memory_type=SemanticMemoryType.SUMMARY,
                content="다른 토픽 요약.",
            ),
        ],
    )

    asyncio.run(
        node.generate_memories(
            PreparedReflection(changed_topic_ids=[changed_topic]),
            context,
        )
    )

    payload = json.loads(captured["text"].split("Prepared reflection:\n", 1)[1])
    flags = {
        item["topic_id"]: item["will_be_replaced"]
        for item in payload["current_memories"]
    }
    assert flags[str(changed_topic)] is True
    assert flags[str(other_topic)] is False
    assert "기존 요약: 우산 물기 제거기를 만들기로 했다." in captured["text"]
    assert "REPLACES" in captured["text"]


def test_resegmentation_moves_utterances_and_never_touches_existing_topics():
    """배치가 발화 소속만 다시 정한다. 기존 topic은 합치지도 이름을 바꾸지도 않는다."""
    room_id = uuid4()
    topic_a, topic_b = uuid4(), uuid4()
    moved_utterance, stayed_utterance = uuid4(), uuid4()

    context = BatchContext(
        room_id=room_id,
        utterances=[
            BatchUtteranceRecord(
                utterance_id=moved_utterance,
                user_id=uuid4(),
                topic_id=topic_a,
                normalized_text="지붕을 씌우는 건 어때?",
            ),
            BatchUtteranceRecord(
                utterance_id=stayed_utterance,
                user_id=uuid4(),
                topic_id=topic_b,
                normalized_text="자물쇠 고리를 굵게 하자.",
            ),
        ],
        topics=[
            BatchTopicRecord(topic_id=topic_a, summary="위치", status=TopicStatus.ACTIVE),
            BatchTopicRecord(topic_id=topic_b, summary="잠금", status=TopicStatus.ACTIVE),
        ],
    )

    service = _reflection_service()
    service.session_factory = Mock(return_value=Mock())
    service.utterance_repository = Mock()
    service.topic_repository = Mock()

    updated, moved = service.apply_topic_resegmentation(
        context=context,
        result=TopicResegmentResult(
            assignments=[
                # 1번(위치)에 있던 발화를 2번(잠금)으로 옮긴다.
                TopicResegmentAssignment(
                    utterance_id=moved_utterance,
                    topic_number=2,
                ),
                TopicResegmentAssignment(
                    utterance_id=stayed_utterance,
                    topic_number=2,
                ),
            ]
        ),
    )

    assert moved == 1
    assert updated.utterances[0].topic_id == topic_b
    assert updated.utterances[1].topic_id == topic_b
    # 기존 topic 2개가 그대로 남아 있고 새로 만들지 않았다.
    assert [item.topic_id for item in updated.topics] == [topic_a, topic_b]
    service.topic_repository.create.assert_not_called()
    service.utterance_repository.update.assert_called_once()


def test_resegmentation_groups_new_topic_utterances_into_one_topic():
    """새 topic으로 간 발화들이 같은 group 라벨이면 topic 하나만 만든다."""
    room_id = uuid4()
    existing_topic = uuid4()
    created_topic = uuid4()
    first, second = uuid4(), uuid4()

    context = BatchContext(
        room_id=room_id,
        utterances=[
            BatchUtteranceRecord(
                utterance_id=first,
                user_id=uuid4(),
                topic_id=existing_topic,
                normalized_text="자물쇠는 어떻게 걸지 정하자.",
            ),
            BatchUtteranceRecord(
                utterance_id=second,
                user_id=uuid4(),
                topic_id=existing_topic,
                normalized_text="고리를 위쪽에 하나 더 달자.",
            ),
        ],
        topics=[
            BatchTopicRecord(
                topic_id=existing_topic, summary="지붕", status=TopicStatus.ACTIVE
            ),
        ],
    )

    service = _reflection_service()
    db = Mock()
    db.get.return_value = SimpleNamespace(embedding=[0.1, 0.2, 0.3])
    service.session_factory = Mock(return_value=db)
    service.utterance_repository = Mock()
    service.topic_repository = Mock()
    service.topic_repository.create.return_value = SimpleNamespace(
        topic_id=created_topic,
        summary="잠금 방식",
    )

    updated, moved = service.apply_topic_resegmentation(
        context=context,
        result=TopicResegmentResult(
            assignments=[
                TopicResegmentAssignment(
                    utterance_id=first,
                    topic_number=0,
                    new_topic_group="잠금",
                    new_topic_summary="잠금 방식",
                ),
                TopicResegmentAssignment(
                    utterance_id=second,
                    topic_number=0,
                    new_topic_group="잠금",
                ),
            ]
        ),
    )

    assert moved == 2
    assert service.topic_repository.create.call_count == 1
    assert [item.topic_id for item in updated.utterances] == [
        created_topic,
        created_topic,
    ]
    assert [item.topic_id for item in updated.topics] == [existing_topic, created_topic]


def test_resegmentation_skips_unknown_utterance_ids():
    """배치에 없는 utterance_id를 돌려줘도 배치 전체를 세우지 않는다."""
    room_id = uuid4()
    topic_id = uuid4()
    known = uuid4()

    context = BatchContext(
        room_id=room_id,
        utterances=[
            BatchUtteranceRecord(
                utterance_id=known,
                user_id=uuid4(),
                topic_id=topic_id,
                normalized_text="지붕을 씌우자.",
            )
        ],
        topics=[
            BatchTopicRecord(
                topic_id=topic_id, summary="지붕", status=TopicStatus.ACTIVE
            )
        ],
    )

    service = _reflection_service()
    service.session_factory = Mock(return_value=Mock())
    service.utterance_repository = Mock()
    service.topic_repository = Mock()

    updated, moved = service.apply_topic_resegmentation(
        context=context,
        result=TopicResegmentResult(
            assignments=[
                TopicResegmentAssignment(utterance_id=uuid4(), topic_number=1),
                TopicResegmentAssignment(utterance_id=known, topic_number=1),
            ]
        ),
    )

    assert moved == 0
    assert updated.utterances[0].topic_id == topic_id


def _validation_context(*records):
    return _context(utterances=list(records))


def _utterance(topic_id, text="발화"):
    return BatchUtteranceRecord(
        utterance_id=uuid4(),
        user_id=uuid4(),
        topic_id=topic_id,
        normalized_text=text,
    )


def test_validation_repairs_fact_topic_from_its_source_utterance():
    """topic_id가 틀려도 정답이 출처 발화에 있으므로 버리지 않고 맞춘다."""
    right_topic, wrong_topic = uuid4(), uuid4()
    source = _utterance(right_topic, "예산은 오만 원을 넘기면 안 돼.")
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="constraint-1",
                topic_id=wrong_topic,
                fact_type=DesignFactType.CONSTRAINT,
                content="전체 예산은 오만 원 이하이다.",
                source_utterance_ids=[source.utterance_id],
                confidence=0.95,
            )
        ]
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source),
        analysis=analysis,
    )

    assert len(validated.facts) == 1
    assert validated.facts[0].topic_id == right_topic


def test_validation_drops_only_the_fact_whose_sources_span_topics():
    """출처가 여러 topic에 걸치면 옳은 값이 없다. 그 fact만 버린다."""
    topic_a, topic_b = uuid4(), uuid4()
    source_a = _utterance(topic_a, "태양광으로 가자.")
    source_b = _utterance(topic_b, "예산은 오만 원이야.")
    good = _utterance(topic_a, "패널은 울타리에 고정하자.")

    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="spanning",
                topic_id=topic_a,
                fact_type=DesignFactType.DECISION,
                content="예산 안에서 태양광을 쓴다.",
                source_utterance_ids=[source_a.utterance_id, source_b.utterance_id],
                confidence=0.9,
            ),
            FactCandidate(
                temp_id="clean",
                topic_id=topic_a,
                fact_type=DesignFactType.PROPOSAL,
                content="패널을 울타리 위에 고정한다.",
                source_utterance_ids=[good.utterance_id],
                confidence=0.9,
            ),
        ]
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source_a, source_b, good),
        analysis=analysis,
    )

    assert [item.temp_id for item in validated.facts] == ["clean"]


def test_validation_strips_out_of_batch_sources_but_keeps_the_fact():
    """배치 밖 발화 id만 떼어내고, 유효한 출처가 남으면 fact를 살린다."""
    topic_id = uuid4()
    source = _utterance(topic_id, "중력식 물탱크로 정하자.")
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="decision-1",
                topic_id=topic_id,
                fact_type=DesignFactType.DECISION,
                content="중력식 물탱크를 쓴다.",
                source_utterance_ids=[source.utterance_id, uuid4()],
                confidence=0.9,
            )
        ]
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source),
        analysis=analysis,
    )

    assert len(validated.facts) == 1
    assert validated.facts[0].source_utterance_ids == [source.utterance_id]


def test_validation_keeps_first_of_duplicate_temp_ids():
    topic_id = uuid4()
    source = _utterance(topic_id)
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="dup",
                topic_id=topic_id,
                fact_type=DesignFactType.PROPOSAL,
                content="먼저 온 fact",
                source_utterance_ids=[source.utterance_id],
                confidence=0.9,
            ),
            FactCandidate(
                temp_id="dup",
                topic_id=topic_id,
                fact_type=DesignFactType.PROPOSAL,
                content="나중에 온 fact",
                source_utterance_ids=[source.utterance_id],
                confidence=0.9,
            ),
        ]
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source),
        analysis=analysis,
    )

    assert [item.content for item in validated.facts] == ["먼저 온 fact"]


def test_validation_drops_self_link_without_failing_the_batch():
    topic_id = uuid4()
    source = _utterance(topic_id)
    reference = FactReference(reference_type="CANDIDATE", reference_id="fact-1")
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="fact-1",
                topic_id=topic_id,
                fact_type=DesignFactType.PROPOSAL,
                content="유일한 fact",
                source_utterance_ids=[source.utterance_id],
                confidence=0.9,
            )
        ],
        links=[
            FactLinkCandidate(
                source=reference,
                target=reference,
                link_type=DesignFactLinkType.SUPPORTS,
                confidence=0.9,
            )
        ],
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source),
        analysis=analysis,
    )

    assert len(validated.facts) == 1
    assert validated.links == []


def test_validation_drops_link_to_unknown_fact_without_failing_the_batch():
    topic_id = uuid4()
    source = _utterance(topic_id)
    analysis = BatchAnalysisResult(
        facts=[
            FactCandidate(
                temp_id="fact-1",
                topic_id=topic_id,
                fact_type=DesignFactType.RATIONALE,
                content="근거 fact",
                source_utterance_ids=[source.utterance_id],
                confidence=0.9,
            )
        ],
        links=[
            FactLinkCandidate(
                source=FactReference(reference_type="CANDIDATE", reference_id="fact-1"),
                target=FactReference(
                    reference_type="EXISTING", reference_id=str(uuid4())
                ),
                link_type=DesignFactLinkType.RATIONALE_OF,
                confidence=0.9,
            )
        ],
    )

    validated = _reflection_service().validate_analysis(
        context=_validation_context(source),
        analysis=analysis,
    )

    assert len(validated.facts) == 1
    assert validated.links == []
