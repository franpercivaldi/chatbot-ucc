import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError
from ..models.gemini_client import generate_answer

# ============ LOGGING / STATS ============
_rewriter_stats = {"success": 0, "parse_fail": 0, "llm_fail": 0}

def get_rewriter_stats() -> Dict[str, Any]:
    """Estadísticas del rewriter desde el último restart."""
    total = _rewriter_stats["success"] + _rewriter_stats["parse_fail"] + _rewriter_stats["llm_fail"]
    return {
        **_rewriter_stats,
        "total": total,
        "success_rate": round(_rewriter_stats["success"] / total, 3) if total > 0 else 0,
    }

def reset_rewriter_stats():
    global _rewriter_stats
    _rewriter_stats = {"success": 0, "parse_fail": 0, "llm_fail": 0}


# ============ PYDANTIC MODEL ============
class RewriteResult(BaseModel):
    """Output estructurado del query rewriter."""
    search_query: str = Field(description="Query reescrita optimizada para búsqueda semántica")
    target_domain: Optional[str] = Field(
        None, 
        description="Dominio principal: aranceles|becas|fechas|reglamentos|carreras|perfiles|general"
    )
    carrera_id: Optional[str] = None
    carrera_nombre: Optional[str] = None
    periodo: Optional[str] = None
    modalidad: Optional[str] = None


# ============ DOMAIN INFERENCE ============
INTENT_TO_DOMAIN = {
    "montos": "aranceles",
    "fechas": "fechas",
    "becas": "becas",
    "info_carrera": "perfiles",
    "requisitos": "carreras",
    "reglamentos": "reglamentos",
}

def _infer_domain_from_intent(intent: str) -> Optional[str]:
    """Infiere dominio basado en el intent detectado."""
    return INTENT_TO_DOMAIN.get(intent)


# ============ SYSTEM PROMPT ============
SYSTEM_MSG = (
    "Sos un reescritor de consultas para un buscador de documentos de Admisiones UCC. "
    "Devolvés SOLO un JSON válido con estas claves exactas:\n"
    "- search_query: string con la consulta reescrita para búsqueda semántica\n"
    "- target_domain: uno de [aranceles, becas, fechas, reglamentos, carreras, perfiles, general] o null\n"
    "- carrera_id: string o null\n"
    "- carrera_nombre: string o null\n"
    "- periodo: string (año) o null\n"
    "- modalidad: string o null\n\n"
    "REGLAS:\n"
    "1. NO agregues texto fuera del JSON\n"
    "2. Si no tenés un dato, usa null (no string vacío)\n"
    "3. search_query debe expandir abreviaturas y ser explícita\n"
    "4. NO inventes valores que no estén en el contexto"
)


def _safe_json_loads(txt: str) -> Dict[str, Any]:
    """Intenta parsear JSON, incluso si viene con texto extra."""
    if not txt:
        return {}
    try:
        return json.loads(txt)
    except Exception:
        pass
    # Intentar extraer el primer objeto { ... }
    try:
        start = txt.find("{")
        end = txt.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(txt[start : end + 1])
    except Exception:
        pass
    return {}


def rewrite_query(
    *, 
    user_message: str, 
    intent: str, 
    meta, 
    ctx_slots: Dict[str, Any], 
    history: List[Dict[str, str]] | None = None
) -> Dict[str, Any]:
    """
    Reescribe la consulta usando estado + intent, devolviendo filtros estructurados.
    
    Siempre devuelve un dict válido con las claves esperadas:
    - search_query, target_domain, carrera_id, carrera_nombre, periodo, modalidad, raw, rewriter_ok
    """
    global _rewriter_stats
    
    # Construir contexto para el prompt
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

    # Construir prompt
    prompt = "Reescribe la consulta del usuario para retrieval semántico."
    prompt += f"\n\nUser message: {user_message.strip()}"
    if hist_block:
        prompt += f"\n\nÚltimos turnos:\n{hist_block}"
    if ctx_block:
        prompt += f"\n\nEstado de conversación: {ctx_block}"
    if meta_block:
        prompt += f"\n\nMetadata explícita: {meta_block}"
    prompt += f"\n\nIntent detectado: {intent or 'general'}"
    prompt += "\n\nDevuelve SOLO el JSON, sin explicaciones."

    # Llamar al LLM
    raw = ""
    start_time = time.time()
    try:
        raw = generate_answer(prompt, system_instruction=SYSTEM_MSG)
    except Exception as e:
        _rewriter_stats["llm_fail"] += 1
        print(f"[rewriter] LLM FAIL: {e}")
        # Fallback sin LLM
        return _build_fallback_result(user_message, intent, meta, ctx_slots)
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Parsear respuesta
    parsed = _safe_json_loads(raw or "")
    
    if not parsed or "search_query" not in parsed:
        _rewriter_stats["parse_fail"] += 1
        print(f"[rewriter] PARSE FAIL (latency={latency_ms}ms): raw={raw[:200] if raw else 'empty'}")
        return _build_fallback_result(user_message, intent, meta, ctx_slots, raw=raw)
    
    # Validar con Pydantic
    try:
        result = RewriteResult(**parsed)
        _rewriter_stats["success"] += 1
        return {
            "search_query": result.search_query,
            "target_domain": result.target_domain,
            "carrera_id": result.carrera_id,
            "carrera_nombre": result.carrera_nombre,
            "periodo": result.periodo,
            "modalidad": result.modalidad,
            "raw": raw,
            "rewriter_ok": True,
            "latency_ms": latency_ms,
        }
    except ValidationError as e:
        _rewriter_stats["parse_fail"] += 1
        print(f"[rewriter] VALIDATION FAIL: {e}")
        # Usar lo que se pudo parsear + defaults
        return {
            "search_query": parsed.get("search_query") or user_message,
            "target_domain": parsed.get("target_domain") or _infer_domain_from_intent(intent),
            "carrera_id": parsed.get("carrera_id"),
            "carrera_nombre": parsed.get("carrera_nombre"),
            "periodo": parsed.get("periodo"),
            "modalidad": parsed.get("modalidad"),
            "raw": raw,
            "rewriter_ok": False,
            "latency_ms": latency_ms,
        }


def _build_fallback_result(
    user_message: str, 
    intent: str, 
    meta, 
    ctx_slots: Dict[str, Any],
    raw: str = ""
) -> Dict[str, Any]:
    """
    Construye resultado de fallback cuando el LLM falla.
    Usa el contexto disponible para inferir valores.
    """
    # Intentar obtener carrera del contexto
    carrera_id = getattr(meta, "carrera_id", None) or ctx_slots.get("carrera_id")
    carrera_nombre = getattr(meta, "carrera", None) or ctx_slots.get("carrera_nombre")
    periodo = getattr(meta, "periodo", None) or ctx_slots.get("periodo")
    modalidad = getattr(meta, "modalidad", None) or ctx_slots.get("modalidad")
    
    # Construir search_query enriquecida si tenemos carrera
    search_query = user_message
    if carrera_nombre and carrera_nombre.lower() not in user_message.lower():
        search_query = f"{user_message} {carrera_nombre}"
    
    return {
        "search_query": search_query,
        "target_domain": _infer_domain_from_intent(intent),
        "carrera_id": carrera_id,
        "carrera_nombre": carrera_nombre,
        "periodo": periodo,
        "modalidad": modalidad,
        "raw": raw,
        "rewriter_ok": False,
        "latency_ms": 0,
    }
