# back/app/catalog/entities.py
import os, json, sqlite3, threading
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz
from ..rag.schema import slugify

CATALOG_DB_PATH = os.environ.get("CATALOG_DB_PATH", "/app/data/xlsx/_catalog/catalog.db")

_lock = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(CATALOG_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CATALOG_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    with _lock, _conn() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS carreras (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          bot_id TEXT NOT NULL,
          carrera_id TEXT NOT NULL DEFAULT '',
          nombre TEXT NOT NULL,
          carrera_slug TEXT NOT NULL,
          facultad TEXT,
          nivel TEXT,
          periodos TEXT,                         -- JSON
          aliases TEXT,                          -- JSON
          UNIQUE (bot_id, carrera_id, carrera_slug)
        );
        """)
        # si la tabla ya existía con NULLs, normalizamos y creamos índice único por si faltara
        cx.execute("UPDATE carreras SET carrera_id='' WHERE carrera_id IS NULL;")
        cx.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_carreras_uni
        ON carreras (bot_id, carrera_id, carrera_slug);
        """)
        cx.commit()

def _merge_json_array(old: Optional[str], new_items: List[str]) -> str:
    base = []
    if old:
        try:
            base = json.loads(old) or []
        except Exception:
            base = []
    for it in new_items:
        s = (it or "").strip()
        if s and s not in base:
            base.append(s)
    return json.dumps(base, ensure_ascii=False)

def upsert_from_records(records: List[Dict[str, Any]], bot_id: str):
    ensure_schema()
    rows = []
    for r in records:
        md = r.get("metadata", {})
        dom = md.get("domain") or md.get("tipo") or "general"
        if dom not in {"carreras", "oferta", "aranceles"}:
            continue

        nombre = (md.get("carrera") or md.get("titulo") or "").strip()
        if not nombre:
            continue

        # 👇 normalizamos vacío, no NULL
        carrera_id = (md.get("carrera_id") or "").strip()
        facultad = (md.get("facultad") or "").strip() or None
        nivel = (md.get("nivel") or md.get("nivel_estudio") or "").strip() or None
        periodo = (md.get("periodo") or "").strip() or None

        aliases = set([nombre])
        if md.get("titulo"):
            aliases.add(str(md.get("titulo")))
        extras = md.get("extras") or {}
        for k in ("alias","alias_carrera","nombre_programa"):
            if extras.get(k):
                aliases.add(str(extras[k]))

        rows.append({
            "bot_id": bot_id,
            "carrera_id": carrera_id,           # 👈 ya normalizado
            "nombre": nombre,
            "carrera_slug": slugify(nombre),
            "facultad": facultad,
            "nivel": nivel,
            "periodo": periodo,
            "aliases": list(aliases),
        })

    with _lock, _conn() as cx:
        for row in rows:
            cur = cx.execute("""
                SELECT periodos, aliases FROM carreras
                WHERE bot_id=? AND carrera_id=? AND carrera_slug=?
            """, (row["bot_id"], row["carrera_id"], row["carrera_slug"]))
            prev = cur.fetchone()

            new_periodos = _merge_json_array(prev["periodos"] if prev else None,
                                             [p for p in [row["periodo"]] if p])
            new_aliases = _merge_json_array(prev["aliases"] if prev else None,
                                            row["aliases"])

            if prev:
                cx.execute("""
                    UPDATE carreras
                    SET nombre=?,
                        facultad=COALESCE(?, facultad),
                        nivel=COALESCE(?, nivel),
                        periodos=?,
                        aliases=?
                    WHERE bot_id=? AND carrera_id=? AND carrera_slug=?
                """, (row["nombre"], row["facultad"], row["nivel"],
                      new_periodos, new_aliases,
                      row["bot_id"], row["carrera_id"], row["carrera_slug"]))
            else:
                cx.execute("""
                    INSERT INTO carreras (bot_id, carrera_id, nombre, carrera_slug, facultad, nivel, periodos, aliases)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (row["bot_id"], row["carrera_id"], row["nombre"], row["carrera_slug"],
                      row["facultad"], row["nivel"], new_periodos, new_aliases))
        cx.commit()


def search_candidates(bot_id: str, q: str, limit: int = 5) -> List[Dict[str, Any]]:
    ensure_schema()
    qn = (q or "").strip()
    if not qn:
        return []
    qn_low = qn.lower()
    with _lock, _conn() as cx:
        cur = cx.execute("SELECT carrera_id, nombre, carrera_slug, facultad, nivel, aliases FROM carreras WHERE bot_id=?", (bot_id,))
        items = []
        for row in cur.fetchall():
            nombre = row["nombre"] or ""
            aliases = []
            try:
                aliases = json.loads(row["aliases"] or "[]")
            except Exception:
                aliases = [nombre]

            # mejor score entre nombre y aliases
            best = max([fuzz.partial_ratio(qn_low, (nombre or "").lower())] +
                       [fuzz.partial_ratio(qn_low, (a or "").lower()) for a in aliases])

            items.append({
                "carrera_id": row["carrera_id"],
                "nombre": nombre,
                "carrera_slug": row["carrera_slug"],
                "facultad": row["facultad"],
                "nivel": row["nivel"],
                "score": int(best),
            })

        items.sort(key=lambda x: x["score"], reverse=True)
        return items[:limit]

def resolve_carrera(bot_id: str, q: str, threshold: int = 82) -> Optional[Dict[str, Any]]:
    cands = search_candidates(bot_id, q, limit=5)
    if not cands:
        return None
    best = cands[0]
    return best if best["score"] >= threshold else None
