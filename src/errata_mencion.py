"""«¿Quizás te referías a @x?»: una mención a un desconocido que se parece a un miembro.

Caso real (24-oct-2026, Domótica): «Juan M.», 124 mensajes en el grupo, escribió
«Era porque @Moliko tenía varios Spot…» queriendo decir @Molkio. El bot lo trató
como una mención a un externo: aviso suave en el grupo y «Algo raro de alguien de
confianza» por privado al admin, que tuvo que mirarlo para nada. Ahora esa mención
no cuenta como externa (`external_mention.posible_errata`) y el bot responde al
mensaje con la sugerencia. Si el autor lo corrige editando, la sugerencia se borra
en el momento; si no, a los 10 min.

Tres cosas que no se deben romper:
- Los @usuario van en `<code>`: así no se avisa a nadie (ni al miembro sugerido
  ni al dueño de lo mal escrito, que puede ser cualquiera de fuera) y en el móvil
  se copian con un toque.
- «No encuentro», no «no está»: el bot solo conoce a quien ha visto, y un miembro
  callado puede llamarse justo así.
- Nunca en los primeros mensajes: un recién llegado que «se equivoca» por una
  tecla con el @ de un admin es la forma de suplantarlo, y ahí la mención sigue
  puntuando como externa.
"""
from __future__ import annotations

import html
import logging
import time

from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .db import DB
from .detectors import external_mention as ext_det
from .i18n import t

log = logging.getLogger(__name__)

ERRATA_TTL_S = 600


def buscar(db: DB, cfg, msg, user, is_first: bool) -> list[tuple[str, str]]:
    """[(lo escrito, el @ del miembro al que se parece)] de este mensaje."""
    if is_first or not cfg.detect_external_mentions:
        return []
    if not ext_det.handles_mencionados(msg):
        return []   # lo normal: sin menciones no se toca la base
    propio = (user.username or "").lower()
    candidatos = [u for u in db.usernames_del_chat(msg.chat_id) if u.lower() != propio]
    return ext_det.erratas_de_mencion(msg, db.resolve_username, candidatos)


async def sugerir(context: ContextTypes.DEFAULT_TYPE, db: DB, cfg, msg,
                  erratas: list[tuple[str, str]]) -> None:
    """Responde al mensaje con la sugerencia. Una sola por mensaje."""
    if not erratas or cfg.shadow:
        return
    if db.errata_pendiente(msg.chat_id, msg.message_id):
        return   # una edición que sigue sin corregirlo: la sugerencia ya está
    texto = "\n".join(t("errata.linea", mal=html.escape(mal), bien=html.escape(bien))
                      for mal, bien in erratas[:3]) + t("errata.pie")
    try:
        sent = await context.bot.send_message(
            chat_id=msg.chat_id, text=texto, parse_mode="HTML",
            reply_to_message_id=msg.message_id,
            disable_notification=True, allow_sending_without_reply=False,
        )
    except TelegramError as exc:
        log.warning("errata: no se pudo sugerir en chat=%s msg=%s: %s",
                    msg.chat_id, msg.message_id, exc)
        return
    db.add_gentle_warning(chat_id=msg.chat_id, user_msg_id=msg.message_id,
                          bot_msg_id=sent.message_id, user_id=msg.from_user.id,
                          errata=[list(e) for e in erratas])
    log.info("errata: sugerido en chat=%s msg=%s user=%s %s", msg.chat_id, msg.message_id,
             msg.from_user.id, ", ".join(f"@{m} → @{b}" for m, b in erratas))
    jq = context.application.job_queue
    if jq:
        jq.run_once(_borrar_job, when=ERRATA_TTL_S,
                    data={"chat_id": msg.chat_id, "user_msg_id": msg.message_id,
                          "bot_msg_id": sent.message_id},
                    name=f"del_errata_{msg.chat_id}_{sent.message_id}")


async def al_editar(context: ContextTypes.DEFAULT_TYPE, db: DB, msg) -> None:
    """Si la edición ya no lleva lo mal escrito, se borra la sugerencia."""
    pend = db.errata_pendiente(msg.chat_id, msg.message_id)
    if not pend:
        return
    bot_msg_id, erratas = pend
    escritos = {h.lower() for h in ext_det.handles_mencionados(msg)}
    if any(str(mal).lower() in escritos for mal, _ in erratas):
        return
    await _borrar(context.bot, db, msg.chat_id, msg.message_id, bot_msg_id)
    log.info("errata: corregida editando en chat=%s msg=%s → sugerencia borrada",
             msg.chat_id, msg.message_id)


async def _borrar(bot, db: DB, chat_id: int, user_msg_id: int, bot_msg_id: int) -> None:
    try:
        await bot.delete_message(chat_id=chat_id, message_id=bot_msg_id)
    except TelegramError as exc:
        log.debug("errata: borrar chat=%s msg=%s: %s", chat_id, bot_msg_id, exc)
    db.delete_gentle_warning(chat_id, user_msg_id)


async def _borrar_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    d = context.job.data
    await _borrar(context.bot, context.bot_data["db"], d["chat_id"], d["user_msg_id"], d["bot_msg_id"])


async def barrido_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Red de seguridad: los `run_once` viven en memoria y un reinicio los pierde."""
    db: DB = context.bot_data["db"]
    for row in db.erratas_vencidas(time.time() - ERRATA_TTL_S - 60):
        await _borrar(context.bot, db, row["chat_id"], row["user_msg_id"], row["bot_msg_id"])
