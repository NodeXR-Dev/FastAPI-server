from app.agent.schema.realtime_agent_schema import (
    FactLinkRecord,
    FactRecord,
    MemoryRecord,
    SourceUtteranceRecord,
)


def build_evidence_context(
    *,
    facts: list[FactRecord],
    memories: list[MemoryRecord],
    links: list[FactLinkRecord],
    utterances: list[SourceUtteranceRecord],
) -> str:
    sections = [
        "MEMORIES:\n"
        + "\n".join(
            f"- id={item.semantic_memory_id}; type={item.memory_type}; content={item.content}"
            for item in memories
        ),
        "FACTS:\n"
        + "\n".join(
            f"- id={item.design_fact_id}; type={item.fact_type}; status={item.status}; content={item.content}"
            for item in facts
        ),
        "LINKS:\n"
        + "\n".join(
            f"- {item.from_fact_id} --{item.link_type}--> {item.to_fact_id}"
            for item in links
        ),
        "SOURCE_UTTERANCES:\n"
        + "\n".join(
            f"- utterance_id={item.utterance_id}; fact_id={item.design_fact_id}; role={item.link_role}; text={item.original_text}"
            for item in utterances
        ),
    ]
    return "\n\n".join(sections)


def message_text(message) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in content
        ).strip()
    return str(content).strip()
