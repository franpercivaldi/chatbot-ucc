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
    RERANKER_MAX_DOCS: int = 15  # budget: máx docs a procesar en reranker (reduce latencia)
    
    # Fallback de retrieval: si hay pocos hits, relajar filtros
    ENABLE_RETRIEVAL_FALLBACK: bool = True
    RETRIEVAL_MIN_HITS: int = 3  # threshold para activar fallback
    
    # Performance: timeouts y límites
    GEMINI_GEN_TIMEOUT: int = 25  # timeout para generación de respuesta
    MAX_HISTORY_TOKENS: int = 2000  # límite aproximado de tokens de historial
    SKIP_REWRITER_THRESHOLD: int = 4  # skip rewriter si query tiene <= N palabras
    
    # Cache de respuestas (evita re-generar para preguntas repetidas)
    ENABLE_RESPONSE_CACHE: bool = True
    RESPONSE_CACHE_TTL: int = 86400  # 24 horas en segundos

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
