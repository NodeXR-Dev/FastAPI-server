import asyncio

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.memory_guard_prompt import MEMORY_GUARD_PROMPT
from app.agent.schema.realtime_agent_schema import AlertDraft, GuardResult
from app.agent.state.realtime_agent_state import RealtimeAgentState
from app.core.config import settings
from app.core.logger import get_logger
from app.service.agent.memory_retrieval_service import MemoryRetrievalService

logger = get_logger(__name__)


class MemoryGuardGraph:
    def __init__(
        self,
        *,
        retrieval_service: MemoryRetrievalService | None = None,
        llm: BaseChatModel | None = None,
        alert_threshold: float | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service or MemoryRetrievalService()
        model = llm or get_agent_llm()
        self.guard_chain = MEMORY_GUARD_PROMPT | model.with_structured_output(
            GuardResult,
        )
        self.alert_threshold = (
            settings.MEMORY_GUARD_ALERT_THRESHOLD
            if alert_threshold is None
            else alert_threshold
        )
        self.graph = self._compile()

    def _compile(self):
        builder = StateGraph(RealtimeAgentState)
        builder.add_node("retrieve_facts", self.retrieve_facts)
        builder.add_node("judge_violation", self.judge_violation)
        builder.add_node("confidence_check", self.confidence_check)
        builder.add_node("create_alert", self.create_alert)
        builder.add_edge(START, "retrieve_facts")
        builder.add_conditional_edges(
            "retrieve_facts",
            self._route_after_retrieval,
        )
        builder.add_edge("judge_violation", "confidence_check")
        builder.add_conditional_edges(
            "confidence_check",
            self._route_after_confidence,
        )
        builder.add_edge("create_alert", END)
        return builder.compile(name="MemoryGuard")

    async def retrieve_facts(self, state: RealtimeAgentState) -> dict:
        try:
            facts = await asyncio.to_thread(
                self.retrieval_service.retrieve_guard_facts,
                room_id=state["room_id"],
                topic_id=state["topic_id"],
                embedding=state["embedding"],
            )
            return {"retrieved_facts": facts}
        except Exception as error:
            logger.exception(
                "[memory_guard_retrieval_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {"errors": ["memory_guard_retrieval_failed"]}

    async def judge_violation(self, state: RealtimeAgentState) -> dict:
        facts_context = "\n".join(
            f"- id={fact.design_fact_id}; type={fact.fact_type}; status={fact.status}; content={fact.content}"
            for fact in state["retrieved_facts"]
        )
        try:
            result = await self.guard_chain.ainvoke(
                {
                    "normalized_text": state["normalized_text"],
                    "facts_context": facts_context,
                },
            )
            guard_result = (
                result
                if isinstance(result, GuardResult)
                else GuardResult.model_validate(result)
            )
            fact_type_by_id = {
                fact.design_fact_id: fact.fact_type
                for fact in state["retrieved_facts"]
            }
            guard_result.related_fact_ids = [
                fact_id
                for fact_id in guard_result.related_fact_ids
                if fact_type_by_id.get(fact_id) == guard_result.violation_type
            ]
            return {"guard_result": guard_result}
        except Exception as error:
            logger.exception(
                "[memory_guard_judgement_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {
                "guard_result": GuardResult(),
                "errors": ["memory_guard_judgement_failed"],
            }

    def confidence_check(self, state: RealtimeAgentState) -> dict:
        result = state["guard_result"]
        return {
            "guard_passed": bool(
                result.violated
                and result.violation_type != "NONE"
                and result.related_fact_ids
                and result.confidence >= self.alert_threshold
            )
        }

    def create_alert(self, state: RealtimeAgentState) -> dict:
        result = state["guard_result"]
        alert_type = (
            "DECISION_VIOLATION"
            if result.violation_type == "DECISION"
            else "CONSTRAINT_VIOLATION"
        )
        return {
            "alerts": [
                AlertDraft(
                    alert_type=alert_type,
                    related_fact_id=fact_id,
                    confidence=result.confidence,
                    message=(
                        result.reason
                        or "기존 설계 결정 또는 제약과의 충돌을 확인해 주세요."
                    ),
                )
                for fact_id in result.related_fact_ids
            ]
        }

    @staticmethod
    def _route_after_retrieval(state: RealtimeAgentState) -> str:
        return "judge_violation" if state["retrieved_facts"] else END

    @staticmethod
    def _route_after_confidence(state: RealtimeAgentState) -> str:
        return "create_alert" if state["guard_passed"] else END
