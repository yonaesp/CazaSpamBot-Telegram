"""Borrar un mensaje pasados N segundos. Un solo sitio para todo el bot.

Había SEIS copias de la misma función repartidas por el código (quips, antiflood,
warns, bienvenidas, avisos de ban, confirmaciones de reporte). Todas hacían
exactamente lo mismo: borrar y tragarse el error. La única diferencia era una
trampa: `admin_report` leía `data["msg_id"]` mientras las otras cinco leían
`data["message_id"]`, así que copiar el patrón del vecino equivocado daba un
`KeyError` en un job, que además falla en silencio dentro de la cola de trabajos.

Dos cosas que conviene recordar al usar esto:

- **Los jobs viven en memoria.** Un reinicio se los lleva por delante, así que un
  borrado programado a horas vista puede no ocurrir nunca. Donde eso importe hace
  falta además un barrido por base de datos, como el de las bienvenidas de
  baneados en `verification.cleanup_job`.
- **0 o negativo significa «no borrar»**, no «borrar ya». Es el mismo convenio que
  el resto de ajustes de duración del proyecto (`verified_ttl_s`,
  `ban_notice_delete_after_s`), donde 0 = permanente.
"""
from __future__ import annotations

import logging

from telegram.error import TelegramError
from telegram.ext import ContextTypes

log = logging.getLogger("antispam")


async def borrar_mensaje_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job canónico: borra el mensaje indicado en `job.data`.

    Acepta `message_id` y, por compatibilidad, el `msg_id` que usaba
    `admin_report`. Si llega el nombre antiguo se deja constancia en el log para
    poder limpiarlo, pero no se rompe.
    """
    data = getattr(context.job, "data", None) or {}
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    if message_id is None and "msg_id" in data:
        message_id = data["msg_id"]
        log.debug("borrado diferido con la clave antigua 'msg_id' (chat=%s)", chat_id)
    if chat_id is None or message_id is None:
        log.warning("borrado diferido sin datos suficientes: %s", data)
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as exc:
        # Lo normal es que ya no exista (lo borró un admin, o el propio bot al
        # banear). No merece más que una línea de depuración.
        log.debug("borrado diferido chat=%s msg=%s: %s", chat_id, message_id, exc)


def programar(context, chat_id: int, message_id: int, segundos: int,
              nombre: str | None = None, extra: dict | None = None) -> str | None:
    """Encola el borrado. Devuelve el nombre del job, o None si no se programó.

    Si ya había un job con el mismo nombre se cancela primero, para que refrescar
    un TTL no acabe con dos borrados encolados sobre el mismo mensaje.
    """
    if not segundos or segundos <= 0:
        return None
    jq = getattr(getattr(context, "application", None), "job_queue", None)
    if jq is None:
        return None
    nombre = nombre or f"del_{chat_id}_{message_id}"
    for job in jq.get_jobs_by_name(nombre):
        job.schedule_removal()
    datos = {"chat_id": chat_id, "message_id": message_id}
    if extra:
        datos.update(extra)
    jq.run_once(borrar_mensaje_job, when=segundos, data=datos, name=nombre)
    return nombre
