import asyncio
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.logger import get_logger
from app.schema.generation.generation_result import GeneratedImageBinary

logger = get_logger(__name__)


class GeminiImageClient:
    def __init__(self) -> None:
        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
        )

    async def generate_image(
        self,
        *,
        prompt_text: str,
    ) -> GeneratedImageBinary:
        logger.info(
            "[gemini_image_generation_started] model=%s | prompt_length=%s",
            settings.GEMINI_MODEL_NAME,
            len(prompt_text),
        )

        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=settings.GEMINI_MODEL_NAME,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        image_bytes: bytes | None = None
        mime_type = "image/png"

        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            if content is None:
                continue

            for part in content.parts or []:
                inline_data = getattr(part, "inline_data", None)

                if inline_data is None:
                    continue

                image_bytes = inline_data.data
                mime_type = inline_data.mime_type or "image/png"
                break

            if image_bytes is not None:
                break

        if image_bytes is None:
            raise ValueError("Gemini 응답에서 이미지 데이터를 찾을 수 없습니다.")

        width, height = self._extract_size(
            image_bytes=image_bytes,
        )

        logger.info(
            "[gemini_image_generation_completed] mime_type=%s | width=%s | height=%s | size=%s",
            mime_type,
            width,
            height,
            len(image_bytes),
        )

        return GeneratedImageBinary(
            image_bytes=image_bytes,
            mime_type=mime_type,
            width=width,
            height=height,
        )

    @staticmethod
    def _extract_size(
        *,
        image_bytes: bytes,
    ) -> tuple[int | None, int | None]:
        try:
            image = Image.open(BytesIO(image_bytes))
            return image.width, image.height
        except Exception:
            return None, None