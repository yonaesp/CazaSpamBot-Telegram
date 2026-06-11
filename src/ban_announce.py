"""Anuncio de bans en el chat con consolidación de ráfagas.

Cuando se banean varios usuarios seguidos, en vez de N mensajes individuales
(que saturan el chat) se borra lo anterior y se publica UN mensaje unificado
con la lista. Umbral: a partir de 3 bans en la misma ráfaga se consolida.

Todos los mensajes (individuales o consolidado) se autoborran tras `delete_after`
segundos (default 3h) contados desde el último ban de la ráfaga.

Estado por chat en `context.bot_data["_ban_burst"][chat_id]`.
"""
from __future__ import annotations

import logging
import time

from telegram.error import TelegramError
from telegram.ext import ContextTypes

log = logging.getLogger(__name__)

# Bans dentro de esta ventana cuentan como "ráfaga" (misma tanda).
BURST_WINDOW_S = 600  # 10 min
# A partir de este nº de bans en la ráfaga, se consolidan en un solo mensaje.
CONSOLIDATE_THRESHOLD = 3


def _fresh_burst() -> dict:
    return {
        "lines": [],               # texto de cada quip de la ráfaga
        "individual_msg_ids": [],  # ids de quips individuales aún sin consolidar
        "consolidated_msg_id": None,
        "last_ts": 0.0,
        "delete_job_name": None,
    }


async def _delete_msg(context, chat_id: int, message_id: int) -> None:
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError:
        pass


def _schedule_delete(context, chat_id: int, message_id: int, delete_after: int,
                     old_job_name: str | None) -> str | None:
    """Programa el borrado del mensaje, cancelando el job anterior si lo había."""
    jq = context.application.job_queue
    if jq is None or delete_after <= 0:
        return None
    # Cancelar job previo (la ráfaga refresca el TTL)
    if old_job_name:
        for job in jq.get_jobs_by_name(old_job_name):
            job.schedule_removal()
    name = f"del_banannounce_{chat_id}_{message_id}"
    jq.run_once(
        _delete_announce_job, when=delete_after,
        data={"chat_id": chat_id, "message_id": message_id}, name=name,
    )
    return name


async def _delete_announce_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    await _delete_msg(context, data["chat_id"], data["message_id"])


async def announce_ban(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    quip_text: str,
    delete_after: int,
) -> None:
    """Anuncia un ban con consolidación de ráfaga. Reemplaza al post directo."""
    store = context.bot_data.setdefault("_ban_burst", {})
    now = time.time()
    burst = store.get(chat_id)
    # Nueva ráfaga si pasó la ventana sin bans
    if burst is None or now - burst["last_ts"] > BURST_WINDOW_S:
        burst = _fresh_burst()
        store[chat_id] = burst
    burst["last_ts"] = now
    burst["lines"].append(quip_text)
    n = len(burst["lines"])

    if n < CONSOLIDATE_THRESHOLD:
        # Mensaje individual normal
        try:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=quip_text, parse_mode="HTML",
                disable_notification=True,
            )
        except TelegramError as exc:
            log.warning("announce_ban send individual falló chat=%s: %s", chat_id, exc)
            return
        burst["individual_msg_ids"].append(sent.message_id)
        _schedule_delete(context, chat_id, sent.message_id, delete_after, None)
        return

    # n >= umbral: consolidar
    # 1) borrar los individuales previos de la ráfaga
    for mid in burst["individual_msg_ids"]:
        await _delete_msg(context, chat_id, mid)
    burst["individual_msg_ids"] = []
    # 2) borrar el consolidado anterior (lo reemplazamos con la lista ampliada)
    if burst["consolidated_msg_id"]:
        await _delete_msg(context, chat_id, burst["consolidated_msg_id"])
    # 3) publicar el consolidado
    header = f"🧹 <b>Limpieza de spam ({n} baneados)</b>\n\n"
    body = "\n".join(burst["lines"])
    text = header + body
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            disable_notification=True, disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.warning("announce_ban send consolidado falló chat=%s: %s", chat_id, exc)
        return
    burst["consolidated_msg_id"] = sent.message_id
    # 4) reprogramar borrado (TTL desde el último ban)
    burst["delete_job_name"] = _schedule_delete(
        context, chat_id, sent.message_id, delete_after, burst["delete_job_name"],
    )
