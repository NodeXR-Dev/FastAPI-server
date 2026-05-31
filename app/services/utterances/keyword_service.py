# app/services/utterances/keyword_service.py

import os
import time
from functools import lru_cache

from openai import OpenAI

from app.core.logger import get_logger
from app.core.performance import performance_tracker
from app.core.response.code import ResponseCode
from app.core.response.exceptions import BadRequestException, ServerException
from app.ai.prompts.keyword_prompt import (
    KEYWORD_EXTRACT_SYSTEM_PROMPT,
    build_keyword_extract_prompt,
)
from app.schemas.openai.keyword import KeywordExtractResult

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ServerException(
            code=ResponseCode.BTUTT500,
            message="OpenAI API Key가 설정되어 있지 않습니다.",
        )

    return OpenAI(api_key=api_key)


class KeywordService:
    def __init__(self):
        self.model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        self.max_nodes = int(os.getenv("GRAPH_EXTRACT_MAX_NODES", "5"))

    def keyword_extract(self, text: str) -> KeywordExtractResult:
        stage = "graph_extract"
        start_time = time.perf_counter()

        logger.info(
            "[graph_extract] start | text_length=%s | model=%s",
            len(text) if text is not None else None,
            self.model_name,
        )

        try:
            if text is None or not text.strip():
                raise BadRequestException(
                    code=ResponseCode.BTUTT400,
                    message="그래프를 추출할 발화 내용은 비어 있을 수 없습니다.",
                )

            client = get_openai_client()
            prompt = build_keyword_extract_prompt(text.strip())

            completion = client.chat.completions.parse(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": KEYWORD_EXTRACT_SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                response_format=KeywordExtractResult,
                temperature=0.2,
            )

            result = self._parse_response(completion)
            result = self._postprocess_result(result)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            avg_ms = performance_tracker.record(stage, elapsed_ms)

            logger.info(
                "[graph_extract] done | elapsed_ms=%.2f | avg_ms=%.2f | node_count=%s | parent_edge_count=%s | internal_edge_count=%s",
                elapsed_ms,
                avg_ms,
                len(result.nodes),
                len(result.parent_edges),
                len(result.internal_edges),
            )

            return result

        except BadRequestException:
            raise

        except ServerException:
            raise

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.exception(
                "[graph_extract] failed | elapsed_ms=%.2f | error=%s",
                elapsed_ms,
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="그래프 추출 중 서버 오류가 발생했습니다.",
            )

    def _parse_response(self, completion) -> KeywordExtractResult:
        try:
            message = completion.choices[0].message

            if getattr(message, "refusal", None):
                raise ServerException(
                    code=ResponseCode.BTUTT500,
                    message="OpenAI 그래프 추출 요청이 거절되었습니다.",
                )

            if message.parsed is None:
                raise ServerException(
                    code=ResponseCode.BTUTT500,
                    message="OpenAI 그래프 추출 응답이 비어 있습니다.",
                )

            if isinstance(message.parsed, KeywordExtractResult):
                return message.parsed

            return KeywordExtractResult.model_validate(message.parsed)

        except ServerException:
            raise

        except Exception as e:
            logger.exception(
                "[graph_extract] parse_failed | error=%s",
                str(e),
            )

            raise ServerException(
                code=ResponseCode.BTUTT500,
                message="OpenAI 그래프 추출 응답 파싱에 실패했습니다.",
            )

    def _postprocess_result(self, result: KeywordExtractResult) -> KeywordExtractResult:
        unique_nodes = []
        seen_node_texts = set()

        for node in result.nodes:
            node_text = node.node_text.strip()

            if not node_text:
                continue

            if node_text in seen_node_texts:
                continue

            seen_node_texts.add(node_text)
            unique_nodes.append(node)

            if len(unique_nodes) >= self.max_nodes:
                break

        valid_node_texts = {node.node_text for node in unique_nodes}

        parent_edges = [
            edge
            for edge in result.parent_edges
            if edge.to_node_text in valid_node_texts
        ]

        internal_edges = [
            edge
            for edge in result.internal_edges
            if edge.from_node_text in valid_node_texts
            and edge.to_node_text in valid_node_texts
            and edge.from_node_text != edge.to_node_text
        ]

        return KeywordExtractResult(
            nodes=unique_nodes,
            parent_edges=parent_edges,
            internal_edges=internal_edges,
        )