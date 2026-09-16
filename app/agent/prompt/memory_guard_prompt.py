from langchain_core.prompts import ChatPromptTemplate


MEMORY_GUARD_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Judge whether the current design utterance itself breaks one or more retrieved facts.
Only use the supplied fact IDs and content. Never invent an ID or fact.

The utterance must assert something that cannot be true at the same time as the fact.
Retrieved facts are the ones most similar to the utterance, so they will almost always share
vocabulary and subject matter with it. Sharing a subject is not a conflict.

Set violated=false in all of these cases, even when the fact is clearly about the same thing:
- The utterance follows, restates, or reinforces the decision or constraint.
- The utterance objects to something because it would break the decision or constraint.
- The utterance points out that a proposal exceeds a limit, or asks the team to stay inside it.
- The utterance only becomes a conflict through an added assumption the speaker never stated.
- The utterance asks a question, agrees, or reacts.
- Evidence is ambiguous, tension is weak, or you are unsure.

DECISION means the utterance adopts something the established decision ruled out.
CONSTRAINT means the utterance adopts something the stated constraint forbids.

Examples, given an established decision "전원은 배터리만 쓰고 220V 콘센트는 쓰지 않는다"
and a constraint "제품 무게는 2kg 이하":
- '전선을 벽 콘센트에 꽂아서 쓰자.' => violated=true, DECISION. 결정이 배제한 것을 채택한다.
- '무게를 줄이려면 배터리를 더 작은 걸로 바꾸자.' => violated=false. 결정을 따른다.
- '콘센트를 쓰면 안 되니까 배터리 용량을 키우자.' => violated=false. 결정을 지지한다.
- '그건 3kg이라 무게 기준을 넘어. 다른 걸 찾자.' => violated=false. 제약을 지키라고 말한다.
- '금속 프레임으로 만들면 튼튼하겠다.' => violated=false. 무게를 넘긴다고 말하지 않았다.
- '프레임을 3kg짜리 통짜 금속으로 하자.' => violated=true, CONSTRAINT. 제약을 넘는 값을 채택한다.

Before answering, state to yourself what the utterance asserts and which fact it cannot coexist
with. If you cannot name both, violated is false.
The reason must be concise Korean text grounded in the supplied facts, and must say what the
utterance adopts and which fact forbids it. Never write a reason that admits there is no conflict.""",
        ),
        (
            "human",
            "Current utterance:\n{normalized_text}\n\nRetrieved facts:\n{facts_context}",
        ),
    ]
)
