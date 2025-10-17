from fastapi import APIRouter, Depends
from ..deps import get_qdrant
from ..rag.embedder import embed_one

router = APIRouter()

@router.get("/")
def liveness():
    return {"status": "ok"}

@router.get("/qdrant")
def check_qdrant(client = Depends(get_qdrant)):
    info = client.get_collections()
    return {"status": "ok", "collections": [c.name for c in info.collections]}

@router.get("/gemini")
def check_gemini():
    vec = embed_one("healthcheck-gemini")
    return {"status": "ok", "dim": len(vec)}
