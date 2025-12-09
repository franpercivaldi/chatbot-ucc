from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Condition 
import httpx
from uuid import uuid4
from .embedder import get_embedding_dim, embed_texts, embed_query
from ..config import settings
from ..schemas.chat import ChatMeta
from .schema import uuid_from_chunk, slugify
from qdrant_client.http.models import MatchAny

MONETARY_KWS = [
    "matric", "arancel", "cuota", "mensual", "$", "pago", "plan",
    "inscrip", "inscripción", "inscripcion",
    "valor", "precio", "costo", "coste", "importe"
]

def ensure_collection(client: QdrantClient, collection: str | None = None):
    coll = collection or settings.QDRANT_COLLECTION
    dim = get_embedding_dim()
    
    existing = client.get_collections()
    names = [c.name for c in existing.collections]
    
    if coll in names:
        # Verificar dimensión
        try:
            info = client.get_collection(coll)
            # Manejo de config anidada (puede variar según versión de cliente)
            # info.config.params.vectors puede ser VectorParams o dict
            current_dim = None
            if hasattr(info.config.params, "vectors") and info.config.params.vectors:
                vecs = info.config.params.vectors
                if hasattr(vecs, "size"):
                    current_dim = vecs.size
                elif isinstance(vecs, dict) and "size" in vecs:
                    current_dim = vecs["size"]
            
            if current_dim and current_dim != dim:
                print(f"[WARN] Recreando colección {coll}: dimensión actual {current_dim} != esperada {dim}")
                client.delete_collection(coll)
            else:
                return
        except Exception as e:
            print(f"[WARN] Error verificando colección {coll}: {e}")
            # Ante la duda, intentamos seguir o recrear si falla upsert
            return

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
    should = []

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
        # Si el periodo es estricto, permitimos el periodo solicitado O "general"
        # Esto es clave para que los documentos JSON (que tienen periodo="general")
        # aparezcan incluso cuando el usuario (o el sistema) infiere un año específico (ej. 2026).
        requested_period = str(meta.periodo)
        must.append(FieldCondition(
            key="periodo", 
            match=MatchAny(any=[requested_period, "general"])
        ))

    # Carrera ID (exact) o Carrera name/slug (use SHOULD to allow either)
    if getattr(meta, "carrera_id", None):
        # Si tenemos ID, buscamos por ID exacto O por nombre (por si el JSON no tiene el ID correcto)
        cid = str(meta.carrera_id)
        conds = [FieldCondition(key="carrera_id", match=MatchValue(value=cid))]
        
        if getattr(meta, "carrera", None):
             val = str(meta.carrera)
             conds.append(FieldCondition(key="carrera", match=MatchValue(value=val)))
             try:
                slug = slugify(val)
                conds.append(FieldCondition(key="carrera_slug", match=MatchValue(value=slug)))
             except Exception:
                pass
        
        must.append(Filter(should=conds))
        
    elif getattr(meta, "carrera", None):
        val = str(meta.carrera)
        # add SHOULD conditions: match 'carrera' exact OR match 'carrera_slug' (slugified)
        should.append(FieldCondition(key="carrera", match=MatchAny(any=[val, val.lower(), val.title()])))
        try:
            slug = slugify(val)
            should.append(FieldCondition(key="carrera_slug", match=MatchAny(any=[slug, val, val.lower()])))
        except Exception:
            pass

    # Facultad: **solo** si el usuario la dio explícitamente (no hay include_facultad)
    if getattr(meta, "facultad", None):
        must.append(FieldCondition(key="facultad", match=MatchValue(value=str(meta.facultad))))

    # Build Filter; include should if present
    if should:
        return Filter(must=must, should=should)
    return Filter(must=must)

def _has_domain(results, dom: str) -> bool:
    def _payload(sp):
        if hasattr(sp, "payload"):
            return sp.payload or {}
        if isinstance(sp, dict):
            return sp.get("payload") or {}
        return {}
    return any((_payload(sp) or {}).get("domain") == dom for sp in results)

