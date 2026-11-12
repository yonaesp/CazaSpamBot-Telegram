"""Avisos de revisión que un ban posterior deja sin sentido (L62).

El aviso «Usuario sospechoso (revisar) … decide tú» se quedaba en el privado con sus
botones aunque el bot baneara después a esa persona por otra regla. El 12-nov-2026 uno
siguió diciendo «ya está DENTRO del grupo» 95 minutos después del ban, y el admin baneó
a mano a quien ya estaba fuera. Aquí se apunta cada aviso al mandarlo y, cuando esa
persona cae baneada, se edita con el motivo y se le quitan los botones.
"""
from __future__ import annotations

import html
import logging

from telegram.error import TelegramError

from .i18n import t

log = logging.getLogger(__name__)


def apuntar(db, enviado, user_id: int, texto: str) -> None:
    """Recuerda un aviso de revisión recién mandado. Nunca lanza."""
    try:
        db.apuntar_revision(int(enviado.chat_id), int(enviado.message_id), int(user_id), texto)
    except Exception as exc:  # noqa: BLE001 — el aviso ya salió; esto es solo memoria
        log.debug("revisiones: no se pudo apuntar el aviso de user=%s: %s", user_id, exc)


async def cerrar_por_ban(bot, db, user_id: int, rule: str) -> int:
    """Edita los avisos abiertos de esa persona: ya está baneada. Nunca lanza."""
    try:
        filas = db.pop_revisiones(int(user_id))
    except Exception as exc:  # noqa: BLE001 — cerrar un aviso jamás tumba un ban
        log.debug("revisiones: no se pudieron leer los avisos de user=%s: %s", user_id, exc)
        return 0
    if not filas:
        return 0
    from . import rule_explain
    motivo = html.escape(rule_explain.explain(rule) or rule or "")
    cerrados = 0
    for fila in filas:
        try:
            await bot.edit_message_text(
                chat_id=fila["admin_chat_id"], message_id=fila["aviso_msg_id"],
                text=fila["texto"] + t("review.banned_after", motivo=motivo),
                parse_mode="HTML", disable_web_page_preview=True)
            cerrados += 1
        except TelegramError as exc:
            log.debug("revisiones: no se pudo cerrar el aviso %s: %s", fila["aviso_msg_id"], exc)
        except Exception as exc:  # noqa: BLE001 — cerrar un aviso jamás tumba un ban
            log.warning("revisiones: fallo cerrando el aviso %s: %s", fila["aviso_msg_id"], exc)
    if cerrados:
        log.info("revisiones: %d aviso(s) de user=%s cerrados tras el ban (%s)", cerrados, user_id, rule)
    return cerrados
