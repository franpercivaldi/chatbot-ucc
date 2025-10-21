import os, sqlite3, json, time, hashlib, threading, unicodedata
from typing import Optional, Dict, Any

DB_PATH = os.environ.get("CACHE_DB_PATH", "/app/state/cache.db")
TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "86400"))  # 24h por defecto
_lock = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx

def ensure_schema():
    with _lock, _conn() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS chat_cache (
          k TEXT PRIMARY KEY,
          created_at INTEGER NOT NULL,
          bot_id TEXT NOT NULL,
          key_fingerprint TEXT NOT NULL,
          payload TEXT NOT NULL
        );
        """)
        cx.execute("CREATE INDEX IF NOT EXISTS idx_cache_bot ON chat_cache(bot_id);")
        cx.commit()

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')

def _normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = _strip_accents(s)
    # opcional: colapsar espacios
    s = ' '.join(s.split())
    return s

def _fingerprint(parts: Dict[str, Any]) -> str:
    # orden estable
    items = [(k, parts.get(k)) for k in sorted(parts.keys())]
    raw = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def make_cache_key(*, bot_id: str, question: str, carrera: Optional[str], periodo: Optional[str]) -> str:
    norm_q = _normalize_text(question)
    norm_c = _normalize_text(carrera or "")
    norm_p = _normalize_text(periodo or "")
    fp = _fingerprint({"bot": bot_id, "q": norm_q, "c": norm_c, "p": norm_p})
    return fp  # usamos el hash como clave; guardamos además un fingerprint legible

def get_cache(*, bot_id: str, question: str, carrera: Optional[str], periodo: Optional[str]) -> Optional[Dict[str, Any]]:
    ensure_schema()
    k = make_cache_key(bot_id=bot_id, question=question, carrera=carrera, periodo=periodo)
    now = int(time.time())
    with _lock, _conn() as cx:
        cur = cx.execute("SELECT created_at, payload FROM chat_cache WHERE k=? AND bot_id=?", (k, bot_id))
        row = cur.fetchone()
        if not row:
            return None
        if row["created_at"] + TTL_SECONDS < now:
            try:
                cx.execute("DELETE FROM chat_cache WHERE k=?", (k,))
                cx.commit()
            except Exception:
                pass
            return None
        try:
            return json.loads(row["payload"])
        except Exception:
            return None

def put_cache(*, bot_id: str, question: str, carrera: Optional[str], periodo: Optional[str], answer: str, sources: list):
    ensure_schema()
    k = make_cache_key(bot_id=bot_id, question=question, carrera=carrera, periodo=periodo)
    now = int(time.time())
    payload = json.dumps({"answer": answer, "sources": sources}, ensure_ascii=False)
    with _lock, _conn() as cx:
        cx.execute("REPLACE INTO chat_cache(k, created_at, bot_id, key_fingerprint, payload) VALUES (?, ?, ?, ?, ?)",
                   (k, now, bot_id, k, payload))
        cx.commit()

# utilidades admin
def stats(bot_id: Optional[str] = None) -> Dict[str, Any]:
    ensure_schema()
    with _lock, _conn() as cx:
        if bot_id:
            cur = cx.execute("SELECT COUNT(*) c FROM chat_cache WHERE bot_id=?", (bot_id,))
        else:
            cur = cx.execute("SELECT COUNT(*) c FROM chat_cache")
        total = cur.fetchone()["c"]
        return {"entries": total, "ttl_seconds": TTL_SECONDS}

def purge(bot_id: Optional[str] = None) -> int:
    ensure_schema()
    with _lock, _conn() as cx:
        if bot_id:
            cur = cx.execute("DELETE FROM chat_cache WHERE bot_id=?", (bot_id,))
        else:
            cur = cx.execute("DELETE FROM chat_cache")
        cx.commit()
        return cur.rowcount
