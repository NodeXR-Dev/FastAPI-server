from langchain_core.prompts import ChatPromptTemplate


_TOPIC_RULES = """Topics group the utterances that discuss one part or one question of the design.

- A short reaction ("응 그게 낫겠다", "그건 좀 비싼데", "맞아 그거 좋다") continues whatever
  topic the previous utterance was about. It never opens a topic of its own.
- A follow-up detail, objection, cost remark, question, or decision about the same object
  continues that object's topic.
- Open a new topic only when the team clearly moves to a different part or question.
- Prefer continuing an existing topic. Splitting a discussion that belongs together is
  worse than keeping two related threads in one topic."""


# 실시간(D): 발화 1건의 topic 배정과 구조 서술을 한 번의 호출로 처리한다.
# 구조 서술만 따로 부르면 같은 발화를 두 번 보내게 되므로 합쳐 둔다.
UTTERANCE_TOPIC_AND_STRUCTURE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You do two things for one Korean design-meeting utterance: assign it to a
discussion topic, and describe what the utterance is doing.

{topic_rules}

topic_number: the number of the topic this utterance continues, or 0 to open a new topic.
new_topic_summary: a short Korean summary, required only when topic_number is 0.

dialogue_move, exactly one:
- PROPOSE: puts forward a design idea, option, or change.
- DECIDE: settles or confirms a design choice, including changing an earlier one.
- ASK: asks a question or requests information.
- AGREE: expresses agreement or acceptance.
- DISAGREE: expresses objection, doubt, or rejection.
- INFORM: states a fact, reason, constraint, or observation without proposing or deciding.
- OTHER: greetings, small talk, or anything none of the above fit.

stance: FOR, AGAINST, or NEUTRAL toward a design option.
confidence: how clearly the utterance fits the chosen dialogue_move.

You are not deciding whether any agent should run. Only assign and describe.
Return structured output only.""".format(topic_rules=_TOPIC_RULES),
        ),
        (
            "human",
            """Topics so far:
{topics}

Recent utterances:
{recent}

New utterance:
{utterance}""",
        ),
    ]
)


# 배치(E): 전체 발화를 한 번에 보고 경계를 다시 긋는다.
# 주제 경계는 사후 판단이라 실시간 순차 배정보다 유리하다.
BATCH_TOPIC_RESEGMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You re-check which topic each new utterance of a Korean design meeting belongs to.

The utterances were assigned one at a time as they arrived, without seeing what came next.
You see the whole batch at once, so correct the assignments that the streaming pass got wrong.

{topic_rules}

For every supplied utterance_id return exactly one assignment:
- topic_number: the number of an existing topic listed below, or 0 for a new topic.
- new_topic_group: when topic_number is 0, a label shared by all utterances of this batch
  that belong to the same new topic. Reuse the same label for utterances that go together.
- new_topic_summary: a short Korean summary, on the first utterance of each new group.

Existing topics already carry design facts, so never merge or rename them; only decide
which utterances belong to them. Return exactly one assignment per supplied utterance_id
and no others. Return structured output only.""".format(topic_rules=_TOPIC_RULES),
        ),
        (
            "human",
            """Existing topics:
{topics}

Batch utterances in order:
{utterances}""",
        ),
    ]
)
