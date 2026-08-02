from langchain_core.prompts import ChatPromptTemplate


FACT_RELATIONSHIP_RULES = """
- SUPPORTS: ARGUMENT_FOR or RATIONALE -> PROPOSAL, DECISION, or CONFLICT
- OPPOSES: ARGUMENT_AGAINST -> PROPOSAL, DECISION, or CONFLICT
- CONSTRAINS: CONSTRAINT -> PROPOSAL or DECISION
- CONFLICTS_WITH: PROPOSAL, DECISION, CONSTRAINT, or CONFLICT -> a different one of those types
- RATIONALE_OF: RATIONALE -> PROPOSAL or DECISION
- RESOLVES: DECISION -> CONFLICT
- VIOLATES: PROPOSAL or DECISION -> CONSTRAINT
""".strip()


REFLECTION_BATCH_ANALYZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You structure a batch of Korean collaborative-design utterances into design facts.
Use only the supplied batch utterances as factual sources. Existing facts and memories are context, not new evidence.

Allowed fact types: PROPOSAL, DECISION, CONSTRAINT, CONFLICT, ARGUMENT_FOR, ARGUMENT_AGAINST, RATIONALE.
Every fact must reference at least one utterance_id from this batch and must use that utterance's topic_id.
Use concise standalone Korean fact text. Do not emit low-value chat, greetings, or questions that contain no design fact.

References use reference_type EXISTING with a supplied design_fact_id, or CANDIDATE with a temp_id from this response.
Allowed relationships:
{relationship_rules}
Do not create self-links. Confidence is a relative extraction signal, not a calibrated probability.
Return structured output only.""".format(
                relationship_rules=FACT_RELATIONSHIP_RULES,
            ),
        ),
        ("human", "Batch context:\n{batch_context_json}"),
    ]
)


REFLECTION_BATCH_RELATIONSHIP_REPAIR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Repair only invalid relationship types or directions in a previously structured reflection batch analysis.
Keep the facts, temp_ids, fact types, provenance, topic_ids, content, and confidence values unchanged.
Return the complete analysis with corrected links. Remove a link if it cannot be corrected without inventing meaning.

Allowed relationships:
{relationship_rules}
Do not create self-links. Return structured output only.""".format(
                relationship_rules=FACT_RELATIONSHIP_RULES,
            ),
        ),
        (
            "human",
            """Batch context:
{batch_context_json}

Previous analysis:
{analysis_json}

Validation error:
{validation_error}""",
        ),
    ]
)


FACT_DEDUP_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Compare each new design fact candidate only with its supplied same-topic, same-type existing facts.
Return exactly one decision per temp_id.

CREATE: meaningfully distinct fact.
KEEP_EXISTING: semantically the same fact; keep existing wording.
UPDATE_EXISTING: same continuing fact but the candidate wording adds a non-conflicting clarification.
SUPERSEDE_EXISTING: a new decision/constraint/proposal explicitly replaces the existing one.

For every non-CREATE action, existing_fact_id must be one of the supplied candidates. Never invent IDs.
Use SUPERSEDE_EXISTING only when replacement is explicit, not merely because two facts differ.""",
        ),
        ("human", "Dedup comparisons:\n{comparisons_json}"),
    ]
)


SEMANTIC_MEMORY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Create compact long-term retrieval memories from the supplied new or changed design facts and relationships.
Design facts remain the source of truth. Do not add information not present in them.
Prefer one compact memory per topic and memory type.
Allowed memory types: SUMMARY, DECISION, CONSTRAINT, CONFLICT, RATIONALE.
Do not promote ordinary PROPOSAL or ARGUMENT facts unless they are needed inside a CONFLICT or SUMMARY memory.
Every memory must cite one or more supplied fact references. Return structured output only.""",
        ),
        ("human", "Prepared reflection:\n{prepared_reflection_json}"),
    ]
)


TOPIC_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Update concise Korean topic summaries for only the supplied changed topics.
Use the prior summary, changed facts, relationships, and proposed memories. Do not invent decisions or constraints.
Return exactly one summary for each supplied topic_id and no other topic.""",
        ),
        ("human", "Changed topic context:\n{topic_context_json}"),
    ]
)
