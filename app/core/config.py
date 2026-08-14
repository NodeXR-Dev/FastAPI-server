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

    # Meshy 는 리메시를 켜지 않으면 원본 밀도 그대로 내보낸다.
    # 실측(2026-08-15): 삼각형 196만 개 / GLB 81MB.
    # 그중 텍스처는 2.4MB 뿐이고 나머지 78.9MB 가 전부 지오메트리였다.
    # Quest 가 씬 전체로 감당하는 양이 그 정도라 모델 하나로 예산을 다 쓰고,
    # 헤드셋이 매번 81MB 를 내려받아야 한다.
    # 0 이하로 두면 상한을 걸지 않는다(예전 동작).
    MESHY_TARGET_POLYCOUNT: int = 30000
    MESHY_TOPOLOGY: str = "triangle"


    EMBEDDING_DIM: int = 1536
    
    TOPIC_DRIFT_THRESHOLD: float = 0.55
    DISCUSSION_SIMILARITY_THRESHOLD: float = 0.78
    TOPIC_SIMILARITY_THRESHOLD: float = 0.75
    AGENT_RETRIEVAL_TOP_K: int = 5
    MEMORY_GUARD_ALERT_THRESHOLD: float = 0.8

    REFLECTION_BATCH_ENABLED: bool = True
    REFLECTION_BATCH_INTERVAL_SECONDS: float = 300.0
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
