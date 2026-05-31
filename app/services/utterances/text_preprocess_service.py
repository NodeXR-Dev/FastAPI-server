# app/services/utterances/text_preprocess_service.py

import re
import time

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException

logger = get_logger(__name__)


class TextPreprocessService:
    def utterance_preprocess(self, text: str) -> str:
        """
        STT 결과 발화를 regex 기반으로 정규화한다.

        정규화 범위:
        - None / 빈 문자열 / 공백 문자열 방지
        - 앞뒤 공백 제거
        - 줄바꿈, 탭을 공백으로 변환
        - 중복 공백 제거
        - 반복 문장부호 정리
        - 정규화 후 빈 문자열 재검증

        추후 필요 시 transformers 기반 문장 교정 모델을
        _model_normalize() 같은 별도 함수로 추가하면 된다.
        """

        stage = "utterance_preprocess"
        start_time = time.perf_counter()

        logger.info(
            "[utterance_preprocess] start | original_length=%s",
            len(text) if text is not None else None,
        )

        try:
            if text is None or not text.strip():
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="발화 내용은 비어 있을 수 없습니다.",
                )

            normalized_text = self._regex_normalize(text)

            if not normalized_text:
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="정규화 후 발화 내용이 비어 있습니다.",
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[utterance_preprocess] done | elapsed_ms=%.2f | avg_ms=%.2f | normalized_length=%s",
                elapsed_ms,
                avg_ms,
                len(normalized_text),
            )

            return normalized_text

        except BadRequestException:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.warning(
                "[utterance_preprocess] bad_request | elapsed_ms=%.2f",
                elapsed_ms,
            )

            raise

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[utterance_preprocess] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="발화 정규화 중 서버 오류가 발생했습니다.",
            )

    def _regex_normalize(self, text: str) -> str:
        """
        regex 기반 기본 정규화.
        모델을 쓰지 않는 빠른 전처리 단계.
        """

        normalized_text = text.strip()

        # 줄바꿈, 탭을 공백으로 변환
        normalized_text = re.sub(r"[\n\t]+", " ", normalized_text)

        # 중복 공백 제거
        normalized_text = re.sub(r"\s+", " ", normalized_text)

        # 반복 문장부호 축약
        normalized_text = re.sub(r"[.]{2,}", ".", normalized_text)
        normalized_text = re.sub(r"[!]{2,}", "!", normalized_text)
        normalized_text = re.sub(r"[?]{2,}", "?", normalized_text)

        return normalized_text.strip()