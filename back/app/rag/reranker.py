from typing import List, Dict, Any
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
                    tokenizer_args={"use_fast": False}
                )
    return _model

def rerank(query: str, docs: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    if not settings.ENABLE_RERANKER or not docs:
        return docs[:top_k]
    model = _get_model()
    pairs = [(query, d["texto"]) for d in docs]
    scores = model.predict(pairs).tolist()
    rescored = []
    for d, s in zip(docs, scores):
        x = dict(d)
        x["rerank_score"] = float(s)
        rescored.append(x)
    rescored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return rescored[:top_k]
