import threading
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from .config import settings
from .routes import health, chat, ingest, metrics
from app.routes import cache_admin
from app.routes import ingest_report
from .rag.embedder import warm_embedder
from .rag.reranker import warm_reranker
from .cache.store import ensure_schema as ensure_cache_schema
from .deps import get_qdrant

app = FastAPI(title="Admisiones UCC – Backend", version="0.1.0")

# CORS
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])
app.include_router(metrics.router, tags=["metrics"])
app.include_router(cache_admin.router, tags=["admin"])
app.include_router(ingest_report.router, tags=["admin"])

# Métricas
Instrumentator().instrument(app).expose(app)


def _run_warmups():
    # 1. Cache de respuestas (crear schema SQLite)
    try:
        ensure_cache_schema()
        print("[warmup] cache schema ok")
    except Exception as e:
        print(f"[warmup] cache schema fail: {e}")
    
    # 2. Qdrant connection
    try:
        client = get_qdrant()
        _ = client.get_collections()
        print("[warmup] qdrant ok")
    except Exception as e:
        print(f"[warmup] qdrant fail: {e}")
    
    # 3. Embedder (API warmup)
    ok_embed = warm_embedder()
    
    # 4. Reranker (model load)
    ok_rerank = warm_reranker()
    
    print(f"[warmup] embedder={'ok' if ok_embed else 'fail'} reranker={'ok' if ok_rerank else 'fail'}")


@app.on_event("startup")
async def warmup_on_start():
    # Ejecutamos en hilo para no bloquear el arranque del servidor.
    threading.Thread(target=_run_warmups, daemon=True).start()

@app.get("/")
def root():
    return {"ok": True, "service": "admisiones-backend"}

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # ⚠️ En prod podés ocultar detalles; por ahora nos sirve para debug
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": str(exc)},
    )