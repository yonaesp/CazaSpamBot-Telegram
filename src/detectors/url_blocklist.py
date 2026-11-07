"""Detector de URLs en blocklist (acortadores típicos de spam)."""
from __future__ import annotations

from urllib.parse import urlparse

from telegram import Message, MessageEntity

from ..i18n import t
from . import Hit, trozo_entidad


def _iter_urls(msg: Message) -> list[str]:
    text = msg.text or msg.caption or ""
    urls: list[str] = []
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    for ent in entities:
        if ent.type == MessageEntity.TEXT_LINK and ent.url:
            urls.append(ent.url)
        elif ent.type == MessageEntity.URL:
            urls.append(trozo_entidad(text, ent.offset, ent.length))
    return urls


# Mencionar un bot de spam fichado (L55): 100, lo que pide un ban. No es regla dura:
# un veterano que avisa «cuidado con @x_bot, es estafa» no cae (trust ≥ 70).
BOT_FICHADO_SCORE = 100


def check(msg: Message, blocklist: list[str], is_first_msg: bool,
          fichados: frozenset[str] = frozenset(), menciones: bool = True) -> Hit:
    """`fichados`: destinos aprendidos de bans de spam (`destinos`), dominio o
    `t.me/canal`. Cuentan igual que la lista fija.

    Con `menciones`, un @bot fichado da `bot_fichado` (L55). La ruta de bots miembro
    lo apaga: un bot de moderación que cita a un spammer no es spam.
    """
    from .. import destinos
    if menciones and fichados:
        bots = destinos.bots_fichados_en((msg.text or "") + "\n" + (msg.caption or ""), fichados)
        if bots:
            return Hit(
                rule="bot_fichado",
                score=BOT_FICHADO_SCORE,
                reason=t("reason.bot_fichado", bots=", ".join(bots)),
                payload={"bots": bots},
            )
    bad: list[str] = []
    for raw in _iter_urls(msg):
        url = raw if "://" in raw else "https://" + raw
        if fichados:
            try:
                partes = urlparse(url)
                k = destinos.clave(partes.netloc or "", partes.path or "")
            except ValueError:
                k = None
            if k and k in fichados:
                bad.append(k)
                continue
        # removeprefix, NO lstrip: `lstrip("www.")` recibe un CONJUNTO de caracteres,
        # así que "wa.me" se convertía en "a.me" y "whatsapp.com" en "hatsapp.com".
        # Inofensivo con la lista actual, pero el día que alguien añada wa.me (vector
        # habitual de spam) el detector no casaría y nadie vería ningún error.
        try:
            host = (urlparse(url).netloc or "").lower().removeprefix("www.")
        except ValueError:
            continue
        if any(host == d or host.endswith("." + d) for d in blocklist):
            bad.append(host)
    if not bad:
        return Hit.none()
    score = 60 if is_first_msg else 25
    return Hit(
        rule="url_blocklist",
        score=score,
        reason=t("reason.url_blocklist", hosts=", ".join(bad)),
        payload={"hosts": bad},
    )
