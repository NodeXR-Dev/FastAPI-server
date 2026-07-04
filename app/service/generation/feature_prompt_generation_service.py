from app.core.logger import get_logger
from app.schema.generation.generation_result import FeaturePromptContext
from app.service.generation.openai_prompt_client import OpenAIPromptClient

logger = get_logger(__name__)


class FeaturePromptGenerationService:
    def __init__(
        self,
        *,
        openai_prompt_client: OpenAIPromptClient | None = None,
    ) -> None:
        self.openai_prompt_client = openai_prompt_client or OpenAIPromptClient()

    async def generate(
        self,
        *,
        context: FeaturePromptContext,
    ) -> str:
        logger.info(
            "[feature_prompt_generation_started] room_id=%s",
            context.room_id,
        )

        context_text = context.to_text()

        prompt_text = await self.openai_prompt_client.generate_feature_image_prompt(
            context_text=context_text,
        )

        logger.info(
            "[feature_prompt_generation_completed] room_id=%s",
            context.room_id,
        )

        return prompt_text