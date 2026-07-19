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

from ..i18n import t
from ..wordlists import load_and_compile
from . import Hit

# Líneas que empiezan con emoji o pictograma
_EMOJI_LINE_RE = re.compile(
    r'^\s*[\U0001F300-\U0001FAFF☀-➿⬀-⯿\U0001F100-\U0001F2FF]',
    re.MULTILINE,
)
# Cifras con símbolo de moneda (cualquier importe).
# El símbolo va DETRÁS en español (500€) y DELANTE en inglés ($500). Se aceptan
# las dos formas: con solo la española, un "Earn $500/day" en un grupo en inglés
# no sumaba señal de dinero y el anuncio se colaba.
# Editable en config/blacklist/commercial_money.txt (defaults de fallback abajo)
# para que un grupo argentino, brasileño o polaco pueda añadir SU moneda.
#
# boundaries=False: casi todos estos patrones empiezan o acaban en un símbolo
# (€, $, R$, S/) y `\b` nunca casa junto a un símbolo, así que envolverlos en
# `\b(?:...)\b` dejaría la lista entera muerta. Cada patrón lleva sus anclajes.
_DEFAULT_MONEY = [
    r"\b\d[\d.,\u00a0\u202f']*\s*[€$£¥₽₴₹₺₩₪₦₱₲₵฿]",
    r"\b\d+(?:[.,]\d+)*\s*(?:EUR|USD|USDT|USDC|d[oó]lares|euros)\b",
    r"[€$£¥₽₴₹₺₩₪₦₱₲₵฿]\s*\d[\d.,]*(?:\s*[kK])?",
    # Códigos ISO en MAYÚSCULAS obligatorias — (?-i:...) apaga el ignore-case
    # solo ahí: en minúscula muchos son palabras normales ("10 try again",
    # "2 cup of flour"). Y siempre pegados a una cifra.
    r"\b\d+(?:[.,]\d+)*\s*(?-i:ARS|MXN|COP|CLP|UYU|PEN|BOB|PYG|VES|GTQ|HNL|NIO"
    r"|CRC|DOP|CUP|BRL|CHF|GBP|CAD|AUD|PLN|CZK|SEK|NOK|DKK|HUF|RON|BGN|TRY|RUB"
    r"|UAH|INR|JPY|CNY|KRW|ZAR)\b",
    r"(?-i:R\$)\s*\d[\d.,]*",
    r"(?-i:S/)\s*\d[\d.,]*",
    r"\b\d[\d.,]*\s*(?:zł|Kč|kr\b|лв|грн)",
    # Nombres de moneda: SOLO pegados a una cifra, y los ambiguos en compuesto
    # (libras ESTERLINAS, coronas SUECAS), nunca sueltos.
    r"\b\d+(?:[.,]\d+)*\s*(?:pesos(?!\s+pesad)|reais|reales|soles|bol[ií]vares"
    r"|guaran[ií]es|quetzales|lempiras|c[oó]rdobas|colones|z[lł]otys?"
    r"|coronas\s+(?:suecas|noruegas|danesas|checas)|francos\s+suizos"
    r"|libras\s+esterlinas|rupias|yenes|rublos|grivnas)\b",
]
# Periodicidad temporal, lo que convierte un importe en oferta laboral spam.
# Ej: "2.800 € al mes", "500€ semanales", "$500/day", "500 ARS mensuales".
# Editable en config/blacklist/commercial_money_periodic.txt. NO contiene
# monedas: se combina con la lista de importes de arriba, así que añadir una
# moneda allí la habilita también aquí. boundaries=False (empiezan por "/").
_DEFAULT_MONEY_PERIODIC = [
    r"al?\s+mes", r"por\s+mes", r"/?\s*mes(?:es)?", r"mensual(?:es)?",
    r"al?\s+semana", r"por\s+semana", r"/?\s*semana", r"semanal(?:es)?",
    r"al\s+a[ñn]o", r"anual(?:es)?", r"di[aá]rios?",
    r"ao?\s+m[eê]s", r"por\s+m[eê]s", r"mensais", r"semanais",
    # periodicidad en inglés: /day, per day, a day, daily...
    r"/\s*(?:day|d|week|wk|month|mo|year|yr|hour|hr)\b",
    r"(?:per|a|an|each)\s+(?:day|week|month|year|hour)\b",
    r"(?:daily|weekly|monthly|yearly|hourly)\b",
]
# Call-to-action publicitario.
# Editable en config/blacklist/commercial_cta.txt (defaults de fallback abajo).
_DEFAULT_CTA = [
    r"post[uú]late", r"cont[aá]ctan?os?", r"cont[aá]ctame", r"inscr[ií]bete",
    r"env[ií]a\s*(?:tu\s*)?(?:cv|curr[ií]culum|mensaje)",
    r"haz\s+click", r"click\s+(?:en|aqu[ií])", r"escr[ií]beme", r"escr[ií]benos",
    r"interesados?\s+(?:escribir|contactar)",
    r"m[aá]s\s+info(?:rmaci[oó]n)?\s+(?:por|en|v[ií]a)\s+(?:dm|md|privado|wsp|whatsapp)",
    r"env[ií]ame?\s+(?:un\s+)?(?:mensaje|dm|md|privado)",
]
# Vocabulario de oferta de trabajo / reclutamiento (lado del que OFRECE empleo,
# que es el patrón spam; NO el de quien busca trabajo y pregunta sin enlace).
# Caso real: "Si estás buscando trabajo... oportunidades de empleo disponibles".
# Editable en config/blacklist/commercial_work.txt (defaults de fallback abajo).
_DEFAULT_WORK = [
    r"vacantes?", r"puestos?\s+disponibles?", r"sueldo", r"salario",
    r"contrato\s+(?:legal|estable|indefinido)",
    r"trabajo\s+(?:estable|legal|garantizado)",
    r"oportunidad(?:es)?\s+(?:laboral(?:es)?|de\s+(?:empleo|trabajo|negocio))",
    r"ofertas?\s+de\s+(?:empleo|trabajo)", r"empleos?\s+disponibles?",
    r"(?:trabaja|trabajo|ingresos?|gana[rs]?|dinero)\s+desde\s+(?:casa|tu\s+m[oó]vil)",
    r"gana[rs]?\s+(?:dinero|hasta\s+\d)",
    r"ingresos?\s+(?:extra|adicionales|garantizados)",
    r"estamos\s+contratando",
    r"se\s+(?:busca|necesita[n]?)\s+(?:personal|empleados?|gente|colaboradores)",
    r"trabajo\s+que\s+m[aá]s\s+te\s+interese",
    r"si\s+est[aá]s\s+buscando\s+(?:trabajo|empleo)",
]
# URL externa (http/https) que NO sea t.me — enlaces a webs de "empleo"/scam.
_EXTERNAL_URL_RE = re.compile(r'https?://(?!t\.me/|telegram\.me/)\S+', re.IGNORECASE)
# Trabajo doméstico / búsqueda de persona — patrón scam "cuidar casa/mascota/niños".
# Editable en config/blacklist/commercial_domestic.txt (defaults de fallback abajo).
# Cada patrón es de DOS piezas a propósito: un "cuidar" o un "busco a alguien"
# sueltos son frases normales y no deben disparar nada.
_DEFAULT_DOMESTIC = [
    r"\b(?:cuidar|atender|alimentar|pasear|limpiar)\b[^.\n]{0,50}"
    r"\b(?:casa|hogar|mascota|perro|gato|ni[ñn]o|familia|jardín|piso|apartamento)\b",
    r"busc[ao]\s+(?:a\s+)?(?:una?\s+)?"
    r"(?:persona|alguien|cuidador(?:a)?|ni[ñn]era|emplead[ao]|se[ñn]ora|"
    r"chica|chico|joven)\s+(?:responsable|seria|de\s+confianza|para)\b",
]
# Sentido de urgencia — palabras GRITADAS típicas de scam.
# Editable en config/blacklist/commercial_urgency.txt (defaults de fallback abajo).
_DEFAULT_URGENCY = [
    r"URGENTE", r"INMEDIAT[OA]", r"EMPEZAR\s+YA", r"HOY\s+MISMO",
    r"R[AÁ]PIDO", r"YA\s*!",
]
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


