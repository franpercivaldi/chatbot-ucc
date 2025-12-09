from typing import Dict, List, Any, Optional
import pandas as pd
import os, re, glob, unicodedata, json
from datetime import datetime
from .schema import (
    SCHEMA_VERSION, slugify, hash_str, make_doc_id, make_chunk_id,
    parse_money_to_float, now_iso_utc
)

# Heurísticas por nombre de archivo/hoja
TYPE_PATTERNS = [
    (r"beca|becas", "becas"),
    (r"arancel|aranceles|cuota|matr[ií]cula", "aranceles"),
    (r"fecha|calendario|inscrip", "fechas"),
    (r"reglamento|norma|condici[oó]n|pol[ií]tica", "reglamentos"),
    (r"oferta|ofertas?-carreras?", "oferta"),
    (r"carrera|datos_carreras|plan|materias", "carreras"),
    (r"faq|preguntas|respuestas", "faq"),
]

DEFAULT_ALIASES = {
    "facultad": ["facultad", "unidad_academica", "escuela", "departamento", "area_estudio", "área", "area"],
    "carrera": ["carrera", "programa", "plan", "nombre_carrera"],
    "modalidad": ["modalidad", "cursado", "régimen", "regimen", "presencialidad", "tipo_cursado"],
    "periodo": ["periodo", "periodo_academico", "anio", "año", "anio_ingreso", "año_ingreso", "cohorte", "year", "vigencia", "año_lectivo"],
    "titulo": ["titulo", "título", "alias", "nombre", "nombre_programa"],
    "carrera_id": ["identificador_carrera", "id_carrera", "codigo_carrera", "cod_carrera"],
}

# Keywords para detectar columnas de montos
MONEY_COL_KWS = [
    "matric", "arancel", "cuota", "mensual", "total", "inscrip", "inscripción", "inscripcion",
    "pago", "importe", "precio", "valor", "costo", "coste"
]

# Aliases por campo "canónico"
NUM_ALIASES = {
    "matricula_general":   ["matricula_general", "matricula", "matricula_gral", "matricula total", "matricula_unica", "matricula comun", "inscripcion", "inscripción"],
    "matricula_ingresante":["matricula_ingresante", "matricula nuevo", "matricula primer ingreso"],
    "arancel_mensual":     ["arancel_mensual", "mensual", "cuota_mensual", "importe_mensual", "precio_mensual", "valor_mensual"],
    "arancel_total":       ["arancel_total", "total", "importe_total", "precio_total", "valor_total"]
}

# helpers
def _primary_key_for_row(domain: str, carrera_id: str, periodo: str, i: int, titulo: str) -> str:
    """
    Devuelve una clave estable para construir el chunk_id.
    Prioridad: carrera_id (+ periodo) > titulo (+ periodo) > índice de fila.
    """
    p = str(periodo or "all").strip()
    if carrera_id:
        return f"{domain}:{carrera_id}:{p}"
    if titulo:
        return f"{domain}:{slugify(titulo)}:{p}"
    return f"{domain}:row-{i}:{p}"

def _domain_from_name_and_cols(fname: str, sheet_name: str, df: Optional[pd.DataFrame]) -> str:
    d = guess_domain(fname, sheet_name, df)
    # Ajustes finos: si trae columnas de arancel → aranceles; si trae IDENTIFICADOR → carreras
    if df is not None:
        cols = set(df.columns)
        if {"matricula_general","matricula_ingresante","arancel_mensual","arancel_total"} & cols:
            d = "aranceles"
        elif {"identificador_carrera","carrera"} & cols and d not in {"aranceles","becas"}:
            # "datos_carreras_ofertas.csv" la tratamos como "carreras"
            d = "carreras"
    return d


def guess_domain(file_name: str, sheet_name: str, df: Optional[pd.DataFrame] = None) -> str:
    base = f"{file_name.lower()} {sheet_name.lower()}"
    for pat, dom in TYPE_PATTERNS:
        if re.search(pat, base):
            return dom
    # Hint por columnas
    if df is not None:
        cols = " ".join(df.columns).lower()
        if re.search(r"arancel|matricula|cuota", cols):
            return "aranceles"
        if re.search(r"beca|cobertura", cols):
            return "becas"
        if re.search(r"identificador_carrera|carrera", cols):
            return "carreras"
    return "general"

def list_data_files(xlsx_dir: str) -> List[str]:
    patterns = ["*.xlsx","*.XLSX","*.xls","*.XLS","*.csv","*.CSV","*.tsv","*.TSV","*.txt","*.TXT","*.json","*.JSON"]
    files: List[str] = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(xlsx_dir, p)))
    return sorted(set(os.path.basename(f) for f in files))

