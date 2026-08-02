import asyncio
from functools import lru_cache
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langsmith.run_helpers import get_current_run_tree

from app.agent.node.reflection_batch_node import ReflectionBatchNode
from app.agent.schema.reflection_batch_schema import (
    BatchAnalysisResult,
)
from app.agent.state.reflection_batch_state import ReflectionBatchState
from app.core.logger import get_logger
from app.service.agent.reflection_batch_service import (
    InvalidFactRelationshipError,
    ReflectionBatchService,
)

logger = get_logger(__name__)


class ReflectionBatchGraph:
    def __init__(
        self,
        *,
        service: ReflectionBatchService | None = None,
        node: ReflectionBatchNode | None = None,
    ) -> None:
        self.service = service or ReflectionBatchService()
        self.node = node or ReflectionBatchNode()
        self.graph = self._compile()

    def _compile(self):
        builder = StateGraph(ReflectionBatchState)
        builder.add_node("load_batch_data", self.load_batch_data)
        builder.add_node("retrieve_related_context", self.retrieve_related_context)
        builder.add_node("build_batch_context", self.build_batch_context)
        builder.add_node("analyze_batch", self.analyze_batch)
        builder.add_node("validate_analysis", self.validate_analysis)
        builder.add_node("deduplicate_facts", self.deduplicate_facts)
        builder.add_node("semantic_memory_generation", self.generate_semantic_memory)
        builder.add_node("topic_summary_generation", self.generate_topic_summaries)
        builder.add_node("persist_reflection", self.persist_reflection)

        builder.add_edge(START, "load_batch_data")
        builder.add_conditional_edges("load_batch_data", self.route_after_load)
        builder.add_edge("retrieve_related_context", "build_batch_context")
        builder.add_edge("build_batch_context", "analyze_batch")
        builder.add_edge("analyze_batch", "validate_analysis")
        builder.add_edge("validate_analysis", "deduplicate_facts")
        builder.add_edge("deduplicate_facts", "semantic_memory_generation")
        builder.add_edge("semantic_memory_generation", "topic_summary_generation")
        builder.add_edge("topic_summary_generation", "persist_reflection")
        builder.add_edge("persist_reflection", END)
        return builder.compile(name="ReflectionBatchGraph")

    async def ainvoke(
        self,
        *,
        room_id: UUID,
        batch_run_id: UUID | None = None,
    ) -> ReflectionBatchState:
        run_id = batch_run_id or uuid4()
        initial_state: ReflectionBatchState = {
            "batch_run_id": run_id,
            "room_id": room_id,
            "utterances": [],
            "graph_events": [],
            "topic_ids": [],
            "topics": [],
            "existing_facts": [],
            "semantic_memories": [],
            "batch_context": None,
            "analysis_result": None,
            "prepared_reflection": None,
            "memory_updates": [],
            "topic_updates": [],
            "persistence_result": None,
        }
        config: RunnableConfig = {
            "run_name": "ReflectionBatchGraph",
            "tags": ["node-xr", "reflection-batch", "cold-path"],
            "metadata": {
                "graph_name": "reflection_batch",
                "batch_run_id": str(run_id),
                "room_id": str(room_id),
            },
        }
        return await self.graph.ainvoke(initial_state, config=config)

    async def load_batch_data(self, state: ReflectionBatchState) -> dict:
        utterances, graph_events, topic_ids = await asyncio.to_thread(
            self.service.load_batch_data,
            room_id=state["room_id"],
        )
        self._add_trace_counts(
            utterance_count=len(utterances),
            graph_event_count=len(graph_events),
            topic_count=len(topic_ids),
        )
        return {
            "utterances": utterances,
            "graph_events": graph_events,
            "topic_ids": topic_ids,
        }

    @staticmethod
    def route_after_load(state: ReflectionBatchState) -> str:
        if state["utterances"] or state["graph_events"]:
            return "retrieve_related_context"
        return END

    async def retrieve_related_context(self, state: ReflectionBatchState) -> dict:
        topics, facts, memories = await asyncio.to_thread(
            self.service.retrieve_related_context,
            room_id=state["room_id"],
            topic_ids=state["topic_ids"],
            graph_events=state["graph_events"],
        )
        return {
            "topics": topics,
            "existing_facts": facts,
            "semantic_memories": memories,
        }

    def build_batch_context(self, state: ReflectionBatchState) -> dict:
        return {
            "batch_context": self.service.build_context(
                room_id=state["room_id"],
                utterances=state["utterances"],
                graph_events=state["graph_events"],
                topics=state["topics"],
                existing_facts=state["existing_facts"],
                semantic_memories=state["semantic_memories"],
            )
        }

    async def analyze_batch(self, state: ReflectionBatchState) -> dict:
        context = self._require_context(state)
        return {"analysis_result": await self.node.analyze(context)}

    async def validate_analysis(self, state: ReflectionBatchState) -> dict:
        context = self._require_context(state)
        analysis = state["analysis_result"] or BatchAnalysisResult()

        try:
            validated = self.service.validate_analysis(
                context=context,
                analysis=analysis,
            )
        except InvalidFactRelationshipError as error:
            logger.warning(
                "[reflection_relationship_repair_started] room_id=%s | error=%s",
                state["room_id"],
                str(error),
            )
            try:
                repaired_analysis = await self.node.repair_analysis_relationships(
                    context=context,
                    analysis=analysis,
                    validation_error=str(error),
                )
                relationship_repair = BatchAnalysisResult(
                    facts=analysis.facts,
                    links=repaired_analysis.links,
                )
                validated = self.service.validate_analysis(
                    context=context,
                    analysis=relationship_repair,
                    discard_invalid_relationships=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception as repair_error:
                logger.exception(
                    "[reflection_relationship_repair_failed] room_id=%s | error=%s",
                    state["room_id"],
                    str(repair_error),
                )
                repaired_analysis = analysis
                validated = self.service.validate_analysis(
                    context=context,
                    analysis=analysis,
                    discard_invalid_relationships=True,
                )
            logger.info(
                "[reflection_relationship_repair_completed] room_id=%s | "
                "original_link_count=%s | repaired_link_count=%s | accepted_link_count=%s",
                state["room_id"],
                len(analysis.links),
                len(repaired_analysis.links),
                len(validated.links),
            )

        return {
            "analysis_result": validated,
        }

    async def deduplicate_facts(self, state: ReflectionBatchState) -> dict:
        return {
            "prepared_reflection": await self.service.deduplicate_facts(
                room_id=state["room_id"],
                context=self._require_context(state),
                analysis=state["analysis_result"] or BatchAnalysisResult(),
                node=self.node,
            )
        }

    async def generate_semantic_memory(self, state: ReflectionBatchState) -> dict:
        prepared = self._require_prepared(state)
        proposals = await self.node.generate_memories(
            prepared,
            self._require_context(state),
        )
        return {
            "memory_updates": self.service.validate_memory_updates(
                context=self._require_context(state),
                prepared=prepared,
                proposals=proposals.memories,
            )
        }

    async def generate_topic_summaries(self, state: ReflectionBatchState) -> dict:
        prepared = self._require_prepared(state)
        if not prepared.changed_topic_ids:
            return {"topic_updates": []}
        topic_context = self.service.build_topic_summary_context(
            context=self._require_context(state),
            prepared=prepared,
            memory_updates=state["memory_updates"],
        )
        proposals = await self.node.summarize_topics(topic_context)
        return {
            "topic_updates": self.service.validate_topic_updates(
                changed_topic_ids=prepared.changed_topic_ids,
                proposals=proposals.topics,
            )
        }

    async def persist_reflection(self, state: ReflectionBatchState) -> dict:
        result = await asyncio.to_thread(
            self.service.persist_reflection,
            room_id=state["room_id"],
            utterance_ids=[item.utterance_id for item in state["utterances"]],
            graph_event_ids=[item.graph_event_id for item in state["graph_events"]],
            prepared=self._require_prepared(state),
            memory_updates=state["memory_updates"],
            topic_updates=state["topic_updates"],
        )
        return {"persistence_result": result}

    @staticmethod
    def _require_context(state: ReflectionBatchState):
        context = state["batch_context"]
        if context is None:
            raise ValueError("batch context is not available")
        return context

    @staticmethod
    def _require_prepared(state: ReflectionBatchState):
        prepared = state["prepared_reflection"]
        if prepared is None:
            raise ValueError("prepared reflection is not available")
        return prepared

    @staticmethod
    def _add_trace_counts(
        *,
        utterance_count: int,
        graph_event_count: int,
        topic_count: int,
    ) -> None:
        run_tree = get_current_run_tree()
        if run_tree is None:
            return
        while run_tree.parent_run is not None:
            run_tree = run_tree.parent_run
        run_tree.add_metadata(
            {
                "utterance_count": utterance_count,
                "graph_event_count": graph_event_count,
                "topic_count": topic_count,
            }
        )


@lru_cache(maxsize=1)
def get_reflection_batch_graph() -> ReflectionBatchGraph:
    return ReflectionBatchGraph()
