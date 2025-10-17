import hashlib, json, os, sqlite3, time
from typing import List
import google.generativeai as genai
from ..config import settings

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "cache")
os.makedirs(CACHE_PATH, exist_ok=True)
DB_PATH = os.path.join(CACHE_PATH, "embeddings.sqlite")

def _db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        vec_json TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")
    return con

def _key(text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x1f")
    h.update(text.encode("utf-8"))
    return h.hexdigest()

def init_gemini():
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY no configurada")
    genai.configure(api_key=settings.GOOGLE_API_KEY)

def _extract_vec(resp) -> List[float]:
    """
    Soporta distintas formas del SDK/REST:
    - {'embedding': {'values': [...]}}
    - {'embedding': [...]}
    - {'embeddings': [{'values': [...]} , ...]}  (no debería ocurrir en single)
    - objeto con .embedding.values
    """
    # dict-like
    if isinstance(resp, dict):
        if "embedding" in resp:
            emb = resp["embedding"]
            if isinstance(emb, dict) and "values" in emb:
                return emb["values"]
            if isinstance(emb, list):
                return emb
        if "embeddings" in resp and resp["embeddings"]:
            emb0 = resp["embeddings"][0]
            if isinstance(emb0, dict) and "values" in emb0:
                return emb0["values"]
    # objeto con atributos
    try:
        emb = getattr(resp, "embedding", None)
        if emb is not None:
            vals = getattr(emb, "values", None)
            if vals is not None:
                return list(vals)
            if isinstance(emb, list):
                return emb
    except Exception:
        pass
    raise ValueError("Formato de respuesta de embeddings desconocido")

def embed_one(text: str, model: str | None = None) -> List[float]:
    model = model or settings.GEMINI_EMBED_MODEL
    init_gemini()
    # Algunos clientes requieren el prefijo "models/"
    model_name = model if model.startswith("models/") else model
    resp = genai.embed_content(
        model=model_name,
        content=text,
        task_type="RETRIEVAL_DOCUMENT"
    )
    return _extract_vec(resp)

def embed_texts(texts: List[str], model: str | None = None) -> List[List[float]]:
    """
    Embeddings con caché, uno por vez (más robusto que batch).
    """
    model = model or settings.GEMINI_EMBED_MODEL
    init_gemini()
    con = _db()
    out: List[List[float]] = [None] * len(texts)  # type: ignore
    misses = []

    for i, t in enumerate(texts):
        k = _key(t, model)
        cur = con.execute("SELECT vec_json FROM cache WHERE key=? AND model=?", (k, model)).fetchone()
        if cur:
            out[i] = json.loads(cur[0])
        else:
            misses.append(i)

    now = time.time()
    for i in misses:
        t = texts[i]
        vec = embed_one(t, model=model)
        out[i] = vec
        k = _key(t, model)
        with con:
            con.execute(
                "INSERT OR REPLACE INTO cache (key, model, vec_json, created_at) VALUES (?, ?, ?, ?)",
                (k, model, json.dumps(vec), now),
            )

    con.close()
    return out  # type: ignore

def get_embedding_dim() -> int:
    vec = embed_one("dim_check")
    return len(vec)


def embed_query(text: str, model: str | None = None) -> List[float]:
    model = model or settings.GEMINI_EMBED_MODEL
    init_gemini()
    model_name = model if model.startswith("models/") else model
    resp = genai.embed_content(
        model=model_name,
        content=text,
        task_type="RETRIEVAL_QUERY"
    )
    return _extract_vec(resp)