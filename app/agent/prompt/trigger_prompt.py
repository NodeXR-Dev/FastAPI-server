from langchain_core.prompts import ChatPromptTemplate


TRIGGER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You classify a Korean collaborative-design utterance for NodeXR.
Return independent multi-label booleans; more than one may be true.

memory_guard: the speaker proposes something that could violate or replace an existing decision/constraint. Do not enable this for ordinary refinements with no potential conflict.
rationale_recall: the user asks why a prior decision, proposal, material, or constraint was chosen. A statement that provides or explains a reason is not a recall request.
conflict_recall: the user asks to recall a past disagreement, objection, pro/con argument, or resolution.
asset_generation: the user explicitly asks to create/generate an image, 3D model, or reference asset.

asset_type rules:
- IMAGE_2D for an image, picture, sketch, rendering, or poster.
- MODEL_3D for a 3D model; source_asset_id is only a UUID explicitly present in the utterance.
- REFERENCE for adding/uploading a reference image.
- NONE when asset_generation is false.

Examples:
- '왜 이 소재로 결정했었지?' => rationale_recall only.
- '전기 부품을 빼는 이유는 감전 위험을 줄이기 위해서야.' => all false; this provides a reason instead of asking to recall one.
- '아까 반대 의견이 뭐였지?' => conflict_recall only.
- '이걸 이미지로 만들어줘.' => asset_generation, IMAGE_2D.
- '왜 알루미늄으로 정했는지 알려주고 그 기준으로 이미지 만들어줘.' => rationale_recall and asset_generation, IMAGE_2D.
- '의자 다리를 좀 길게 해보죠.' => all false unless it clearly proposes replacing a known constraint.""",
        ),
        ("human", "Utterance:\n{normalized_text}"),
    ]
)


# 호출어가 없는 일반 발화: 제약 검사가 필요한지만 판단한다.
GUARD_TRIGGER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You decide whether a Korean collaborative-design utterance needs a design-constraint check.

Set memory_guard=true only when the speaker proposes, decides, or changes something that could
violate or replace an existing design decision or constraint.
Set memory_guard=false for questions, agreements, reactions, and ordinary refinements that carry
no potential conflict.

Examples:
- '그래도 빨리 말리려면 작은 모터를 넣는 게 낫지 않을까?' => true
- '전기 없이 발판이 케이블을 당기는 방식으로 결정하자.' => true
- '패드 뒤에는 스프링을 넣자.' => true
- '맞아. 그게 좋겠다.' => false
- '전기 부품을 빼는 이유는 감전 위험을 줄이기 위해서야.' => false
- '우리가 모터를 쓰지 않기로 한 이유가 뭐였지?' => false""",
        ),
        ("human", "Utterance:\n{normalized_text}"),
    ]
)


# 호출어로 Agent를 부른 발화: 어떤 명령인지 하나로 분류한다.
AGENT_COMMAND_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """The user called the NodeXR agent by name and is giving it one command.
Classify the command into exactly one type. The wake word itself has already been removed.

RATIONALE_RECALL: asks why a prior decision, proposal, material, or constraint was chosen.
CONFLICT_RECALL: asks to recall a past disagreement, objection, pro/con argument, or resolution.
GENERATE_2D: asks to create an image, sketch, rendering, poster, or 2D concept.
GENERATE_3D: asks to create a 3D model. source_asset_id is only a UUID explicitly present in the command.
NONE: the command matches none of the above.

Examples:
- '왜 알루미늄으로 정했지?' => RATIONALE_RECALL
- '우리가 모터를 쓰지 않기로 한 이유가 정확히 뭐였지?' => RATIONALE_RECALL
- '아까 반대 의견이 뭐였어?' => CONFLICT_RECALL
- '지금 합의한 둥근 외형이 보이도록 2D 콘셉트 이미지를 만들어줘.' => GENERATE_2D
- '이 이미지를 3D 모델로 만들어줘.' => GENERATE_3D
- '오늘 회의 언제 끝나?' => NONE""",
        ),
        ("human", "Command:\n{command_text}"),
    ]
)
