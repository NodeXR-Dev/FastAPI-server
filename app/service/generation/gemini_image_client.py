import asyncio
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.logger import get_logger
from app.schema.generation.generation_result import GeneratedImageBinary

logger = get_logger(__name__)


class GeminiImageClient:
    MIME_TYPE_BY_FORMAT = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }

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

        response = await self._generate_content(
            contents=prompt_text,
        )

        generated_image = await asyncio.to_thread(
            self._parse_generated_image,
            response=response,
        )

        logger.info(
            "[gemini_image_generation_completed] mime_type=%s | width=%s | height=%s | size=%s",
            generated_image.mime_type,
            generated_image.width,
            generated_image.height,
            len(generated_image.image_bytes),
        )
        return generated_image

    async def edit_image_colors(
        self,
        *,
        prompt_text: str,
        source_image_bytes: bytes,
        source_mime_type: str,
        guide_image_bytes: bytes,
        guide_mime_type: str,
    ) -> GeneratedImageBinary:
        logger.info(
            "[gemini_color_change_started] model=%s | prompt_length=%s | source_size=%s | guide_size=%s",
            settings.GEMINI_MODEL_NAME,
            len(prompt_text),
            len(source_image_bytes),
            len(guide_image_bytes),
        )

        response = await self._generate_content(
            contents=[
                prompt_text,
                types.Part.from_bytes(
                    data=source_image_bytes,
                    mime_type=source_mime_type,
                ),
                types.Part.from_bytes(
                    data=guide_image_bytes,
                    mime_type=guide_mime_type,
                ),
            ],
        )
        generated_image = await asyncio.to_thread(
            self._parse_generated_image,
            response=response,
        )

        logger.info(
            "[gemini_color_change_completed] mime_type=%s | width=%s | height=%s | size=%s",
            generated_image.mime_type,
            generated_image.width,
            generated_image.height,
            len(generated_image.image_bytes),
        )
        return generated_image

    async def _generate_content(self, *, contents):
        return await asyncio.to_thread(
            self.client.models.generate_content,
            model=settings.GEMINI_MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

    def _parse_generated_image(self, *, response) -> GeneratedImageBinary:

        image_bytes: bytes | None = None

        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            if content is None:
                continue

            for part in content.parts or []:
                inline_data = getattr(part, "inline_data", None)

                if inline_data is None:
                    continue

                image_bytes = inline_data.data
                break

            if image_bytes is not None:
                break

        if image_bytes is None:
            raise ValueError("Gemini 응답에서 이미지 데이터를 찾을 수 없습니다.")

        mime_type, width, height = self.inspect_image(
            image_bytes=image_bytes,
        )

        return GeneratedImageBinary(
            image_bytes=image_bytes,
            mime_type=mime_type,
            width=width,
            height=height,
        )

    @classmethod
    def inspect_image(
        cls,
        *,
        image_bytes: bytes,
    ) -> tuple[str, int, int]:
        if not image_bytes:
            raise ValueError("이미지 데이터가 비어 있습니다.")

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                mime_type = cls.MIME_TYPE_BY_FORMAT.get(image.format or "")
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValueError("이미지 데이터를 디코딩할 수 없습니다.") from exc

        if mime_type is None:
            raise ValueError("지원하지 않는 이미지 형식입니다.")
        if width <= 0 or height <= 0:
            raise ValueError("이미지 크기가 올바르지 않습니다.")

        return mime_type, width, height
