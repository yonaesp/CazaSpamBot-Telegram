"""Detector: bio del perfil con señales claras de spam (promo, sexual, comercial).

Patrón típico de spammer: bio con link `t.me/+...` (invite), `t.me/joinchat`,
emojis sexuales (😈🔥🥵💋👅) + texto en idioma distinto al del grupo (alemán,
inglés, ruso para grupos españoles), promesa monetaria, CTA explícito.

Caso real (2026-05-30): `Hier geht's zu mir😈:https://t.me/+Th8C... 🔥🥵`
— alemán + invite link + emojis sexuales = spam OnlyFans/escort.

Score acumulado por señales. Una sola NO basta, requiere combinación (≥60).

Caso real (31-oct-2026): «Get inspired, then go. Cursway → t.me/+3JVb…» (Helen),
«Holidays made simple. Cursway → …» (Gloria) y «Find warm seas and good flights
→ …» (Brook). Sin emojis ni palabras de spam: cada bio sola son 40 puntos. Lo que
las delata es la flecha que apunta al enlace y que las tres llevan EL MISMO enlace
privado (red). Con `db` y `user_id`, `check` apunta los enlaces privados que ve y
cuenta cuántas cuentas más los llevan.
"""
from __future__ import annotations

import re

from ..i18n import t
from ..wordlists import load_and_compile
from . import Hit
# Cifras monetarias: se reutiliza la lista de `commercial_ad` para que el admin
# añada su moneda UNA vez (config/blacklist/commercial_money.txt) y valga para
# los dos detectores.
from .commercial_ad import money_re as _money_re

