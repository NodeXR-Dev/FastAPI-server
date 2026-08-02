import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.agent.graph.realtime_agent_graph import RealtimeAgentGraph
from app.agent.node.trigger_router_node import TriggerRouterNode
from app.agent.schema.realtime_agent_schema import (
    AgentResponse,
    FactLinkRecord,
    FactRecord,
    GuardResult,
    SourceUtteranceRecord,
    TriggerResult,
)
from app.agent.subgraph.conflict_recall_graph import ConflictRecallGraph
from app.agent.subgraph.memory_guard_graph import MemoryGuardGraph
from app.agent.subgraph.rationale_recall_graph import RationaleRecallGraph
from app.repository.topic_repository import TopicMatch
from app.service.agent.asset_generation_adapter import AssetGenerationAdapter
from app.service.websocket.connection_manager import RoomConnectionManager
from app.service.agent.realtime_agent_result_service import RealtimeAgentResultService
from app.service.utterance.auto_utterance_service import AutoUtteranceService
from app.service.utterance.topic_routing_service import TopicRoutingService
from app.api import ws_room_event


class StructuredFakeLLM:
    def __init__(self, responder):
        self.responder = responder

    def with_structured_output(self, _schema):
        return RunnableLambda(self.responder)


def make_state(*, normalized_text: str = "테스트 발화") -> dict:
    return {
        "room_id": uuid4(),
        "user_id": uuid4(),
        "utterance_id": uuid4(),
        "original_text": normalized_text,
        "normalized_text": normalized_text,
        "embedding": [0.1, 0.2, 0.3],
        "topic_id": uuid4(),
        "triggers": TriggerResult(),
        "guard_result": GuardResult(),
        "guard_passed": False,
        "retrieved_facts": [],
        "retrieved_memories": [],
        "fact_links": [],
        "source_utterances": [],
        "alerts": [],
        "responses": [],
        "generation_requests": [],
        "ws_events": [],
        "errors": [],
    }


def test_topic_routes_to_similar_active_topic_and_updates_incremental_centroid():
    room_id = uuid4()
    utterance_id = uuid4()
    topic_id = uuid4()
    topic = SimpleNamespace(
        topic_id=topic_id,
        centroid_embedding=[0.2, 0.4],
    )
    topic_repository = Mock()
    topic_repository.find_most_similar_active_topic.return_value = TopicMatch(
        topic=topic,
        similarity=0.91,
    )
    topic_repository.count_linked_utterances.return_value = 3
    utterance_repository = Mock()
    service = TopicRoutingService(
        topic_repository=topic_repository,
        utterance_repository=utterance_repository,
        similarity_threshold=0.75,
    )

    result = service.route_topic(
        Mock(),
        room_id=room_id,
        utterance_id=utterance_id,
        normalized_text="의자 재질",
        embedding=[0.6, 0.0],
    )

    assert result == topic_id
    topic_repository.create.assert_not_called()
    assert topic_repository.update_centroid.call_args.kwargs["centroid_embedding"] == pytest.approx(
        [0.3, 0.3]
    )
    utterance_repository.update.assert_called_once()


def test_topic_creates_new_topic_when_similarity_is_below_threshold():
    new_topic_id = uuid4()
    topic_repository = Mock()
    topic_repository.find_most_similar_active_topic.return_value = TopicMatch(
        topic=SimpleNamespace(topic_id=uuid4()),
        similarity=0.4,
    )
    topic_repository.create.return_value = SimpleNamespace(topic_id=new_topic_id)
    utterance_repository = Mock()
    service = TopicRoutingService(
        topic_repository=topic_repository,
        utterance_repository=utterance_repository,
        similarity_threshold=0.75,
    )

    result = service.route_topic(
        Mock(),
        room_id=uuid4(),
        utterance_id=uuid4(),
        normalized_text="완전히 새로운 주제",
        embedding=[0.1, 0.9],
    )

    assert result == new_topic_id
    assert topic_repository.create.call_args.kwargs["centroid_embedding"] == [0.1, 0.9]
    topic_repository.update_centroid.assert_not_called()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("의자 다리를 좀 길게 해보죠.", TriggerResult()),
        (
            "왜 이 소재로 결정했었지?",
            TriggerResult(rationale_recall=True),
        ),
        (
            "아까 반대 의견이 뭐였지?",
            TriggerResult(conflict_recall=True),
        ),
        (
            "이걸 이미지로 만들어줘.",
            TriggerResult(asset_generation=True, asset_type="IMAGE_2D"),
        ),
        (
            "왜 알루미늄으로 정했는지 알려주고 그 기준으로 이미지 만들어줘.",
            TriggerResult(
                rationale_recall=True,
                asset_generation=True,
                asset_type="IMAGE_2D",
            ),
        ),
    ],
)
def test_trigger_router_supports_no_single_and_multi_trigger(text, expected):
    def classify(prompt):
        prompt_text = prompt.messages[-1].content
        if "알루미늄" in prompt_text:
            return TriggerResult(
                rationale_recall=True,
                asset_generation=True,
                asset_type="IMAGE_2D",
            )
        if "왜 이 소재" in prompt_text:
            return TriggerResult(rationale_recall=True)
        if "반대 의견" in prompt_text:
            return TriggerResult(conflict_recall=True)
        if "이미지로" in prompt_text:
            return TriggerResult(asset_generation=True, asset_type="IMAGE_2D")
        return TriggerResult()

    node = TriggerRouterNode(llm=StructuredFakeLLM(classify))
    result = asyncio.run(node.classify_triggers(make_state(normalized_text=text)))

    assert result["triggers"] == expected


