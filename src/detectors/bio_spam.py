"""Detector: bio del perfil con señales claras de spam (promo, sexual, comercial).

Patrón típico de spammer: bio con link `t.me/+...` (invite), `t.me/joinchat`,
emojis sexuales (😈🔥🥵💋👅) + texto en idioma distinto al del grupo (alemán,
inglés, ruso para grupos españoles), promesa monetaria, CTA explícito.

Caso real (2026-05-30): `Hier geht's zu mir😈:https://t.me/+Th8C... 🔥🥵`
— alemán + invite link + emojis sexuales = spam OnlyFans/escort.

Score acumulado por señales. Una sola NO basta, requiere combinación (≥60).
"""
from __future__ import annotations

import re

from . import Hit
from ..wordlists import load_and_compile

# t.me/+ABC o t.me/joinchat/ → invite link a canal/grupo externo
_TG_INVITE_RE = re.compile(
    r't\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+',
    re.IGNORECASE,
)
# Cualquier link t.me/ a un canal/grupo (no a user)
_TG_LINK_RE = re.compile(r't\.me/[A-Za-z0-9_]{4,}', re.IGNORECASE)
# URLs externas
_EXTERNAL_URL_RE = re.compile(
    r'\b(?:https?://|www\.)\S+',
    re.IGNORECASE,
)
# Emojis sexuales/promo (escort, OnlyFans, etc.)
_SEXUAL_EMOJI_RE = re.compile(
    r'[\U0001F608\U0001F525\U0001F975\U0001F48B\U0001F445\U0001F351\U0001F4A6\U0001F608]',
)
# Emojis "dinero / commerce"
_MONEY_EMOJI_RE = re.compile(
    r'[\U0001F4B0\U0001F4B5\U0001F4B6\U0001F4B7\U0001F4B8\U0001F4B3\U0001F911]',
)
# Cifras monetarias (cualquier longitud + símbolo moneda)
_MONEY_RE = re.compile(
    r'\b\d{2,}(?:[.,]\d+)*\s*(?:€|\$|EUR|USD|euros|d[oó]lares)',
    re.IGNORECASE,
)
# CTA promocional
_CTA_RE = re.compile(
    r'\b(?:dm\b|md\b|escr[ií]beme|cont[aá]ctame|cl[ií]ck|haz\s+click|'
    r'aqu[ií]\s+est[oa]y|link\s+(?:en\s+)?(?:bio|perfil)|sigueme|join\s+now|'
    r'follow\s+me|come\s+see\s+me|hier\s+geht|'
    r'(?:consulta(?:r)?|visita(?:r)?|mira(?:r)?|ve[ra]?)\s+(?:el\s+|mi\s+|la\s+)?'
    r'(?:sitio|web|p[aá]gina|perfil)|m[aá]s\s+info\s+en)',
    re.IGNORECASE,
)
# Servicios ilegales / hacking en bio (caso real: "experto en piratería informática").
# Editable en config/blacklist/bio_illegal_services.txt (defaults de fallback abajo).
_DEFAULT_BIO_ILLEGAL = [
    r"pirater[ií]a\s+inform[aá]tica", r"hacking", r"hacker", r"hacke[oa]",
    r"cracke[oa]", r"experto\s+en\s+(?:pirater[ií]a|hacking|seguridad)",
    r"robo\s+de\s+(?:cuentas?|datos)", r"espionaje", r"spyware",
    r"recupera(?:r|ci[oó]n)\s+(?:cuentas?|contrase[ñn]as?|dinero)",
]
_ILLEGAL_RE = load_and_compile("bio_illegal_services.txt", _DEFAULT_BIO_ILLEGAL)
# Keywords spam adulto/cripto/casino/préstamo (multi-idioma).
# Editable en config/blacklist/bio_spam_keywords.txt (defaults de fallback abajo).
_DEFAULT_BIO_SPAM_KEYWORDS = [
    r"onlyfans", r"cam(?:girl)?", r"escort", r"sugar(?:daddy|baby)?", r"crypto",
    r"bitcoin", r"btc", r"casino", r"bet", r"prestamo", r"préstamo", r"payday",
    r"forex", r"trading\s+signal", r"nft", r"geil(?:e|en|er)?", r"nackt",
    r"sexy", r"hot\s+girl", r"teen", r"videos?\s+priv", r"fotos?\s+priv",
    r"contenido\s+exclusivo", r"18\+",
]
_SPAM_KEYWORDS_RE = load_and_compile("bio_spam_keywords.txt", _DEFAULT_BIO_SPAM_KEYWORDS)
# Texto en idioma distinto al español: alemán, inglés, ruso típicos en bios spammer
_FOREIGN_LANG_HINT_RE = re.compile(
    r'\b(?:hier|geht|zu\s+mir|hello|come|see|join|here|click|profile|'
    r'mein|sehen|kontakt|mehr|von\s+der|von\s+mir|schau|folge|'
    r'check\s+me|my\s+profile|link\s+below)\b',
    re.IGNORECASE,
)


def check(bio: str | None) -> Hit:
    if not bio or len(bio.strip()) < 5:
        return Hit.none()

    text = bio.strip()
    score = 0
    reasons: list[str] = []

    if _TG_INVITE_RE.search(text):
        score += 40  # invite privado t.me/+ en bio = señal fuerte (users reales no lo ponen)
        reasons.append("invite link privado en bio (t.me/+...)")
    elif _TG_LINK_RE.search(text):
        score += 25
        reasons.append("link t.me/ a canal/grupo externo")
    elif _EXTERNAL_URL_RE.search(text):
        score += 15
        reasons.append("URL externa en bio")

    if _SEXUAL_EMOJI_RE.search(text):
        score += 20
        reasons.append("emojis sexuales/promo")
    if _MONEY_EMOJI_RE.search(text) or _MONEY_RE.search(text):
        score += 15
        reasons.append("promesa monetaria")
    if _CTA_RE.search(text) or _FOREIGN_LANG_HINT_RE.search(text):
        score += 15
        reasons.append("call-to-action / idioma extranjero")
    if _SPAM_KEYWORDS_RE.search(text):
        score += 30
        reasons.append("keywords spam (onlyfans/crypto/casino/etc.)")
    if _ILLEGAL_RE.search(text):
        score += 30
        reasons.append("servicios ilegales/hacking (piratería informática/etc.)")

    if score < 60:
        return Hit.none()

    return Hit(
        rule="bio_spam",
        score=min(score, 200),
        reason="Bio sospechosa: " + " + ".join(reasons),
        payload={"bio_preview": text[:200], "score": score},
    )
