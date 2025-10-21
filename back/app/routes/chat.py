from fastapi import APIRouter, Depends
from ..schemas.chat import ChatRequest, ChatResponse, ChatMeta
from ..schemas.common import Source
from ..deps import get_qdrant
from ..bots.profiles import get_profile
from ..catalog.entities import resolve_carrera
from ..rag.retriever import search
from ..rag.reranker import rerank
from ..rag.prompts import build_prompt
from ..models.gemini_client import generate_answer
from ..config import settings
from ..session.store import load as load_ctx, save as save_ctx
from ..metrics.store import log_chat_event
from ..intent.router import detect_intent
from ..cache.store import get_cache, put_cache

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
    user_text = req.message.strip()

    # 0) Detectar intención (montos/fechas/requisitos/becas/reglamentos/handoff/general)
    intent_res = detect_intent(user_text)  # -> intent, ensure_domains

    # 1) cargar contexto previo
    ctx, history = load_ctx(session_id, bot_id)  # ctx: dict; history: list[{role,content}]
    slot_carrera_id   = ctx.get("carrera_id")
    slot_carrera_name = ctx.get("carrera_nombre")
    slot_periodo      = ctx.get("periodo")
    slot_facultad     = ctx.get("facultad")

    # 2) enriquecer meta con lo detectado y/o contexto
    meta = req.meta or ChatMeta()

    # carrera: intentar detectar de la pregunta
    det = resolve_carrera(bot_id, user_text)
    new_carrera_detected = bool(det)

    if det:
        if det.get("carrera_id"):  # preferimos ID si existe
            meta.carrera_id = det["carrera_id"]
        meta.carrera = det["nombre"]
        # 🔑 si detectamos una nueva carrera en este turno, no arrastrar facultad previa
        ctx.pop("facultad", None)
    else:
        # si no se detectó carrera en este turno, usar SOLO carrera del contexto; NO copiar facultad
        if slot_carrera_id and not meta.carrera_id:
            meta.carrera_id = slot_carrera_id
        if slot_carrera_name and not meta.carrera:
            meta.carrera = slot_carrera_name

    # período: si no lo dijo, heredar del contexto o inferir por regex
    if not meta.periodo:
        meta.periodo = _infer_periodo_from_text(user_text) or slot_periodo

    # --------------------- CACHE LOOKUP ---------------------
    cache_hit = get_cache(
        bot_id=bot_id,
        question=user_text,
        carrera=meta.carrera or slot_carrera_name,
        periodo=meta.periodo or slot_periodo
    )
    if cache_hit:
        answer = cache_hit.get("answer", "")
        cached_sources = cache_hit.get("sources", [])

        # log de métricas para hit de cache
        try:
            log_chat_event(
                bot_id=bot_id,
                session_id=session_id,
                user_query=user_text,
                answer=answer,
                ctx_slots={
                    "carrera_nombre": meta.carrera or slot_carrera_name,
                    "carrera_id": meta.carrera_id or ctx.get("carrera_id"),
                    "periodo": meta.periodo or slot_periodo,
                    "facultad": meta.facultad or ctx.get("facultad"),
                },
                retrieval_debug={"intent": "cache_hit", "domains": [], "files": []},
                success=True,
                tokens_in=0,
                tokens_out=len(answer or ""),
                extra={"cache": "hit"}
            )
        except Exception:
            pass

        # actualizar historial y devolver
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": answer[:1200]})
        save_ctx(session_id, bot_id, ctx, history)

        # Source puede venir como dict → casteamos
        src_objs = [Source(**s) if isinstance(s, dict) else s for s in cached_sources]
        return ChatResponse(answer=answer, sources=src_objs)
    # ------------------ FIN CACHE LOOKUP --------------------

    # 3) retrieve + rerank (con meta enriquecida + dominios asegurados por intención)
    raw_hits = search(
        client, user_text, meta=meta, top_k=settings.RAG_TOP_K,
        bot_id=bot_id, allowed_domains=allowed_domains,
        ensure_domains=intent_res.ensure_domains
    )
    if not raw_hits:
        contact = profile.get("contact", {}) or {}
        fallback = "No encontré información suficiente en la base para responder con confianza."
        if any(contact.values()):
            fallback += f" Podés escribir a {contact.get('email') or contact.get('phone') or 'Admisiones'}."
        # actualizamos historial igual
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": fallback})
        save_ctx(session_id, bot_id, ctx, history)
        return ChatResponse(answer=fallback, sources=[])

    final_docs = rerank(user_text, raw_hits, top_k=settings.RAG_RERANK_K)

    # 4) prompt (+historial/contexto opcional)
    prompt = build_prompt(
        user_text,
        final_docs,
        chat_history=history[-4:],
        context_slots={
            "carrera_nombre": meta.carrera or slot_carrera_name,
            "periodo": meta.periodo or slot_periodo,
            "facultad": meta.facultad or slot_facultad,  # solo para redacción, no para filtrar
        },
    )
    system_override = profile.get("system_instruction") or None
    answer = generate_answer(prompt, system_instruction=system_override) or \
             "No pude generar una respuesta. Intenta de nuevo."

    # 5) actualizar contexto con lo detectado esta vez (si hubo detección)
    if det:
        ctx["carrera_id"] = det.get("carrera_id") or ctx.get("carrera_id")
        ctx["carrera_nombre"] = det.get("nombre") or ctx.get("carrera_nombre")
        if det.get("facultad"):
            ctx["facultad"] = det["facultad"]
    # refrescar periodo si el user lo dijo/lo inferimos
    if meta.periodo:
        ctx["periodo"] = meta.periodo
    # sólo persistir facultad si vino explícita en este turno (meta.facultad seteada a mano)
    if meta.facultad:
        ctx["facultad"] = meta.facultad

    # 6) guardar historial corto
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": answer[:1200]})  # truncamos un poco
    save_ctx(session_id, bot_id, ctx, history)

    # 7) construir sources
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

    # debug (incluye intención)
    dbg_domains = list({(h["metadata"] or {}).get("domain") for h in final_docs})
    dbg_files   = list({(h["metadata"] or {}).get("fuente_archivo") for h in final_docs})
    payload = {"answer": answer, "sources": sources}
    if req.debug:
        payload["retrieval_debug"] = {
            "context_slots": ctx,
            "used_meta": meta.dict(),
            "intent": intent_res.intent,
            "domains": dbg_domains,
            "files": dbg_files,
        }

    # Éxito: si había dominios obligatorios por intención y no aparecieron, marcar False
    need = set(intent_res.ensure_domains or [])
    have = set(dbg_domains)
    success = True if not need else bool(have & need)

    # --- CACHE SAVE (si hubo docs) ---
    if final_docs:
        try:
            put_cache(
                bot_id=bot_id,
                question=user_text,
                carrera=meta.carrera or slot_carrera_name,
                periodo=meta.periodo or slot_periodo,
                answer=answer,
                sources=[s.dict() for s in sources]  # pydantic -> dict
            )
        except Exception:
            pass
    # --- FIN CACHE SAVE ---

    # Log de métricas (guarda intención dentro de retrieval_debug)
    log_chat_event(
        bot_id=bot_id,
        session_id=session_id,
        user_query=user_text,
        answer=answer,
        ctx_slots={
            "carrera_nombre": meta.carrera or ctx.get("carrera_nombre"),
            "carrera_id": meta.carrera_id or ctx.get("carrera_id"),
            "periodo": meta.periodo or ctx.get("periodo"),
            "facultad": meta.facultad or ctx.get("facultad"),
        },
        retrieval_debug=payload.get("retrieval_debug") or {
            "intent": intent_res.intent, "domains": dbg_domains, "files": dbg_files
        },
        success=success,
        tokens_in=None,
        tokens_out=None,
        extra={}
    )

    return ChatResponse(**payload)
