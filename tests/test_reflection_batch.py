import asyncio
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
    TopicSummaryProposal,
    TopicSummaryProposalBundle,
)
from app.model.enum import (
    DesignFactLinkType,
    DesignFactStatus,
    DesignFactType,
    SemanticMemoryType,
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


def test_validation_rejects_fact_without_batch_provenance():
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

    with pytest.raises(ValueError, match="outside the batch"):
        service.validate_analysis(context=context, analysis=analysis)


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
