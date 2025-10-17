from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from qdrant_client.http.models import Condition 
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

def _build_filter(
    meta,
    *, bot_id: str,
    allowed_domains: list[str] | None,
    strict_period: bool,
    required_domain: str | None = None,
    include_facultad: bool = True,
    include_modalidad: bool = True,
):
    must = [FieldCondition(key="bot_id", match=MatchValue(value=bot_id))]
    if allowed_domains:
        must.append(FieldCondition(key="domain", match=MatchAny(any=allowed_domains)))
    if required_domain:
        must.append(FieldCondition(key="domain", match=MatchValue(value=required_domain)))

    if meta:
        if getattr(meta, "carrera_id", None):
            must.append(FieldCondition(key="carrera_id", match=MatchValue(value=str(meta.carrera_id))))
        if getattr(meta, "carrera", None) and str(meta.carrera).lower() != "general":
            must.append(FieldCondition(key="carrera", match=MatchValue(value=str(meta.carrera))))
        if include_facultad and getattr(meta, "facultad", None):
            must.append(FieldCondition(key="facultad", match=MatchValue(value=str(meta.facultad))))
        if include_modalidad and getattr(meta, "modalidad", None):
            must.append(FieldCondition(key="modalidad", match=MatchValue(value=str(meta.modalidad))))
        if strict_period and getattr(meta, "periodo", None):
            must.append(FieldCondition(key="periodo", match=MatchValue(value=str(meta.periodo))))
    return Filter(must=must)

def _has_domain(results, dom: str) -> bool:
    return any((sp.payload or {}).get("domain") == dom for sp in results)

def search(client: QdrantClient, query: str, meta, top_k: int, *, bot_id: str, allowed_domains: Optional[list[str]], ensure_domains: Optional[list[str]] = None) -> List[Dict[str, Any]]:
    ensure_domains = ensure_domains or []
    qvec = embed_query(query, model=settings.GEMINI_EMBED_MODEL)

    # 1) pasada estricta (respeta periodo si viene)
    f1 = _build_filter(meta, bot_id=bot_id, allowed_domains=allowed_domains or [], strict_period=True)
    res1 = client.search(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec, limit=top_k, with_payload=True, query_filter=f1)

    # 2) detectar si la query es monetaria
    qlow = (query or "").lower()
    wants_money = any(k in qlow for k in MONETARY_KWS)
    if wants_money and "aranceles" not in ensure_domains:
        ensure_domains = ["aranceles"] + ensure_domains

    # 3) para cualquier dominio "asegurado" que falte, buscamos una 2ª vez relajando período y exigiendo ese dominio
    extra = []
    for dom in ensure_domains:
        if not _has_domain(res1, dom):
            f2 = _build_filter(
                meta,
                bot_id=bot_id,
                allowed_domains=allowed_domains or [],
                strict_period=False,           # 🔓 período relajado
                required_domain=dom,
                include_facultad=False,        # ❌ sin facultad
                include_modalidad=False        # ❌ sin modalidad
            )
            r2 = client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=qvec,
                limit=max(3, top_k // 2),
                with_payload=True,
                query_filter=f2
            )
            extra.extend(r2)

    # 4) merge + dedupe por chunk_id/point_uuid
    seen = set()
    merged = []
    for sp in (res1 + extra):
        payload = sp.payload or {}
        ck = payload.get("chunk_id") or payload.get("point_uuid")
        if ck in seen:
            continue
        seen.add(ck)
        merged.append(sp)

    # 5) salida (igual que antes)
    out: List[Dict[str, Any]] = []
    for sp in merged[:top_k]:
        payload = sp.payload or {}
        out.append({
            "texto": payload.get("texto", ""),
            "metadata": payload,
            "score": float(sp.score or 0.0),
        })
    return out