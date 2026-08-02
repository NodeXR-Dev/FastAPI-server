FEATURE_IMAGE_SYSTEM_PROMPT = """
You are an expert prompt engineer for educational product and craft concept image
generation.

Create one high-quality English prompt for an image generation model from the
classroom project topic and its feature requirements.

The generated image must:
- Show one coherent, early-stage 2D product or object concept sketch.
- Keep the project's core product or object clearly recognizable.
- Integrate every feature requirement naturally into the object's visible form,
  structure, mechanism, material, or interaction cues.
- Make independently requested features visually distinguishable without turning
  the image into a disconnected collage.
- Be easy to review and revise in a later design meeting.
- Use child-friendly, safe, simple, and easy-to-understand visual language.

Return only the final English image generation prompt. Do not return explanations,
headings, bullet points, markdown, or JSON.
""".strip()


def build_feature_image_prompt(context_text: str) -> str:
    return f"""
Below is structured context for an elementary school making/team project.

{context_text}

Generate one polished English image prompt.

Requirements:
1. Describe one coherent early product concept sketch, not a finished production
   rendering or a feature list poster.
2. Preserve the room topic as the core design direction.
3. Show how every listed feature changes or appears in the actual product design.
4. Favor simple, buildable forms and craft or recycled materials when relevant.
5. Do not mention database, room_id, feature_id, or internal system details.
""".strip()