def process_json_file(path: str, bot_id: str) -> List[Dict[str, Any]]:
    """
    Procesa archivos JSON específicos (como datos_generales_carreras.json).
    Estructura esperada: Lista de objetos con "unidad" y "carreras".
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] No pude leer JSON {path}: {e}")
        return []

    records = []
    # Si es una lista, iteramos. Si es dict, lo envolvemos.
    items = data if isinstance(data, list) else [data]

    for item in items:
        # Caso específico: datos_generales_carreras.json tiene "unidad" y "carreras"
        unidad = str(item.get("unidad") or "")
        carreras = item.get("carreras", [])
        
        if not isinstance(carreras, list):
            continue

        for car in carreras:
            if not isinstance(car, dict):
                continue
            
            # Extracción de metadatos
            # 1. Carrera ID
            carrera_id = str(car.get("codigoSiucc") or car.get("carrera") or "")
            
            # 2. Nombre Carrera (buscar en datos_especiales o usar slug)
            nombre_carrera = ""
            datos_especiales = car.get("datos_especiales", [])
            
            # Construcción del texto y búsqueda de nombre
            text_parts = []
            
            # Agregar info base si existe
            if unidad:
                text_parts.append(f"UNIDAD ACADÉMICA: {unidad}")
            
            # Agregar palabras clave al texto para mejorar retrieval
            kws = str(car.get("palabras_clave") or "").strip()
            if kws:
                text_parts.append(f"PALABRAS CLAVE: {kws}")

            for de in datos_especiales:
                titulo = str(de.get("titulo") or "").strip()
                contenido = str(de.get("contenido") or "").strip()
                
                if not titulo or not contenido:
                    continue
                
                # Detectar nombre carrera
                if "nombre de la carrera" in titulo.lower():
                    nombre_carrera = contenido
                
                text_parts.append(f"{titulo.upper()}: {contenido}")
            
            # Fallback nombre carrera
            if not nombre_carrera:
                nombre_carrera = str(car.get("carrera") or "Desconocida")

            # 3. Periodo (General por defecto para info estática)
            periodo = "general"

            # 4. Domain (Usamos 'perfiles' para diferenciar de CSVs administrativos)
            domain = "perfiles"
            
            # Slug de carrera para facilitar búsqueda
            # Usamos una lista para incluir tanto el slug del nombre completo como el código corto (ej. "indumentaria-alta-moda")
            slugs = [slugify(nombre_carrera)]
            short_code = str(car.get("carrera") or "").strip()
            if short_code and short_code not in slugs:
                slugs.append(short_code)
            
            carrera_slug = slugs

            # Construcción del record
            full_text = " | ".join(text_parts)
            
            # ID determinístico
            doc_id = make_doc_id(path, "json")
            # Usamos carrera_id como clave primaria si existe
            primary_key = f"{domain}:{carrera_id}:{periodo}"
            chunk_id = make_chunk_id(doc_id, primary_key)

            # Guardamos el texto también en el payload para que Qdrant lo devuelva.
            # Sin esto, los perfiles aparecían en la búsqueda pero llegaban con texto vacío.
            meta = {
                "schema_version": SCHEMA_VERSION,
                "domain": domain,
                "tipo": domain,
                "doc_id": doc_id,
                "carrera": nombre_carrera,
                "carrera_slug": carrera_slug,  # Agregamos slug explícito
                "carrera_id": carrera_id,
                "periodo": periodo,
                "facultad": unidad,
                "bot_id": bot_id,
                "chunk_id": chunk_id,
                "source_file": os.path.basename(path),
                "fuente_archivo": os.path.basename(path), # Para debug consistente
                "texto": full_text,
                "timestamp": now_iso_utc()
            }

            records.append({
                "texto": full_text,
                "metadata": meta
            })
            
    return records

def _read_any(path: str) -> Dict[str, pd.DataFrame]:
    low = path.lower()
    if low.endswith((".csv", ".txt")):
        import csv
        encodings = ["utf-8","utf-8-sig","latin-1"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    sample = f.read(4096)
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                sep = dialect.delimiter or ","
                return {"CSV": pd.read_csv(path, encoding=enc, sep=sep)}
            except Exception:
                continue
        return {"CSV": pd.read_csv(path, encoding="utf-8", sep=",", on_bad_lines="skip")}
    if low.endswith((".tsv",)):
        return {"TSV": pd.read_csv(path, sep="\t")}
    xls = pd.ExcelFile(path)
    return {sheet: xls.parse(sheet_name=sheet) for sheet in xls.sheet_names}

def _load_schema_map(xlsx_dir: str) -> Dict[str, Any]:
    cfg = {"aliases": {}, "defaults": {}}
    p = os.path.join(xlsx_dir, "_schema_map.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                user = json.load(f)
            cfg["aliases"] = user.get("aliases", {})
            cfg["defaults"] = user.get("defaults", {})
        except Exception:
            pass
    return cfg

def _merge_aliases(user_aliases: Dict[str, List[str]]) -> Dict[str, List[str]]:
    aliases = {k: list(v) for k, v in DEFAULT_ALIASES.items()}
    for k, lst in user_aliases.items():
        k2 = slugify(k)
        aliases.setdefault(k2, [])
        aliases[k2].extend(slugify(x) for x in lst)
        aliases[k2] = sorted(set(aliases[k2]))
    return aliases

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [slugify(c) for c in df.columns]
    return df

def _first_nonempty(row: pd.Series, cols: List[str]) -> Optional[str]:
    for c in cols:
        if c in row and str(row[c]).strip():
            return str(row[c]).strip()
    return None

def _guess_periodo_from_text(text: str) -> Optional[str]:
    m = re.search(r"(19|20)\d{2}", text)
    return m.group(0) if m else None

def row_to_text(row: pd.Series) -> str:
    parts = []
    for col, val in row.items():
        sval = "" if pd.isna(val) else str(val).strip()
        if not sval:
            continue
        parts.append(f"{col.upper()}: {sval}")
    return " | ".join(parts)

def load_xlsx_dir(xlsx_dir: str, *, bot_id: str = "public-admisiones") -> List[Dict[str, Any]]:
    cfg = _load_schema_map(xlsx_dir)
    aliases = _merge_aliases(cfg.get("aliases", {}))
    defaults = { slugify(k): str(v) for k, v in cfg.get("defaults", {}).items() }

    records: List[Dict[str, Any]] = []
    for fname in list_data_files(xlsx_dir):
        path = os.path.join(xlsx_dir, fname)
        
        if fname.lower().endswith(".json"):
            records.extend(process_json_file(path, bot_id))
            continue

        try:
            sheets = _read_any(path)
        except Exception as e:
            print(f"[WARN] No pude abrir {fname}: {e}")
            continue

        for sheet_name, df in sheets.items():
            if df is None or df.empty:
                continue
            df = normalize_columns(df).dropna(how="all").fillna("")
            domain = _domain_from_name_and_cols(fname, sheet_name, df)
            doc_id = make_doc_id(path, sheet_name)

            # candidatos por campo canónico
            cand = {
                "facultad": aliases["facultad"],
                "carrera": aliases["carrera"],
                "modalidad": aliases["modalidad"],
                "periodo": aliases["periodo"],
                "titulo": aliases["titulo"],
                "carrera_id": aliases["carrera_id"],
            }

            for i, row in df.iterrows():
                texto = row_to_text(row)
                if not texto:
                    continue

                # Normalización por fila (acceso case-insensitive)
                norm = {k: ("" if pd.isna(row[k]) else str(row[k]).strip()) for k in row.index}
                def get(*keys):
                    for k in keys:
                        kk = slugify(k)
                        # ya normalizaste columnas con normalize_columns -> están slugificadas
                        if kk in norm and norm[kk]:
                            return norm[kk]
                    return None

                # ---------- Título ----------
                # Preferimos 'titulo' canónico; si no, primera columna con texto
                titulo = _first_nonempty(row, cand["titulo"]) or defaults.get("titulo")
                if not titulo:
                    for c in row.index:
                        if str(row[c]).strip():
                            titulo = str(row[c]).strip()
                            break
                titulo = titulo or domain

                # ---------- Campos base ----------
                facultad  = _first_nonempty(row, cand["facultad"])  or defaults.get("facultad")
                modalidad = _first_nonempty(row, cand["modalidad"]) or defaults.get("modalidad") or "general"

                # Período: si no viene explícito, intenta del texto / nombre del archivo
                periodo = _first_nonempty(row, cand["periodo"]) or defaults.get("periodo")
                if not periodo:
                    periodo = _guess_periodo_from_text(texto) or _guess_periodo_from_text(fname) or "general"

                # ---------- Carrera & Carrera ID (clave del fix) ----------
                # Regla: en 'carreras' u 'oferta' usar CARRERA; si no hay, usar ALIAS (nombre público).
                #       en 'aranceles' también intentamos CARRERA y luego ALIAS.
                carrera_id = _first_nonempty(row, cand["carrera_id"]) or ""
                if domain in ("carreras", "oferta"):
                    carrera = get("carrera") or get("alias")  # primero CARRERA, luego ALIAS
                elif domain == "aranceles":
                    carrera = get("carrera") or get("alias")
                else:
                    carrera = _first_nonempty(row, cand["carrera"]) or get("alias")

                # ¡Importante!: si no hay nombre de carrera, NO pongas "general"
                carrera = carrera if carrera and carrera.strip() else None

                # ---------- IDs determinísticos ----------
                primary_key = _primary_key_for_row(domain, (carrera_id or "").strip(), str(periodo), i, titulo)
                chunk_id = make_chunk_id(doc_id, primary_key)
                row_hash = hash_str(texto)

                # ---------- Slugs ----------
                carrera_slug = slugify(carrera) if carrera else None
                facultad_slug = slugify(facultad) if facultad else None

                # ---------- Números (aranceles) ----------
                numbers: Dict[str, Any] = {}

                # 0) Mapa "columna -> valor string" ya normalizado
                #    (tenemos 'norm' arriba con columnas slugificadas)
                # 1) Intenta por aliases canónicos
                def _fill_if_present(target_key: str, alias_list: list[str]):
                    for a in alias_list:
                        if a in norm and norm[a]:
                            val = parse_money_to_float(norm[a])
                            if val is not None:
                                numbers[target_key] = float(val)
                                return True
                    return False

                _fill_if_present("matricula_general",    NUM_ALIASES["matricula_general"])
                _fill_if_present("matricula_ingresante", NUM_ALIASES["matricula_ingresante"])
                _fill_if_present("arancel_mensual",      NUM_ALIASES["arancel_mensual"])
                _fill_if_present("arancel_total",        NUM_ALIASES["arancel_total"])

                # 2) Si sigue vacío, heurística: cualquier columna con KW de dinero
                if not numbers:
                    for col, sval in norm.items():
                        if not sval:
                            continue
                        if any(kw in col for kw in MONEY_COL_KWS):
                            val = parse_money_to_float(sval)
                            if val is not None:
                                # mapeo heurístico del nombre
                                if "mensual" in col or "cuota" in col:
                                    numbers.setdefault("arancel_mensual", float(val))
                                elif "total" in col:
                                    numbers.setdefault("arancel_total", float(val))
                                elif "matric" in col or "inscrip" in col:
                                    numbers.setdefault("matricula_general", float(val))
                                else:
                                    # guarda como "otra_cifra_*" por si acaso
                                    numbers.setdefault(f"otra_cifra_{col[:18]}", float(val))

                # 3) Cuotas y flags
                if "cant_cuotas_plan_pagos" in norm and norm["cant_cuotas_plan_pagos"]:
                    try:
                        numbers["cant_cuotas_plan_pagos"] = int(str(norm["cant_cuotas_plan_pagos"]).strip() or "0")
                    except Exception:
                        pass

                if "tiene_plan_pagos" in norm and norm["tiene_plan_pagos"]:
                    v = norm["tiene_plan_pagos"].strip().lower()
                    numbers["tiene_plan_pagos"] = v in ("s","si","sí","true","1","y","yes")

                # 4) Derivación (después de parsear)
                if domain == "aranceles":
                    mensual = numbers.get("arancel_mensual")
                    cuotas = numbers.get("cant_cuotas_plan_pagos") or 0
                    total = numbers.get("arancel_total")
                    if mensual and cuotas and not total:
                        numbers["arancel_total_estimado"] = round(float(mensual) * float(cuotas), 2)


                # ---------- Proveniencia y extras ----------
                extras = {}
                for c in row.index:
                    v = str(row[c]).strip()
                    if v:
                        extras[slugify(c)] = v  # guarda claves normalizadas

                metadata = {
                    "schema_version": SCHEMA_VERSION,
                    "bot_id": bot_id,
                    "domain": domain,
                    "tipo": domain,  # compat retro
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "row_hash": row_hash,
                    "inserted_at": now_iso_utc(),
                    "source_path": os.path.normpath(path),
                    "fuente_archivo": fname,
                    "fuente_hoja": sheet_name,
                    "fuente_fila": int(i),

                    # canónicos
                    "titulo": titulo,
                    "facultad": facultad,
                    "modalidad": modalidad,
                    "periodo": str(periodo),

                    # unión / lookup
                    "carrera": carrera,               # ← ahora correcto (None si no hay)
                    "carrera_id": carrera_id,         # ← si existe
                    "carrera_slug": carrera_slug,     # ← solo si hay carrera
                    "facultad_slug": facultad_slug,

                    # auxiliares
                    "numbers": numbers if numbers else None,
                    "extras": extras,
                    "texto": texto,
                }
                # limpiar None
                metadata = {k: v for k, v in metadata.items() if v is not None}

                records.append({"texto": texto, "metadata": metadata})

    return records
