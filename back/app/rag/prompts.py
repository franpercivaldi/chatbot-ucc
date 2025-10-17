SYSTEM_QA = """Eres el asistente de Admisiones de la Universidad Católica de Córdoba.
Responde en español rioplatense, claro y conciso.

Si una respuesta depende de un período/año, aclara qué período estás usando.
Si la evidencia es insuficiente, dilo y sugerí contacto humano.
No inventes datos ni políticas.
"""

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
        # últimas 2-3 intervenciones resumidas
        tail = chat_history[-4:]
        for t in tail:
            role = t.get("role","user")
            txt = t.get("content","")
            hist_block += f"{role}: {txt}\n"

    # armá tu prompt como antes; ejemplo:
    docs_block = "\n".join([f"[{i+1}] {d['texto']}" for i, d in enumerate(docs)])
    return f"""{context_block}{hist_block}
Pregunta: {query}

Contexto recuperado:
{docs_block}

Instrucciones: responde breve y cita [n] donde n sea el índice del fragmento relevante.
"""