# t.me/+ABC o t.me/joinchat/ → invite link a canal/grupo externo
_TG_INVITE_RE = re.compile(
    r't\.me/(?:\+|joinchat/)[A-Za-z0-9_-]+',
    re.IGNORECASE,
)
# El código de una invitación privada. Distingue mayúsculas: es la clave del enlace.
_INVITE_CODE_RE = re.compile(r't\.me/(?:\+|joinchat/)([A-Za-z0-9_-]{6,})', re.IGNORECASE)
# Cualquier link t.me/ a un canal/grupo (no a user)
_TG_LINK_RE = re.compile(r't\.me/[A-Za-z0-9_]{4,}', re.IGNORECASE)
# Una flecha que apunta al enlace («Cursway → t.me/+…», «👉 https://…») es una
# llamada a la acción sin palabras. Solo cuenta pegada al enlace: una flecha suelta
# no dice nada. Los dos puntos no cuentan, porque «Web: https://…» es lo normal.
_FLECHA_AL_ENLACE_RE = re.compile(
    r'(?:→|⟶|➔|➜|➡|👉|👇|⬇|⤵|»|>>)️?\s*'
    r'(?:https?://)?(?:t\.me/|www\.|(?:[a-z0-9-]+\.)+[a-z]{2,10}/)',
    re.IGNORECASE,
)
# Red: cuántas cuentas MÁS llevan el mismo enlace privado. Con una suma 15 y con
# dos o más, 30: el enlace (40) y la red solos llegan a 60 con tres cuentas; con
# dos hace falta además otra señal (la flecha, un emoji, una palabra…). Dos
# conocidos con el mismo grupo privado en la bio no bastan para un ban.
RED_UNA = 15
RED_VARIAS = 30
# URLs externas
# Proporción de alfabeto NO latino a partir de la cual se considera que la bio
# está escrita en otro sistema de escritura. No vale con «¿hay alguna letra
# latina?»: el spam de USDT escribe «收U» y «18万U», y esa U sola bastaba para
# colarse. Se reutiliza el mismo cálculo que usa el detector de mensajes.
_RATIO_NO_LATINA = 0.6
_EXTERNAL_URL_RE = re.compile(
    r'\b(?:https?://|www\.)\S+',
    re.IGNORECASE,
)
# Dominio sin `https://` ni `www.`, con ruta detrás: «stake1036.com/?c=tg». Sin la
# barra no se cuenta, para no tomar por enlace un «trabajo en Google.com» o un
# correo. Caso real (28-oct-2026, Charlotte): la bio enlazaba así un espejo de
# casino y no sumaba ni un punto.
_BARE_URL_RE = re.compile(
    r'(?<![@\w.])(?:[a-z0-9-]+\.)+[a-z]{2,10}/\S*',
    re.IGNORECASE,
)
# Enlace con código de campaña o de referido (`?c=tg`, `?ref=`, `utm_source=`…):
# quien enlaza su web no le pone un rastreador; quien la anuncia, sí. Suma 20, así
# que ni con el enlace (15) y una llamada a la acción (15) llega a 60: hace falta
# además algo del tema (casino, contenido adulto…).
_CAMPAIGN_PARAM_RE = re.compile(
    r'[?&](?:c|ref|r|aff|affiliate|promo|promocode|code|clickid|subid|'
    r'utm_source|utm_campaign|utm_medium)=',
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
# CTA promocional en la bio.
# Editable en config/blacklist/bio_cta.txt (defaults de fallback abajo).
_DEFAULT_BIO_CTA = [
    r"dm\b", r"md\b", r"escr[ií]beme", r"cont[aá]ctame", r"cl[ií]ck",
    r"haz\s+click", r"aqu[ií]\s+est[oa]y", r"link\s+(?:en\s+)?(?:bio|perfil)",
    r"sigueme", r"join\s+now", r"follow\s+me", r"come\s+see\s+me", r"hier\s+geht",
    r"(?:consulta(?:r)?|visita(?:r)?|mira(?:r)?|ve[ra]?)\s+(?:el\s+|mi\s+|la\s+)?"
    r"(?:sitio|web|p[aá]gina|perfil)",
    r"m[aá]s\s+info\s+en",
]
# Servicios ilegales / hacking en bio (caso real: "experto en piratería informática").
# Editable en config/blacklist/bio_illegal_services.txt (defaults de fallback abajo).
_DEFAULT_BIO_ILLEGAL = [
    r"pirater[ií]a\s+inform[aá]tica", r"hacking", r"hacker", r"hacke[oa]",
    r"cracke[oa]", r"experto\s+en\s+(?:pirater[ií]a|hacking|seguridad)",
    r"robo\s+de\s+(?:cuentas?|datos)", r"espionaje", r"spyware",
    r"recupera(?:r|ci[oó]n)\s+(?:cuentas?|contrase[ñn]as?|dinero)",
]

def _illegal_re() -> re.Pattern:
    return load_and_compile("bio_illegal_services.txt", _DEFAULT_BIO_ILLEGAL)



# Keywords spam adulto/cripto/casino/préstamo (multi-idioma).
# Editable en config/blacklist/bio_spam_keywords.txt (defaults de fallback abajo).
_DEFAULT_BIO_SPAM_KEYWORDS = [
    r"onlyfans", r"cam(?:girl)?", r"escort", r"sugar(?:daddy|baby)?", r"crypto",
    r"bitcoin", r"btc", r"casino", r"bet", r"prestamo", r"préstamo", r"payday",
    r"forex", r"trading\s+signal", r"nft", r"geil(?:e|en|er)?", r"nackt",
    r"sexy", r"hot\s+girl", r"teen", r"videos?\s+priv", r"fotos?\s+priv",
    r"contenido\s+exclusivo", r"18\+",
]


def _spam_keywords_re() -> re.Pattern:
    return load_and_compile("bio_spam_keywords.txt", _DEFAULT_BIO_SPAM_KEYWORDS)


def _cta_re() -> re.Pattern:
    return load_and_compile("bio_cta.txt", _DEFAULT_BIO_CTA)


# Texto en idioma distinto al español: alemán, inglés, ruso típicos en bios spammer
_FOREIGN_LANG_HINT_RE = re.compile(
    r'\b(?:hier|geht|zu\s+mir|hello|come|see|join|here|click|profile|'
    r'mein|sehen|kontakt|mehr|von\s+der|von\s+mir|schau|folge|'
    r'check\s+me|my\s+profile|link\s+below)\b',
    re.IGNORECASE,
)


def enlaces_privados(bio: str | None) -> list[str]:
    """Códigos de las invitaciones privadas (t.me/+…, joinchat) de una bio."""
    return sorted({m.group(1) for m in _INVITE_CODE_RE.finditer(bio or "")})


def _otras_cuentas(db, user_id: int, bio: str) -> int:
    """Apunta los enlaces privados de la bio y devuelve el máximo de cuentas más
    que lleva alguno. Un fallo de la base cuenta como «ninguna»."""
    otras = 0
    for enlace in enlaces_privados(bio):
        try:
            otras = max(otras, db.registrar_enlace_bio(enlace, user_id))
        except Exception:  # noqa: BLE001 — una consulta no puede tumbar la moderación
            pass
    return otras


def check(bio: str | None, db=None, user_id: int | None = None) -> Hit:
    if not bio or len(bio.strip()) < 5:
        return Hit.none()

    text = bio.strip()
    # Sin URLs: son siempre latinas y falsearían la comprobación de alfabeto.
    # ORDEN IMPORTANTE: primero la URL completa (con esquema) y después los enlaces
    # sueltos sin `https://`. Al revés quedaba un «https://» huérfano contando como
    # texto latino, que bajaba la proporción y colaba la bio.
    sin_urls = re.sub(r"t\.me/\S+", " ", _EXTERNAL_URL_RE.sub(" ", text))
    sin_urls = _BARE_URL_RE.sub(" ", sin_urls)
    score = 0
    reasons: list[str] = []

    if _TG_INVITE_RE.search(text):
        score += 40  # invite privado t.me/+ en bio = señal fuerte (users reales no lo ponen)
        reasons.append(t("reason.bio_invite_link"))
    elif _TG_LINK_RE.search(text):
        score += 25
        reasons.append(t("reason.bio_tg_link"))
    elif _EXTERNAL_URL_RE.search(text) or _BARE_URL_RE.search(text):
        score += 15
        reasons.append(t("reason.bio_external_url"))
    if _CAMPAIGN_PARAM_RE.search(text):
        score += 20
        reasons.append(t("reason.bio_campaign_link"))

    if _SEXUAL_EMOJI_RE.search(text):
        score += 20
        reasons.append(t("reason.bio_sexual_emoji"))
    if _MONEY_EMOJI_RE.search(text) or _money_re().search(text):
        score += 15
        reasons.append(t("reason.bio_money"))
    if (_cta_re().search(text) or _FOREIGN_LANG_HINT_RE.search(text)
            or _FLECHA_AL_ENLACE_RE.search(text)):
        score += 15
        reasons.append(t("reason.bio_cta"))
    otras = _otras_cuentas(db, user_id, text) if db is not None and user_id else 0
    if otras >= 2:
        score += RED_VARIAS
        reasons.append(t("reason.bio_red_varias", n=otras))
    elif otras == 1:
        score += RED_UNA
        reasons.append(t("reason.bio_red_una"))
    # Bio SIN una sola letra latina + enlace a un canal. Las señales de arriba
    # (emojis, CTA, cifras de dinero) están pensadas para texto latino, así que una
    # bio entera en otro alfabeto no sumaba NADA y se quedaba en los 40 del enlace,
    # por debajo del umbral. Caso real (7-ago-2026): «【新币公群】…押金18万U:
    # https://t.me/+…», publicidad de blanqueo, que pasaba como bio inocente.
    #
    # Se exige ADEMÁS un enlace de invitación PRIVADO (t.me/+ o joinchat), no uno
    # cualquiera: quien tiene un canal propio lo enlaza por su @nombre público, y
    # eso es corriente en cualquier idioma. El enlace privado en una bio es lo que
    # no hace nadie normal. Con «cualquier enlace t.me» se marcaba a un ruso que
    # anunciaba su canal, y eso es un falso positivo con ban al entrar.
    from .unicode_script import non_allowed_ratio as _ratio_no_latina
    _r, _ = _ratio_no_latina(sin_urls, ["latin"])
    if _TG_INVITE_RE.search(text) and _r >= _RATIO_NO_LATINA:
        score += 20
        reasons.append(t("reason.bio_no_latina"))

    if _spam_keywords_re().search(text):
        score += 30
        reasons.append(t("reason.bio_keywords"))
    if _illegal_re().search(text):
        score += 30
        reasons.append(t("reason.bio_illegal"))

    if score < 60:
        return Hit.none()

    return Hit(
        rule="bio_spam",
        score=min(score, 200),
        reason=t("reason.bio_spam", details=" + ".join(reasons)),
        payload={"bio_preview": text[:200], "score": score, "otras_cuentas": otras},
    )
