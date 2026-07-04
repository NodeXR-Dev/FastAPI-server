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
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str = "gemini-3.1-flash-image"
    MESHY_API_KEY: str | None = None
    
    EMBEDDING_DIM: int = 1536
    
    TOPIC_DRIFT_THRESHOLD: float = 0.55
    DISCUSSION_SIMILARITY_THRESHOLD: float = 0.78

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()