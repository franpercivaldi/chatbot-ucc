from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from .config import settings
from .routes import health, chat, ingest

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

# Métricas
Instrumentator().instrument(app).expose(app)

@app.get("/")
def root():
    return {"ok": True, "service": "admisiones-backend"}
