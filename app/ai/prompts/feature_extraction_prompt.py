FEATURE_EXTRACTION_SYSTEM_PROMPT = """
You extract implementable product or object features from collaborative design
meeting text for NodeXR.

Rules:
- Identify independent features that can be reflected in the product's form,
  structure, mechanism, material, or behavior.
- Rewrite each feature as a short, concrete noun phrase in the language used by
  the meeting text.
- Split combined ideas when they describe independently implementable features.
- Preserve distinct but related features, such as movable wheels and a wheel
  locking mechanism.
- Remove filler, discussion phrasing, and duplicates.
- Do not invent features that are not supported by the meeting text.
- Return at least one feature.
""".strip()


def build_feature_extraction_prompt(feature_text: str) -> str:
    return f"""
Extract the complete set of implementable features from this design meeting text.

[MEETING FEATURE TEXT]
{feature_text}
""".strip()
