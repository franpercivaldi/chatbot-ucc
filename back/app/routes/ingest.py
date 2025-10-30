import os
import traceback
from typing import Dict, List
import pandas as pd
from fastapi import APIRouter, Depends, Query

from ..deps import admin_key, get_qdrant
from ..config import settings
from ..rag.chunking import load_xlsx_dir, list_data_files, normalize_columns, _domain_from_name_and_cols
from ..rag.retriever import upsert_records, count_points
from ..catalog.entities import upsert_from_records
from ..ingest.validate import validate_dataframe, save_reports_jsonl
from ..rag.pdf_loader import load_pdf_dir

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


# ============ PREVIEW ============
@router.get("/preview")
def ingest_preview(
    bot_id: str = Query("public-admisiones"),
    source: str = Query("all", pattern="^(all|xlsx|docs)$"),
    only_domain: str | None = Query(None),
    sample_size: int = Query(10, ge=1, le=200),
):
    # Rutas base
    xlsx_dir_try = os.path.join("/app", "data", "xlsx", bot_id)
    xlsx_dir_fallback = "/app/data/xlsx"
    docs_dir = os.path.join("/app", "data", "docs", bot_id)

    # Resolución de carpeta de planillas
    data_dir = xlsx_dir_try if os.path.isdir(xlsx_dir_try) else (xlsx_dir_fallback if os.path.isdir(xlsx_dir_fallback) else None)

    # Registros y archivos
    records: List[Dict] = []
    files_x: List[str] = []
    files_p: List[str] = []

    # CSV/XLSX
    if source in ("all", "xlsx") and data_dir:
        files_x = list_data_files(data_dir)
        records_x = load_xlsx_dir(data_dir, bot_id=bot_id) or []
        records.extend(records_x)

    # PDFs
    if source in ("all", "docs") and os.path.isdir(docs_dir):
        records_p = load_pdf_dir(bot_id) or []
        records.extend(records_p)
        # listar PDFs
        for root, _, fs in os.walk(docs_dir):
            files_p.extend([
                os.path.relpath(os.path.join(root, f), docs_dir)
                for f in fs if f.lower().endswith(".pdf")
            ])

    files = files_x + [f"(PDF) {p}" for p in sorted(files_p)]

    if only_domain:
        records = [r for r in records if (r.get("metadata", {}).get("domain") == only_domain)]

    sample = records[:sample_size] if records else []

    counts_by_domain: Dict[str, int] = {}
    for r in records:
        d = (r.get("metadata", {}).get("domain") or "general")
        counts_by_domain[d] = counts_by_domain.get(d, 0) + 1

    return {
        "files": files,
        "counts_by_domain": counts_by_domain,
        "sample": sample,
        "total_records": len(records),
        "bot_id": bot_id,
        "source": source,
    }


# ============ INGESTA GENERAL ============
@router.post("/run")
def ingest_run(
    _: None = Depends(admin_key),
    client = Depends(get_qdrant),
    bot_id: str = Query("public-admisiones"),
    source: str = Query("all", pattern="^(all|xlsx|docs)$"),
):
    # Paths
    xlsx_dir_try = os.path.join("/app", "data", "xlsx", bot_id)
    xlsx_dir_fallback = "/app/data/xlsx"
    docs_dir = os.path.join("/app", "data", "docs", bot_id)

    records: List[Dict] = []
    files_xlsx: List[str] = []
    files_pdf: List[str] = []
    file_reports = []

    # ---------- 1) Planillas (xlsx/csv) ----------
    if source in ("all", "xlsx"):
        if os.path.isdir(xlsx_dir_try):
            xlsx_dir = xlsx_dir_try
        elif os.path.isdir(xlsx_dir_fallback):
            xlsx_dir = xlsx_dir_fallback
        else:
            xlsx_dir = None

        if xlsx_dir:
            files_xlsx = list_data_files(xlsx_dir)

            # VALIDACIÓN (no bloqueante)
            try:
                for fname in files_xlsx:
                    path = os.path.join(xlsx_dir, fname)
                    try:
                        sheets = _read_any(path)
                    except Exception:
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
                        df_norm = normalize_columns(df).dropna(how="all").fillna("")
                        domain = _domain_from_name_and_cols(fname, sheet_name, df_norm)
                        try:
                            rep = validate_dataframe(bot_id=bot_id, file=fname, sheet=sheet_name, domain=domain, df=df_norm)
                            file_reports.append(rep)
                        except Exception:
                            from ..ingest.validate import Problem, FileReport
                            file_reports.append(FileReport(
                                bot_id=bot_id, file=fname, sheet=sheet_name, domain=domain, rows=len(df_norm),
                                problems=[Problem(level="error", code="validation_exception",
                                                  msg="Excepción durante la validación de esta hoja")]
                            ))
                if file_reports:
                    save_reports_jsonl(REPORTS_PATH, file_reports)
            except Exception:
                pass

            # INGESTA de planillas
            if files_xlsx:
                records += load_xlsx_dir(xlsx_dir, bot_id=bot_id) or []

    # ---------- 2) PDFs ----------
    if source in ("all", "docs") and os.path.isdir(docs_dir):
        records += load_pdf_dir(bot_id) or []
        for root, _, fs in os.walk(docs_dir):
            files_pdf.extend([
                os.path.relpath(os.path.join(root, f), docs_dir)
                for f in fs if f.lower().endswith(".pdf")
            ])

    # ---------- 3) Si no hay nada, devolvemos mensaje claro ----------
    if not records:
        return {
            "ok": False,
            "msg": f"No hay archivos para ingerir (xlsx_dir='{xlsx_dir_try if os.path.isdir(xlsx_dir_try) else xlsx_dir_fallback}', docs_dir='{docs_dir}')",
            "archivos": files_xlsx + [f"(PDF) {p}" for p in sorted(files_pdf)],
            "bot_id": bot_id,
            "source": source,
            "validation": {
                "reports_saved": len(file_reports),
                "reports_path": REPORTS_PATH
            }
        }

    # ---------- 4) Upserts (catálogo + vectores) ----------
    try:
        upsert_from_records(records, bot_id=bot_id)
        upsert_records(client, records, collection=settings.QDRANT_COLLECTION)
        cnt = count_points(client, settings.QDRANT_COLLECTION)

        return {
            "ok": True,
            "msg": "Ingesta completada",
            "found_rows": len(records),
            "collection": settings.QDRANT_COLLECTION,
            "count_now": cnt,
            "archivos": files_xlsx + [f"(PDF) {p}" for p in sorted(files_pdf)],
            "bot_id": bot_id,
            "source": source,
            "validation": {
                "reports_saved": len(file_reports),
                "reports_path": REPORTS_PATH
            }
        }
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        return {"ok": False, "msg": f"Error en ingesta: {e.__class__.__name__}: {e}", "trace": tb}


# ============ ALIAS LEGACY ============
@router.post("/xlsx")
def ingest_xlsx_legacy(
    _: None = Depends(admin_key),
    client = Depends(get_qdrant),
    bot_id: str = Query("public-admisiones"),
):
    # Alias hacia /run con source=all
    return ingest_run(_, client, bot_id, source="all")


# ============ RESET ============
@router.delete("/reset")
def ingest_reset(_: None = Depends(admin_key), client = Depends(get_qdrant)):
    try:
        client.delete_collection(settings.QDRANT_COLLECTION)
    except Exception:
        pass
    return {"ok": True, "msg": f"Collection {settings.QDRANT_COLLECTION} eliminada"}
