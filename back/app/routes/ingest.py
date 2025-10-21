import os
import traceback
from typing import Dict
import pandas as pd
from fastapi import APIRouter, Depends, Query

from ..deps import admin_key, get_qdrant
from ..config import settings
from ..rag.chunking import load_xlsx_dir, list_data_files, normalize_columns, _domain_from_name_and_cols
from ..rag.retriever import upsert_records, count_points
from ..catalog.entities import upsert_from_records
from ..ingest.validate import validate_dataframe, save_reports_jsonl

router = APIRouter()

# Ruta por defecto para guardar reportes de validación
REPORTS_PATH = os.environ.get("INGEST_REPORTS_PATH", "/app/state/ingest_reports.jsonl")

# ---------- helpers locales para lectura de archivos (solo para validación) ----------
def _read_any(path: str) -> Dict[str, pd.DataFrame]:
    """
    Lee CSV/TSV/TXT/XLS/XLSX y devuelve dict {sheet_name: DataFrame}.
    Es solo para VALIDACIÓN (la ingesta real usa load_xlsx_dir).
    """
    low = path.lower()
    if low.endswith((".csv", ".txt")):
        import csv
        encodings = ["utf-8", "utf-8-sig", "latin-1"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    sample = f.read(4096)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                sep = dialect.delimiter or ","
                return {"CSV": pd.read_csv(path, encoding=enc, sep=sep)}
            except Exception:
                continue
        # fallback
        return {"CSV": pd.read_csv(path, encoding="utf-8", sep=",", on_bad_lines="skip")}
    if low.endswith((".tsv",)):
        return {"TSV": pd.read_csv(path, sep="\t")}
    # Excel (todas las hojas)
    xls = pd.ExcelFile(path)
    return {sheet: xls.parse(sheet_name=sheet) for sheet in xls.sheet_names}


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

    counts_by_domain: Dict[str, int] = {}
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
    # 1) Ubicación de datos
    xlsx_dir = os.path.join("/app", "data", "xlsx", bot_id)
    if not os.path.isdir(xlsx_dir):
        return {"ok": False, "msg": f"No existe {xlsx_dir}"}

    files = list_data_files(xlsx_dir)
    if not files:
        return {"ok": True, "msg": f"No se encontraron archivos en {xlsx_dir}", "indexed": 0}

    # 2) VALIDACIÓN (por archivo/hoja) + guardado de reportes JSONL
    file_reports = []
    try:
        for fname in files:
            path = os.path.join(xlsx_dir, fname)
            try:
                sheets = _read_any(path)
            except Exception:
                # si no se puede abrir el archivo, lo reportamos como error de archivo
                from ..ingest.validate import Problem, FileReport
                file_reports.append(FileReport(
                    bot_id=bot_id, file=fname, sheet="(open-error)", domain="general", rows=0,
                    problems=[Problem(level="error", code="file_open_error",
                                      msg=f"No se pudo abrir el archivo {fname}")]
                ))
                continue

            for sheet_name, df in (sheets or {}).items():
                if df is None or df.empty:
                    continue
                # normalizar columnas y dominio
                df_norm = normalize_columns(df).dropna(how="all").fillna("")
                domain = _domain_from_name_and_cols(fname, sheet_name, df_norm)
                try:
                    rep = validate_dataframe(
                        bot_id=bot_id, file=fname, sheet=sheet_name, domain=domain, df=df_norm
                    )
                    file_reports.append(rep)
                except Exception:
                    # no romper ingesta si falla el validador en alguna hoja
                    from ..ingest.validate import Problem, FileReport
                    file_reports.append(FileReport(
                        bot_id=bot_id, file=fname, sheet=sheet_name, domain=domain, rows=len(df_norm),
                        problems=[Problem(level="error", code="validation_exception",
                                          msg="Excepción durante la validación de esta hoja")]
                    ))
        # persistimos reportes
        if file_reports:
            save_reports_jsonl(REPORTS_PATH, file_reports)
    except Exception:
        # nunca impedir la ingesta por la validación
        pass

    # 3) INGESTA real (records -> catálogo + qdrant)
    try:
        records = load_xlsx_dir(xlsx_dir, bot_id=bot_id)
        upsert_from_records(records, bot_id=bot_id)
        total = len(records)
        if total == 0:
            return {
                "ok": True,
                "msg": "No se encontraron filas válidas en los archivos",
                "indexed": 0,
                "archivos": files,
                "bot_id": bot_id,
                "validation": {
                    "reports_saved": len(file_reports),
                    "reports_path": REPORTS_PATH
                }
            }

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
            "validation": {
                "reports_saved": len(file_reports),
                "reports_path": REPORTS_PATH
            }
        }
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        return {"ok": False, "msg": f"Error en ingesta: {e.__class__.__name__}: {e}", "trace": tb}


@router.delete("/reset")
def ingest_reset(_: None = Depends(admin_key), client = Depends(get_qdrant)):
    try:
        client.delete_collection(settings.QDRANT_COLLECTION)
    except Exception:
        pass
    return {"ok": True, "msg": f"Collection {settings.QDRANT_COLLECTION} eliminada"}