def _illegal_services_re() -> re.Pattern:
    return load_and_compile("commercial_illegal_services.txt", _DEFAULT_ILLEGAL_SERVICES)


def _cta_re() -> re.Pattern:
    return load_and_compile("commercial_cta.txt", _DEFAULT_CTA)


def _work_re() -> re.Pattern:
    return load_and_compile("commercial_work.txt", _DEFAULT_WORK)


def money_re() -> re.Pattern:
    """Importes con moneda. Pública: `bio_spam` usa la MISMA lista de monedas."""
    return load_and_compile("commercial_money.txt", _DEFAULT_MONEY, boundaries=False)


def _periodic_terms_re() -> re.Pattern:
    return load_and_compile(
        "commercial_money_periodic.txt", _DEFAULT_MONEY_PERIODIC, boundaries=False,
    )


# Cache del regex compuesto <importe><periodicidad>. La clave son los dos
# patrones ya compilados, así que si cambia una lista (o el idioma activo)
# cambia la clave y se recompone solo.
_PERIODIC_CACHE: dict[tuple[str, str], re.Pattern] = {}


def _periodic_money_re() -> re.Pattern:
    """Importe pegado a una periodicidad: "2.800 € al mes", "$500/day"."""
    money, periodic = money_re().pattern, _periodic_terms_re().pattern
    key = (money, periodic)
    rx = _PERIODIC_CACHE.get(key)
    if rx is None:
        rx = re.compile(rf"{money}\s*{periodic}", re.IGNORECASE)
        _PERIODIC_CACHE[key] = rx
    return rx