def test_memory_guard_creates_alert_for_grounded_high_confidence_violation():
    fact_id = uuid4()
    retrieval_service = Mock()
    retrieval_service.retrieve_guard_facts.return_value = [
        FactRecord(
            design_fact_id=fact_id,
            topic_id=uuid4(),
            fact_type="CONSTRAINT",
            status="ACTIVE",
            content="목재만 사용한다.",
        )
    ]
    llm = StructuredFakeLLM(
        lambda _prompt: GuardResult(
            violated=True,
            violation_type="CONSTRAINT",
            related_fact_ids=[fact_id],
            confidence=0.95,
            reason="플라스틱 사용은 목재 전용 제약과 충돌합니다.",
        )
    )
    graph = MemoryGuardGraph(
        retrieval_service=retrieval_service,
        llm=llm,
        alert_threshold=0.8,
    ).graph

    result = asyncio.run(
        graph.ainvoke(make_state(normalized_text="플라스틱으로 만들자."))
    )

    assert len(result["alerts"]) == 1
    assert result["alerts"][0].related_fact_id == fact_id
    assert result["alerts"][0].alert_type == "CONSTRAINT_VIOLATION"


def test_memory_guard_without_relevant_fact_does_not_call_llm_or_create_alert():
    retrieval_service = Mock()
    retrieval_service.retrieve_guard_facts.return_value = []
    llm = StructuredFakeLLM(Mock(side_effect=AssertionError("LLM should not run")))
    graph = MemoryGuardGraph(
        retrieval_service=retrieval_service,
        llm=llm,
        alert_threshold=0.8,
    ).graph

    result = asyncio.run(graph.ainvoke(make_state()))

    assert result["alerts"] == []


def test_rationale_recall_tracks_fact_links_and_source_utterance_provenance():
    decision_id = uuid4()
    rationale_id = uuid4()
    source_id = uuid4()
    decision = FactRecord(
        design_fact_id=decision_id,
        fact_type="DECISION",
        status="CONFIRMED",
        content="알루미늄을 사용한다.",
    )
    rationale = FactRecord(
        design_fact_id=rationale_id,
        fact_type="RATIONALE",
        status="ACTIVE",
        content="가볍고 재활용하기 쉽다.",
    )
    retrieval_service = Mock()
    retrieval_service.retrieve_rationale_seeds.return_value = ([decision], [])
    retrieval_service.retrieve_related_context.return_value = (
        [decision, rationale],
        [
            FactLinkRecord(
                from_fact_id=rationale_id,
                to_fact_id=decision_id,
                link_type="RATIONALE_OF",
            )
        ],
        [
            SourceUtteranceRecord(
                utterance_id=source_id,
                design_fact_id=rationale_id,
                link_role="SOURCE",
                original_text="가볍고 재활용하기 쉬워요.",
            )
        ],
    )
    graph = RationaleRecallGraph(
        retrieval_service=retrieval_service,
        llm=RunnableLambda(lambda _prompt: AIMessage(content="가볍고 재활용하기 쉽기 때문입니다.")),
    ).graph

    result = asyncio.run(graph.ainvoke(make_state(normalized_text="왜 정했지?")))

    assert result["fact_links"][0].link_type == "RATIONALE_OF"
    assert result["responses"][0].source_utterance_ids == [source_id]
    assert set(result["responses"][0].related_fact_ids) == {decision_id, rationale_id}


