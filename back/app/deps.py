from fastapi import Depends, Header, HTTPException, status
from .config import settings
from qdrant_client import QdrantClient

def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL, timeout=settings.QDRANT_TIMEOUT)

def admin_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
