from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "NodeXR"

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    DATABASE_URL: str
    DB_ECHO: bool

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET_2D_ASSETS: str = "nodexr-2d-assets"
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_BASE_URL: str = "http://localhost:9000"

    OPENAI_API_KEY: str
    OPENAI_PROMPT_MODEL: str = "gpt-4.1-mini"
    AGENT_LLM_MODEL: str | None = None
    AGENT_LLM_TIMEOUT_SECONDS: float = 10.0
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-image"
    MESHY_API_KEY: str | None = None
    MESHY_BASE_URL: str = "https://api.meshy.ai"
    MESHY_POLL_INTERVAL_SECONDS: float = 5.0
    MESHY_POLL_TIMEOUT_SECONDS: float = 900.0
    MESHY_HTTP_TIMEOUT_SECONDS: float = 60.0
    
    EMBEDDING_DIM: int = 768

    TOPIC_DRIFT_THRESHOLD: float = 0.55
    DISCUSSION_SIMILARITY_THRESHOLD: float = 0.78
    TOPIC_SIMILARITY_THRESHOLD: float = 0.75
    AGENT_RETRIEVAL_TOP_K: int = 5
    AGENT_RETRIEVAL_FALLBACK_ENABLED: bool = False
    AGENT_RETRIEVAL_MIN_SIMILARITY: float = 0.0
    MEMORY_GUARD_ALERT_THRESHOLD: float = 0.8

    # Agent 결과를 응답에 포함(False)할지, 백그라운드 처리 후 push(True)할지.
    AGENT_ASYNC_DISPATCH_ENABLED: bool = False
    # 같은 room의 다른 참가자에게도 발화/Agent 이벤트를 전파할지.
    ROOM_EVENT_BROADCAST_ENABLED: bool = False
    # off | shadow (shadow는 판정만 로깅하고 동작을 바꾸지 않는다)
    NOISE_FILTER_MODE: str = "shadow"
    # True면 Recall/생성 요청은 호출어("노드베어")가 있는 발화에서만 수행한다.
    AGENT_WAKE_WORD_REQUIRED: bool = True

    REFLECTION_BATCH_ENABLED: bool = True
    REFLECTION_BATCH_INTERVAL_SECONDS: float = 300.0
    REFLECTION_BATCH_MAX_CONSECUTIVE_FAILURES: int = 3
    REFLECTION_BATCH_MAX_BACKOFF_CYCLES: float = 12.0
    REFLECTION_BATCH_MAX_UTTERANCES: int = 200
    REFLECTION_BATCH_MAX_GRAPH_EVENTS: int = 200
    REFLECTION_FACT_TOP_K: int = 100
    REFLECTION_MEMORY_TOP_K: int = 50
    BATCH_FACT_MIN_CONFIDENCE: float = 0.65
    BATCH_LINK_MIN_CONFIDENCE: float = 0.65
    FACT_DEDUP_SIMILARITY_THRESHOLD: float = 0.82

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "NodeXR-realtime-agent"
    LANGSMITH_ENDPOINT: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()
