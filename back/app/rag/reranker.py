from typing import List, Dict, Any, Optional
from sentence_transformers import CrossEncoder
import threading, os
from ..config import settings

_model = None
_lock = threading.Lock()

def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                # Forzamos tokenizer "slow" para evitar el conversor que pide tiktoken
                _model = CrossEncoder(
                    "BAAI/bge-reranker-base",
                    tokenizer_kwargs={"use_fast": False}
                )
    return _model

def _domain_boost(domain: str | None, intent: str | None, ensure_domains: List[str] | None) -> float:
    d = (domain or "").lower()
    intent = (intent or "").lower()
    ensure_domains = ensure_domains or []

    # Boost perfiles cuando la intención es info de carrera (perfil, descripción, etc.).
    if d == "perfiles" and (intent == "info_carrera" or "perfiles" in ensure_domains):
        return 1.35

    # Ligero boost a "carreras" en la misma intención para que no pierda contra aranceles.
    if d == "carreras" and (intent == "info_carrera" or "carreras" in ensure_domains):
        return 1.05

    # Penalizar aranceles en intents de perfil para que no eclipsen descripciones.
    if d == "aranceles" and intent == "info_carrera":
        return 0.85

    return 1.0


def rerank(query: str, docs: List[Dict[str, Any]], top_k: int,
           *, intent: Optional[str] = None, ensure_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not settings.ENABLE_RERANKER or not docs:
        return docs[:top_k]
    ensure_domains = [d.lower() for d in (ensure_domains or [])]
    model = _get_model()
    pairs = [(query, d["texto"]) for d in docs]
    scores = model.predict(pairs).tolist()
    rescored = []
    for d, s in zip(docs, scores):
        x = dict(d)
        dom = (d.get("metadata") or {}).get("domain")
        boost = _domain_boost(dom, intent, ensure_domains)
        x["rerank_score"] = float(s * boost)
        rescored.append(x)
    rescored.sort(key=lambda x: x["rerank_score"], reverse=True)

    # Garantizar al menos un documento por cada dominio requerido (ej. perfiles para info de carrera).
    seen = set()
    ensured = []
    for dom in ensure_domains:
        best_for_dom = next((d for d in rescored if (d.get("metadata") or {}).get("domain", "").lower() == dom), None)
        if best_for_dom:
            ck = (best_for_dom.get("metadata") or {}).get("chunk_id") or (best_for_dom.get("metadata") or {}).get("point_uuid")
            if ck not in seen:
                ensured.append(best_for_dom)
                seen.add(ck)

    ordered = ensured[:]
    for d in rescored:
        ck = (d.get("metadata") or {}).get("chunk_id") or (d.get("metadata") or {}).get("point_uuid")
        if ck in seen:
            continue
        seen.add(ck)
        ordered.append(d)
        if len(ordered) >= top_k:
            break

    return ordered[:top_k]


def warm_reranker() -> bool:
    """Carga el modelo de rerank en memoria y ejecuta un predict mínimo."""
    try:
        model = _get_model()
        _ = model.predict([("warmup", "warmup doc")])
        return True
    except Exception as e:
        print(f"[warmup] reranker fallo: {e}")
        return False
