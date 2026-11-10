"""Borrar un mensaje pasados N segundos. Un solo sitio para todo el bot.

Había SEIS copias de la misma función repartidas por el código (quips, antiflood,
warns, bienvenidas, avisos de ban, confirmaciones de reporte). Todas hacían
exactamente lo mismo: borrar y tragarse el error. La única diferencia era una
trampa: `admin_report` leía `data["msg_id"]` mientras las otras cinco leían
`data["message_id"]`, así que copiar el patrón del vecino equivocado daba un
`KeyError` en un job, que además falla en silencio dentro de la cola de trabajos.

Dos cosas que conviene recordar al usar esto:

- **Los jobs viven en memoria**, y un reinicio se los lleva por delante. Por eso
  `programar` apunta además el borrado en la base (`borrados_pendientes`) y
  `barrido_job` borra cada 5 min lo vencido que se quedó sin job. Antes, lo publicado
  poco antes de un reinicio se quedaba en el grupo para siempre: el 10-nov-2026 había
  8 avisos de hasta seis meses (L61). Todo borrado programado pasa por `programar`
  (hay test): un `jq.run_once(borrar_mensaje_job, …)` a pelo no sobrevive al reinicio.
- **0 o negativo significa «no borrar»**, no «borrar ya». Es el mismo convenio que
  el resto de ajustes de duración del proyecto (`verified_ttl_s`,
  `ban_notice_delete_after_s`), donde 0 = permanente.
"""
from __future__ import annotations

import logging
import time

from telegram.error import BadRequest, NetworkError, TelegramError
from telegram.ext import ContextTypes

log = logging.getLogger("antispam")


def _db_de(context):
    return (getattr(context, "bot_data", None) or {}).get("db")


def _olvidar(context, chat_id: int, message_id: int) -> None:
    db = _db_de(context)
    if db is None:
        return
    try:
        db.olvidar_borrado(chat_id, message_id)
    except Exception as exc:  # noqa: BLE001 — la fila se la lleva el barrido
        log.debug("borrado diferido: no se pudo olvidar chat=%s msg=%s: %s", chat_id, message_id, exc)


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
        if _es_de_red(exc):
            return          # la fila se queda: lo reintenta el barrido
    _olvidar(context, chat_id, message_id)


def _es_de_red(exc: TelegramError) -> bool:
    """Un fallo de red se reintenta; «no existe» o «sin permiso» no van a cambiar."""
    return isinstance(exc, NetworkError) and not isinstance(exc, BadRequest)


def programar(context, chat_id: int, message_id: int, segundos: int,
              nombre: str | None = None, extra: dict | None = None) -> str | None:
    """Encola el borrado. Devuelve el nombre del job, o None si no se programó.

    Si ya había un job con el mismo nombre se cancela primero, para que refrescar
    un TTL no acabe con dos borrados encolados sobre el mismo mensaje. El borrado
    queda también en la base, por si un reinicio se lleva el job.
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
    apuntar(context, chat_id, message_id, segundos)
    return nombre


def apuntar(context, chat_id: int, message_id: int, segundos: int) -> None:
    """Deja el borrado en la base, sin job. Para quien borra con un job propio (que
    además limpia sus tablas): si un reinicio se lo lleva, el barrido borra el mensaje."""
    db = _db_de(context)
    if db is None or not segundos or segundos <= 0:
        return
    try:
        db.apuntar_borrado(chat_id, message_id, time.time() + segundos)
    except Exception as exc:  # noqa: BLE001 — el job en memoria sigue en pie
        log.warning("borrado diferido: no se pudo apuntar chat=%s msg=%s: %s",
                    chat_id, message_id, exc)


# El job en memoria borra a su hora; el barrido solo recoge lo que se quedó sin job,
# así que espera un margen para no adelantarse a él.
MARGEN_BARRIDO_S = 90
# Pasado este tiempo de más, una fila que sigue fallando por la red se da por perdida.
ABANDONO_S = 24 * 3600
MAX_POR_BARRIDO = 50


async def barrido_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra los mensajes vencidos que un reinicio dejó sin su job. Nunca lanza."""
    db = _db_de(context)
    if db is None:
        return
    ahora = time.time()
    try:
        filas = db.borrados_vencidos(ahora - MARGEN_BARRIDO_S, MAX_POR_BARRIDO)
    except Exception as exc:  # noqa: BLE001
        log.warning("borrado diferido: el barrido no pudo leer la base: %s", exc)
        return
    borrados = 0
    for fila in filas:
        chat_id, message_id, vence = fila["chat_id"], fila["message_id"], fila["vence"]
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            borrados += 1
        except TelegramError as exc:
            if _es_de_red(exc) and ahora - vence < ABANDONO_S:
                log.debug("borrado diferido: barrido chat=%s msg=%s, se reintenta: %s",
                          chat_id, message_id, exc)
                continue
        _olvidar(context, chat_id, message_id)
    if borrados:
        log.info("borrado diferido: el barrido borró %d mensaje(s) que se quedaron sin su job",
                 borrados)
