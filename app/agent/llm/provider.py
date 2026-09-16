from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


@lru_cache(maxsize=1)
def get_agent_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.AGENT_LLM_MODEL or settings.OPENAI_PROMPT_MODEL,
        temperature=0,
        timeout=settings.AGENT_LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


@lru_cache(maxsize=1)
def get_batch_llm() -> ChatOpenAI:
    """콜드 패스(배치) 전용. 한 번에 수십~수백 발화를 넣으므로 핫 패스보다
    넉넉한 타임아웃을 쓴다. 실측에서 발화 18건 재분할이 10초에서 끊겼다."""
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.AGENT_LLM_MODEL or settings.OPENAI_PROMPT_MODEL,
        temperature=0,
        timeout=settings.REFLECTION_BATCH_LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
