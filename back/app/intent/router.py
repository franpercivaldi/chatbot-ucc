import re
from dataclasses import dataclass
from typing import List

@dataclass
class IntentResult:
    intent: str
    ensure_domains: List[str]

# Palabras clave por intención (en minúsculas)
KWS = {
    "montos": [
        r"\b(arancel(?:es)?)\b", r"\bmatr[ií]cul[ao]\b", r"\bcuota[s]?\b", r"\bmensual(?:idad)?\b",
        r"\bvalor(?:es)?\b", r"\bprecio[s]?\b", r"\bcost[eo]s?\b", r"\bimporte[s]?\b",
        r"\bplan(?:es)?\s+de\s+pago[s]?\b", r"\bpagar\b", r"\bpagos?\b",
    ],
    "fechas": [
        r"\bfecha[s]?\b", r"\bcalendario\b", r"\binscripci[oó]n(?:es)?\b", r"\bpreinscripci[oó]n\b",
        r"\bcurso[s]?\s+de\s+ingreso\b", r"\binicio\b", r"\bempieza[n]?\b", r"\bcomien[cz]a\b",
    ],
    "requisitos": [
        r"\brequisito[s]?\b", r"\bcondicion(?:es)?\b", r"\bdocumentaci[oó]n\b", r"\bpapel(es)?\b",
        r"\bingreso\b", r"\bqu[eé]\s+necesito\b", r"\bdebo\b",
    ],
    "reglamentos": [
        r"\breglamento[s]?\b", r"\bnorma[s]?\b", r"\bpol[ií]tica[s]?\b", r"\bcondiciones\s+generales\b",
    ],
    "becas": [
        r"\bbeca[s]?\b", r"\bdescuento[s]?\b", r"\bfinanciamien?to\b", r"\bayuda\s+econ[oó]mica\b",
        r"\bprogra?ma[s]?\s+de\s+becas\b",
    ],
    "info_carrera": [
        r"\bperfil\b", r"\bdescripci[oó]n\b", r"\bqu[eé]\s+hace\b", r"\bde\s+qu[eé]\s+trata\b",
        r"\bplan\s+de\s+estudio[s]?\b", r"\bduraci[oó]n\b", r"\bt[ií]tulo[s]?\b", r"\bincumbencia[s]?\b",
        r"\bsalida\s+laboral\b", r"\bcampo\s+ocupacional\b",
        r"\bd[oó]nde\s+trabaja\b", r"\bdonde\s+trabaja\b", r"\b(en\s+)?qu[eé]\s+(lugar(es)?|ambito[s]?|campo[s]?)\s+trabaja\b",
        r"\b(ambito|ámbito)\s+laboral\b", r"\b(opciones|lugares)\s+de\s+trabajo\b",
    ],
    "handoff": [
        r"\b(hablar|charlar|comunicar(me)?)\s+con\s+(un[a]?\s+)?(humano|asesor|persona)\b",
        r"\b(telefono|tel[eé]fono|whatsapp|mail|correo)\b",
    ],
}

# Mapeo intención -> dominios a asegurar
DOMAINS_BY_INTENT = {
    "montos": ["aranceles"],
    "fechas": ["fechas"],
    "requisitos": ["carreras", "reglamentos"],   # suelen vivir en carreras/reglamentos
    "reglamentos": ["reglamentos"],
    "becas": ["becas"],
    "info_carrera": ["perfiles", "carreras"],
    # "handoff": []  # no fuerza retrieve
}

def detect_intent(text: str) -> IntentResult:
    t = (text or "").lower()
    # prioridad: handoff primero (si quiere humano, no enredar)
    for pat in KWS["handoff"]:
        if re.search(pat, t):
            return IntentResult(intent="handoff", ensure_domains=[])

    for intent, pats in KWS.items():
        if intent == "handoff":
            continue
        if any(re.search(p, t) for p in pats):
            return IntentResult(intent=intent, ensure_domains=DOMAINS_BY_INTENT.get(intent, []))

    # por defecto: general
    return IntentResult(intent="general", ensure_domains=[])
