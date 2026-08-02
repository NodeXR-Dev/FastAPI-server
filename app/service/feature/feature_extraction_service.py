from openai import AsyncOpenAI

from app.ai.prompts.feature_extraction_prompt import (
    FEATURE_EXTRACTION_SYSTEM_PROMPT,
    build_feature_extraction_prompt,
)
from app.core.config import settings
from app.core.logger import get_logger
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException
from app.schema.feature.extraction import FeatureExtractionResult

logger = get_logger(__name__)


class FeatureExtractionService:
    def __init__(self, *, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def extract(self, *, feature_text: str) -> list[str]:
        if not feature_text or not any(
            character.isalnum() for character in feature_text
        ):
            raise BadRequestException(code=ResponseCode.FEATURE400)

        normalized_text = feature_text.strip()
        logger.info(
            "[feature_extraction_started] model=%s | text_length=%s",
            settings.OPENAI_PROMPT_MODEL,
            len(normalized_text),
        )

        try:
            completion = await self.client.chat.completions.parse(
                model=settings.OPENAI_PROMPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": FEATURE_EXTRACTION_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": build_feature_extraction_prompt(normalized_text),
                    },
                ],
                response_format=FeatureExtractionResult,
                temperature=0.1,
            )
            result = self._parse_completion(completion)
            feature_texts = self._deduplicate(result)

            if not feature_texts:
                raise ServerException(
                    code=ResponseCode.FEATURE500,
                    message="OpenAI 응답에서 저장할 기능을 찾을 수 없습니다.",
                )

            logger.info(
                "[feature_extraction_completed] feature_count=%s",
                len(feature_texts),
            )
            return feature_texts

        except (BadRequestException, ServerException):
            raise
        except Exception as error:
            logger.exception(
                "[feature_extraction_failed] text_length=%s | error=%s",
                len(normalized_text),
                str(error),
            )
            raise ServerException(
                code=ResponseCode.FEATURE500,
                message="OpenAI 기능 추출에 실패했습니다.",
            ) from error

    def _parse_completion(self, completion) -> FeatureExtractionResult:
        try:
            message = completion.choices[0].message

            if getattr(message, "refusal", None):
                raise ServerException(
                    code=ResponseCode.FEATURE500,
                    message="OpenAI 기능 추출 요청이 거절되었습니다.",
                )

            if message.parsed is None:
                raise ServerException(
                    code=ResponseCode.FEATURE500,
                    message="OpenAI 기능 추출 응답이 비어 있습니다.",
                )

            if isinstance(message.parsed, FeatureExtractionResult):
                return message.parsed

            return FeatureExtractionResult.model_validate(message.parsed)

        except ServerException:
            raise
        except Exception as error:
            raise ServerException(
                code=ResponseCode.FEATURE500,
                message="OpenAI 기능 추출 응답 파싱에 실패했습니다.",
            ) from error

    def _deduplicate(self, result: FeatureExtractionResult) -> list[str]:
        feature_texts: list[str] = []
        seen: set[str] = set()

        for feature in result.features:
            feature_text = feature.text.strip()
            normalized_key = feature_text.casefold()

            if not feature_text or normalized_key in seen:
                continue

            seen.add(normalized_key)
            feature_texts.append(feature_text)

        return feature_texts
