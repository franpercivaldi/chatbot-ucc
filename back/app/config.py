from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    APP_PORT: int = 8000
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    ADMIN_API_KEY: str = "cambia-esto"

    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-pro"
    GEMINI_EMBED_MODEL: str = "text-embedding-004"
    GEMINI_TIMEOUT: int = 30

    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "admisiones"
    QDRANT_TIMEOUT: int = 5

    RAG_TOP_K: int = 30
    RAG_RERANK_K: int = 5
    ENABLE_RERANKER: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
