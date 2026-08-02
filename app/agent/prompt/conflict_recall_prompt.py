from langchain_core.prompts import ChatPromptTemplate


CONFLICT_RECALL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Answer a Korean user's request to recall a prior design conflict.
Separate supporting and opposing arguments according to the supplied fact types and links.
Use only the supplied facts, relationships, and source utterances.
If evidence is insufficient, say so explicitly. Never invent a dispute, argument, resolution, or quote.""",
        ),
        (
            "human",
            "Question:\n{normalized_text}\n\nEvidence:\n{evidence_context}",
        ),
    ]
)
