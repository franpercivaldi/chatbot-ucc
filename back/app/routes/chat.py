from fastapi import APIRouter, Depends
from ..schemas.chat import ChatRequest, ChatResponse, ChatMeta
from ..deps import get_qdrant
from ..bots.profiles import get_profile
from ..catalog.entities import resolve_carrera
from ..rag.retriever import search
from ..rag.reranker import rerank
from ..rag.prompts import build_prompt
from ..models.gemini_client import generate_answer
from ..config import settings
from ..session.store import load as load_ctx, save as save_ctx

router = APIRouter()

def _infer_periodo_from_text(text: str) -> str | None:
    import re
    m = re.search(r"(19|20)\d{2}", text or "")
    return m.group(0) if m else None

@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest, client = Depends(get_qdrant)):
    bot_id, profile = get_profile(req.bot_id)
    session_id = req.session_id or "anon"
    allowed_domains = profile.get("allowed_domains", [])

    # 1) cargar contexto previo
    ctx, history = load_ctx(session_id, bot_id)  # ctx: dict; history: list[{role,content}]
    # slots conocidos
    slot_carrera_id   = ctx.get("carrera_id")
    slot_carrera_name = ctx.get("carrera_nombre")
    slot_periodo      = ctx.get("periodo")
    slot_facultad     = ctx.get("facultad")

    # 2) enriquecer meta con lo detectado y/o contexto
    meta = req.meta or ChatMeta()
    user_text = req.message.strip()

    # carrera: intentar detectar de la pregunta
    det = resolve_carrera(bot_id, user_text)
    if det:
        if det.get("carrera_id"):  # preferimos ID si existe
            meta.carrera_id = det["carrera_id"]
        meta.carrera = det["nombre"]
    else:
        # si el usuario no menciona, usar lo último del contexto
        if slot_carrera_id and not meta.carrera_id:
            meta.carrera_id = slot_carrera_id
        if slot_carrera_name and not meta.carrera:
            meta.carrera = slot_carrera_name

    # período: si no lo dijo, heredar del contexto o inferir por regex
    if not meta.periodo:
        meta.periodo = _infer_periodo_from_text(user_text) or slot_periodo

    # facultad: heredar si viene vacía
    if not meta.facultad and slot_facultad:
        meta.facultad = slot_facultad

    # 3) retrieve + rerank (con meta enriquecida)
    raw_hits = search(client, user_text, meta=meta, top_k=settings.RAG_TOP_K,
                      bot_id=bot_id, allowed_domains=allowed_domains)
    if not raw_hits:
        contact = profile.get("contact", {}) or {}
        fallback = "No encontré información suficiente en la base para responder con confianza."
        if any(contact.values()):
            fallback += f" Podés escribir a {contact.get('email') or contact.get('phone') or 'Admisiones'}."
        # actualizamos historial igual
        history.append({"role":"user", "content": user_text})
        history.append({"role":"assistant", "content": fallback})
        save_ctx(session_id, bot_id, ctx, history)
        return ChatResponse(answer=fallback, sources=[])

    final_docs = rerank(user_text, raw_hits, top_k=settings.RAG_RERANK_K)

    # 4) prompt (+historial/contexto opcional)
    prompt = build_prompt(user_text, final_docs,
                          chat_history=history[-4:],
                          context_slots={
                              "carrera_nombre": meta.carrera or slot_carrera_name,
                              "periodo": meta.periodo or slot_periodo,
                              "facultad": meta.facultad or slot_facultad,
                          })
    system_override = profile.get("system_instruction") or None
    answer = generate_answer(prompt, system_instruction=system_override) or "No pude generar una respuesta. Intenta de nuevo."

    # 5) actualizar contexto con lo detectado esta vez (si hubo detección)
    if det:
        ctx["carrera_id"] = det.get("carrera_id") or ctx.get("carrera_id")
        ctx["carrera_nombre"] = det.get("nombre") or ctx.get("carrera_nombre")
        if det.get("facultad"):
            ctx["facultad"] = det["facultad"]
    # refrescar periodo si el user lo dijo/lo inferimos
    if meta.periodo:
        ctx["periodo"] = meta.periodo
    if meta.facultad:
        ctx["facultad"] = meta.facultad

    # 6) guardar historial corto
    history.append({"role":"user", "content": user_text})
    history.append({"role":"assistant", "content": answer[:1200]})  # truncamos un poco
    save_ctx(session_id, bot_id, ctx, history)

    # 7) construir sources como antes
    from ..schemas.common import Source
    sources = []
    for d in final_docs:
        m = d.get("metadata", {})
        sources.append(Source(
            titulo=m.get("titulo"),
            tipo=m.get("tipo") or m.get("domain"),
            fuente_archivo=m.get("fuente_archivo"),
            fuente_hoja=m.get("fuente_hoja"),
            fuente_fila=m.get("fuente_fila"),
            periodo=m.get("periodo"),
        ))

    payload = {"answer": answer, "sources": sources}
    if req.debug:
        payload["retrieval_debug"] = {
            "context_slots": ctx,
            "used_meta": meta.dict(),
            "domains": list({(h["metadata"] or {}).get("domain") for h in final_docs}),
            "files": list({(h["metadata"] or {}).get("fuente_archivo") for h in final_docs}),
        }
    return ChatResponse(**payload)
