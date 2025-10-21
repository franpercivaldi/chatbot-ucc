from fastapi import APIRouter, Query
from ..metrics.store import top_carreras, top_dominios, unanswered, daily_counts

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
