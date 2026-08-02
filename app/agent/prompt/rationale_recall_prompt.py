from langchain_core.prompts import ChatPromptTemplate


RATIONALE_RECALL_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Answer a Korean user's question about the rationale for a prior design choice.
Use only the supplied semantic memories, design facts, relationships, and source utterances.
If the evidence does not establish a rationale, clearly say that the stored evidence is insufficient.
Do not invent a decision, relationship, speaker statement, or source.""",
        ),
        (
            "human",
            "Question:\n{normalized_text}\n\nEvidence:\n{evidence_context}",
        ),
    ]
)
