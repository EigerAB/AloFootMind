from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_URL: str = "postgresql+asyncpg://alofootmind:alofootmind@localhost:5432/alofootmind"
    REDIS_URL: str = "redis://localhost:6379/0"
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    STATSBOMB_DATA_PATH: str = ""
    EMBEDDING_MODEL: str = "BAAI/bge-m3"

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


settings = Settings()
