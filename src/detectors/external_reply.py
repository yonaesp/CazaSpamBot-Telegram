"""Detector: promoción de un canal EXTERNO mediante cita a otro chat (external_reply).

Técnica vista en producción: el spammer responde/cita un mensaje de SU canal
externo, de forma que su mensaje muestra un bloque citado «etiquetado» que al pulsar
lleva a ese canal (p.ej. @Forexrading120). El texto visible suele ser un CTA mínimo
(«Please Join») y el reclamo real (señales de forex, etc.) va DENTRO de la cita.

Como el canal no aparece como enlace ni como @mención en el texto, `external_mention`
no lo ve: hay que mirar `msg.external_reply`.

Señal: usuario que en su primer mensaje cita un CANAL/supergrupo EXTERNO con
`@username` (público y unible) que NO moderamos. Score alto pero < 100 para que el
trust score pueda degradarlo (borderline → revisión, no ban directo).

Anti-FP:
  - Solo canales/supergrupos con username público (una cita a un chat privado sin @
    no es «unible por el enlace»: señal débil, se ignora).
  - Citas a NUESTROS propios chats moderados se ignoran.
  - Fuera del primer mensaje el score baja mucho (un veterano que cite algo puntual
    no debe ser baneado).
"""
from __future__ import annotations

from telegram import Message

from ..i18n import t
from . import Hit


def check(msg: Message, is_first_msg: bool, is_moderated_chat=None) -> Hit:
    er = getattr(msg, "external_reply", None)
    if er is None:
        return Hit.none()
    chat = getattr(er, "chat", None)
    if chat is None:
        return Hit.none()
    if getattr(chat, "type", None) not in ("channel", "supergroup"):
        return Hit.none()
    username = getattr(chat, "username", None)
    if not username:
        return Hit.none()  # canal privado sin @: señal débil, no disparamos
    if is_moderated_chat is not None:
        try:
            if is_moderated_chat(chat.id):
                return Hit.none()  # cita a uno de nuestros propios grupos
        except Exception:  # noqa: BLE001
            pass
    score = 80 if is_first_msg else 35
    title = getattr(chat, "title", None) or username
    return Hit(
        rule="external_quote_channel",
        score=score,
        reason=(t("reason.external_quote", title=title, username=username)
                + (" " + t("reason.external_quote_first_msg") if is_first_msg else "")),
        payload={"channel": username, "first_msg": is_first_msg},
    )
