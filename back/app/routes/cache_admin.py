from fastapi import APIRouter, Query
from ..cache.store import stats, purge

router = APIRouter()

@router.get("/admin/cache/stats")
def cache_stats(bot_id: str | None = Query(None)):
    return stats(bot_id)

@router.post("/admin/cache/purge")
def cache_purge(bot_id: str | None = Query(None)):
    n = purge(bot_id)
    return {"deleted": n}
