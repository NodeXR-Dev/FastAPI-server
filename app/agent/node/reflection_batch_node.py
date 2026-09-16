import json

from langchain_core.language_models import BaseChatModel

from app.agent.llm.provider import get_batch_llm
from app.agent.prompt.topic_prompt import BATCH_TOPIC_RESEGMENT_PROMPT
from app.agent.prompt.reflection_batch_prompt import (
    FACT_DEDUP_PROMPT,
    REFLECTION_BATCH_ANALYZER_PROMPT,
    REFLECTION_BATCH_RELATIONSHIP_REPAIR_PROMPT,
    SEMANTIC_MEMORY_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)
from app.agent.schema.reflection_batch_schema import (
    BatchAnalysisResult,
    BatchContext,
    DedupComparison,
    FactDedupJudgeResult,
    PreparedReflection,
    SemanticMemoryProposalBundle,
    TopicResegmentResult,
    TopicSummaryProposalBundle,
)


class ReflectionBatchNode:
    def __init__(self, *, llm: BaseChatModel | None = None) -> None:
        model = llm or get_batch_llm()
        self.analysis_chain = (
            REFLECTION_BATCH_ANALYZER_PROMPT
            | model.with_structured_output(BatchAnalysisResult)
        ).with_config(run_name="LLM Batch Analyzer")
        self.analysis_repair_chain = (
            REFLECTION_BATCH_RELATIONSHIP_REPAIR_PROMPT
            | model.with_structured_output(BatchAnalysisResult)
        ).with_config(run_name="LLM Batch Relationship Repair")
        self.dedup_chain = (
            FACT_DEDUP_PROMPT
            | model.with_structured_output(FactDedupJudgeResult)
        ).with_config(run_name="Fact Dedup Semantic Judge")
        self.memory_chain = (
            SEMANTIC_MEMORY_PROMPT
            | model.with_structured_output(SemanticMemoryProposalBundle)
        ).with_config(run_name="Semantic Memory Generation")
        self.topic_resegment_chain = (
            BATCH_TOPIC_RESEGMENT_PROMPT
            | model.with_structured_output(TopicResegmentResult)
        ).with_config(run_name="Batch Topic Resegmentation")
        self.topic_summary_chain = (
            TOPIC_SUMMARY_PROMPT
            | model.with_structured_output(TopicSummaryProposalBundle)
        ).with_config(run_name="Topic Summary Generation")

    async def analyze(self, context: BatchContext) -> BatchAnalysisResult:
        if not context.utterances:
            return BatchAnalysisResult()
        result = await self.analysis_chain.ainvoke(
            {"batch_context_json": context.model_dump_json()},
        )
        return (
            result
            if isinstance(result, BatchAnalysisResult)
            else BatchAnalysisResult.model_validate(result)
        )

    async def repair_analysis_relationships(
        self,
        *,
        context: BatchContext,
        analysis: BatchAnalysisResult,
        validation_error: str,
    ) -> BatchAnalysisResult:
        result = await self.analysis_repair_chain.ainvoke(
            {
                "batch_context_json": context.model_dump_json(),
                "analysis_json": analysis.model_dump_json(),
                "validation_error": validation_error,
            },
        )
        return (
            result
            if isinstance(result, BatchAnalysisResult)
            else BatchAnalysisResult.model_validate(result)
        )

    async def judge_dedup(
        self,
        comparisons: list[DedupComparison],
    ) -> FactDedupJudgeResult:
        if not comparisons:
            return FactDedupJudgeResult()
        result = await self.dedup_chain.ainvoke(
            {
                "comparisons_json": "["
                + ",".join(item.model_dump_json() for item in comparisons)
                + "]"
            },
        )
        return (
            result
            if isinstance(result, FactDedupJudgeResult)
            else FactDedupJudgeResult.model_validate(result)
        )

    async def generate_memories(
        self,
        prepared: PreparedReflection,
        context: BatchContext,
    ) -> SemanticMemoryProposalBundle:
        if not prepared.changed_topic_ids:
            return SemanticMemoryProposalBundle()
        changed_topic_ids = set(prepared.changed_topic_ids)
        result = await self.memory_chain.ainvoke(
            {
                "prepared_reflection_json": json.dumps(
                    {
                        "prepared": prepared.model_dump(mode="json"),
                        "topics": [
                            item.model_dump(mode="json") for item in context.topics
                        ],
                        "existing_facts": [
                            item.model_dump(mode="json")
                            for item in context.existing_facts
                        ],
                        # 저장은 (topic_id, memory_type)당 1행을 덮어쓰므로,
                        # 어떤 행이 이번 제안으로 사라질 수 있는지 명시해 병합을 유도한다.
                        "current_memories": [
                            {
                                **item.model_dump(mode="json"),
                                "will_be_replaced": item.topic_id in changed_topic_ids,
                            }
                            for item in context.semantic_memories
                        ],
                    },
                    ensure_ascii=False,
                )
            },
        )
        return (
            result
            if isinstance(result, SemanticMemoryProposalBundle)
            else SemanticMemoryProposalBundle.model_validate(result)
        )

    async def resegment_topics(self, context: BatchContext) -> TopicResegmentResult:
        """전체 배치를 한 번에 보고 발화의 topic 배정을 다시 긋는다."""
        if not context.utterances:
            return TopicResegmentResult()
        topics_block = "\n".join(
            f"{number}. {item.summary or '(요약 없음)'}"
            for number, item in enumerate(context.topics, start=1)
        ) or "- (없음)"
        topic_number = {
            item.topic_id: number
            for number, item in enumerate(context.topics, start=1)
        }
        utterances_block = "\n".join(
            f"- utterance_id={item.utterance_id} "
            f"(현재 topic {topic_number.get(item.topic_id, '?')}): {item.normalized_text}"
            for item in context.utterances
        )
        result = await self.topic_resegment_chain.ainvoke(
            {"topics": topics_block, "utterances": utterances_block},
        )
        return (
            result
            if isinstance(result, TopicResegmentResult)
            else TopicResegmentResult.model_validate(result)
        )

    async def summarize_topics(self, topic_context_json: str) -> TopicSummaryProposalBundle:
        result = await self.topic_summary_chain.ainvoke(
            {"topic_context_json": topic_context_json},
        )
        return (
            result
            if isinstance(result, TopicSummaryProposalBundle)
            else TopicSummaryProposalBundle.model_validate(result)
        )
