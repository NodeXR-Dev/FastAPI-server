from langchain_core.prompts import ChatPromptTemplate


FACT_RELATIONSHIP_RULES = """
- SUPPORTS: ARGUMENT_FOR or RATIONALE -> PROPOSAL, DECISION, or CONFLICT
- OPPOSES: ARGUMENT_AGAINST -> PROPOSAL, DECISION, or CONFLICT
- CONSTRAINS: CONSTRAINT -> PROPOSAL or DECISION
- CONFLICTS_WITH: PROPOSAL, DECISION, CONSTRAINT, or CONFLICT -> a different one of those types
- RATIONALE_OF: RATIONALE -> PROPOSAL or DECISION
- RESOLVES: DECISION -> ISSUE
- RESOLVES: DECISION -> CONFLICT
- VIOLATES: PROPOSAL or DECISION -> CONSTRAINT

The source type and the target type decide the direction. Read each link as
"source --link_type--> target".

Correct examples:
- RATIONALE "가벼워야 들고 다니기 쉽다" --RATIONALE_OF--> DECISION "알루미늄으로 만든다"
- CONSTRAINT "예산은 5만 원 이하" --CONSTRAINS--> PROPOSAL "모터를 단다"
- ARGUMENT_AGAINST "가격이 비싸다" --OPPOSES--> PROPOSAL "알루미늄을 쓴다"
- DECISION "목재로 확정한다" --RESOLVES--> CONFLICT "목재와 알루미늄 중 무엇을 쓸지 대립"

Wrong examples, and why:
- PROPOSAL --CONSTRAINS--> CONSTRAINT: the source of CONSTRAINS must be the CONSTRAINT itself.
- ARGUMENT_FOR --SUPPORTS--> RATIONALE: RATIONALE cannot be a SUPPORTS target.
- DECISION --RATIONALE_OF--> PROPOSAL: only a RATIONALE can be the source of RATIONALE_OF.
Emit a link only when the batch utterances state the connection. Emitting no link is
better than emitting a link with the wrong direction.
""".strip()


REFLECTION_BATCH_ANALYZER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You structure a batch of Korean collaborative-design utterances into design facts.
Use only the supplied batch utterances as factual sources. Existing facts and memories are context, not new evidence.

Allowed fact types: PROPOSAL, DECISION, CONSTRAINT, CONFLICT, ARGUMENT_FOR, ARGUMENT_AGAINST, RATIONALE, ISSUE.
ISSUE is an open problem the team has named but not yet resolved or argued about.
Use CONFLICT instead when two stated positions oppose each other.
Every fact must reference at least one utterance_id from this batch and must use that utterance's topic_id.
Use concise standalone Korean fact text. Do not emit low-value chat, greetings, or questions that contain no design fact.
Do not create a fact from a request addressed to the agent, such as asking it to generate an image or a 3D model.

target_scope: the part of the product this fact is about, as a short Korean noun phrase
taken from the utterances, such as '물탱크' or '전원부'. Leave it null when the fact is about
the whole product or the utterances do not name a part.
design_dimension: which aspect the fact constrains, as one short Korean word such as
'재료', '비용', '구조', '안전', '크기', '전원'. Leave it null when no aspect is clear.
Never invent either value. An empty field is better than a guessed one.

source_utterance_ids must contain utterance_id values from this batch.
related_existing_fact_ids must contain design_fact_id values taken from the supplied existing facts. Never put an utterance_id there; leave the list empty when no existing fact is clearly related.

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
            """Maintain compact long-term retrieval memories for a design meeting.

Storage keeps exactly one memory row per (topic_id, memory_type). Emitting a memory for a pair
that already exists REPLACES the stored content for that pair. Nothing is appended and nothing
is merged for you.

current_memories lists what is stored right now. Entries with will_be_replaced=true cover the
topics changed by this batch, so they are the ones your output can overwrite.

When you emit a memory for a (topic_id, memory_type) pair that already appears in current_memories,
rewrite that memory so it still covers everything the stored content covered, then fold in what the
new or changed design facts add. Never return only the new part: whatever you leave out is lost.
Drop a previously covered point only when a supplied fact explicitly supersedes or contradicts it.
When no memory exists yet for that pair, write it from the supplied facts alone.

Design facts are the source of truth for anything new. Do not add information that appears neither
in the supplied facts nor in the memory you are updating.
Prefer one compact memory per topic and memory type.
Allowed memory types: SUMMARY, DECISION, CONSTRAINT, CONFLICT, RATIONALE.
Do not promote ordinary PROPOSAL or ARGUMENT facts unless they are needed inside a CONFLICT or SUMMARY memory.

A memory type is allowed only when at least one cited fact has a compatible type:
- SUMMARY: any fact type
- DECISION: needs a DECISION fact
- CONSTRAINT: needs a CONSTRAINT fact
- CONFLICT: needs a CONFLICT, ISSUE, ARGUMENT_FOR, or ARGUMENT_AGAINST fact
- RATIONALE: needs a RATIONALE fact
If no cited fact has a compatible type, do not emit that memory at all. Emitting fewer memories is
better than emitting one that its cited facts cannot support.
Every cited fact must belong to the memory's own topic_id.
Write every memory content in Korean, matching the language of the design facts.
Every memory must cite one or more supplied fact references; cite the facts that support the parts
you added or changed. Return structured output only.""",
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
