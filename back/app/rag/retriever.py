from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Condition 
from uuid import uuid4
from .embedder import get_embedding_dim, embed_texts, embed_query
from ..config import settings
from ..schemas.chat import ChatMeta
from .schema import uuid_from_chunk
from qdrant_client.http.models import MatchAny

MONETARY_KWS = [
    "matric", "arancel", "cuota", "mensual", "$", "pago", "plan",
    "inscrip", "inscripción", "inscripcion",
    "valor", "precio", "costo", "coste", "importe"
]

def ensure_collection(client: QdrantClient, collection: str | None = None):
    coll = collection or settings.QDRANT_COLLECTION
    existing = client.get_collections()
    names = [c.name for c in existing.collections]
    if coll in names:
        return
    dim = get_embedding_dim()
    client.create_collection(
        collection_name=coll,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

def upsert_records(client: QdrantClient, records: List[Dict[str, Any]], collection: str | None = None, batch: int = 128):
    coll = collection or settings.QDRANT_COLLECTION
    ensure_collection(client, coll)
    texts = [r["texto"] for r in records]
    vectors = embed_texts(texts, model=settings.GEMINI_EMBED_MODEL)

    points: List[PointStruct] = []
    for vec, rec in zip(vectors, records):
        meta = rec["metadata"]
        chunk_id = meta.get("chunk_id")
        bot = meta.get("bot_id", "default")
        
        # Incluir bot en el ID deterministico para aislar colecciones logicas por bot
        pid = uuid_from_chunk(f"{bot}:{chunk_id}") if chunk_id else str(uuid4())
        
        meta.setdefault("point_uuid", pid)
        
        points.append(PointStruct(
            id=pid,
            vector=vec,
            payload=meta
        ))
        if len(points) >= batch:
            client.upsert(collection_name=coll, points=points)
            points = []
    if points:
        client.upsert(collection_name=coll, points=points)

def count_points(client: QdrantClient, collection: str | None = None) -> int:
    coll = collection or settings.QDRANT_COLLECTION
    try:
        info = client.count(coll, exact=True)
        return info.count or 0
    except Exception:
        return 0

def _build_filter(meta, *, bot_id: str, allowed_domains: list[str], strict_period: bool = True,
                  required_domain: str | None = None, allowed_org_units: list[str] | None = None):
    
    must = [FieldCondition(key="bot_id", match=MatchValue(value=bot_id))]

    # Dominios permitidos / requeridos
    if allowed_domains:
        must.append(FieldCondition(key="domain", match=MatchAny(any=allowed_domains)))
    if required_domain:
        must.append(FieldCondition(key="domain", match=MatchValue(value=required_domain)))

    # Org units (si viene). "*" = admin (no filtramos)
    if allowed_org_units and not (len(allowed_org_units) == 1 and allowed_org_units[0] == "*"):
        must.append(FieldCondition(key="org_unit", match=MatchAny(any=allowed_org_units)))

    # Periodo (estricto solo si strict_period=True)
    if getattr(meta, "periodo", None) and strict_period:
        must.append(FieldCondition(key="periodo", match=MatchValue(value=str(meta.periodo))))

    # Carrera ID / nombre (si vienen)
    if getattr(meta, "carrera_id", None):
        must.append(FieldCondition(key="carrera_id", match=MatchValue(value=str(meta.carrera_id))))
    elif getattr(meta, "carrera", None):
        must.append(FieldCondition(key="carrera", match=MatchValue(value=str(meta.carrera))))

    # Facultad: **solo** si el usuario la dio explícitamente (no hay include_facultad)
    if getattr(meta, "facultad", None):
        must.append(FieldCondition(key="facultad", match=MatchValue(value=str(meta.facultad))))

    return Filter(must=must)

def _has_domain(results, dom: str) -> bool:
    return any((sp.payload or {}).get("domain") == dom for sp in results)

def search(client, query: str, meta, top_k: int, *, bot_id: str,
           allowed_domains: list[str], ensure_domains: list[str] | None = None,
           allowed_org_units: list[str] | None = None):
    ensure_domains = ensure_domains or []
    qvec = embed_query(query, model=settings.GEMINI_EMBED_MODEL)

    # 1) pasada estricta
    f1 = _build_filter(meta, bot_id=bot_id, allowed_domains=allowed_domains,
                       strict_period=True, allowed_org_units=allowed_org_units)
    res1 = client.search(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec,
                         limit=top_k, with_payload=True, query_filter=f1)

    # 2) detectar intención monetaria, etc. (tu lógica existente)
    qlow = (query or "").lower()
    wants_money = any(k in qlow for k in MONETARY_KWS)
    if wants_money and "aranceles" not in ensure_domains:
        ensure_domains = ["aranceles"] + ensure_domains

    # 3) asegurar dominios que falten (relajando periodo)
    extra = []
    for dom in ensure_domains:
        if not _has_domain(res1, dom):
            f2 = _build_filter(meta, bot_id=bot_id, allowed_domains=allowed_domains,
                               strict_period=False, required_domain=dom,
                               allowed_org_units=allowed_org_units)
            r2 = client.search(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec,
                               limit=max(3, top_k // 2), with_payload=True, query_filter=f2)
            extra.extend(r2)

    # 4) merge + dedupe (igual)
    seen, merged = set(), []
    for sp in (res1 + extra):
        payload = sp.payload or {}
        ck = payload.get("chunk_id") or payload.get("point_uuid")
        if ck in seen:
            continue
        seen.add(ck)
        merged.append(sp)

    # 5) salida
    out = []
    for sp in merged[:top_k]:
        payload = sp.payload or {}
        out.append({
            "texto": payload.get("texto", ""),
            "metadata": payload,
            "score": float(sp.score or 0.0),
        })
    return out
