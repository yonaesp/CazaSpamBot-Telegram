"""Destinos fichados: adónde llevan los enlaces de las cuentas baneadas por spam.

El admin pidió (1-nov-2026) que el bot aprenda de los bans. «Cualquier `t.me/…` en
la bio» no vale: en el barrido del 31-oct, 9 veteranos legítimos lo llevan (el admin
de una comunidad de Apple, una guía de programación, un canal de fondos). Lo que se
aprende es el DESTINO concreto: un dominio, un canal o una invitación que ya salió
en el spam de una cuenta baneada. La cuenta robada de BitNest y la de «付费广告»
(L50) llevaban `bitnest.me/…` y `t.me/ZOGJ001`: con eso fichado, la siguiente bio o
mensaje que los lleve ya no pasa.

Reglas, porque esto aprende solo:
- Solo fichan los bans en los que el spam ES el enlace (`REGLAS_QUE_FICHAN`): la bio
  que delató a la cuenta, el destino que se anuncia solo, el enlace adulto, el
  referido y lo que confirmas tú con los botones. Un anuncio o una estafa de
  inversión pueden citar una web legítima (un periódico) y fichada tumbaría el
  primer mensaje de cualquiera que la enlace; un ban manual puede ser por insultar.
- Nunca se ficha una plataforma compartida (`NUNCA`): YouTube, Instagram, GitHub…
- En las plataformas donde el destino es la ruta (`POR_RUTA`: t.me, telegra.ph,
  wa.me…) se ficha el canal o la invitación, nunca la plataforma entera.
- Al desbanear a alguien se olvida lo que se fichó de esa cuenta (`olvidar`).
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

REGLAS_QUE_FICHAN = frozenset({
    "bio_spam", "cuenta_robada", "manual_review_ban", "link_target_spam", "adult_link",
    "via_bot_referral",
})

# Plataformas donde cualquiera tiene su página: fichar el dominio marcaría a todos.
NUNCA = frozenset({
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "fb.com", "fb.me",
    "tiktok.com", "x.com", "twitter.com", "github.com", "github.io", "gitlab.com",
    "linkedin.com", "google.com", "google.es", "goo.gl", "wikipedia.org", "amazon.com",
    "amazon.es", "amzn.to", "amzn.eu", "aliexpress.com", "apple.com", "microsoft.com",
    "telegram.org", "whatsapp.com", "reddit.com", "twitch.tv", "discord.gg", "discord.com",
    "medium.com", "blogspot.com", "wordpress.com", "spotify.com", "pinterest.com",
})
# Donde el destino es la ruta: se ficha `t.me/canal`, no `t.me`.
POR_RUTA = frozenset({"t.me", "telegram.me", "telegram.dog", "telegra.ph", "wa.me", "linktr.ee"})
_ALIAS = {"telegram.me": "t.me", "telegram.dog": "t.me"}
# Segundo nivel de los dominios de país: `bbc.co.uk` es `bbc.co.uk`, no `co.uk`.
_SEGUNDO_NIVEL = frozenset({"co", "com", "org", "net", "gob", "gov", "edu", "ac"})

# Con esquema, con `www.` o con ruta: «Hola.Que tal» no es un dominio.
_URL_RE = re.compile(
    r"(?:(?P<esq>https?://)|(?P<www>www\.))?"
    r"(?P<host>(?:[a-z0-9-]+\.)+[a-z]{2,24})\.?"
    # Solo caracteres de URL: un emoji pegado («t.me/+M9Mb…💋», bio de isabelle) no
    # es parte del enlace.
    r"(?P<ruta>/[A-Za-z0-9\-._~/?#@!$&*+,;=%:]*)?",
    re.IGNORECASE,
)


_SEGMENTO_RE = re.compile(r"\+?[A-Za-z0-9_-]+")


def _dominio(host: str) -> str:
    partes = host.split(".")
    if len(partes) >= 3 and partes[-2] in _SEGUNDO_NIVEL:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def clave(host: str, ruta: str = "") -> str | None:
    """La clave de un destino, o None si no se puede fichar."""
    host = host.lower().removeprefix("www.").rstrip(".")
    host = _ALIAS.get(host, host)
    if host in POR_RUTA:
        trozos = [p for p in (ruta or "").split("/") if p]
        if not trozos:
            return None
        # `joinchat/HASH` y `+HASH` son la misma invitación.
        primero = "+" + trozos[1] if trozos[0].lower() == "joinchat" and len(trozos) > 1 else trozos[0]
        m = _SEGMENTO_RE.match(primero)
        return f"{host}/{m.group(0).lower()}" if m else None
    dom = _dominio(host)
    if dom in NUNCA or host in NUNCA:
        return None
    return dom


def claves(texto: str | None) -> list[str]:
    """Los destinos fichables de un texto (bio o mensaje), sin repetir."""
    vistas: list[str] = []
    for m in _URL_RE.finditer(texto or ""):
        if not (m.group("esq") or m.group("www") or m.group("ruta")):
            continue
        k = clave(m.group("host"), m.group("ruta") or "")
        if k and k not in vistas:
            vistas.append(k)
    return vistas


def sin_enlaces(texto: str) -> str:
    """El texto sin sus enlaces (los que `claves` reconoce y cualquier `t.me/…`)."""
    return re.sub(r"\S*t\.me/\S+", " ", _URL_RE.sub(
        lambda m: " " if (m.group("esq") or m.group("www") or m.group("ruta")) else m.group(0),
        texto or "")).strip()


def aprender_de_ban(db, user_id: int, texto: str | None, reglas: str) -> int:
    """Ficha los destinos de un ban con evidencia de spam. Nunca lanza."""
    try:
        if not set((reglas or "").split("+")) & REGLAS_QUE_FICHAN:
            return 0
        nuevas = claves(texto)
        for k in nuevas:
            db.fichar_destino(k, user_id, reglas)
        if nuevas:
            log.info("destinos: fichados %s de user=%s (%s)", nuevas, user_id, reglas)
        return len(nuevas)
    except Exception as exc:  # noqa: BLE001 — aprender nunca tumba un ban
        log.debug("destinos: no se pudo fichar de user=%s: %s", user_id, exc)
        return 0


def olvidar(db, user_id: int) -> None:
    """Al desbanear, lo que se fichó solo por esa cuenta sobra."""
    try:
        n = db.olvidar_destinos(user_id)
        if n:
            log.info("destinos: olvidados %d destinos de user=%s (desbaneado)", n, user_id)
    except Exception as exc:  # noqa: BLE001
        log.debug("destinos: no se pudo olvidar a user=%s: %s", user_id, exc)


def fichados_en(db, texto: str | None) -> list[str]:
    """Los destinos del texto que ya están fichados. Una base rota cuenta como «ninguno»."""
    ks = claves(texto)
    if not ks or db is None:
        return []
    try:
        fichados = db.destinos_fichados()
    except Exception as exc:  # noqa: BLE001
        log.debug("destinos: base ilegible: %s", exc)
        return []
    return [k for k in ks if k in fichados]


def fichados(db) -> frozenset[str]:
    """Todos los destinos fichados, para `url_blocklist`."""
    try:
        return frozenset(db.destinos_fichados()) if db is not None else frozenset()
    except Exception as exc:  # noqa: BLE001
        log.debug("destinos: base ilegible: %s", exc)
        return frozenset()