def search(client, query: str, meta, top_k: int, *, bot_id: str,
           allowed_domains: list[str], ensure_domains: list[str] | None = None,
           allowed_org_units: list[str] | None = None):
    ensure_domains = ensure_domains or []
    qvec = embed_query(query, model=settings.GEMINI_EMBED_MODEL)

    # Helper: use the appropriate client method (compatibility across qdrant-client versions)
    def _qdrant_search_try(**kwargs):
        # Try several common variants of the search API on the client.
        last_exc = None
        # 1) direct `search` with expected kwargs
        try:
            return client.search(**kwargs)
        except Exception as e:
            last_exc = e
        # 2) `search` positional fallback
        try:
            return client.search(kwargs.get("collection_name"), kwargs.get("query_vector"), kwargs.get("limit"), with_payload=kwargs.get("with_payload"), query_filter=kwargs.get("query_filter"))
        except Exception as e:
            last_exc = e
        # 3) `search_points` variant (older/newer clients)
        try:
            # some versions use `vector` and `filter` names
            return client.search_points(collection_name=kwargs.get("collection_name"), vector=kwargs.get("query_vector"), limit=kwargs.get("limit"), with_payload=kwargs.get("with_payload"), query_filter=kwargs.get("query_filter"))
        except Exception as e:
            last_exc = e
        # 4) try underlying http client if available
        try:
            http = getattr(client, "http", None)
            if http is not None and hasattr(http, "search"):
                return http.search(**kwargs)
        except Exception as e:
            last_exc = e
        # 5) fallback: call Qdrant HTTP API directly via httpx
        try:
            url = settings.QDRANT_URL.rstrip("/") + f"/collections/{kwargs.get('collection_name')}/points/search"
            # build basic payload
            payload = {
                "vector": kwargs.get("query_vector"),
                "limit": kwargs.get("limit"),
                "with_payload": bool(kwargs.get("with_payload")),
            }
            # if we were given a Filter object (from qdrant_client models), try to convert to dict
            qf = kwargs.get("query_filter")
            if qf is not None:
                try:
                    # Some model objects provide .dict(); try that first
                    payload["filter"] = qf.dict() if hasattr(qf, "dict") else qf.__dict__
                except Exception:
                    # Fallback: as last resort, set None (no filter)
                    payload["filter"] = None

            with httpx.Client(timeout=settings.QDRANT_TIMEOUT) as hc:
                resp = hc.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                # qdrant returns 'result' list with 'payload' and 'score'
                return data.get("result", [])
        except Exception as e:
            last_exc = e
        # If none worked, re-raise a clear error
        raise AttributeError("Qdrant client has no compatible 'search' method. Last error: %s" % (last_exc,))

    # 1) pasada estricta
    f1 = _build_filter(meta, bot_id=bot_id, allowed_domains=allowed_domains,
                       strict_period=True, allowed_org_units=allowed_org_units)
    res1 = _qdrant_search_try(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec,
                              limit=top_k, with_payload=True, query_filter=f1)

    # 2) detectar intención monetaria, etc. (tu lógica existente)
    qlow = (query or "").lower()
    wants_money = any(k in qlow for k in MONETARY_KWS)
    if wants_money and "aranceles" not in ensure_domains:
        ensure_domains = ["aranceles"] + ensure_domains

    # 3) asegurar dominios que falten (relajando periodo)
    extra = []
    for dom in ensure_domains:
        # Siempre hacemos una pasada dedicada para 'carreras' cuando el usuario dio carrera,
        # porque puede haber hits en CSVs que oculten los JSON con perfil.
        has_carrera_meta = (getattr(meta, "carrera", None) or getattr(meta, "carrera_id", None))
        # Si el usuario indicó carrera, obligamos pasada dedicada también para 'perfiles'
        force_dom = (dom in ("carreras", "perfiles") and has_carrera_meta)
        
        if force_dom or not _has_domain(res1, dom):
            f2 = _build_filter(meta, bot_id=bot_id, allowed_domains=allowed_domains,
                               strict_period=False, required_domain=dom,
                               allowed_org_units=allowed_org_units)
            r2 = _qdrant_search_try(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec,
                                   limit=max(3, top_k // 2), with_payload=True, query_filter=f2)
            
            # Fallback: si falló y tenemos carrera, probamos SIN filtro de carrera
            if not r2 and force_dom:
                class MetaProxy:
                    def __init__(self, original):
                        self._orig = original
                    def __getattr__(self, name):
                        if name in ("carrera", "carrera_id"):
                            return None
                        return getattr(self._orig, name, None)

                f3 = _build_filter(MetaProxy(meta), bot_id=bot_id, allowed_domains=allowed_domains,
                                   strict_period=False, required_domain=dom,
                                   allowed_org_units=allowed_org_units)
                
                print(f"[DEBUG] Fallback search for domain {dom} without carrera filter")
                r3 = _qdrant_search_try(collection_name=settings.QDRANT_COLLECTION, query_vector=qvec,
                                       limit=3, with_payload=True, query_filter=f3)
                extra.extend(r3)
            else:
                extra.extend(r2)

    # 4) merge + dedupe (igual)
    seen, merged = set(), []
    def _payload(sp):
        if hasattr(sp, "payload"):
            return sp.payload or {}
        if isinstance(sp, dict):
            return sp.get("payload") or {}
        return {}

    def _score(sp):
        if hasattr(sp, "score"):
            return sp.score
        if isinstance(sp, dict):
            return sp.get("score")
        return None

    # Damos prioridad a los resultados forzados de ensure_domains (extra) para que no queden truncados
    # si la pasada base res1 llena el top_k.
    for sp in (extra + res1):
        payload = _payload(sp)
        ck = payload.get("chunk_id") or payload.get("point_uuid")
        if ck in seen:
            continue
        seen.add(ck)
        merged.append(sp)

    # 5) salida
    out = []
    for sp in merged[:top_k]:
        payload = _payload(sp)
        s = _score(sp)
        out.append({
            "texto": payload.get("texto", ""),
            "metadata": payload,
            "score": float(s or 0.0),
        })
    return out
