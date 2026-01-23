SYSTEM_QA = """Eres el asistente de Admisiones de la Universidad Católica de Córdoba.
Responde en español rioplatense, cálido pero conciso, con tono institucional y orientado a ayudar a futuros estudiantes.

Si una respuesta depende de un período/año, aclara cuál estás usando. Si la evidencia es insuficiente, dilo con transparencia y ofrece contactar al equipo de Admisiones. No inventes datos ni políticas.
"""

# Límites de tokens aproximados (1 token ≈ 4 chars en español)
MAX_HISTORY_CHARS = 8000  # ~2000 tokens
MAX_MSG_CHARS = 600  # ~150 tokens por mensaje


def _compress_history(chat_history: list | None, max_chars: int = MAX_HISTORY_CHARS) -> list:
    """
    Comprime el historial para no exceder el límite de tokens.
    - Trunca mensajes individuales muy largos
    - Recorta desde el inicio si el total excede el límite
    """
    if not chat_history:
        return []
    
    # Paso 1: truncar mensajes individuales
    compressed = []
    for h in chat_history:
        role = h.get("role", "user")
        content = (h.get("content") or "")[:MAX_MSG_CHARS]
        if len(h.get("content", "")) > MAX_MSG_CHARS:
            content = content.rsplit(" ", 1)[0] + "..."  # cortar en palabra
        compressed.append({"role": role, "content": content})
    
    # Paso 2: si aún excede, recortar desde el inicio
    total_chars = sum(len(h.get("content", "")) for h in compressed)
    while total_chars > max_chars and len(compressed) > 1:
        removed = compressed.pop(0)
        total_chars -= len(removed.get("content", ""))
    
    return compressed


def build_prompt(query: str, docs: list, chat_history: list | None = None, context_slots: dict | None = None) -> str:
    context_block = ""
    if context_slots:
        parts = []
        if context_slots.get("carrera_nombre"):
            parts.append(f"Carrera: {context_slots['carrera_nombre']}")
        if context_slots.get("periodo"):
            parts.append(f"Período: {context_slots['periodo']}")
        if context_slots.get("facultad"):
            parts.append(f"Facultad: {context_slots['facultad']}")
        if parts:
            context_block = "Contexto actual: " + " | ".join(parts) + "\n"
    
    hist_block = ""
    if chat_history:
        # Comprimir historial para no exceder límite de tokens
        compressed = _compress_history(chat_history[-6:])  # últimos 6 turnos máx
        for t in compressed:
            role = t.get("role","user")
            txt = t.get("content","")
            hist_block += f"{role}: {txt}\n"

    # armá tu prompt como antes; ejemplo:
    docs_block = "\n".join([f"[{i+1}] {d['texto']}" for i, d in enumerate(docs)])
    return f"""{context_block}{hist_block}
Pregunta: {query}

Contexto recuperado:
{docs_block}

Instrucciones: responde breve, directa y en tono amable institucional, usando solo la información del contexto recuperado. Si falta información, dilo y sugerí contactar al equipo de Admisiones.
"""
