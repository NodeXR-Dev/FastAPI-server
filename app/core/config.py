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
    MINIO_BUCKET: str
    MINIO_USE_SSL: bool = False

    GEMINI_API_KEY: str | None = None
    MESHY_API_KEY: str | None = None
    
    EMBEDDING_DIM: int = 1536
    
    TOPIC_DRIFT_THRESHOLD: float = 0.55
    DISCUSSION_SIMILARITY_THRESHOLD: float = 0.78

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()