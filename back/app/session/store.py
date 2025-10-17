import os, sqlite3, json, threading, time

DB_PATH = os.environ.get("CONV_DB_PATH", "/app/state/conversations.db")
_lock = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx

def ensure_schema():
    with _lock, _conn() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
          session_id TEXT NOT NULL,
          bot_id     TEXT NOT NULL,
          ctx_json   TEXT NOT NULL,
          history_json TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY (session_id, bot_id)
        );""")
        cx.commit()

def load(session_id: str, bot_id: str):
    ensure_schema()
    with _lock, _conn() as cx:
        cur = cx.execute(
            "SELECT ctx_json, history_json FROM conversations WHERE session_id=? AND bot_id=?",
            (session_id, bot_id),
        )
        row = cur.fetchone()
        if not row:
            return {}, []
        ctx = json.loads(row["ctx_json"] or "{}")
        hist = json.loads(row["history_json"] or "[]")
        return ctx, hist

def save(session_id: str, bot_id: str, ctx: dict, history: list):
    ensure_schema()
    now = int(time.time())
    ctx_s = json.dumps(ctx, ensure_ascii=False)
    hist_s = json.dumps(history[-8:], ensure_ascii=False)  # guardamos últimas ~4 interacciones
    with _lock, _conn() as cx:
        cur = cx.execute(
            "UPDATE conversations SET ctx_json=?, history_json=?, updated_at=? WHERE session_id=? AND bot_id=?",
            (ctx_s, hist_s, now, session_id, bot_id),
        )
        if cur.rowcount == 0:
            cx.execute(
                "INSERT INTO conversations(session_id, bot_id, ctx_json, history_json, updated_at) VALUES (?,?,?,?,?)",
                (session_id, bot_id, ctx_s, hist_s, now),
            )
        cx.commit()
