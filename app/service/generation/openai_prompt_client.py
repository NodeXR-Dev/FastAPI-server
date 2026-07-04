from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class OpenAIPromptClient:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
        )
    async def generate_feature_image_prompt(
        self,
        *,
        context_text: str,
    ) -> str:
            logger.info(
                "[openai_feature_prompt_generation_started] model=%s | context_length=%s",
                settings.OPENAI_PROMPT_MODEL,
                len(context_text),
            )

            system_prompt = """
    You are an expert prompt engineer for educational product and craft concept image generation.

    Your job:
    - Read the classroom project topic and feature requirements.
    - Create one high-quality English prompt for an image generation model.
    - The image should be suitable for elementary school students' making/team project.
    - The result should look like a clear 2D concept sketch or poster-style design.
    - Reflect all feature requirements.
    - Use child-friendly, safe, simple, and easy-to-understand visual language.
    - Return ONLY the final English image generation prompt.
    - Do not output explanations, headings, bullet points, markdown, or JSON.
            """.strip()

            user_prompt = f"""
    Below is structured context for an elementary school making/team project.

    {context_text}

    Generate one polished English image prompt.

    Requirements:
    1. The prompt must describe one coherent 2D concept image.
    2. The concept should be easy for elementary school students to understand.
    3. The design should look buildable using simple craft or recycled materials when relevant.
    4. The image should clearly reflect the topic and all feature requirements.
    5. Do not mention database, room_id, feature_id, or internal system details.
            """.strip()

            response = await self.client.responses.create(
                model=settings.OPENAI_PROMPT_MODEL,
                input=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
            )

            prompt_text = response.output_text.strip()

            if not prompt_text:
                raise ValueError("OpenAI가 빈 feature 기반 이미지 프롬프트를 반환했습니다.")

            logger.info(
                "[openai_feature_prompt_generation_completed] prompt_length=%s",
                len(prompt_text),
            )
            logger.info(
                "[openai_feature_prompt_generated] prompt=%s",
                prompt_text,
            )

            return prompt_text

    async def generate_image_prompt(
        self,
        *,
        context_text: str,
    ) -> str:
        logger.info(
            "[openai_prompt_generation_started] model=%s | context_length=%s",
            settings.OPENAI_PROMPT_MODEL,
            len(context_text),
        )

        system_prompt = """
You are an expert prompt engineer for product and concept image generation.

Your job is to convert structured design meeting context into one high-quality English image generation prompt.

Rules:
- Return only one final English prompt.
- Do not include headings, bullet points, explanations, JSON, or markdown.
- Do not mention internal IDs.
- Use the room topic as the main design direction.
- Reflect the feature requirements.
- Reflect the graph node chains.
- Emphasized part nodes are important visual components.
- The final prompt should describe a clean, coherent, high-quality 2D concept rendering.
        """.strip()

        user_prompt = f"""
Below is structured context from a collaborative design meeting.

{context_text}

Generate one polished English image prompt.
        """.strip()

        response = await self.client.responses.create(
            model=settings.OPENAI_PROMPT_MODEL,
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )

        prompt_text = response.output_text.strip()

        if not prompt_text:
            raise ValueError("OpenAI가 빈 프롬프트를 반환했습니다.")

        logger.info(
            "[openai_prompt_generation_completed] prompt_length=%s",
            len(prompt_text),
        )
        logger.info(
            "[openai_prompt_generated] prompt=%s",
            prompt_text,
        )

        return prompt_text