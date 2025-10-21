import os, sqlite3, json, time, threading
from typing import Optional, Dict, Any, List

DB_PATH = os.environ.get("ANALYTICS_DB_PATH", "/app/state/analytics.db")
_lock = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx

def ensure_schema():
    with _lock, _conn() as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS chat_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts INTEGER NOT NULL,                 -- epoch seconds
          bot_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          user_query TEXT NOT NULL,
          answer_short TEXT,                   -- recorte de la respuesta
          detected_carrera TEXT,               -- nombre
          detected_carrera_id TEXT,            -- id si se tuvo
          periodo TEXT,
          facultad TEXT,
          intent TEXT,                         -- (futuro) si clasificás intención
          used_domains TEXT,                   -- JSON array
          files TEXT,                          -- JSON array
          success INTEGER,                     -- 1 si respondió con datos, 0 si fallback
          had_aranceles INTEGER,               -- 1 si hubo doc de aranceles
          tokens_in INTEGER,                   -- opcional
          tokens_out INTEGER,                  -- opcional
          extra JSON                           -- JSON libre (UA, referrer, etc.)
        );
        """)
        cx.execute("CREATE INDEX IF NOT EXISTS idx_events_bot_ts ON chat_events(bot_id, ts);")
        cx.execute("CREATE INDEX IF NOT EXISTS idx_events_carrera ON chat_events(detected_carrera, periodo);")
        cx.execute("CREATE INDEX IF NOT EXISTS idx_events_domains ON chat_events(bot_id);")
        cx.commit()

def log_chat_event(
    *, bot_id: str, session_id: str, user_query: str, answer: str,
    ctx_slots: Dict[str, Any] | None, retrieval_debug: Dict[str, Any] | None,
    success: bool, tokens_in: int | None = None, tokens_out: int | None = None,
    extra: Dict[str, Any] | None = None
):
    ensure_schema()
    ts = int(time.time())
    ctx = ctx_slots or {}
    dbg = retrieval_debug or {}
    domains = dbg.get("domains") or []
    files = dbg.get("files") or []
    had_aranceles = 1 if ("aranceles" in set(domains)) else 0

    with _lock, _conn() as cx:
        cx.execute("""
        INSERT INTO chat_events (
          ts, bot_id, session_id, user_query, answer_short,
          detected_carrera, detected_carrera_id, periodo, facultad,
          intent, used_domains, files, success, had_aranceles,
          tokens_in, tokens_out, extra
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts, bot_id, session_id, user_query, (answer or "")[:400],
            ctx.get("carrera_nombre") or ctx.get("carrera"), ctx.get("carrera_id"),
            ctx.get("periodo"), ctx.get("facultad"),
            dbg.get("intent"), json.dumps(list(domains), ensure_ascii=False),
            json.dumps(list(files), ensure_ascii=False),
            1 if success else 0, had_aranceles,
            tokens_in or 0, tokens_out or 0,
            json.dumps(extra or {}, ensure_ascii=False)
        ))
        cx.commit()

# ------ Consultas agregadas ------

def top_carreras(bot_id: str, since: int | None = None, limit: int = 20) -> List[dict]:
    ensure_schema()
    where = "WHERE bot_id=? AND detected_carrera IS NOT NULL AND detected_carrera<>''"
    args: list[Any] = [bot_id]
    if since:
        where += " AND ts>=?"
        args.append(int(since))
    sql = f"""
    SELECT detected_carrera as carrera,
           periodo,
           COUNT(*) as consultas,
           SUM(had_aranceles) as con_aranceles
    FROM chat_events
    {where}
    GROUP BY detected_carrera, periodo
    ORDER BY consultas DESC
    LIMIT {int(limit)}
    """
    with _lock, _conn() as cx:
        cur = cx.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

def top_dominios(bot_id: str, since: int | None = None) -> List[dict]:
    ensure_schema()
    where = "WHERE bot_id=?"
    args = [bot_id]
    if since:
        where += " AND ts>=?"
        args.append(int(since))
    sql = f"""
    SELECT json_each.value as domain, COUNT(*) as usos
    FROM chat_events, json_each(used_domains)
    {where}
    GROUP BY domain
    ORDER BY usos DESC
    """
    with _lock, _conn() as cx:
        cur = cx.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

def unanswered(bot_id: str, since: int | None = None, limit: int = 50) -> List[dict]:
    ensure_schema()
    where = "WHERE bot_id=? AND success=0"
    args = [bot_id]
    if since:
        where += " AND ts>=?"
        args.append(int(since))
    sql = f"""
    SELECT ts, session_id, user_query, answer_short
    FROM chat_events
    {where}
    ORDER BY ts DESC
    LIMIT {int(limit)}
    """
    with _lock, _conn() as cx:
        cur = cx.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

def daily_counts(bot_id: str, days: int = 30) -> List[dict]:
    ensure_schema()
    since = int(time.time()) - days*86400
    sql = """
    SELECT strftime('%Y-%m-%d', ts, 'unixepoch') as day,
           COUNT(*) as total,
           SUM(success) as ok
    FROM chat_events
    WHERE bot_id=? AND ts>=?
    GROUP BY day ORDER BY day ASC
    """
    with _lock, _conn() as cx:
        cur = cx.execute(sql, (bot_id, since))
        return [dict(r) for r in cur.fetchall()]
