import re
from dataclasses import dataclass
from typing import List

@dataclass
class IntentResult:
    intent: str
    ensure_domains: List[str]

# Palabras clave por intención (en minúsculas)
# Expandidas para cubrir variantes coloquiales argentinas y más sinónimos
KWS = {
    "saludo": [
        r"\bhola\b", r"\bholi\b", r"\bholis\b", r"\bholaa+\b",
        r"\bbuen\s*d[ií]a\b", r"\bbuenos\s*d[ií]as\b",
        r"\bbuenas\b", r"\bbuenas\s+tardes\b", r"\bbuenas\s+noches\b", 
        r"\bque\s+tal\b", r"\bq\s*tal\b", r"\bcomo\s+va\b", r"\bc[oó]mo\s+and[aá]s\b",
        r"\bey\b", r"\bhey\b", r"\bwenas\b",
    ],
    "montos": [
        # Aranceles y matrículas
        r"\b(arancel(?:es)?)\b", r"\bmatr[ií]cul[ao]s?\b", 
        r"\bcuota[s]?\b", r"\bmensual(?:es|idad(?:es)?)?\b",
        # Precios y costos
        r"\bvalor(?:es)?\b", r"\bprecio[s]?\b", r"\bcost[eo]s?\b", r"\bimporte[s]?\b",
        r"\btarifa[s]?\b", r"\bmonto[s]?\b",
        # Pagos
        r"\bplan(?:es)?\s+de\s+pago[s]?\b", r"\bpagar\b", r"\bpagos?\b",
        r"\bfinanciaci[oó]n\b", r"\bfinanciamien?to\b", r"\bcuotas\s+sin\s+inter[eé]s\b",
        # Preguntas de costo
        r"\bcu[aá]nt[ao]\s+sale\b", r"\bcu[aá]nt[ao]\s+cuesta\b", r"\bcu[aá]nt[ao]\s+vale\b",
        r"\bcu[aá]nt[ao]\s+es\b", r"\bcu[aá]l\s+es\s+el\s+(valor|precio|costo)\b",
        r"\bcuesta\b", r"\bvale\b", r"\bsale\b",
        # Coloquial argentino
        r"\bguita\b", r"\bplata\b", r"\bmanga\b", r"\bpesos\b", r"\bd[oó]lares\b",
        r"\bcu[aá]nto\s+hay\s+que\s+poner\b", r"\bqu[eé]\s+tan\s+caro\b",
    ],
    "fechas": [
        # Fechas y calendario
        r"\bfecha[s]?\b", r"\bcalendario\b", r"\bcronograma\b", r"\bagenda\b",
        # Inscripciones
        r"\binscripci[oó]n(?:es)?\b", r"\bpreinscripci[oó]n(?:es)?\b", r"\binscribir(?:me|se)?\b",
        r"\banota(?:r(?:me|se)?)?\b", r"\bmatricular(?:me|se)?\b",
        # Curso de ingreso
        r"\bcurso[s]?\s+de\s+ingreso\b", r"\bnivelaci[oó]n\b", r"\bpropede[uú]tico\b",
        # Inicio y periodos
        r"\binicio\b", r"\bempie[cz]a[n]?\b", r"\bcomien[cz]a[n]?\b", r"\barranca[n]?\b",
        r"\bcu[aá]ndo\b", r"\bper[ií]odo\b", r"\bsemestre\b", r"\bcuatrimestre\b",
        r"\ba[ñn]o\s+acad[eé]mico\b", r"\bciclo\s+lectivo\b",
        # Plazos
        r"\bplazo[s]?\b", r"\bvencimien?to\b", r"\bl[ií]mite\b", r"\bcierre\b",
        r"\bhasta\s+cu[aá]ndo\b", r"\b[uú]ltimo\s+d[ií]a\b",
    ],
    "requisitos": [
        # Requisitos y condiciones
        r"\brequisito[s]?\b", r"\bcondici[oó]n(?:es)?\b", r"\bexigencia[s]?\b",
        # Documentación
        r"\bdocumentaci[oó]n\b", r"\bdocumento[s]?\b", r"\bpapel(?:es)?\b", r"\bpapeleo\b",
        r"\btr[aá]mite[s]?\b", r"\bgestiones?\b",
        # Ingreso
        r"\bingreso\b", r"\bingresar\b", r"\bentrar\b", r"\bacceder\b",
        # Preguntas de necesidad
        r"\bqu[eé]\s+necesito\b", r"\bqu[eé]\s+tengo\s+que\b", r"\bqu[eé]\s+debo\b",
        r"\bqu[eé]\s+hace\s+falta\b", r"\bqu[eé]\s+piden\b", r"\bqu[eé]\s+me\s+piden\b",
        r"\bdebo\b", r"\bnecesito\b", r"\bhace\s+falta\b",
        # Requisitos académicos
        r"\bsecundario\b", r"\bt[ií]tulo\s+secundario\b", r"\banal[ií]tico\b",
        r"\bpromedio\b", r"\bnota[s]?\s+m[ií]nima\b",
    ],
    "reglamentos": [
        r"\breglamento[s]?\b", r"\bnorma(?:s|tiva)?\b", r"\bpol[ií]tica[s]?\b", 
        r"\bcondiciones\s+generales\b", r"\br[eé]gimen\b",
        r"\bestatuto[s]?\b", r"\bregulaci[oó]n(?:es)?\b", r"\bley(?:es)?\b",
        r"\bprohib(?:ido|ici[oó]n)\b", r"\bpermitido\b", r"\bautorizado\b",
        r"\bsancion(?:es)?\b", r"\bfalta[s]?\b", r"\bexpulsi[oó]n\b",
    ],
    "becas": [
        # Becas
        r"\bbeca[s]?\b", r"\bbecado\b", r"\bbecario\b",
        # Descuentos y ayudas
        r"\bdescuento[s]?\b", r"\brebaja[s]?\b", r"\bbeneficio[s]?\b", r"\bexenci[oó]n(?:es)?\b",
        r"\bayuda\s+econ[oó]mica\b", r"\bayuda\s+financiera\b", r"\bsubsidio[s]?\b",
        # Programas
        r"\bprogra?ma[s]?\s+de\s+becas\b", r"\bconvocatoria[s]?\s+de\s+becas?\b",
        # Coloquial
        r"\bpagar\s+menos\b", r"\bbonificaci[oó]n\b", r"\bpromo(?:ci[oó]n)?\b",
        r"\bhay\s+(alguna\s+)?ayuda\b", r"\bpuedo\s+acceder\s+a\s+(una\s+)?beca\b",
    ],
    "info_carrera": [
        # Perfil y descripción
        r"\bperfil(?:es)?\b", r"\bdescripci[oó]n\b", r"\bpresentaci[oó]n\b",
        r"\bqu[eé]\s+es\b", r"\bde\s+qu[eé]\s+(se\s+)?trata\b", r"\bqu[eé]\s+hace\b",
        r"\ben\s+qu[eé]\s+consiste\b", r"\bc[oó]mo\s+es\b",
        # Plan de estudios
        r"\bplan\s+de\s+estudio[s]?\b", r"\bcurr[ií]cul[ao]\b", r"\bmalla\s+curricular\b",
        r"\bmaterias?\b", r"\basignaturas?\b", r"\bcontenidos?\b",
        # Duración y título
        r"\bduraci[oó]n\b", r"\bcu[aá]nto\s+dura\b", r"\bcu[aá]ntos\s+a[ñn]os\b",
        r"\bt[ií]tulo[s]?\b", r"\bgrado\b", r"\bdiploma\b", r"\bcertificaci[oó]n\b",
        r"\bincumbencia[s]?\b", r"\balcance[s]?\b", r"\bhabilitaci[oó]n\b",
        # Salida laboral
        r"\bsalida[s]?\s+laboral(?:es)?\b", r"\bcampo\s+ocupacional\b", r"\bcampo\s+laboral\b",
        r"\bd[oó]nde\s+(se\s+)?trabaja\b", r"\bdonde\s+trabaja\b", 
        r"\b(en\s+)?qu[eé]\s+(lugar(?:es)?|[aá]mbito[s]?|campo[s]?|[aá]rea[s]?)\s+(se\s+)?trabaja\b",
        r"\b([aá]mbito|ambito)\s+laboral\b", r"\b(opciones|lugares)\s+de\s+trabajo\b",
        r"\bde\s+qu[eé]\s+(puedo\s+)?trabaja?r?\b", r"\blaburo\b", r"\blaburar\b",
        # Modalidad
        r"\bmodalidad(?:es)?\b", r"\bpresencial\b", r"\bvirtual\b", r"\bdistancia\b",
        r"\bh[ií]brido\b", r"\bonline\b", r"\bremoto\b",
        # Info general de carrera
        r"\binfo(?:rmaci[oó]n)?\s+(de|sobre)\b", r"\bcontame\s+(de|sobre)\b",
        r"\bdecime\s+(de|sobre)\b", r"\bexplicame\b",
    ],
    "handoff": [
        r"\b(hablar|charlar|comunicar(?:me)?)\s+con\s+(un[a]?\s+)?(humano|asesor|persona|alguien)\b",
        r"\b(tel[eé]fono|whatsapp|mail|correo|email)\b",
        r"\bcontacto\b", r"\bcomunicar(?:me|se)?\b", r"\bllamar\b",
        r"\batencion\s+(al\s+)?cliente\b", r"\bsoporte\b",
        r"\bno\s+entend[eé]s\b", r"\bno\s+me\s+sirve\b", r"\bquiero\s+hablar\b",
    ],
    # Nueva intención: comparaciones
    "comparar": [
        r"\bdiferencia[s]?\s+(entre|de)\b", r"\bcomparar\b", r"\bcomparaci[oó]n\b",
        r"\bvs\.?\b", r"\bversus\b", r"\bo\s+mejor\b",
        r"\bcu[aá]l\s+(es\s+)?mejor\b", r"\bqu[eé]\s+conviene\b", r"\bqu[eé]\s+me\s+recomend[aá]s\b",
    ],
}

