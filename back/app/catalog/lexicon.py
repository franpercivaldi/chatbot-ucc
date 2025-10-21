# app/catalog/lexicon.py
import unicodedata, re
from qdrant_client import QdrantClient
from collections import Counter

def _norm(s:str)->str:
    s=(s or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c)!="Mn")

def build_carrera_lexicon(client: QdrantClient, collection: str) -> list[str]:
    seen = Counter()
    scrolled, nextp = client.scroll(collection_name=collection, with_payload=True, limit=200)
    while True:
        for pt in scrolled:
            pay = pt.payload or {}
            cn = pay.get("carrera_norm") or _norm(pay.get("carrera") or "")
            if cn:
                seen[cn]+=1
        if not nextp: break
        scrolled, nextp = client.scroll(collection_name=collection, with_payload=True, limit=200, offset=nextp)
    # devolvemos únicas ordenadas por frecuencia
    return [c for c,_ in seen.most_common()]

def guess_carrera_terms(q_norm: str, lexicon: list[str]) -> list[str]:
    # tokens de la query
    toks = re.findall(r"[a-záéíóúñ]+", q_norm)
    # prefijos razonables (evita 'ing' por demasiado corto)
    pref = {t for t in toks if len(t)>=5}
    out=set()
    for term in pref:
        for car in lexicon:
            if car.startswith(term) or term.startswith(car[:len(term)]):
                out.add(car)
    # fuzzy simple por distancia (sin libs externas): aceptamos si comparten ≥70% del prefijo
    # (ya con prefix nos alcanza para odonto/psico/conta, etc.)
    return list(out)
