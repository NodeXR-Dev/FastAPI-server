from openai import AsyncOpenAI

from app.ai.prompts.feature_image_prompt import (
    FEATURE_IMAGE_SYSTEM_PROMPT,
    build_feature_image_prompt,
)
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# 배경 제거는 시스템 규칙만으로는 자주 무시된다(방·책상·아이가 그려져 나왔다).
# 이미지 모델에 마지막으로 읽히는 자리에 한 번 더 못을 박는다.
#
# 2D 이미지가 나오는 경로는 두 개이고 둘 다 이 문구를 붙여야 한다.
#   1) 로비 요구사항 기반 최초 생성 → generate_feature_image_prompt
#   2) 회의 중 '2D 생성' 버튼       → generate_image_prompt
# (2)에만 붙여 뒀더니 최초 이미지에만 배경이 딸려 나왔다.
ISOLATED_PRODUCT_SUFFIX = (
    "The product is isolated on a pure white background, "
    "cut out with no environment, no room, no furniture, no people, "
    "and no scenery of any kind. Product only."
)


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

        response = await self.client.responses.create(
            model=settings.OPENAI_PROMPT_MODEL,
            input=[
                {
                    "role": "system",
                    "content": FEATURE_IMAGE_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": build_feature_image_prompt(context_text),
                },
            ],
        )

        prompt_text = response.output_text.strip()

        if not prompt_text:
            raise ValueError("OpenAI가 빈 feature 기반 이미지 프롬프트를 반환했습니다.")

        prompt_text = f"{prompt_text} {ISOLATED_PRODUCT_SUFFIX}"

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
- Depict exactly ONE isolated product. Never a scene, workspace, studio, or collage.
- Pure white background only. No environment, no room, no desk, no floor, no wall, no sky.
- The product must look cut out on plain white, like a catalog cutout.
- No people, children, hands, furniture, plants, posters, or decorations of any kind.
- Single three-quarter view of the whole product, centered, fully visible, nothing cropped.
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

        prompt_text = f"{prompt_text} {ISOLATED_PRODUCT_SUFFIX}"

        logger.info(
            "[openai_prompt_generation_completed] prompt_length=%s",
            len(prompt_text),
        )
        logger.info(
            "[openai_prompt_generated] prompt=%s",
            prompt_text,
        )

        return prompt_text
