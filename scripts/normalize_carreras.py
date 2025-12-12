from __future__ import annotations

import csv
import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "xlsx" / "public-admisiones"
OUT_DIR = BASE_DIR / "data" / "normalized"

ARANCELES_FILE = RAW_DIR / "aranceles_carreras.csv"
DATOS_FILE = RAW_DIR / "datos_carreras_ofertas.csv"
OFERTAS_FILE = RAW_DIR / "ofertas-carreras.csv"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Helpers ---

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "na"

def detect_sep(path: Path) -> str:
    sample = path.read_text(encoding="utf-8", errors="ignore")[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter or ","
    except Exception:
        # fallback: detect semicolon presence
        if sample.count(";") > sample.count(","):
            return ";"
        return ","

def read_csv_any(path: Path) -> pd.DataFrame:
    sep = detect_sep(path)
    return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)

def parse_money(raw: str) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("$", "").replace(" ", "")
    s = s.replace(".", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def parse_int(raw: str) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None

def norm_name(text: str) -> str:
    return slugify(text or "").lower()

# --- Issue logging ---

Issue = Dict[str, str]

def log_issue(issues: List[Issue], issue_type: str, source_file: str, raw_row_index: int | str, carrera_id: str = "", details: str = "") -> None:
    issues.append({
        "issue_type": issue_type,
        "source_file": source_file,
        "raw_row_index": str(raw_row_index),
        "carrera_id": str(carrera_id or ""),
        "details": details,
    })

# --- Loading ---

def load_raw_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    aranceles = read_csv_any(ARANCELES_FILE) if ARANCELES_FILE.exists() else pd.DataFrame()
    datos = read_csv_any(DATOS_FILE) if DATOS_FILE.exists() else pd.DataFrame()
    ofertas = read_csv_any(OFERTAS_FILE) if OFERTAS_FILE.exists() else pd.DataFrame()
    logger.info("Loaded raw files: aranceles=%d rows, datos=%d rows, ofertas=%d rows", len(aranceles), len(datos), len(ofertas))
    return aranceles, datos, ofertas

# --- Normalization core ---

def normalize_carreras(aranceles: pd.DataFrame, datos: pd.DataFrame, ofertas: pd.DataFrame, issues: List[Issue]):
    records = {}
    name_index: Dict[str, List[str]] = {}
    alias_rows: List[Tuple[str, str]] = []

    def add_to_index(cid: str, *names: str):
        for n in names:
            if not n:
                continue
            key = norm_name(n)
            if not key:
                continue
            name_index.setdefault(key, [])
            if cid not in name_index[key]:
                name_index[key].append(cid)

    # 1) cargar datos y aranceles por ID
    for idx, row in datos.iterrows():
        cid = str(row.get("IDENTIFICADOR_CARRERA") or "").strip()
        if not cid:
            log_issue(issues, "MISSING_ID", "datos_carreras_ofertas", idx, details="Fila sin IDENTIFICADOR_CARRERA")
            continue
        carrera = str(row.get("CARRERA") or "").strip()
        titulo = str(row.get("TITULO") or "").strip()
        area = str(row.get("AREA_ESTUDIO") or "").strip()
        nivel = str(row.get("NIVEL_ESTUDIO") or "").strip()
        rec = records.get(cid, {"carrera_id": cid})
        if carrera:
            if rec.get("carrera_nombre") and rec["carrera_nombre"].lower() != carrera.lower():
                log_issue(issues, "ID_CONFLICT", "datos_carreras_ofertas", idx, cid, details=f"Nombre distinto para ID {cid}: '{rec.get('carrera_nombre')}' vs '{carrera}'")
            rec["carrera_nombre"] = rec.get("carrera_nombre") or carrera
        if titulo:
            rec["titulo"] = rec.get("titulo") or titulo
        if area:
            rec["area_estudio"] = rec.get("area_estudio") or area
        if nivel:
            rec["nivel_estudio"] = rec.get("nivel_estudio") or nivel
        records[cid] = rec
        add_to_index(cid, carrera, titulo)
        alias_rows.extend([(cid, a) for a in [carrera, titulo] if a])

    for idx, row in aranceles.iterrows():
        cid = str(row.get("IDENTIFICADOR_CARRERA") or "").strip()
        carrera = str(row.get("CARRERA") or "").strip()
        if not cid:
            log_issue(issues, "MISSING_ID", "aranceles_carreras", idx, details="Fila sin IDENTIFICADOR_CARRERA")
            continue
        rec = records.get(cid, {"carrera_id": cid})
        if carrera:
            if rec.get("carrera_nombre") and rec["carrera_nombre"].lower() != carrera.lower():
                log_issue(issues, "ID_CONFLICT", "aranceles_carreras", idx, cid, details=f"Nombre distinto para ID {cid}: '{rec.get('carrera_nombre')}' vs '{carrera}'")
            rec["carrera_nombre"] = rec.get("carrera_nombre") or carrera
        records[cid] = rec
        add_to_index(cid, carrera)
        if carrera:
            alias_rows.append((cid, carrera))

    # 2) ofertas-carreras: sin ID, intentar match
    def resolve_id_for_offer(alias: str, titulo: str) -> Tuple[str, bool]:
        candidates = []
        for val in [alias, titulo]:
            key = norm_name(val) if val else ""
            if key and key in name_index:
                candidates.extend(name_index[key])
        if candidates:
            return candidates[0], False  # choose first match
        base = alias or titulo or "sin-nombre"
        return f"AUTO_{slugify(base)[:32]}", True

    for idx, row in ofertas.iterrows():
        alias = str(row.get("ALIAS") or "").strip()
        titulo = str(row.get("TITULO") or "").strip()
        cid, is_auto = resolve_id_for_offer(alias, titulo)
        if is_auto and cid not in records:
            log_issue(issues, "MISSING_ID_AUTO", "ofertas-carreras", idx, cid, details="Se generó carrera_id sintético")
        rec = records.get(cid, {"carrera_id": cid})
        if not rec.get("carrera_nombre"):
            rec["carrera_nombre"] = alias or titulo
        if not rec.get("titulo") and titulo:
            rec["titulo"] = titulo
        records[cid] = rec
        add_to_index(cid, alias, titulo)
        for a in [alias, titulo]:
            if a:
                alias_rows.append((cid, a))

    carreras_rows = []
    for rec in records.values():
        carreras_rows.append({
            "carrera_id": rec.get("carrera_id"),
            "carrera_nombre": rec.get("carrera_nombre"),
            "titulo": rec.get("titulo"),
            "area_estudio": rec.get("area_estudio"),
            "nivel_estudio": rec.get("nivel_estudio"),
        })

    # dedupe aliases
    alias_dedup = []
    seen_alias = set()
    for cid, al in alias_rows:
        key = (cid, al.strip())
        if al and key not in seen_alias:
            seen_alias.add(key)
            alias_dedup.append({"carrera_id": cid, "alias": al.strip()})

    return pd.DataFrame(carreras_rows), pd.DataFrame(alias_dedup), name_index


def normalize_ofertas(datos: pd.DataFrame, ofertas: pd.DataFrame, name_index: Dict[str, List[str]], issues: List[Issue]):
    rows = []

    def match_id(alias: str, titulo: str) -> Optional[str]:
        for val in [alias, titulo]:
            key = norm_name(val) if val else ""
            if key and key in name_index:
                return name_index[key][0]
        return None

    # datos_carreras_ofertas
    for idx, row in datos.iterrows():
        cid = str(row.get("IDENTIFICADOR_CARRERA") or "").strip()
        anio_raw = row.get("ANIO_INGRESO")
        anio = parse_int(anio_raw)
        if anio is None and (anio_raw is not None and str(anio_raw).strip() != ""):
            log_issue(issues, "PARSE_ERROR_ANIO", "datos_carreras_ofertas", idx, cid, details=f"No pude parsear ANIO_INGRESO='{anio_raw}'")
        rows.append({
            "carrera_id": cid,
            "anio_ingreso": anio,
            "periodo": str(anio) if anio is not None else "",
            "cursos_ingreso": row.get("CURSOS_INGRESO"),
            "inicio_actividad": row.get("INICIO_ACTIVIDAD"),
            "fuente": "datos_carreras_ofertas",
        })

    # ofertas-carreras
    for idx, row in ofertas.iterrows():
        alias = str(row.get("ALIAS") or "").strip()
        titulo = str(row.get("TITULO") or "").strip()
        cid = match_id(alias, titulo)
        if not cid:
            cid = f"AUTO_{slugify(alias or titulo or str(idx))[:32]}"
            log_issue(issues, "UNMATCHED_OFERTA", "ofertas-carreras", idx, cid, details="No se encontró match por nombre; se asignó ID sintético")
        anio_raw = row.get("ANIO_INGRESO")
        anio = parse_int(anio_raw)
        if anio is None and (anio_raw is not None and str(anio_raw).strip() != ""):
            log_issue(issues, "PARSE_ERROR_ANIO", "ofertas-carreras", idx, cid, details=f"No pude parsear ANIO_INGRESO='{anio_raw}'")
        rows.append({
            "carrera_id": cid,
            "anio_ingreso": anio,
            "periodo": str(anio) if anio is not None else "",
            "cursos_ingreso": row.get("CURSOS_INGRESO"),
            "inicio_actividad": row.get("INICIO_ACTIVIDAD"),
            "fuente": "ofertas-carreras",
        })

    return pd.DataFrame(rows)


def normalize_aranceles(aranceles: pd.DataFrame, issues: List[Issue]):
    rows = []
    for idx, row in aranceles.iterrows():
        cid = str(row.get("IDENTIFICADOR_CARRERA") or "").strip()
        if not cid:
            log_issue(issues, "MISSING_ID", "aranceles_carreras", idx, details="Fila sin IDENTIFICADOR_CARRERA")
            continue
        raw_fields = {
            "admision_raw": row.get("ADMISION"),
            "matricula_general_raw": row.get("MATRICULA_GENERAL"),
            "matricula_ingresante_raw": row.get("MATRICULA_INGRESANTE"),
            "arancel_mensual_raw": row.get("ARANCEL_MENSUAL"),
            "arancel_total_raw": row.get("ARANCEL_TOTAL"),
        }
        parsed_fields = {}
        for k, v in raw_fields.items():
            if k.endswith("_raw") and v is not None and str(v).strip():
                num = parse_money(str(v))
                target = k.replace("_raw", "")
                parsed_fields[target] = num
                if num is None:
                    log_issue(issues, "PARSE_ERROR_MONTO", "aranceles_carreras", idx, cid, details=f"No pude parsear monto '{v}' en {k}")
        rows.append({
            "carrera_id": cid,
            "anio_ingreso": "",
            "periodo": "",
            **raw_fields,
            "admision": parsed_fields.get("admision"),
            "matricula_general": parsed_fields.get("matricula_general"),
            "matricula_ingresante": parsed_fields.get("matricula_ingresante"),
            "arancel_mensual": parsed_fields.get("arancel_mensual"),
            "arancel_total": parsed_fields.get("arancel_total"),
            "carrera_nombre_raw": row.get("CARRERA"),
        })
    return pd.DataFrame(rows)


def write_outputs(carreras: pd.DataFrame, ofertas_norm: pd.DataFrame, aranceles_norm: pd.DataFrame, aliases: pd.DataFrame, issues: List[Issue]):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    carreras.to_csv(OUT_DIR / "carreras.csv", index=False)
    ofertas_norm.to_csv(OUT_DIR / "ofertas_carreras.csv", index=False)
    aranceles_norm.to_csv(OUT_DIR / "aranceles_carreras.csv", index=False)
    aliases.to_csv(OUT_DIR / "aliases_carreras.csv", index=False)
    pd.DataFrame(issues).to_csv(OUT_DIR / "normalization_issues.csv", index=False)


def summarize(carreras: pd.DataFrame, ofertas_norm: pd.DataFrame, aranceles_norm: pd.DataFrame, issues: List[Issue]):
    logger.info("Carreras únicas: %d", carreras["carrera_id"].nunique())
    logger.info("Filas ofertas_carreras: %d", len(ofertas_norm))
    logger.info("Filas aranceles_carreras: %d", len(aranceles_norm))
    logger.info("Issues registrados: %d", len(issues))


def main():
    aranceles, datos, ofertas = load_raw_data()
    issues: List[Issue] = []

    carreras, aliases, name_index = normalize_carreras(aranceles, datos, ofertas, issues)
    ofertas_norm = normalize_ofertas(datos, ofertas, name_index, issues)
    aranceles_norm = normalize_aranceles(aranceles, issues)

    write_outputs(carreras, ofertas_norm, aranceles_norm, aliases, issues)
    summarize(carreras, ofertas_norm, aranceles_norm, issues)


if __name__ == "__main__":
    main()
