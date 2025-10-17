import os, traceback
from fastapi import APIRouter, Depends, Query
from ..deps import admin_key, get_qdrant
from ..config import settings
from ..rag.chunking import load_xlsx_dir, list_data_files
from ..rag.retriever import upsert_records, count_points
from ..catalog.entities import upsert_from_records

router = APIRouter()

import os
import traceback
from fastapi import APIRouter, Depends, Query
from ..deps import admin_key, get_qdrant
from ..config import settings
from ..rag.chunking import load_xlsx_dir, list_data_files

router = APIRouter()

@router.get("/preview")
def ingest_preview(
    bot_id: str = Query("public-admisiones"),
    only_domain: str | None = Query(None),
    sample_size: int = Query(10, ge=1, le=200),
):
    base_dir = "/app/data/xlsx"
    data_dir = os.path.join(base_dir, bot_id)  # subcarpeta por bot
    if not os.path.isdir(data_dir):
        # fallback por si aún no separaste por bot
        data_dir = base_dir

    files = list_data_files(data_dir)
    records = load_xlsx_dir(data_dir, bot_id=bot_id) or []

    counts_by_domain = {}
    for r in records:
        d = (r.get("metadata", {}).get("domain") or "general")
        counts_by_domain[d] = counts_by_domain.get(d, 0) + 1

    if only_domain:
        sample = [r for r in records if (r.get("metadata", {}).get("domain") == only_domain)][:sample_size]
    else:
        sample = records[:sample_size]

    # 👇 nunca null
    if sample is None:
        sample = []

    return {
        "files": files,
        "counts_by_domain": counts_by_domain,
        "sample": sample,
        "total_records": len(records),
        "bot_id": bot_id,
    }


@router.post("/xlsx")
def ingest_xlsx(
    _: None = Depends(admin_key),
    client = Depends(get_qdrant),
    bot_id: str = Query("public-admisiones"),
):
    xlsx_dir = os.path.join("/app", "data", "xlsx", bot_id)
    if not os.path.isdir(xlsx_dir):
        return {"ok": False, "msg": f"No existe {xlsx_dir}"}

    files = list_data_files(xlsx_dir)
    if not files:
        return {"ok": True, "msg": f"No se encontraron archivos en {xlsx_dir}", "indexed": 0}

    try:
        records = load_xlsx_dir(xlsx_dir, bot_id=bot_id)
        upsert_from_records(records, bot_id=bot_id)
        total = len(records)
        if total == 0:
            return {"ok": True, "msg": "No se encontraron filas válidas en los archivos", "indexed": 0, "archivos": files, "bot_id": bot_id}

        upsert_records(client, records, collection=settings.QDRANT_COLLECTION)
        cnt = count_points(client, settings.QDRANT_COLLECTION)
        return {
            "ok": True,
            "msg": "Ingesta completada",
            "found_rows": total,
            "collection": settings.QDRANT_COLLECTION,
            "count_now": cnt,
            "archivos": files,
            "bot_id": bot_id,
        }
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        return {"ok": False, "msg": f"Error en ingesta: {e.__class__.__name__}: {e}", "trace": tb}


@router.delete("/reset")
def ingest_reset(_: None = Depends(admin_key), client = Depends(get_qdrant)):
    from ..config import settings
    try:
        client.delete_collection(settings.QDRANT_COLLECTION)
    except Exception:
        pass
    return {"ok": True, "msg": f"Collection {settings.QDRANT_COLLECTION} eliminada"}