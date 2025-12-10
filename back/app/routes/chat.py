from fastapi import APIRouter, Depends, Request
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
from ..metrics.store import log_chat_event
from ..intent.router import detect_intent
from ..rag.schema import slugify  # para normalizar org_units

router = APIRouter()

def _infer_periodo_from_text(text: str) -> str | None:
    import re
    m = re.search(r"(19|20)\d{2}", text or "")
    return m.group(0) if m else None

def _parse_org_units_header(h: str | None) -> list[str] | None:
    if not h:
        return None
    vals = [x.strip() for x in h.split(",") if x.strip()]
    return [slugify(v) for v in vals] if vals else None


def _prioritize_by_domain(docs, intent: str | None):
    """Para intents de perfil, forzamos que los dominios más relevantes queden arriba.
    Orden sugerido: perfiles > carreras > oferta > todo lo demás.
    """
    if not docs:
        return docs
    if intent != "info_carrera":
        return docs

    order = {"perfiles": 0, "carreras": 1, "oferta": 2}

    def _key(d):
        dom = (d.get("metadata") or {}).get("domain") or "zzz"
        return (order.get(str(dom).lower(), 99))

    return sorted(docs, key=_key)

@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, client = Depends(get_qdrant)):
    # --- Defaults seguros ---
    safe_answer = "No pude generar una respuesta. Intentá de nuevo más tarde."
    sources = []
    retrieval_debug = None

    # --- Perfil del bot / dominios permitidos ---
    bot_id, profile = get_profile(req.bot_id)
    session_id = req.session_id or "anon"
    allowed_domains = profile.get("allowed_domains", [])
    user_text = (req.message or "").strip()

    # --- Org units (V1: header; V2: JWT) ---
    org_hdr = request.headers.get("x-org-units")
    # Solo aplicamos org_units para bots que usan ese concepto (interno)
    use_org_units = (bot_id != "public-admisiones")  # o leé un flag del profile si querés
    allowed_org_units = (_parse_org_units_header(org_hdr) or ["general"]) if use_org_units else None

    # --- Intención, contexto, meta ---
    intent_res = detect_intent(user_text)  # -> intent, ensure_domains
    ctx, history = load_ctx(session_id, bot_id)
    slot_carrera_id   = ctx.get("carrera_id")
    slot_carrera_name = ctx.get("carrera_nombre")
    slot_periodo      = ctx.get("periodo")
    slot_facultad     = ctx.get("facultad")

    meta = req.meta or ChatMeta()

    # --- Saludo corto: responder sin retrieval ---
    if intent_res.intent == "saludo":
        answer = "Hola, soy el asistente virtual de Admisiones de la UCC. Contame en qué carrera o tema te puedo ayudar (aranceles, requisitos, fechas, becas)."
        history.append({"role":"user", "content": user_text})
        history.append({"role":"assistant", "content": answer})
        save_ctx(session_id, bot_id, ctx, history)

        retrieval_debug = {
            "context_slots": ctx,
            "used_meta": meta.dict(),
            "intent": intent_res.intent,
            "domains": [],
            "files": [],
            "org_units": allowed_org_units,
        }

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
            retrieval_debug=retrieval_debug,
            success=True,
            tokens_in=None,
            tokens_out=None,
            extra={"org_units": allowed_org_units}
        )

        return ChatResponse(answer=answer, sources=[], retrieval_debug=retrieval_debug if req.debug else None)

    # Detección de carrera en el turno
    det = resolve_carrera(bot_id, user_text)
    if det:
        if det.get("carrera_id"):
            meta.carrera_id = det["carrera_id"]
        meta.carrera = det["nombre"]
        # Si se detecta nueva carrera, no arrastrar facultad vieja
        ctx.pop("facultad", None)
    else:
        # Usar SOLO carrera de contexto (no copiar facultad)
        if slot_carrera_id and not meta.carrera_id:
            meta.carrera_id = slot_carrera_id
        if slot_carrera_name and not meta.carrera:
            meta.carrera = slot_carrera_name

    # Período: inferir si no vino
    if not meta.periodo:
        meta.periodo = _infer_periodo_from_text(user_text) or slot_periodo

    # Si hay una carrera detectada (en el turno o en contexto), aseguramos dominios clave
    ensure_domains = list(intent_res.ensure_domains or [])
    has_carrera = bool(meta.carrera or meta.carrera_id or slot_carrera_name or slot_carrera_id)
    if has_carrera:
        for dom in ("perfiles", "carreras"):
            if dom not in ensure_domains:
                ensure_domains.append(dom)

    try:
        # --- Retrieve con filtro por org_unit ---
        raw_hits = search(
            client, user_text, meta=meta, top_k=settings.RAG_TOP_K,
            bot_id=bot_id, allowed_domains=allowed_domains,
            ensure_domains=ensure_domains,
            allowed_org_units=allowed_org_units,
        )

        if not raw_hits:
            # fallback early: sin resultados
            contact = profile.get("contact", {}) or {}
            ans = "No encontré información suficiente en la base para responder con confianza."
            if any(contact.values()):
                ans += f" Podés escribir a {contact.get('email') or contact.get('phone') or 'Mesa de ayuda'}."
            # guardar historial
            history.append({"role":"user", "content": user_text})
            history.append({"role":"assistant", "content": ans})
            save_ctx(session_id, bot_id, ctx, history)

            # debug mínimo
            retrieval_debug = {
                "context_slots": ctx,
                "used_meta": meta.dict(),
                "intent": intent_res.intent,
                "domains": [],
                "files": [],
                "org_units": allowed_org_units,
            }

            # métricas
            log_chat_event(
                bot_id=bot_id,
                session_id=session_id,
                user_query=user_text,
                answer=ans,
                ctx_slots={
                    "carrera_nombre": meta.carrera or ctx.get("carrera_nombre"),
                    "carrera_id": meta.carrera_id or ctx.get("carrera_id"),
                    "periodo": meta.periodo or ctx.get("periodo"),
                    "facultad": meta.facultad or ctx.get("facultad"),
                },
                retrieval_debug=retrieval_debug,
                success=False,
                tokens_in=None,
                tokens_out=None,
                extra={"org_units": allowed_org_units}
            )
            return ChatResponse(answer=ans, sources=[],
                                retrieval_debug=retrieval_debug if req.debug else None)

        # --- Rerank ---
        final_docs = rerank(
            user_text,
            raw_hits,
            top_k=settings.RAG_RERANK_K,
            intent=intent_res.intent,
            ensure_domains=ensure_domains,
        )
        final_docs = _prioritize_by_domain(final_docs, intent_res.intent)

        # --- Prompt & generación ---
        prompt = build_prompt(
            user_text,
            final_docs,
            chat_history=history[-4:],
            context_slots={
                "carrera_nombre": meta.carrera or slot_carrera_name,
                "periodo": meta.periodo or slot_periodo,
                "facultad": meta.facultad or slot_facultad,
            },
        )
        system_override = profile.get("system_instruction") or None
        answer = generate_answer(prompt, system_instruction=system_override)
        if not answer:
            answer = safe_answer

        # --- Actualizar contexto ---
        if det:
            ctx["carrera_id"] = det.get("carrera_id") or ctx.get("carrera_id")
            ctx["carrera_nombre"] = det.get("nombre") or ctx.get("carrera_nombre")
            if det.get("facultad"):
                ctx["facultad"] = det["facultad"]
        if meta.periodo:
            ctx["periodo"] = meta.periodo
        if meta.facultad:
            ctx["facultad"] = meta.facultad

        # --- Guardar historial ---
        history.append({"role":"user", "content": user_text})
        history.append({"role":"assistant", "content": answer[:1200]})
        save_ctx(session_id, bot_id, ctx, history)

        # --- Sources ---
        from ..schemas.common import Source
        sources = []
        for d in final_docs:
            m = d.get("metadata", {}) or {}
            sources.append(Source(
                titulo=m.get("titulo"),
                tipo=m.get("tipo") or m.get("domain"),
                fuente_archivo=m.get("fuente_archivo"),
                fuente_hoja=m.get("fuente_hoja"),
                fuente_fila=m.get("fuente_fila"),
                periodo=m.get("periodo"),
            ))

        dbg_domains = list({(h.get("metadata") or {}).get("domain") for h in final_docs})
        dbg_files   = list({(h.get("metadata") or {}).get("fuente_archivo") for h in final_docs})
        retrieval_debug = {
            "context_slots": ctx,
            "used_meta": meta.dict(),
            "intent": intent_res.intent,
            "domains": dbg_domains,
            "files": dbg_files,
            "org_units": allowed_org_units,
        }

        # Éxito: si había dominios obligatorios por intención y no aparecieron, marcar False
        need = set(intent_res.ensure_domains or [])
        have = set(dbg_domains)
        success = True if not need else bool(have & need)

        # Métricas
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
            retrieval_debug=retrieval_debug,
            success=success,
            tokens_in=None,
            tokens_out=None,
            extra={"org_units": allowed_org_units}
        )

        return ChatResponse(
            answer=answer,
            sources=sources,
            retrieval_debug=retrieval_debug if req.debug else None
        )

    except Exception as e:
        # Fallback de emergencia: nunca devolvemos null
        ans = f"Ocurrió un error procesando la consulta: {e}"
        history.append({"role":"user", "content": user_text})
        history.append({"role":"assistant", "content": ans})
        save_ctx(session_id, bot_id, ctx, history)

        retrieval_debug = {
            "context_slots": ctx,
            "used_meta": meta.dict(),
            "intent": getattr(intent_res, "intent", None),
            "domains": [],
            "files": [],
            "org_units": allowed_org_units,
            "error": str(e),
        }

        log_chat_event(
            bot_id=bot_id,
            session_id=session_id,
            user_query=user_text,
            answer=ans,
            ctx_slots={
                "carrera_nombre": meta.carrera or ctx.get("carrera_nombre"),
                "carrera_id": meta.carrera_id or ctx.get("carrera_id"),
                "periodo": meta.periodo or ctx.get("periodo"),
                "facultad": meta.facultad or ctx.get("facultad"),
            },
            retrieval_debug=retrieval_debug,
            success=False,
            tokens_in=None,
            tokens_out=None,
            extra={"org_units": allowed_org_units}
        )

        return ChatResponse(
            answer=ans,
            sources=[],
            retrieval_debug=retrieval_debug if req.debug else None
        )
