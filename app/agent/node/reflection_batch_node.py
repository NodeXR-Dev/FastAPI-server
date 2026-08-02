import json

from langchain_core.language_models import BaseChatModel

from app.agent.llm.provider import get_agent_llm
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
    TopicSummaryProposalBundle,
)


class ReflectionBatchNode:
    def __init__(self, *, llm: BaseChatModel | None = None) -> None:
        model = llm or get_agent_llm()
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
                        "semantic_memories": [
                            item.model_dump(mode="json")
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

    async def summarize_topics(self, topic_context_json: str) -> TopicSummaryProposalBundle:
        result = await self.topic_summary_chain.ainvoke(
            {"topic_context_json": topic_context_json},
        )
        return (
            result
            if isinstance(result, TopicSummaryProposalBundle)
            else TopicSummaryProposalBundle.model_validate(result)
        )
