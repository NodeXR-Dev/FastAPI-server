from langchain_core.language_models import BaseChatModel

from app.agent.llm.provider import get_agent_llm
from app.agent.prompt.trigger_prompt import (
    AGENT_COMMAND_PROMPT,
    GUARD_TRIGGER_PROMPT,
    TRIGGER_PROMPT,
)
from app.agent.schema.realtime_agent_schema import (
    AgentCommandResult,
    GuardTriggerResult,
    TriggerResult,
)
from app.agent.state.realtime_agent_state import RealtimeAgentState
from app.core.config import settings
from app.core.logger import get_logger
from app.service.utterance.wake_word_service import WakeWordService

logger = get_logger(__name__)


class TriggerRouterNode:
    """호출어 유무에 따라 서로 다른 분류기를 태운다.

    호출어가 있으면 "어떤 명령인가"만, 없으면 "제약 검사가 필요한가"만 묻는다.
    하나의 프롬프트로 4개 라벨을 동시에 판단하던 방식보다 각 호출의 판단 범위가 좁다.
    """

    def __init__(
        self,
        *,
        llm: BaseChatModel | None = None,
        wake_word_service: WakeWordService | None = None,
    ) -> None:
        model = llm or get_agent_llm()
        self.wake_word_service = wake_word_service or WakeWordService()
        self.legacy_chain = TRIGGER_PROMPT | model.with_structured_output(TriggerResult)
        self.guard_chain = GUARD_TRIGGER_PROMPT | model.with_structured_output(
            GuardTriggerResult,
        )
        self.command_chain = AGENT_COMMAND_PROMPT | model.with_structured_output(
            AgentCommandResult,
        )

    async def classify_triggers(self, state: RealtimeAgentState) -> dict:
        if not settings.AGENT_WAKE_WORD_REQUIRED:
            return await self._classify_legacy(state)

        is_command = state.get("is_agent_command")
        command_text = state.get("command_text") or ""

        if is_command is None:
            match = self.wake_word_service.detect(state["normalized_text"])
            is_command = match.matched
            command_text = match.command_text

        if is_command:
            return await self._classify_command(state, command_text=command_text)

        return await self._classify_guard(state)

    async def _classify_command(
        self,
        state: RealtimeAgentState,
        *,
        command_text: str,
    ) -> dict:
        try:
            result = await self.command_chain.ainvoke({"command_text": command_text})
            command = (
                result
                if isinstance(result, AgentCommandResult)
                else AgentCommandResult.model_validate(result)
            )
        except Exception as error:
            logger.exception(
                "[agent_command_classification_failed] room_id=%s | utterance_id=%s "
                "| error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {
                "triggers": TriggerResult(),
                "errors": ["agent_command_classification_failed"],
            }

        logger.info(
            "[agent_command_classified] room_id=%s | utterance_id=%s "
            "| command_type=%s | command_text=%s",
            state["room_id"],
            state["utterance_id"],
            command.command_type,
            command_text,
        )
        return {"triggers": self._to_triggers(command)}

    async def _classify_guard(self, state: RealtimeAgentState) -> dict:
        try:
            result = await self.guard_chain.ainvoke(
                {"normalized_text": state["normalized_text"]},
            )
            guard = (
                result
                if isinstance(result, GuardTriggerResult)
                else GuardTriggerResult.model_validate(result)
            )
        except Exception as error:
            logger.exception(
                "[agent_trigger_classification_failed] room_id=%s | utterance_id=%s "
                "| error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {
                "triggers": TriggerResult(),
                "errors": ["trigger_classification_failed"],
            }

        logger.info(
            "[agent_trigger_classified] room_id=%s | utterance_id=%s | mode=guard "
            "| memory_guard=%s",
            state["room_id"],
            state["utterance_id"],
            guard.memory_guard,
        )
        return {"triggers": TriggerResult(memory_guard=bool(guard.memory_guard))}

    async def _classify_legacy(self, state: RealtimeAgentState) -> dict:
        try:
            result = await self.legacy_chain.ainvoke(
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
            logger.info(
                "[agent_trigger_classified] room_id=%s | utterance_id=%s | mode=legacy "
                "| memory_guard=%s | rationale_recall=%s | conflict_recall=%s "
                "| asset_generation=%s | asset_type=%s | all_false=%s",
                state["room_id"],
                state["utterance_id"],
                triggers.memory_guard,
                triggers.rationale_recall,
                triggers.conflict_recall,
                triggers.asset_generation,
                triggers.asset_type,
                not (
                    triggers.memory_guard
                    or triggers.rationale_recall
                    or triggers.conflict_recall
                    or triggers.asset_generation
                ),
            )
            return {"triggers": triggers}
        except Exception as error:
            logger.exception(
                "[agent_trigger_classification_failed] room_id=%s | utterance_id=%s "
                "| error=%s",
                state["room_id"],
                state["utterance_id"],
                str(error),
            )
            return {
                "triggers": TriggerResult(),
                "errors": ["trigger_classification_failed"],
            }

    @staticmethod
    def _to_triggers(command: AgentCommandResult) -> TriggerResult:
        asset_type = "NONE"
        if command.command_type == "GENERATE_2D":
            asset_type = "IMAGE_2D"
        elif command.command_type == "GENERATE_3D":
            asset_type = "MODEL_3D"

        return TriggerResult(
            memory_guard=False,
            rationale_recall=command.command_type == "RATIONALE_RECALL",
            conflict_recall=command.command_type == "CONFLICT_RECALL",
            asset_generation=asset_type != "NONE",
            asset_type=asset_type,
            source_asset_id=(
                command.source_asset_id
                if command.command_type == "GENERATE_3D"
                else None
            ),
        )
