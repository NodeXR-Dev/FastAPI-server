import json

from langchain_core.language_models import BaseChatModel

from app.agent.llm.provider import get_batch_llm
from app.agent.prompt.meeting_report_prompt import (
    MEETING_REPORT_DECISION_INFERENCE_PROMPT,
)
from app.agent.schema.meeting_report_schema import (
    InferredTopicDecisionBundle,
    TopicDecisionContext,
)


class MeetingReportNode:
    """리포트 생성에서 쓰는 유일한 LLM 호출.

    명시적 DECISION 이 없는 Topic 들을 한 번에 묶어 보낸다. Topic 수만큼 부르지 않는다.
    """

    def __init__(self, *, llm: BaseChatModel | None = None) -> None:
        model = llm or get_batch_llm()
        self.decision_inference_chain = (
            MEETING_REPORT_DECISION_INFERENCE_PROMPT
            | model.with_structured_output(InferredTopicDecisionBundle)
        ).with_config(run_name="Meeting Report Decision Inference")

    async def infer_decisions(
        self,
        contexts: list[TopicDecisionContext],
    ) -> InferredTopicDecisionBundle:
        if not contexts:
            return InferredTopicDecisionBundle()
        result = await self.decision_inference_chain.ainvoke(
            {
                "topics_json": json.dumps(
                    [item.model_dump(mode="json") for item in contexts],
                    ensure_ascii=False,
                )
            },
        )
        return (
            result
            if isinstance(result, InferredTopicDecisionBundle)
            else InferredTopicDecisionBundle.model_validate(result)
        )
