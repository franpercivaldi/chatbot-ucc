# back/app/ingest/validate.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import re, json, time

# dominios y requisitos mínimos (por header canónico o alias)
REQ_BY_DOMAIN = {
    "carreras": [
        ("identificador_carrera", ["identificador_carrera","id_carrera","codigo_carrera","cod_carrera"]),
        ("carrera", ["carrera","alias","nombre","nombre_carrera","programa"])
    ],
    "aranceles": [
        ("carrera", ["carrera","alias","nombre"]),
        # al menos una de las cifras:
        ("any_monto", ["matricula_general","matricula_ingresante","arancel_mensual","arancel_total",
                       "mensual","cuota","total","matricula","inscripcion","inscripción"])
    ],
    "oferta": [
        ("titulo", ["titulo","título","alias","nombre"]),
        ("periodo", ["periodo","anio_ingreso","año_ingreso","cohorte","año","anio"])
    ],
    "becas": [
        ("titulo", ["titulo","título","programa","nombre"]),
    ],
    "fechas": [
        ("periodo", ["periodo","anio","año","vigencia"])
    ],
}

MONEY_RX = re.compile(r"\$?\s*\d{1,3}(\.\d{3})*(,\d{2})?$")

@dataclass
class Problem:
    level: str         # "error" | "warn" | "info"
    code: str
    msg: str
    row: Optional[int] = None
    col: Optional[str] = None
    sample: Optional[str] = None

@dataclass
class FileReport:
    bot_id: str
    file: str
    sheet: str
    domain: str
    rows: int
    problems: List[Problem]

    def to_dict(self):
        return {
            "bot_id": self.bot_id,
            "file": self.file,
            "sheet": self.sheet,
            "domain": self.domain,
            "rows": self.rows,
            "problems": [asdict(p) for p in self.problems],
        }

def _has_any_col(cols: List[str], aliases: List[str]) -> bool:
    got = set(cols)
    return any(a in got for a in aliases)

def _first_present(cols: List[str], aliases: List[str]) -> Optional[str]:
    for a in aliases:
        if a in cols:
            return a
    return None

def validate_dataframe(*, bot_id: str, file: str, sheet: str, domain: str, df: pd.DataFrame) -> FileReport:
    problems: List[Problem] = []
    cols = [c for c in df.columns]

    # 1) requisitos mínimos por dominio
    reqs = REQ_BY_DOMAIN.get(domain, [])
    for canonical, aliases in reqs:
        if canonical == "any_monto":
            if not any(a in cols for a in aliases):
                problems.append(Problem("error","missing_money_cols",
                    f"No se encontró ninguna columna de montos entre: {aliases}"))
        else:
            if not _has_any_col(cols, aliases):
                problems.append(Problem("warn","missing_required",
                    f"Falta columna requerida para {canonical}. Aliases aceptados: {aliases}"))

    # 2) chequeos fila a fila (muestras)
    sample_rows = min(len(df), 200)
    money_cols = [c for c in cols if any(k in c for k in ["matric","arancel","mensual","total","cuota","inscrip"])]
    periodo_cols = [c for c in cols if c in ["periodo","anio","año","anio_ingreso","año_ingreso","cohorte","vigencia"]]

    for i in range(sample_rows):
        row = df.iloc[i]
        # a) montos con formato raro
        for mc in money_cols:
            sval = str(row.get(mc,"")).strip()
            if not sval:
                continue
            if not MONEY_RX.match(sval):
                # permitimos que haya valores “otros” pero avisamos
                problems.append(Problem("warn","money_format_suspect",
                    f"Formato de dinero sospechoso en {mc}", row=i, col=mc, sample=sval))
        # b) periodo ausente total
        if domain in ("carreras","oferta","fechas"):
            if periodo_cols and all(str(row.get(pc,"")).strip()=="" for pc in periodo_cols):
                problems.append(Problem("info","no_periodo_row",
                    "Fila sin periodo detectable", row=i))

    # 3) filas totalmente vacías
    empty_rows = int(df.isna().all(axis=1).sum())
    if empty_rows:
        problems.append(Problem("info","empty_rows","Filas vacías detectadas", sample=str(empty_rows)))

    return FileReport(
        bot_id=bot_id, file=file, sheet=sheet, domain=domain, rows=len(df), problems=problems
    )

def save_reports_jsonl(path: str, reports: List[FileReport]) -> None:
    recs = []
    now = int(time.time())
    for r in reports:
        d = r.to_dict()
        d["ts"] = now
        recs.append(d)
    with open(path, "a", encoding="utf-8") as f:
        for d in recs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
