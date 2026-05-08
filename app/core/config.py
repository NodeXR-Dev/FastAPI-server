from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "NodeXR"

    DATABASE_URL: str

    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_BUCKET: str = "nodexr-assets"
    MINIO_USE_SSL: bool = False

    GEMINI_API_KEY: str | None = None
    MESHY_API_KEY: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()