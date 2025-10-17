import hashlib, unicodedata, re, time, os
from typing import Optional
import uuid

SCHEMA_VERSION = 1

def slugify(s: str | None) -> str:
    if not s:
        return "general"
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.strip().lower())
    return s.strip("_") or "general"

def hash_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def make_doc_id(source_path: str, sheet_name: str) -> str:
    sp = os.path.normpath(source_path)
    return hash_str(f"{sp}|{sheet_name}")

def make_chunk_id(doc_id: str, primary_key: str) -> str:
    # primary_key: idealmente un ID estable (IDENTIFICADOR_CARRERA, código, etc.)
    return hash_str(f"{doc_id}|{primary_key}")

def now_iso_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

_money_re = re.compile(r"[-+]?\d{1,3}(\.\d{3})*(,\d+)?|[-+]?\d+(\.\d+)?")

def parse_money_to_float(v: Optional[str | float | int]) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Buscar número “latino” $ 62.000,00 o similar
    m = _money_re.search(s.replace(" ", ""))
    if not m:
        return None
    num = m.group(0)
    # Si tiene miles con punto y decimales con coma → normalizar
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".")
    elif "," in num and "." not in num:
        num = num.replace(",", ".")
    try:
        return float(num)
    except Exception:
        return None

def uuid_from_chunk(chunk_id: str) -> str:
    """
    Devuelve un UUID determinístico a partir del chunk_id (string).
    Usamos namespace URL para tener estabilidad cross-plataforma.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))