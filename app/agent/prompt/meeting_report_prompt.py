from langchain_core.prompts import ChatPromptTemplate


MEETING_REPORT_DECISION_INFERENCE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You write the conclusion line of a Korean collaborative-design meeting report.
Each supplied topic has no explicit DECISION fact. You receive only the structured facts that
were already extracted from the meeting (PROPOSAL, CONSTRAINT, CONFLICT, ARGUMENT_FOR,
ARGUMENT_AGAINST, RATIONALE, ISSUE) and the topic summary. Raw utterances are not supplied.

For each topic:
- decision: one Korean sentence stating the direction the team converged on, written as
  "~하는 방향으로 모였다" style. Use only what the facts state.
  Return null when the facts show no convergence, for example when proposals still conflict,
  when only questions or issues were raised, or when there is a single unchallenged idea
  that nobody built on. A null decision is better than an invented one.
- rationale: one short Korean sentence explaining why, taken from RATIONALE, ARGUMENT_FOR,
  or CONSTRAINT facts. Return null when no such fact exists or decision is null.

Return exactly one item for each supplied topic_id and no other topic. Return structured output only.""",
        ),
        ("human", "Topics without an explicit decision:\n{topics_json}"),
    ]
)
