from __future__ import annotations

import json
import logging
import unicodedata
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Paths (defaults)
BASE_DIR = Path(__file__).resolve().parents[1]
RAW_JSON_PATHS = [
    BASE_DIR / "data" / "json" / "datos_generales_carreras.json",
    BASE_DIR / "data" / "xlsx" / "public-admisiones" / "datos_generales_carreras.json",
]
CARRERAS_CSV_PATH = BASE_DIR / "data" / "normalized" / "carreras.csv"
OUT_DIR = BASE_DIR / "data" / "normalized"
OUT_JSON = OUT_DIR / "datos_generales_carreras_normalizado.json"
OUT_ISSUES = OUT_DIR / "datos_generales_carreras_issues.csv"

# Logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Issue:
    issue_type: str
    source_unit: str
    source_carrera: str
    carrera_id: str
    detail: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class CarreraMapping:
    carrera_id: str
    carrera_nombre: str
    titulo: str


# --------- utils ---------

def slugify(text: str) -> str:
    if text is None:
        return ""
    txt = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    txt = txt.lower()
    out = []
    for ch in txt:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", ",", ".", "_", "/", "?", "¿", "!", "¡", ":", ";", "(" , ")"}:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug

def normalize_name(text: str) -> str:
    if text is None:
        return ""
    return slugify(text)