def _domestic_re() -> re.Pattern:
    return load_and_compile("commercial_domestic.txt", _DEFAULT_DOMESTIC)


def _urgency_re() -> re.Pattern:
    return load_and_compile("commercial_urgency.txt", _DEFAULT_URGENCY)


def check(msg: Message, is_first_msg: bool = False) -> Hit:
    text = (msg.text or msg.caption or "").strip()
    # NFC: unifica acentos (combining vs precompuesto) para que los regex con
    # tildes (extracci[oó]n, an[oó]nimos) casen sea cual sea la forma unicode.
    text = unicodedata.normalize("NFC", text)
    if not text or len(text) < 40:
        return Hit.none()

    emoji_lines = len(_EMOJI_LINE_RE.findall(text))
    has_periodic_money = bool(_periodic_money_re().search(text))
    has_money = bool(money_re().search(text))
    has_cta = bool(_cta_re().search(text))
    has_work = bool(_work_re().search(text))
    has_tg_link = "t.me/" in text.lower() or "telegram.me/" in text.lower()
    has_external_url = bool(_EXTERNAL_URL_RE.search(text))
    has_domestic = bool(_domestic_re().search(text))
    has_urgency = bool(_urgency_re().search(text))
    illegal = _illegal_services_re().findall(text)
    n_illegal = len(set(m.lower() for m in illegal))

    score = 0
    reasons: list[str] = []
    # Servicios ilegales/scam: señal MUY fuerte. 1 keyword = 35, 2+ = 55.
    if n_illegal >= 2:
        score += 55
        reasons.append(t("reason.ad_illegal_multi", n=n_illegal))
    elif n_illegal == 1:
        score += 35
        reasons.append(t("reason.ad_illegal_single"))
    if emoji_lines >= 3:
        score += 30
        reasons.append(t("reason.ad_emoji_lines", n=emoji_lines))
    elif emoji_lines >= 2:
        score += 15
        reasons.append(t("reason.ad_emoji_lines_few"))
    # Periodic money pesa más que money simple (oferta laboral típica scam)
    if has_periodic_money:
        score += 25
        reasons.append(t("reason.ad_periodic_money"))
    elif has_money:
        score += 20
        reasons.append(t("reason.ad_money"))
    if has_cta:
        score += 20
        reasons.append(t("reason.ad_cta"))
    if has_work:
        score += 15
        reasons.append(t("reason.ad_work"))
    if has_tg_link:
        score += 20
        reasons.append(t("reason.ad_tg_link"))
    elif has_external_url:
        # Enlace web SOLO (sin más señales) NO debe banear: un usuario fiable
        # puede compartir una web en su primer mensaje. Pesa poco por sí mismo.
        score += 15
        reasons.append(t("reason.ad_external_url"))
    # COMBO clave del job-spam: lenguaje de oferta de empleo + un enlace. Esto sí
    # es el patrón inequívoco (reclutamiento + link), aunque el perfil parezca
    # fiable (foto antigua, etc.). Caso real: empleo.vertexgloball.com.
    if has_work and (has_tg_link or has_external_url):
        score += 35
        reasons.append(t("reason.ad_job_spam"))
    if has_domestic:
        score += 20
        reasons.append(t("reason.ad_domestic"))
    if has_urgency:
        score += 10
        reasons.append(t("reason.ad_urgency"))

    if is_first_msg and score > 0:
        score += 15
        reasons.append(t("reason.ad_first_msg"))

    # Umbral mínimo: una sola señal NO basta. Se requieren al menos 2-3 combinadas.
    if score < 60:
        return Hit.none()

    return Hit(
        rule="commercial_ad",
        score=score,
        reason=t("reason.commercial_ad", details=" + ".join(reasons)),
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
