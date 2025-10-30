# back/app/rag/pdf_loader.py
from __future__ import annotations
import os, re, json, unicodedata
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
import pdfplumber

from .schema import (
    SCHEMA_VERSION, slugify, hash_str, make_doc_id, make_chunk_id,
    now_iso_utc, parse_money_to_float
)

PDF_BASE_DIR = "/app/data/docs"

DOMAIN_HINTS = [
    (r"reglamento|norma|politic|procedim|proceso|manual|instructivo", "reglamentos"),
]

MONEY_RX = re.compile(r"(\$?\s?[\d\.\,]+(?:,\d{2})?)")  # captura $ 1.234,56 / 1234,56 / 1.234
PERCENT_RX = re.compile(r"(\d{1,3})\s?%")

def _strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")

def _guess_domain(file_name: str) -> str:
    base = _strip_accents(file_name.lower())
    for rx, dom in DOMAIN_HINTS:
        if re.search(rx, base):
            return dom
    return "reglamentos"  # default para este bot

def _list_pdf_files(bot_id: str) -> List[str]:
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
    base = os.path.join(PDF_BASE_DIR, bot_id)
    try:
        rel = os.path.relpath(path, base)
        parts = rel.split(os.sep)
        return slugify(parts[0]) if len(parts) > 1 else "general"
    except Exception:
        return "general"

def _chunk_paragraphs(text: str, max_chars: int = 1100, overlap: int = 120) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    if not paras:
        text = (text or "").strip()
        return [text[i:i+max_chars] for i in range(0, len(text), max_chars)] if text else []
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if not buf:
            buf = p
            continue
        if len(buf) + 2 + len(p) <= max_chars:
            buf = buf + "\n\n" + p
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if len(buf) > overlap else buf
            buf = (tail + "\n\n" + p) if tail else p
    if buf:
        chunks.append(buf)
    return chunks

def _doc_title(doc: fitz.Document, file_name: str) -> str:
    meta = doc.metadata or {}
    title = meta.get("title") or os.path.splitext(os.path.basename(file_name))[0]
    return title.strip() or os.path.splitext(os.path.basename(file_name))[0]

def _numbers_from_text(text: str) -> Dict[str, Any]:
    nums: Dict[str, Any] = {}
    # montos (se guardan como lista si hay varios)
    money = []
    for m in MONEY_RX.findall(text or ""):
        val = parse_money_to_float(m)
        if val is not None:
            money.append(val)
    if money:
        nums["money_values"] = money

    # porcentajes
    perc = []
    for p in PERCENT_RX.findall(text or ""):
        try:
            perc.append(int(p))
        except Exception:
            pass
    if perc:
        nums["perc_values"] = perc
    return nums

def _markdown_from_table(table: List[List[str]]) -> str:
    """
    Convierte una tabla (lista de filas) en Markdown simple.
    Asume primera fila como encabezados si el contenido parece textual.
    """
    if not table:
        return ""
    # normalizar a str
    tbl = [[("" if c is None else str(c)).strip() for c in row] for row in table]

    has_header = True
    # heurística simple: si la primera fila tiene texto no-numérico
    if tbl and all(not re.search(r"\d", c) for c in tbl[0]):
        has_header = True
    # si no, igual tratamos la primera fila como encabezado para mayor legibilidad
    header = tbl[0]
    rows = tbl[1:] if len(tbl) > 1 else []

    # armar markdown
    md = []
    md.append("| " + " | ".join(header) + " |")
    md.append("| " + " | ".join("---" for _ in header) + " |")
    for r in rows:
        # pad columns
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        md.append("| " + " | ".join(r) + " |")
    return "\n".join(md)

def _extract_tables_pdfplumber(pdf_path: str) -> Dict[int, List[Dict[str, Any]]]:
    """
    Devuelve un dict page_idx -> lista de tablas, cada tabla con:
    {"markdown": str, "json": List[List[str]], "text_joined": str}
    """
    out: Dict[int, List[Dict[str, Any]]] = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                if not tables:
                    continue
                out[i] = []
                for t in tables:
                    # t es List[List[Any]]; normalizamos a str
                    json_tbl = [[("" if c is None else str(c)).strip() for c in row] for row in t]
                    md = _markdown_from_table(json_tbl)
                    text_joined = "\n".join([" | ".join(row) for row in json_tbl])
                    out[i].append({"markdown": md, "json": json_tbl, "text_joined": text_joined})
    except Exception:
        # no romper si pdfplumber falla
        return out
    return out

def load_pdf_dir(bot_id: str) -> List[Dict[str, Any]]:
    """
    Carga PDFs de /app/data/docs/<bot_id>, genera:
      - Chunks de texto por párrafo
      - Chunks de tablas (markdown + json) con metadata.is_table=true
      - metadata.numbers con montos/porcentajes detectados
    """
    records: List[Dict[str, Any]] = []
    pdf_paths = _list_pdf_files(bot_id)
    if not pdf_paths:
        return records

    for path in pdf_paths:
        fname = os.path.basename(path)
        domain = _guess_domain(fname)
        org_unit = _org_unit_from_path(path, bot_id)

        # 1) Extraer tablas con pdfplumber (antes de texto)
        tables_by_page = _extract_tables_pdfplumber(path)

        # 2) Texto con PyMuPDF
        try:
            doc = fitz.open(path)
        except Exception:
            continue

        doc_id = make_doc_id(path, "PDF")
        title = _doc_title(doc, fname)

        for page_idx in range(len(doc)):
            # 2.a) primero los chunks de TABLAS (si hay)
            if page_idx in tables_by_page:
                for k, tbl in enumerate(tables_by_page[page_idx]):
                    md = tbl.get("markdown") or ""
                    if not md.strip():
                        continue
                    text_for_numbers = tbl.get("text_joined") or md
                    numbers = _numbers_from_text(text_for_numbers) or None

                    primary_key = f"{domain}:{org_unit}:p{page_idx+1}:t{k}"
                    chunk_id = make_chunk_id(doc_id, primary_key)
                    row_hash = hash_str(md)

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
                        "fuente_fila": int(page_idx),
                        "org_unit": org_unit,
                        "titulo": title,
                        "page_from": page_idx + 1,
                        "page_to": page_idx + 1,
                        "is_table": True,
                        "table_json": tbl.get("json"),  # estructura cruda por si queremos usarla en el futuro
                        "numbers": numbers,
                    }
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    records.append({"texto": md, "metadata": metadata})

            # 2.b) ahora chunks de TEXTO de la página
            try:
                page = doc[page_idx]
                txt = page.get_text("text") or ""
                txt = txt.replace("\r", "\n").strip()
                if not txt:
                    continue
                chunks = _chunk_paragraphs(txt, max_chars=1100, overlap=120)
                for j, ch in enumerate(chunks):
                    numbers = _numbers_from_text(ch) or None

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
                        "fuente_fila": int(page_idx),
                        "org_unit": org_unit,
                        "titulo": title,
                        "page_from": page_idx + 1,
                        "page_to": page_idx + 1,
                        "numbers": numbers,
                        "texto": ch,
                    }
                    metadata = {k: v for k, v in metadata.items() if v is not None}
                    records.append({"texto": ch, "metadata": metadata})
            except Exception:
                continue

        try:
            doc.close()
        except Exception:
            pass

    return records
