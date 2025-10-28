# back/app/rag/pdf_loader.py
from __future__ import annotations
import os, re, unicodedata
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF

from .schema import (
    SCHEMA_VERSION, slugify, hash_str, make_doc_id, make_chunk_id, now_iso_utc
)

PDF_BASE_DIR = "/app/data/docs"

DOMAIN_HINTS = [
    (r"reglamento|norma|politic|procedim|proceso|manual|instructivo", "reglamentos"),
]

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")

def _guess_domain(file_name: str) -> str:
    base = _strip_accents(file_name.lower())
    for rx, dom in DOMAIN_HINTS:
        if re.search(rx, base):
            return dom
    return "reglamentos"  # default para este bot

def _list_pdf_files(bot_id: str) -> List[str]:
    """
    Busca PDFs en /app/data/docs/<bot_id>/**.pdf
    """
    base = os.path.join(PDF_BASE_DIR, bot_id)
    if not os.path.isdir(base):
        return []
    out: List[str] = []
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(".pdf"):
                out.append(os.path.join(root, f))
    return sorted(out)

def _org_unit_from_path(path: str, bot_id: str) -> str:
    """
    Toma el nombre del subdirectorio inmediato dentro de /docs/<bot_id>.
    /docs/interno-academico/rrhh/archivo.pdf -> rrhh
    Si no hay subdir, 'general'.
    """
    base = os.path.join(PDF_BASE_DIR, bot_id)
    try:
        rel = os.path.relpath(path, base)
        parts = rel.split(os.sep)
        return slugify(parts[0]) if len(parts) > 1 else "general"
    except Exception:
        return "general"

def _chunk_paragraphs(text: str, max_chars: int = 1000, overlap: int = 120) -> List[str]:
    """
    Chunking simple por párrafos con solapamiento pequeño.
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    if not paras:
        # si no hay dobles saltos, cortamos por longitud
        text = (text or "").strip()
        return [text[i:i+max_chars] for i in range(0, len(text), max_chars)] if text else []

    chunks: List[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
            continue
        if len(buf) + 1 + len(p) <= max_chars:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            # overlap tomando cola del buffer
            tail = buf[-overlap:] if len(buf) > overlap else buf
            buf = tail + "\n\n" + p
    if buf:
        chunks.append(buf)
    return chunks

def _doc_title(doc: fitz.Document, file_name: str) -> str:
    meta = doc.metadata or {}
    title = meta.get("title") or os.path.splitext(os.path.basename(file_name))[0]
    return title.strip() or os.path.splitext(os.path.basename(file_name))[0]

def load_pdf_dir(bot_id: str) -> List[Dict[str, Any]]:
    """
    Carga todos los PDFs de /app/data/docs/<bot_id> y devuelve records estilo RAG:
    [{ "texto": "...", "metadata": {...}}]
    """
    records: List[Dict[str, Any]] = []
    pdf_paths = _list_pdf_files(bot_id)
    if not pdf_paths:
        return records

    for path in pdf_paths:
        try:
            doc = fitz.open(path)
        except Exception:
            # no frenar por un PDF roto
            continue

        fname = os.path.basename(path)
        doc_id = make_doc_id(path, "PDF")
        domain = _guess_domain(fname)
        org_unit = _org_unit_from_path(path, bot_id)
        title = _doc_title(doc, fname)

        # Extraemos texto página a página
        for page_idx in range(len(doc)):
            try:
                page = doc[page_idx]
                txt = page.get_text("text") or ""
                txt = txt.replace("\r", "\n").strip()
                if not txt:
                    continue  # página sin texto (posible escaneado)
                chunks = _chunk_paragraphs(txt, max_chars=1100, overlap=120)
                for j, ch in enumerate(chunks):
                    # ids determinísticos por doc + page + idx chunk
                    primary_key = f"{domain}:{org_unit}:p{page_idx+1}:c{j}"
                    chunk_id = make_chunk_id(doc_id, primary_key)
                    row_hash = hash_str(ch)

                    metadata = {
                        "schema_version": SCHEMA_VERSION,
                        "bot_id": bot_id,
                        "domain": domain,
                        "tipo": domain,
                        "doc_id": doc_id,
                        "chunk_id": chunk_id,
                        "row_hash": row_hash,
                        "inserted_at": now_iso_utc(),
                        "source_path": os.path.normpath(path),
                        "fuente_archivo": fname,
                        "fuente_hoja": "PDF",
                        "fuente_fila": int(page_idx),  # page index como "fila"
                        # enriquecimiento
                        "org_unit": org_unit,
                        "titulo": title,
                        "periodo": None,  # Paso 2: inferir año si corresponde
                        "texto": ch,
                        # auxiliares
                        "page_from": page_idx + 1,
                        "page_to": page_idx + 1,
                    }
                    # limpiar None
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    records.append({"texto": ch, "metadata": metadata})
            except Exception:
                continue

        try:
            doc.close()
        except Exception:
            pass

    return records
