"""Detector: usuario que envía un mensaje con botones inline (reply_markup).

Los usuarios normales NO pueden enviar mensajes con `reply_markup` (teclados
inline). Solo bots y canales. Cuando un usuario reenvía un mensaje de un canal
que tenía botones inline, esos botones se PRESERVAN en el forward.

Por tanto, encontrar `msg.reply_markup` en un mensaje cuyo `from_user` es un
usuario humano (no bot) es señal casi inequívoca de:
  a) Forward desde canal/bot promocional.
  b) Mensaje del propio user creado vía bot externo (raro en grupos normales).

Score alto pero NO inmediato 100 para permitir trust score (veteranos que
ocasionalmente reenvían algo de un canal legítimo no se banean).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

from telegram import Message

from ..i18n import t
from . import Hit

# --- El enlace de REFERIDO publicado con un bot inline ------------------------
# Caso real (21-oct-2026, Windows 11): «Lil Pani», miembro desde 2025 con 27
# preguntas sobre Windows, publicó con @case_rush_bot «A free case every day in
# Case Rush! Stars, gifts and NFTs» y un botón a la mini-app con SU código:
# `t.me/case_rush_bot/app?startapp=r_5414865354`. Cobra por cada uno que entre. El
# bot solo borraba y avisaba, porque un mensaje vía bot con botones puede ser una
# encuesta de @vote o un juego, que llevan botones de callback y no un enlace.
#
# Lo que distingue el anuncio es el parámetro de arranque que identifica a quien
# publica: su propio id, o un código que empieza por ref/r_/invite/aff. Un cheque de
# cripto (`t.me/send?start=CQ…`) también lleva parámetro, pero no es un referido y
# no cuenta. Es estructural, como el ancla de `investment_scam`: no se externaliza.
_PARAMS_DE_ARRANQUE = frozenset({"start", "startapp", "startattach", "startgroup"})
_HOSTS_TELEGRAM = frozenset({"t.me", "telegram.me", "telegram.dog"})
_MARCA_REFERIDO_RE = re.compile(
    r"^(?:ref(?:erral)?|r|invite|inv|aff(?:iliate)?|partner)(?:[_\-]|(?=\d))", re.IGNORECASE)


def _param_arranque(url: str) -> str | None:
    """Valor de start/startapp de un enlace a un bot o una mini-app; None si no es eso."""
    try:
        partes = urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return None
    esquema, host = partes.scheme.lower(), (partes.netloc or "").lower()
    if not ((esquema in ("http", "https") and host in _HOSTS_TELEGRAM)
            or (esquema == "tg" and host == "resolve")):
        return None
    for clave, valor in parse_qsl(partes.query):
        if clave.lower() in _PARAMS_DE_ARRANQUE and valor:
            return valor
    return None


def enlaces_de_referido(msg: Message, user_id: int | None) -> list[str]:
    """URLs de los botones que son un enlace de referido de quien publica."""
    rm = getattr(msg, "reply_markup", None)
    out: list[str] = []
    for row in getattr(rm, "inline_keyboard", None) or []:
        for btn in row:
            url = getattr(btn, "url", None)
            valor = _param_arranque(url) if url else None
            if not valor:
                continue
            if (user_id and str(user_id) in valor) or _MARCA_REFERIDO_RE.match(valor):
                out.append(url)
    return out


def check(msg: Message) -> Hit:
    rm = getattr(msg, "reply_markup", None)
    if rm is None:
        return Hit.none()
    keyboard = getattr(rm, "inline_keyboard", None) or []
    n_buttons = sum(len(row) for row in keyboard)
    if n_buttons == 0:
        return Hit.none()

    # Recopilar URLs de los botones para el log/quip (algunos botones tienen url, otros callback_data)
    urls: list[str] = []
    for row in keyboard:
        for btn in row:
            url = getattr(btn, "url", None)
            if url:
                urls.append(url)

    score = 90  # alto pero no max, para que el trust score pueda degradar
    reasons = [t("reason.inline_buttons", n_buttons=n_buttons)]
    if urls:
        reasons.append(t("reason.inline_buttons_urls", n_urls=len(urls)))
    return Hit(
        rule="inline_buttons_from_user",
        score=score,
        reason=" + ".join(reasons),
        payload={
            "n_buttons": n_buttons,
            "urls": urls[:5],
        },
    )
