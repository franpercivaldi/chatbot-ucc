from fastapi import APIRouter, Query
from ..metrics.store import top_carreras, top_dominios, unanswered, daily_counts
from ..rag.embedder import get_cache_stats
from ..rag.query_rewriter import get_rewriter_stats
from ..cache.store import stats as response_cache_stats, purge as purge_response_cache

router = APIRouter()

@router.get("/admin/metrics/top-carreras")
def _top_carreras(bot_id: str = Query("public-admisiones"), days: int = Query(90), limit: int = Query(20)):
    import time
    since = int(time.time()) - days*86400 if days else None
    return {"bot_id": bot_id, "days": days, "items": top_carreras(bot_id, since, limit)}

@router.get("/admin/metrics/dominios")
def _doms(bot_id: str = Query("public-admisiones"), days: int = Query(90)):
    import time
    since = int(time.time()) - days*86400 if days else None
    return {"bot_id": bot_id, "days": days, "items": top_dominios(bot_id, since)}

@router.get("/admin/metrics/unanswered")
def _un(bot_id: str = Query("public-admisiones"), days: int = Query(30), limit: int = Query(50)):
    import time
    since = int(time.time()) - days*86400 if days else None
    return {"bot_id": bot_id, "days": days, "items": unanswered(bot_id, since, limit)}

@router.get("/admin/metrics/daily")
def _daily(bot_id: str = Query("public-admisiones"), days: int = Query(30)):
    return {"bot_id": bot_id, "days": days, "items": daily_counts(bot_id, days)}

@router.get("/admin/metrics/embeddings-cache")
def _embeddings_cache():
    """Estadísticas de cache de embeddings (hits/misses desde el último restart)."""
    stats = get_cache_stats()
    query_total = stats["query_hits"] + stats["query_misses"]
    doc_total = stats["doc_hits"] + stats["doc_misses"]
    return {
        "query_hits": stats["query_hits"],
        "query_misses": stats["query_misses"],
        "query_hit_rate": round(stats["query_hits"] / query_total, 3) if query_total > 0 else 0,
        "doc_hits": stats["doc_hits"],
        "doc_misses": stats["doc_misses"],
        "doc_hit_rate": round(stats["doc_hits"] / doc_total, 3) if doc_total > 0 else 0,
    }

@router.get("/admin/metrics/query-rewriter")
def _query_rewriter():
    """Estadísticas del query rewriter (éxitos/fallos de parseo/LLM desde restart)."""
    stats = get_rewriter_stats()
    return {
        "success": stats["success"],
        "parse_fail": stats["parse_fail"],
        "llm_fail": stats["llm_fail"],
        "total": stats["total"],
        "success_rate": stats["success_rate"],
    }

@router.get("/admin/metrics/response-cache")
def _response_cache(bot_id: str = Query(None)):
    """Estadísticas del cache de respuestas (entradas almacenadas en SQLite)."""
    stats = response_cache_stats(bot_id)
    return {
        "bot_id": bot_id or "all",
        "entries": stats["entries"],
        "ttl_seconds": stats["ttl_seconds"],
    }

@router.delete("/admin/metrics/response-cache")
def _purge_response_cache(bot_id: str = Query(None)):
    """Purga el cache de respuestas (todo o por bot_id)."""
    deleted = purge_response_cache(bot_id)
    return {"purged": deleted, "bot_id": bot_id or "all"}
