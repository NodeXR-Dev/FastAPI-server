from functools import lru_cache
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.node.trigger_router_node import TriggerRouterNode
from app.agent.schema.realtime_agent_schema import (
    AgentResponse,
    GenerationRequest,
    GuardResult,
    TriggerResult,
)
from app.agent.state.realtime_agent_state import RealtimeAgentState
from app.agent.subgraph.conflict_recall_graph import ConflictRecallGraph
from app.agent.subgraph.memory_guard_graph import MemoryGuardGraph
from app.agent.subgraph.rationale_recall_graph import RationaleRecallGraph
from app.core.logger import get_logger
from app.service.agent.realtime_agent_result_service import RealtimeAgentResultService

logger = get_logger(__name__)


class RealtimeAgentGraph:
    def __init__(
        self,
        *,
        trigger_router: TriggerRouterNode | None = None,
        memory_guard: MemoryGuardGraph | None = None,
        rationale_recall: RationaleRecallGraph | None = None,
        conflict_recall: ConflictRecallGraph | None = None,
        result_service: RealtimeAgentResultService | None = None,
    ) -> None:
        self.trigger_router = trigger_router or TriggerRouterNode()
        self.memory_guard_graph = (memory_guard or MemoryGuardGraph()).graph
        self.rationale_recall_graph = (
            rationale_recall or RationaleRecallGraph()
        ).graph
        self.conflict_recall_graph = (
            conflict_recall or ConflictRecallGraph()
        ).graph
        self.result_service = result_service or RealtimeAgentResultService()
        self.graph = self._compile()

    def _compile(self):
        builder = StateGraph(RealtimeAgentState)
        builder.add_node(
            "classify_triggers",
            self.trigger_router.classify_triggers,
        )
        builder.add_node("memory_guard", self.run_memory_guard)
        builder.add_node("rationale_recall", self.run_rationale_recall)
        builder.add_node("conflict_recall", self.run_conflict_recall)
        builder.add_node("asset_generation", self.run_asset_generation)
        builder.add_node("collect_results", self.collect_results)
        builder.add_node("persist_and_notify", self.persist_and_notify)

        builder.add_edge(START, "classify_triggers")
        builder.add_conditional_edges(
            "classify_triggers",
            self.route_triggers,
            [
                "memory_guard",
                "rationale_recall",
                "conflict_recall",
                "asset_generation",
                "collect_results",
            ],
        )
        for branch in (
            "memory_guard",
            "rationale_recall",
            "conflict_recall",
            "asset_generation",
        ):
            builder.add_edge(branch, "collect_results")
        builder.add_edge("collect_results", "persist_and_notify")
        builder.add_edge("persist_and_notify", END)
        return builder.compile(name="RealtimeAgentGraph")

    async def ainvoke(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        utterance_id: UUID,
        original_text: str,
        normalized_text: str,
        embedding: list[float],
        topic_id: UUID,
    ) -> RealtimeAgentState:
        initial_state: RealtimeAgentState = {
            "room_id": room_id,
            "user_id": user_id,
            "utterance_id": utterance_id,
            "original_text": original_text,
            "normalized_text": normalized_text,
            "embedding": embedding,
            "topic_id": topic_id,
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
        config: RunnableConfig = {
            "run_name": "RealtimeAgentGraph",
            "tags": ["realtime-agent", "utterance-hot-path"],
            "metadata": {
                "graph_name": "RealtimeAgentGraph",
                "room_id": str(room_id),
                "utterance_id": str(utterance_id),
                "topic_id": str(topic_id),
            },
            "max_concurrency": 4,
        }
        return await self.graph.ainvoke(initial_state, config=config)

    @staticmethod
    def route_triggers(state: RealtimeAgentState) -> list[str]:
        triggers = state["triggers"]
        routes: list[str] = []
        if triggers.memory_guard:
            routes.append("memory_guard")
        if triggers.rationale_recall:
            routes.append("rationale_recall")
        if triggers.conflict_recall:
            routes.append("conflict_recall")
        if triggers.asset_generation:
            routes.append("asset_generation")
        return routes or ["collect_results"]

    async def run_memory_guard(
        self,
        state: RealtimeAgentState,
        config: RunnableConfig,
    ) -> dict:
        return await self._run_subgraph(
            name="memory_guard",
            graph=self.memory_guard_graph,
            state=state,
            config=config,
            output_keys=("retrieved_facts", "alerts", "errors"),
        )

    async def run_rationale_recall(
        self,
        state: RealtimeAgentState,
        config: RunnableConfig,
    ) -> dict:
        return await self._run_subgraph(
            name="rationale_recall",
            graph=self.rationale_recall_graph,
            state=state,
            config=config,
            output_keys=(
                "retrieved_facts",
                "retrieved_memories",
                "fact_links",
                "source_utterances",
                "responses",
                "errors",
            ),
        )

    async def run_conflict_recall(
        self,
        state: RealtimeAgentState,
        config: RunnableConfig,
    ) -> dict:
        return await self._run_subgraph(
            name="conflict_recall",
            graph=self.conflict_recall_graph,
            state=state,
            config=config,
            output_keys=(
                "retrieved_facts",
                "fact_links",
                "source_utterances",
                "responses",
                "errors",
            ),
        )

    async def run_asset_generation(self, state: RealtimeAgentState) -> dict:
        triggers = state["triggers"]
        if triggers.asset_type == "NONE":
            return {
                "responses": [
                    AgentResponse(
                        response_type="ASSET_GENERATION",
                        message="생성할 Asset 유형을 확인하지 못했습니다.",
                    )
                ]
            }
        return {
            "generation_requests": [
                GenerationRequest(
                    asset_type=triggers.asset_type,
                    source_asset_id=triggers.source_asset_id,
                )
            ]
        }

    @staticmethod
    def collect_results(state: RealtimeAgentState) -> dict:
        return {}

    async def persist_and_notify(self, state: RealtimeAgentState) -> dict:
        try:
            events = await self.result_service.persist_and_build_events(
                room_id=state["room_id"],
                user_id=state["user_id"],
                utterance_id=state["utterance_id"],
                topic_id=state["topic_id"],
                alerts=state["alerts"],
                responses=state["responses"],
                generation_requests=state["generation_requests"],
            )
            return {"ws_events": events}
        except Exception as error:
            logger.exception(
                "[agent_result_persist_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": ["persist_and_notify_failed"]}

    @staticmethod
    async def _run_subgraph(
        *,
        name: str,
        graph: Any,
        state: RealtimeAgentState,
        config: RunnableConfig,
        output_keys: tuple[str, ...],
    ) -> dict:
        try:
            child_config = dict(config)
            child_config["run_name"] = name
            result = await graph.ainvoke(state, config=child_config)
            return {key: result[key] for key in output_keys if result.get(key)}
        except Exception as error:
            logger.exception(
                "[agent_subgraph_failed] subgraph=%s | room_id=%s | utterance_id=%s | error=%s",
                name,
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": [f"{name}_failed"]}


@lru_cache(maxsize=1)
def get_realtime_agent_graph() -> RealtimeAgentGraph:
    return RealtimeAgentGraph()