def test_conflict_recall_preserves_support_and_opposition_relationships():
    conflict_id = uuid4()
    for_id = uuid4()
    against_id = uuid4()
    source_id = uuid4()
    conflict = FactRecord(
        design_fact_id=conflict_id,
        fact_type="CONFLICT",
        status="ACTIVE",
        content="재료 선택 논쟁",
    )
    retrieval_service = Mock()
    retrieval_service.retrieve_conflict_seeds.return_value = [conflict]
    retrieval_service.retrieve_related_context.return_value = (
        [
            conflict,
            FactRecord(
                design_fact_id=for_id,
                fact_type="ARGUMENT_FOR",
                status="ACTIVE",
                content="가볍다.",
            ),
            FactRecord(
                design_fact_id=against_id,
                fact_type="ARGUMENT_AGAINST",
                status="ACTIVE",
                content="비싸다.",
            ),
        ],
        [
            FactLinkRecord(
                from_fact_id=for_id,
                to_fact_id=conflict_id,
                link_type="SUPPORTS",
            ),
            FactLinkRecord(
                from_fact_id=against_id,
                to_fact_id=conflict_id,
                link_type="OPPOSES",
            ),
        ],
        [
            SourceUtteranceRecord(
                utterance_id=source_id,
                design_fact_id=against_id,
                link_role="OPPOSING_EVIDENCE",
                original_text="가격이 너무 비싸요.",
            )
        ],
    )
    graph = ConflictRecallGraph(
        retrieval_service=retrieval_service,
        llm=RunnableLambda(lambda _prompt: AIMessage(content="찬성은 경량성, 반대는 가격이었습니다.")),
    ).graph

    result = asyncio.run(graph.ainvoke(make_state(normalized_text="반대가 뭐였지?")))

    assert {link.link_type for link in result["fact_links"]} == {"SUPPORTS", "OPPOSES"}
    assert result["responses"][0].source_utterance_ids == [source_id]


def test_parallel_branch_failure_does_not_drop_asset_generation_request():
    class TriggerStub:
        async def classify_triggers(self, _state):
            return {
                "triggers": TriggerResult(
                    rationale_recall=True,
                    asset_generation=True,
                    asset_type="IMAGE_2D",
                )
            }

    async def fail_branch(_state):
        raise RuntimeError("rationale failed")

    empty_graph = SimpleNamespace(graph=RunnableLambda(lambda _state: {}))
    failing_graph = SimpleNamespace(graph=RunnableLambda(fail_branch))
    result_service = Mock()
    result_service.persist_and_build_events = AsyncMock(
        return_value=[{"event_type": "AGENT_GUIDE"}],
    )
    graph = RealtimeAgentGraph(
        trigger_router=TriggerStub(),
        memory_guard=empty_graph,
        rationale_recall=failing_graph,
        conflict_recall=empty_graph,
        result_service=result_service,
    )
    state = make_state(normalized_text="근거를 알려주고 이미지도 만들어줘")

    result = asyncio.run(
        graph.ainvoke(
            room_id=state["room_id"],
            user_id=state["user_id"],
            utterance_id=state["utterance_id"],
            original_text=state["original_text"],
            normalized_text=state["normalized_text"],
            embedding=state["embedding"],
            topic_id=state["topic_id"],
        )
    )

    assert "rationale_recall_failed" in result["errors"]
    requests = result_service.persist_and_build_events.call_args.kwargs[
        "generation_requests"
    ]
    assert len(requests) == 1
    assert requests[0].asset_type == "IMAGE_2D"
    assert result["ws_events"] == [{"event_type": "AGENT_GUIDE"}]


def test_trigger_timeout_keeps_committed_utterance(monkeypatch):
    from app.service.utterance import auto_utterance_service as module

    monkeypatch.setattr(module, "trace", lambda *args, **kwargs: nullcontext())
    room_id = uuid4()
    user_id = uuid4()
    utterance_id = uuid4()
    topic_id = uuid4()
    db = Mock()
    room_repository = Mock()
    room_repository.find_room_by_id.return_value = SimpleNamespace(is_active=True)
    room_repository.find_joined_member_by_user_id.return_value = SimpleNamespace()
    utterance_repository = Mock()
    utterance_repository.create.return_value = SimpleNamespace(
        utterance_id=utterance_id,
    )
    graph = Mock()
    graph.ainvoke = AsyncMock(side_effect=TimeoutError("trigger timeout"))
    service = AutoUtteranceService(
        db,
        text_preprocess_service=Mock(
            utterance_preprocess=Mock(return_value="정규화 발화")
        ),
        embedding_service=Mock(embed_text=Mock(return_value=[0.1, 0.2])),
        topic_routing_service=Mock(
            route_topic=Mock(return_value=topic_id),
        ),
        utterance_repository=utterance_repository,
        room_repository=room_repository,
        realtime_agent_graph=graph,
    )

    events = asyncio.run(
        service.handle_auto_utterance(
            room_id=room_id,
            user_id=user_id,
            payload={"utterance": "원본 발화"},
        )
    )

    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert events[0]["payload"]["utterance_id"] == str(utterance_id)
    assert events[0]["payload"]["topic_id"] == str(topic_id)


