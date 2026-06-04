# app/services/utterances/embedding_service.py

import time
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException

logger = get_logger(__name__)


EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """
    서버 내 embedding 모델을 최초 1회만 로드한다.

    주의:
    - 모델 로딩은 오래 걸릴 수 있으므로 요청마다 로드하면 안 됨
    - lru_cache를 사용해서 서버 프로세스 내에서 재사용
    - jhgan/ko-sroberta-multitask는 일반적으로 768차원 embedding을 반환
    - 따라서 DB의 vector dimension도 768로 맞춰야 함
    """

    logger.info(
        "[embedding_model_load] start | model_name=%s",
        EMBEDDING_MODEL_NAME,
    )

    try:
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        logger.info(
            "[embedding_model_load] done | model_name=%s",
            EMBEDDING_MODEL_NAME,
        )

        return model

    except Exception as e:
        logger.exception(
            "[embedding_model_load] failed | model_name=%s | error=%s",
            EMBEDDING_MODEL_NAME,
            str(e),
        )

        raise ServerException(
            code=ResponseCode.BTUTT500,
            message="임베딩 모델 로딩 중 서버 오류가 발생했습니다.",
        )


class EmbeddingService:
    def embed_text(self, text: str) -> list[float]:
        """
        정규화된 발화를 embedding vector로 변환한다.

        사용 위치:
        - utterances.embedding 저장
        - topics.centroid_embedding 계산
        - semantic_memories.embedding 저장
        """

        stage = "embedding_model"
        start_time = time.perf_counter()

        logger.info(
            "[embedding_model] start | text_length=%s",
            len(text) if text is not None else None,
        )

        try:
            if text is None or not text.strip():
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="임베딩할 발화 내용은 비어 있을 수 없습니다.",
                )

            model = get_embedding_model()

            embedding = model.encode(
                text,
                normalize_embeddings=True,
            ).tolist()

            if not embedding:
                raise ServerException(
                    code=ResponseCode.BTUTT500,
                    message="임베딩 결과가 비어 있습니다.",
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[embedding_model] done | elapsed_ms=%.2f | avg_ms=%.2f | dim=%s",
                elapsed_ms,
                avg_ms,
                len(embedding),
            )

            return embedding

        except BadRequestException:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.warning(
                "[embedding_model] bad_request | elapsed_ms=%.2f",
                elapsed_ms,
            )

            raise

        except ServerException:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[embedding_model] server_exception | elapsed_ms=%.2f",
                elapsed_ms,
            )

            raise

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[embedding_model] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="임베딩 생성 중 서버 오류가 발생했습니다.",
            )