# Mapeo intención -> dominios a asegurar
DOMAINS_BY_INTENT = {
    "saludo": [],
    "montos": ["aranceles"],
    "fechas": ["fechas"],
    "requisitos": ["carreras", "reglamentos"],
    "reglamentos": ["reglamentos"],
    "becas": ["becas"],
    "info_carrera": ["perfiles", "carreras"],
    "comparar": ["perfiles", "carreras", "aranceles"],
    # "handoff": []  # no fuerza retrieve
}

def detect_intent(text: str) -> IntentResult:
    t = (text or "").lower()
    word_count = len(t.split())
    
    # prioridad: handoff primero (si quiere humano, no enredar)
    for pat in KWS["handoff"]:
        if re.search(pat, t):
            return IntentResult(intent="handoff", ensure_domains=[])

    # Prioridad: primero otras intenciones (evitar que "hola" intercepte consultas reales)
    for intent, pats in KWS.items():
        if intent in ("saludo", "handoff"):
            continue
        if any(re.search(p, t) for p in pats):
            return IntentResult(intent=intent, ensure_domains=DOMAINS_BY_INTENT.get(intent, []))

    # saludos cortos: solo si no detectamos otras intenciones y el turno es breve
    if word_count <= 4:
        for pat in KWS["saludo"]:
            if re.search(pat, t):
                return IntentResult(intent="saludo", ensure_domains=[])

    # por defecto: general
    return IntentResult(intent="general", ensure_domains=[])