def test_asset_adapter_enqueues_existing_2d_task_without_waiting():
    task_service = Mock()
    task_service.generate_from_features = AsyncMock(return_value=None)
    adapter = AssetGenerationAdapter(
        image_2d_task_service=task_service,
        model_3d_service=Mock(),
    )
    room_id = uuid4()
    user_id = uuid4()

    async def run():
        response = await adapter.enqueue(
            room_id=room_id,
            user_id=user_id,
            request=SimpleNamespace(asset_type="IMAGE_2D", source_asset_id=None),
        )
        await asyncio.sleep(0)
        return response

    response = asyncio.run(run())

    task_service.generate_from_features.assert_awaited_once_with(
        room_id=room_id,
        user_id=user_id,
        job_id=None,
    )
    assert response == AgentResponse(
        response_type="ASSET_GENERATION",
        message="2D 이미지 생성 요청을 접수했습니다.",
    )


def test_asset_enqueue_failure_does_not_drop_recall_response():
    db = Mock()
    asset_adapter = Mock()
    asset_adapter.enqueue = AsyncMock(side_effect=RuntimeError("invalid source"))
    service = RealtimeAgentResultService(
        session_factory=Mock(return_value=db),
        agent_repository=Mock(),
        asset_adapter=asset_adapter,
    )

    events = asyncio.run(
        service.persist_and_build_events(
            room_id=uuid4(),
            user_id=uuid4(),
            utterance_id=uuid4(),
            topic_id=uuid4(),
            alerts=[],
            responses=[
                AgentResponse(
                    response_type="RATIONALE_RECALL",
                    message="저장된 근거입니다.",
                )
            ],
            generation_requests=[
                SimpleNamespace(asset_type="MODEL_3D", source_asset_id=uuid4())
            ],
        )
    )

    assert [event["payload"]["guide_type"] for event in events] == [
        "RATIONALE_RECALL",
        "ASSET_GENERATION",
    ]
    assert events[0]["payload"]["message"] == "저장된 근거입니다."
    assert events[1]["payload"]["message"] == "Asset 생성 요청을 처리하지 못했습니다."


def test_websocket_sends_all_prepared_events_only_to_request_socket(monkeypatch):
    manager = Mock()
    manager.send_personal_message = AsyncMock()
    monkeypatch.setattr(ws_room_event, "room_ws_manager", manager)
    websocket = Mock()
    events = [
        {"event_type": "UTTERANCE_CREATED"},
        {"event_type": "AGENT_GUIDE"},
    ]

    asyncio.run(
        ws_room_event.send_server_events_to_requester(
            websocket=websocket,
            server_events=events,
        )
    )

    assert manager.send_personal_message.await_count == 2
    assert [
        call.args[1]
        for call in manager.send_personal_message.await_args_list
    ] == events
    assert all(
        call.args[0] is websocket
        for call in manager.send_personal_message.await_args_list
    )


def test_connection_manager_sends_to_matching_user_without_room_multicast():
    room_id = uuid4()
    requester_id = uuid4()
    other_user_id = uuid4()
    requester_socket = Mock()
    requester_socket.send_json = AsyncMock()
    other_socket = Mock()
    other_socket.send_json = AsyncMock()
    manager = RoomConnectionManager()
    manager.register(
        room_id=room_id,
        websocket=requester_socket,
        user_id=requester_id,
    )
    manager.register(
        room_id=room_id,
        websocket=other_socket,
        user_id=other_user_id,
    )
    message = {"event_type": "2D_GENERATED", "job_id": str(uuid4())}

    sent = asyncio.run(
        manager.send_to_user(
            room_id=room_id,
            user_id=requester_id,
            message=message,
        )
    )

    assert sent is True
    requester_socket.send_json.assert_awaited_once_with(message)
    other_socket.send_json.assert_not_awaited()
