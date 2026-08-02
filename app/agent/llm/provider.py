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
