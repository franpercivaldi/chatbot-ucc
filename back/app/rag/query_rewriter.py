import json
from typing import Any, Dict, List, Optional
from ..models.gemini_client import generate_answer

SYSTEM_MSG = (
    "Sos un reescritor de consultas para un buscador de documentos de Admisiones. "
    "Devolvés SOLO un JSON con claves search_query, target_domain, carrera_id, "
    "carrera_nombre, periodo, modalidad. No expliques nada, no agregues texto fuera del JSON. "
    "Si no tenés un dato, usa null. target_domain debe ser uno de: aranceles, becas, fechas, "
    "reglamentos, carreras, perfiles, general. No inventes valores."
)


def _safe_json_loads(txt: str) -> Dict[str, Any]:
    try:
        return json.loads(txt)
    except Exception:
        pass
    # intentar extraer el primer objeto { ... }
    try:
        start = txt.find("{")
        end = txt.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(txt[start : end + 1])
    except Exception:
        return {}
    return {}


def rewrite_query(*, user_message: str, intent: str, meta, ctx_slots: Dict[str, Any], history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
    """Reescribe la consulta usando estado + intent, devolviendo filtros estructurados.

    Siempre devuelve un dict con las claves esperadas, aunque el modelo falle.
    """
    hist_lines: List[str] = []
    for h in history or []:
        role = h.get("role") or "user"
        content = (h.get("content") or "").strip()
        if not content:
            continue
        hist_lines.append(f"{role}: {content}")
    hist_block = "\n".join(hist_lines[-4:])

    ctx_parts = []
    for key in ("carrera_id", "carrera_nombre", "periodo", "modalidad", "facultad", "ultimo_intent", "ultimo_domain"):
        val = ctx_slots.get(key)
        if val:
            ctx_parts.append(f"{key}: {val}")
    ctx_block = " | ".join(ctx_parts)

    meta_parts = []
    for key in ("carrera_id", "carrera", "periodo", "modalidad", "facultad"):
        val = getattr(meta, key, None)
        if val:
            meta_parts.append(f"{key}: {val}")
    meta_block = " | ".join(meta_parts)

    prompt = (
        "Reescribe la consulta del usuario para retrieval.")
    prompt += "\nUser message: " + user_message.strip()
    if hist_block:
        prompt += "\nUltimos turnos:\n" + hist_block
    if ctx_block:
        prompt += "\nEstado previo: " + ctx_block
    if meta_block:
        prompt += "\nMeta explícita: " + meta_block
    prompt += "\nIntent detectado: " + (intent or "")
    prompt += (
        "\nDevuelve JSON con claves: search_query (string reescrita), target_domain (string o null), "
        "carrera_id, carrera_nombre, periodo, modalidad. No agregues nada más."
    )

    raw = ""
    try:
        raw = generate_answer(prompt, system_instruction=SYSTEM_MSG)
    except Exception:
        raw = ""

    parsed = _safe_json_loads(raw or "") or {}
    return {
        "search_query": parsed.get("search_query") or user_message,
        "target_domain": parsed.get("target_domain") or None,
        "carrera_id": parsed.get("carrera_id") or None,
        "carrera_nombre": parsed.get("carrera_nombre") or None,
        "periodo": parsed.get("periodo") or None,
        "modalidad": parsed.get("modalidad") or None,
        "raw": raw,
    }
