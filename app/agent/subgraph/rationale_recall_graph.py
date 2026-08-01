import asyncio

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.rationale_recall_prompt import RATIONALE_RECALL_PROMPT
from app.agent.schema.realtime_agent_schema import AgentResponse
from app.agent.state.realtime_agent_state import RealtimeAgentState
from app.agent.subgraph.recall_context import build_evidence_context, message_text
from app.core.logger import get_logger
from app.model.enum import DesignFactLinkType
from app.service.agent.memory_retrieval_service import MemoryRetrievalService

logger = get_logger(__name__)


class RationaleRecallGraph:
    def __init__(
        self,
        *,
        retrieval_service: MemoryRetrievalService | None = None,
        llm: BaseChatModel | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service or MemoryRetrievalService()
        self.response_chain = RATIONALE_RECALL_PROMPT | (llm or get_agent_llm())
        self.graph = self._compile()

    def _compile(self):
        builder = StateGraph(RealtimeAgentState)
        builder.add_node("retrieve_memory", self.retrieve_memory)
        builder.add_node("retrieve_links", self.retrieve_links)
        builder.add_node("generate_response", self.generate_response)
        builder.add_edge(START, "retrieve_memory")
        builder.add_edge("retrieve_memory", "retrieve_links")
        builder.add_edge("retrieve_links", "generate_response")
        builder.add_edge("generate_response", END)
        return builder.compile(name="RationaleRecall")

    async def retrieve_memory(self, state: RealtimeAgentState) -> dict:
        try:
            facts, memories = await asyncio.to_thread(
                self.retrieval_service.retrieve_rationale_seeds,
                room_id=state["room_id"],
                topic_id=state["topic_id"],
                embedding=state["embedding"],
            )
            return {
                "retrieved_facts": facts,
                "retrieved_memories": memories,
            }
        except Exception as error:
            logger.exception(
                "[rationale_retrieval_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": ["rationale_retrieval_failed"]}

    async def retrieve_links(self, state: RealtimeAgentState) -> dict:
        if not state["retrieved_facts"]:
            return {}
        try:
            facts, links, utterances = await asyncio.to_thread(
                self.retrieval_service.retrieve_related_context,
                room_id=state["room_id"],
                seed_facts=state["retrieved_facts"],
                link_types=[
                    DesignFactLinkType.RATIONALE_OF,
                    DesignFactLinkType.SUPPORTS,
                ],
            )
            seed_ids = {fact.design_fact_id for fact in state["retrieved_facts"]}
            return {
                "retrieved_facts": [
                    fact for fact in facts if fact.design_fact_id not in seed_ids
                ],
                "fact_links": links,
                "source_utterances": utterances,
            }
        except Exception as error:
            logger.exception(
                "[rationale_link_retrieval_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": ["rationale_link_retrieval_failed"]}

    async def generate_response(self, state: RealtimeAgentState) -> dict:
        if not state["retrieved_facts"] and not state["retrieved_memories"]:
            return {
                "responses": [
                    AgentResponse(
                        response_type="RATIONALE_RECALL",
                        message="저장된 근거를 찾지 못했습니다.",
                    )
                ]
            }
        try:
            response = await self.response_chain.ainvoke(
                {
                    "normalized_text": state["normalized_text"],
                    "evidence_context": build_evidence_context(
                        facts=state["retrieved_facts"],
                        memories=state["retrieved_memories"],
                        links=state["fact_links"],
                        utterances=state["source_utterances"],
                    ),
                }
            )
            return {
                "responses": [
                    AgentResponse(
                        response_type="RATIONALE_RECALL",
                        message=message_text(response),
                        related_fact_ids=list(
                            dict.fromkeys(
                                fact.design_fact_id
                                for fact in state["retrieved_facts"]
                            )
                        ),
                        source_utterance_ids=list(
                            dict.fromkeys(
                                item.utterance_id
                                for item in state["source_utterances"]
                            )
                        ),
                    )
                ]
            }
        except Exception as error:
            logger.exception(
                "[rationale_response_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": ["rationale_response_failed"]}