def parse_int_safe(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None

def build_carrera_id_from_codigos(cod_uni: str, cod_carr: str) -> Optional[str]:
    if not cod_uni or not cod_carr:
        return None
    cu = str(cod_uni).strip()
    cc = str(cod_carr).strip()
    if not cu or not cc:
        return None
    return f"{cu}{cc}"


# --------- loaders ---------

def load_raw_json() -> List[Dict[str, Any]]:
    for p in RAW_JSON_PATHS:
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info("Loaded JSON from %s", p)
            return data if isinstance(data, list) else []
    raise FileNotFoundError("No se encontró datos_generales_carreras.json en las rutas esperadas")


def load_carreras_csv_mapping() -> Tuple[Dict[str, CarreraMapping], Dict[str, List[str]]]:
    if not CARRERAS_CSV_PATH.exists():
        logger.warning("No se encontró %s; se continuará sin mapping CSV", CARRERAS_CSV_PATH)
        return {}, {}
    df = pd.read_csv(CARRERAS_CSV_PATH, dtype=str, keep_default_na=False)
    by_id: Dict[str, CarreraMapping] = {}
    name_index: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        cid = str(row.get("carrera_id") or "").strip()
        if not cid:
            continue
        nombre = str(row.get("carrera_nombre") or "").strip()
        titulo = str(row.get("titulo") or "").strip()
        by_id[cid] = CarreraMapping(carrera_id=cid, carrera_nombre=nombre, titulo=titulo)
        for val in [cid, nombre, titulo]:
            key = normalize_name(val)
            if not key:
                continue
            name_index.setdefault(key, [])
            if cid not in name_index[key]:
                name_index[key].append(cid)
    logger.info("Loaded mapping from carreras.csv: %d carreras", len(by_id))
    return by_id, name_index


# --------- normalization of datos_especiales ---------

def normalize_datos_especiales(datos_especiales: List[Dict[str, Any]], issues: List[Issue], unidad: str, carrera_slug: str) -> Tuple[Dict[str, Any], Dict[str, str], List[Dict[str, str]], Optional[str]]:
    metricas: Dict[str, Any] = {}
    titulos_genero: Dict[str, str] = {}
    secciones: List[Dict[str, str]] = []
    nombre_formal: Optional[str] = None

    def add_section(titulo: str, contenido: str):
        clave = slugify(titulo) or "seccion"
        secciones.append({
            "clave": clave,
            "titulo": titulo,
            "contenido": contenido,
        })

    for item in datos_especiales or []:
        titulo = str(item.get("titulo") or "").strip()
        contenido = str(item.get("contenido") or "").strip()
        if not titulo and not contenido:
            continue
        tnorm = titulo.lower()

        if "duracion" in tnorm and "a" in tnorm:  # años/ano/año
            val = parse_int_safe(contenido)
            if val is None:
                issues.append(Issue("PARSE_ERROR_INT", unidad, carrera_slug, "", f"No pude parsear duracion '{contenido}'"))
            else:
                metricas["duracion_anios"] = val
            continue
        if "asignatura" in tnorm:
            val = parse_int_safe(contenido)
            if val is None:
                issues.append(Issue("PARSE_ERROR_INT", unidad, carrera_slug, "", f"No pude parsear asignaturas '{contenido}'"))
            else:
                metricas["cantidad_asignaturas"] = val
            continue
        if "egresad" in tnorm:
            val = parse_int_safe(contenido)
            if val is None:
                issues.append(Issue("PARSE_ERROR_INT", unidad, carrera_slug, "", f"No pude parsear egresados '{contenido}'"))
            else:
                metricas["cantidad_egresados"] = val
            continue
        if "inscrip" in tnorm and "promedio" in tnorm:
            val = parse_int_safe(contenido)
            if val is None:
                issues.append(Issue("PARSE_ERROR_INT", unidad, carrera_slug, "", f"No pude parsear inscriptos '{contenido}'"))
            else:
                metricas["promedio_anual_inscriptos"] = val
            continue
        if "titulo masculino" in tnorm:
            titulos_genero["masculino"] = contenido
            continue
        if "titulo femenino" in tnorm:
            titulos_genero["femenino"] = contenido
            continue
        if "nombre de la carrera" in tnorm:
            nombre_formal = contenido
            continue

        add_section(titulo, contenido)

    return metricas, titulos_genero, secciones, nombre_formal


# --------- ID resolution ---------

def resolve_carrera_id(entry: Dict[str, Any], mapping_by_id: Dict[str, CarreraMapping], name_index: Dict[str, List[str]], issues: List[Issue], unidad: str) -> Tuple[str, bool]:
    codigo_siucc = str(entry.get("codigoSiucc") or entry.get("codigo_siucc") or "").strip()
    nombre_corto = str(entry.get("carrera") or "").strip()
    nombre_formal_hint = entry.get("_nombre_formal_hint") or ""
    cod_uni = str(entry.get("cod_uni") or "").strip()
    cod_carr = str(entry.get("cod_carr") or "").strip()

    # a) match by codigo_siucc equals carrera_id
    if codigo_siucc:
        if codigo_siucc in mapping_by_id:
            return codigo_siucc, False
        key = normalize_name(codigo_siucc)
        if key in name_index:
            return name_index[key][0], False

    # b) match by names (corto / formal)
    for val in [nombre_corto, nombre_formal_hint]:
        key = normalize_name(val)
        if key and key in name_index:
            cids = name_index[key]
            if len(cids) > 1:
                issues.append(Issue("NAME_MATCH_MULTIPLE", unidad, nombre_corto, "", f"Coincidencias {cids} para nombre '{val}'"))
            return cids[0], False

    # c) build from cod_uni + cod_carr
    built = build_carrera_id_from_codigos(cod_uni, cod_carr)
    if built:
        if built in mapping_by_id:
            return built, False
        issues.append(Issue("ID_BUILT_NO_MATCH_CSV", unidad, nombre_corto, built, "ID construido por cod_uni+cod_carr sin match en CSV"))
        return built, True

    # d) synthetic stable
    base = nombre_corto or codigo_siucc or "sin_nombre"
    synthetic = f"JSON_{slugify(base)}_{uuid.uuid5(uuid.NAMESPACE_URL, base).hex[:8]}"
    issues.append(Issue("SYNTHETIC_ID", unidad, nombre_corto, synthetic, "No se pudo resolver carrera_id; se generó sintético"))
    return synthetic, True


# --------- main normalization ---------

def normalize_all(data: List[Dict[str, Any]], mapping_by_id: Dict[str, CarreraMapping], name_index: Dict[str, List[str]]) -> Tuple[List[Dict[str, Any]], List[Issue]]:
    normalized: List[Dict[str, Any]] = []
    issues: List[Issue] = []

    for unit_idx, item in enumerate(data):
        unidad = str(item.get("unidad") or "").strip()
        carreras = item.get("carreras") or []
        if not isinstance(carreras, list):
            issues.append(Issue("INVALID_CARRERAS", unidad, "", "", f"carreras no es lista en unidad idx {unit_idx}"))
            continue

        for car_idx, car in enumerate(carreras):
            if not isinstance(car, dict):
                issues.append(Issue("INVALID_CARRERA_ITEM", unidad, "", "", f"Item no dict en carreras idx {car_idx}"))
                continue

            datos_especiales = car.get("datos_especiales") or []
            metricas, titulos_genero, secciones, nombre_formal_from_especiales = normalize_datos_especiales(
                datos_especiales, issues, unidad, str(car.get("carrera") or "")
            )

            # hint for resolver
            car["_nombre_formal_hint"] = nombre_formal_from_especiales or ""

            carrera_id, synthetic = resolve_carrera_id(car, mapping_by_id, name_index, issues, unidad)

            nombre_formal = nombre_formal_from_especiales or car.get("nombre_formal") or ""
            nombre_corto = str(car.get("carrera") or "").strip()

            norm_entry = {
                "carrera_id": carrera_id,
                "unidad": unidad,
                "nombre_corto": nombre_corto,
                "nombre_formal": nombre_formal or None,
                "palabras_clave": car.get("palabras_clave"),
                "link_inscripcion": car.get("link_inscripcion"),
                "codigo_siucc": car.get("codigoSiucc") or car.get("codigo_siucc"),
                "uni_id": car.get("uni_id"),
                "cod_uni": car.get("cod_uni"),
                "cod_carr": car.get("cod_carr"),
                "metricas": metricas if metricas else None,
                "titulos_genero": titulos_genero if titulos_genero else None,
                "secciones": secciones,
                "synthetic_id": synthetic,
            }
            normalized.append(norm_entry)

    return normalized, issues


def write_outputs(normalized: List[Dict[str, Any]], issues: List[Issue]):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    pd.DataFrame([i.to_dict() for i in issues]).to_csv(OUT_ISSUES, index=False)
    logger.info("Escribí %s y %s", OUT_JSON, OUT_ISSUES)


def summarize(normalized: List[Dict[str, Any]], issues: List[Issue]):
    carreras = {n.get("carrera_id") for n in normalized}
    logger.info("Carreras normalizadas: %d", len(carreras))
    logger.info("Registros generados: %d", len(normalized))
    logger.info("Issues: %d", len(issues))


def main():
    data = load_raw_json()
    mapping_by_id, name_index = load_carreras_csv_mapping()
    normalized, issues = normalize_all(data, mapping_by_id, name_index)
    write_outputs(normalized, issues)
    summarize(normalized, issues)


if __name__ == "__main__":
    main()
