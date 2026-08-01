from langchain_core.prompts import ChatPromptTemplate


MEMORY_GUARD_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Judge whether the current design utterance clearly conflicts with one or more retrieved facts.
Only use the supplied fact IDs and content. Never invent an ID or fact.
Set violated=false for ambiguity, weak tension, or when evidence is insufficient.
DECISION means contradicting/replacing an established decision.
CONSTRAINT means violating a stated constraint.
The reason must be concise Korean text grounded in the supplied facts.""",
        ),
        (
            "human",
            "Current utterance:\n{normalized_text}\n\nRetrieved facts:\n{facts_context}",
        ),
    ]
)
