"""Detector: estructura de anuncio comercial publicado en grupos.

Patrón típico de spam laboral / cripto / promo:
  🚧 ¡Trabaja en Construcción en España! 🇪🇸
  💶 Sueldo: 2.000€ – 3.700€ al mes
  📋 Contrato legal y trabajo estable
  📩 ¡Postúlate ahora! https://t.me/...

Características que un usuario humano normal NO combina:
  - Múltiples líneas que empiezan con emoji (anuncio formateado/copiado).
  - Promesa monetaria explícita (cifras + €/EUR/USD/$).
  - Call-to-action publicitario (postúlate, contáctanos, escríbeme).
  - Enlace t.me/... o externo al final.
  - Vocabulario de oferta (vacante, sueldo, contrato).

Score se suma por señales acumuladas. Una sola señal NO basta. El umbral
mínimo (60) garantiza que un user normal hablando de su sueldo o de un
trabajo NO dispara, porque le faltan estructura+CTA+link.
"""
from __future__ import annotations

import re
import unicodedata

from telegram import Message

from . import Hit
from ..wordlists import load_and_compile

# Líneas que empiezan con emoji o pictograma
_EMOJI_LINE_RE = re.compile(
    r'^\s*[\U0001F300-\U0001FAFF☀-➿⬀-⯿\U0001F100-\U0001F2FF]',
    re.MULTILINE,
)
# Cifras con símbolo de moneda (cualquier importe)
_MONEY_RE = re.compile(
    r'\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*[€$]|'
    r'\b\d{2,}\s*(?:€|EUR|USD|\$|d[oó]lares|euros)\b',
    re.IGNORECASE,
)
# Cifras con periodicidad temporal — patrón típico de oferta laboral spam
# Ej: "2.800 € al mes", "500€ semanales", "3000 dólares por mes"
_PERIODIC_MONEY_RE = re.compile(
    r'\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\s*'
    r'(?:€|\$|EUR|USD|euros|d[oó]lares)\s*'
    r'(?:al?\s+mes|por\s+mes|/?\s*mes(?:es)?|mensual(?:es)?|'
    r'al?\s+semana|por\s+semana|/?\s*semana|semanal(?:es)?|'
    r'al\s+a[ñn]o|anual(?:es)?)\b',
    re.IGNORECASE,
)
# Call-to-action publicitario
_CTA_RE = re.compile(
    r'\b(post[uú]late|cont[aá]ctan?os?|cont[aá]ctame|inscr[ií]bete|'
    r'env[ií]a\s*(tu\s*)?(cv|curr[ií]culum|mensaje)|'
    r'haz\s+click|click\s+(en|aqu[ií])|escr[ií]beme|escr[ií]benos|'
    r'interesados?\s+(escribir|contactar)|'
    r'm[aá]s\s+info(rmaci[oó]n)?\s+(por|en|v[ií]a)\s+(dm|md|privado|wsp|whatsapp)|'
    r'env[ií]ame?\s+(un\s+)?(mensaje|dm|md|privado))',
    re.IGNORECASE,
)
# Vocabulario de oferta de trabajo / reclutamiento (lado del que OFRECE empleo,
# que es el patrón spam; NO el de quien busca trabajo y pregunta sin enlace).
# Caso real: "Si estás buscando trabajo... oportunidades de empleo disponibles".
_WORK_RE = re.compile(
    r'\b(vacantes?|puestos?\s+disponibles?|sueldo|salario|'
    r'contrato\s+(legal|estable|indefinido)|trabajo\s+(estable|legal|garantizado)|'
    r'oportunidad(?:es)?\s+(?:laboral(?:es)?|de\s+(?:empleo|trabajo|negocio))|'
    r'ofertas?\s+de\s+(?:empleo|trabajo)|empleos?\s+disponibles?|'
    r'(?:trabaja|trabajo|ingresos?|gana[rs]?|dinero)\s+desde\s+(?:casa|tu\s+m[oó]vil)|'
    r'gana[rs]?\s+(?:dinero|hasta\s+\d)|ingresos?\s+(?:extra|adicionales|garantizados)|'
    r'estamos\s+contratando|se\s+(?:busca|necesita[n]?)\s+(?:personal|empleados?|gente|colaboradores)|'
    r'trabajo\s+que\s+m[aá]s\s+te\s+interese|si\s+est[aá]s\s+buscando\s+(?:trabajo|empleo))\b',
    re.IGNORECASE,
)
# URL externa (http/https) que NO sea t.me — enlaces a webs de "empleo"/scam.
_EXTERNAL_URL_RE = re.compile(r'https?://(?!t\.me/|telegram\.me/)\S+', re.IGNORECASE)
# Trabajo doméstico / búsqueda de persona — patrón scam "cuidar casa/mascota/niños"
_DOMESTIC_OFFER_RE = re.compile(
    r'\b(cuidar|atender|alimentar|pasear|limpiar)\b[^.\n]{0,50}'
    r'\b(casa|hogar|mascota|perro|gato|ni[ñn]o|familia|jardín|piso|apartamento)\b'
    r'|'
    r'\bbusc[ao]\s+(?:a\s+)?(?:una?\s+)?'
    r'(persona|alguien|cuidador(?:a)?|ni[ñn]era|emplead[ao]|se[ñn]ora|'
    r'chica|chico|joven)\s+(?:responsable|seria|de\s+confianza|para)\b',
    re.IGNORECASE,
)
# Sentido de urgencia — palabras GRITADAS típicas de scam
_URGENCY_RE = re.compile(
    r'(?:¡\s*)?\b(URGENTE|INMEDIAT[OA]|EMPEZAR\s+YA|HOY\s+MISMO|R[AÁ]PIDO|YA\s*!)\b',
    re.IGNORECASE,
)
# Servicios ILEGALES / scam: hacking, acceso a cuentas, espionaje, recuperación
# de dinero. Caso real: "SERVICIOS PROFESIONALES DE HACKING".
# Editable en config/blacklist/commercial_illegal_services.txt (estos son los
# defaults de fallback si el archivo no existe).
_DEFAULT_ILLEGAL_SERVICES = [
    r"hacking", r"hacke[oa]r?", r"hacker", r"cracke[oa]r?",
    r"extracci[oó]n\s+de\s+(?:fotos|videos|datos|informaci[oó]n)",
    r"acceso\s+a\s+(?:redes\s+sociales|instagram|tiktok|whatsapp|facebook|cuentas?)",
    r"recuperaci[oó]n\s+de\s+(?:dinero|fondos|cuenta|contrase[ñn]a)",
    r"espia(?:r|je)", r"rastrear?\s+(?:tel[eé]fono|m[oó]vil|persona)",
    r"servicios?\s+an[oó]nimos?", r"clientes?\s+serios?",
    r"clonar?\s+(?:whatsapp|tarjeta|sim)",
    r"informaci[oó]n\s+(?:personal|privada)\s+de",
]
_ILLEGAL_SERVICES_RE = load_and_compile(
    "commercial_illegal_services.txt", _DEFAULT_ILLEGAL_SERVICES,
)


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    text = (msg.text or msg.caption or "").strip()
    # NFC: unifica acentos (combining vs precompuesto) para que los regex con
    # tildes (extracci[oó]n, an[oó]nimos) casen sea cual sea la forma unicode.
    text = unicodedata.normalize("NFC", text)
    if not text or len(text) < 40:
        return Hit.none()

    emoji_lines = len(_EMOJI_LINE_RE.findall(text))
    has_periodic_money = bool(_PERIODIC_MONEY_RE.search(text))
    has_money = bool(_MONEY_RE.search(text))
    has_cta = bool(_CTA_RE.search(text))
    has_work = bool(_WORK_RE.search(text))
    has_tg_link = "t.me/" in text.lower() or "telegram.me/" in text.lower()
    has_external_url = bool(_EXTERNAL_URL_RE.search(text))
    has_domestic = bool(_DOMESTIC_OFFER_RE.search(text))
    has_urgency = bool(_URGENCY_RE.search(text))
    illegal = _ILLEGAL_SERVICES_RE.findall(text)
    n_illegal = len(set(m.lower() for m in illegal))

    score = 0
    reasons: list[str] = []
    # Servicios ilegales/scam: señal MUY fuerte. 1 keyword = 35, 2+ = 55.
    if n_illegal >= 2:
        score += 55
        reasons.append(f"servicios ilegales/scam ({n_illegal} señales: hacking/acceso cuentas/etc.)")
    elif n_illegal == 1:
        score += 35
        reasons.append("vocabulario de servicios ilegales/scam")
    if emoji_lines >= 3:
        score += 30
        reasons.append(f"{emoji_lines} líneas con emoji header (anuncio formateado)")
    elif emoji_lines >= 2:
        score += 15
        reasons.append("varias líneas con emoji header")
    # Periodic money pesa más que money simple (oferta laboral típica scam)
    if has_periodic_money:
        score += 25
        reasons.append("cifra € + periodicidad (al mes/semanal/...)")
    elif has_money:
        score += 20
        reasons.append("promesa monetaria explícita")
    if has_cta:
        score += 20
        reasons.append("call-to-action publicitario")
    if has_work:
        score += 15
        reasons.append("vocabulario de oferta laboral")
    if has_tg_link:
        score += 20
        reasons.append("enlace t.me/")
    elif has_external_url:
        # Enlace web SOLO (sin más señales) NO debe banear: un usuario fiable
        # puede compartir una web en su primer mensaje. Pesa poco por sí mismo.
        score += 15
        reasons.append("enlace web externo")
    # COMBO clave del job-spam: lenguaje de oferta de empleo + un enlace. Esto sí
    # es el patrón inequívoco (reclutamiento + link), aunque el perfil parezca
    # fiable (foto antigua, etc.). Caso real: empleo.vertexgloball.com.
    if has_work and (has_tg_link or has_external_url):
        score += 35
        reasons.append("oferta de empleo + enlace (patrón de job-spam)")
    if has_domestic:
        score += 20
        reasons.append("oferta doméstica / búsqueda de persona")
    if has_urgency:
        score += 10
        reasons.append("urgencia gritada (URGENTE, INMEDIATO, etc.)")

    if is_first_msg and score > 0:
        score += 15
        reasons.append("primer mensaje del user")

    # Umbral mínimo: una sola señal NO basta. Se requieren al menos 2-3 combinadas.
    if score < 60:
        return Hit.none()

    return Hit(
        rule="commercial_ad",
        score=score,
        reason="Anuncio comercial: " + " + ".join(reasons),
        payload={
            "emoji_lines": emoji_lines,
            "has_money": has_money,
            "has_periodic_money": has_periodic_money,
            "has_cta": has_cta,
            "has_work": has_work,
            "has_tg_link": has_tg_link,
            "has_external_url": has_external_url,
            "has_domestic": has_domestic,
            "has_urgency": has_urgency,
            "score": score,
        },
    )
