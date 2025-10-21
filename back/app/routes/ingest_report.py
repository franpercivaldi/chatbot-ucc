# back/app/routes/ingest_report.py
from fastapi import APIRouter, Query
import os, json

router = APIRouter()

REPORTS_PATH = os.environ.get("INGEST_REPORTS_PATH", "/app/state/ingest_reports.jsonl")

@router.get("/ingest/report")
def get_ingest_report(bot_id: str = Query(...), last_n: int = Query(50)):
    """Devuelve los últimos N reportes de validación para un bot_id."""
    if not os.path.isfile(REPORTS_PATH):
        return {"items": []}

    items = []
    try:
        with open(REPORTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj.get("bot_id") == bot_id:
                        items.append(obj)
                except Exception:
                    continue
    except Exception:
        return {"items": []}

    items = sorted(items, key=lambda x: x.get("ts", 0), reverse=True)[:last_n]
    return {"items": items}
