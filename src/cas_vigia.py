"""CAS apagado sin que nadie lo sepa: se avisa al admin (L65).

En noviembre de 2026 la API de CAS empezó a pedir una clave en cada consulta. El bot
tomaba el rechazo («API key required») por «no está en la lista» y lo guardaba como
limpio: una lista entera apagada sin una sola línea de aviso. Al arrancar y una vez al
día se comprueba que CAS contesta de verdad; si falta la clave o CAS la rechaza, el
admin recibe un privado, una vez por motivo, y otro cuando vuelve a funcionar.
"""
from __future__ import annotations

import html
import logging

from telegram.error import TelegramError

from . import notify_prefs
from .detectors import cas
from .i18n import t

log = logging.getLogger("antispam.cas_vigia")

PREF_AVISADO = "_cas_aviso"
SIN_CLAVE = "sin_clave"
BIEN = "bien"
# Una cuenta que existe siempre (la de avisos de Telegram): solo importa si CAS contesta.
_ID_DE_PRUEBA = 777000


async def _avisar_apagado(context, texto: str) -> bool:
    """Suena: los grupos se quedan con una lista de spammers menos."""
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            disable_web_page_preview=True,
            disable_notification=notify_prefs.sin_sonido(db, importante=True),
        )
    except TelegramError as exc:
        log.warning("cas_vigia: no se pudo avisar al admin: %s", exc)
        return False
    return True


async def _avisar_vuelve(context) -> bool:
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=t("cas.vuelve"), parse_mode="HTML",
            disable_notification=notify_prefs.sin_sonido(db, importante=False),
        )
    except TelegramError as exc:
        log.warning("cas_vigia: no se pudo avisar al admin: %s", exc)
        return False
    return True


async def comprobar_job(context) -> None:
    """Al arrancar y cada día: ¿contesta CAS de verdad?"""
    cfg, db = context.bot_data["cfg"], context.bot_data["db"]
    session = context.bot_data.get("http")
    if not cfg.cas_enabled or not cfg.admin_notify_chat_id:
        return
    avisado = db.get_text_pref(PREF_AVISADO) or ""
    if not cas.clave():
        log.warning("CAS apagado: su API pide clave y falta CAS_API_KEY en el .env")
        if avisado != SIN_CLAVE and await _avisar_apagado(context, t("cas.sin_clave")):
            db.set_text_pref(PREF_AVISADO, SIN_CLAVE)
        return
    if session is None:
        return
    resultado, _, motivo = await cas.consultar(_ID_DE_PRUEBA, session)
    if resultado == cas.SIN_RESPUESTA:
        # No se sabe: ni se da por bueno ni se avisa por un corte de red. Mañana, otra vez.
        log.warning("cas_vigia: CAS no contesta a la prueba (%s)", motivo)
        return
    if resultado == cas.RECHAZADA:
        log.warning("CAS apagado: rechaza la clave (%s)", motivo)
        marca = f"rechazada:{motivo}"[:120]
        if avisado != marca and await _avisar_apagado(
                context, t("cas.rechazada", motivo=html.escape(motivo))):
            db.set_text_pref(PREF_AVISADO, marca)
        return
    if avisado and avisado != BIEN and await _avisar_vuelve(context):
        log.info("cas_vigia: CAS vuelve a contestar")
    db.set_text_pref(PREF_AVISADO, BIEN)
