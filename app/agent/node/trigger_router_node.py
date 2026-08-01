from langchain_core.language_models import BaseChatModel

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.trigger_prompt import TRIGGER_PROMPT
from app.agent.schema.realtime_agent_schema import TriggerResult
from app.agent.state.realtime_agent_state import RealtimeAgentState
from app.core.logger import get_logger

logger = get_logger(__name__)


class TriggerRouterNode:
    def __init__(self, *, llm: BaseChatModel | None = None) -> None:
        model = llm or get_agent_llm()
        self.chain = TRIGGER_PROMPT | model.with_structured_output(TriggerResult)

    async def classify_triggers(
        self,
        state: RealtimeAgentState,
    ) -> dict:
        try:
            result = await self.chain.ainvoke(
                {"normalized_text": state["normalized_text"]},
            )
            triggers = (
                result
                if isinstance(result, TriggerResult)
                else TriggerResult.model_validate(result)
            )
            if not triggers.asset_generation:
                triggers.asset_type = "NONE"
                triggers.source_asset_id = None
            return {"triggers": triggers}
        except Exception as error:
            logger.exception(
                "[agent_trigger_classification_failed] room_id=%s | utterance_id=%s | error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {
                "triggers": TriggerResult(),
                "errors": ["trigger_classification_failed"],
            }
