from langchain_core.prompts import ChatPromptTemplate


TRIGGER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You classify a Korean collaborative-design utterance for NodeXR.
Return independent multi-label booleans; more than one may be true.

memory_guard: the speaker proposes something that could violate or replace an existing decision/constraint. Do not enable this for ordinary refinements with no potential conflict.
rationale_recall: the user asks why a prior decision, proposal, material, or constraint was chosen.
conflict_recall: the user asks to recall a past disagreement, objection, pro/con argument, or resolution.
asset_generation: the user explicitly asks to create/generate an image, 3D model, or reference asset.

asset_type rules:
- IMAGE_2D for an image, picture, sketch, rendering, or poster.
- MODEL_3D for a 3D model; source_asset_id is only a UUID explicitly present in the utterance.
- REFERENCE for adding/uploading a reference image.
- NONE when asset_generation is false.

Examples:
- '왜 이 소재로 결정했었지?' => rationale_recall only.
- '아까 반대 의견이 뭐였지?' => conflict_recall only.
- '이걸 이미지로 만들어줘.' => asset_generation, IMAGE_2D.
- '왜 알루미늄으로 정했는지 알려주고 그 기준으로 이미지 만들어줘.' => rationale_recall and asset_generation, IMAGE_2D.
- '의자 다리를 좀 길게 해보죠.' => all false unless it clearly proposes replacing a known constraint.""",
        ),
        ("human", "Utterance:\n{normalized_text}"),
    ]
)
