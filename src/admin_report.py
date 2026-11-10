"""Sistema de reporte público vía @admin.

Cuando un usuario escribe @admin (típicamente respondiendo a un mensaje
sospechoso de otro usuario), Telegram avisa nativamente a todos los admins
del grupo. Además mi bot:

1. Responde al reporter: "🙏 Un admin lo revisará, gracias por avisar"
2. Auto-borra esa confirmación a los 60 segundos
3. Registra el reporte en `admin_reports` con el msg_id reportado

Si después un admin (manual o vía bot) borra el mensaje reportado, el bridge
Telethon (events.MessageDeleted) detecta el delete y este módulo:

4. Borra el mensaje @admin del reporter (sin warn ni strike)
5. Publica un thanks gracioso al reporter
6. Marca el reporte como resuelto en DB

El thanks se auto-borra a los 5 min para no ensuciar el grupo.
"""
from __future__ import annotations

import asyncio
import html
import logging
import random
import re

from telegram import Message
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import borrado_diferido, enlaces, notify_prefs, temas
from .db import DB
from .i18n import t, variant_keys

log = logging.getLogger(__name__)

# Detección de @admin como mención (con/sin entity)
_ADMIN_MENTIONS = ("@admin", "@admins", "@administrador", "@administradores")
_ADMIN_RE = re.compile(r"(?<![A-Za-z0-9_])@(?:admin|admins|administrador|administradores)(?![A-Za-z0-9_])", re.IGNORECASE)

CONFIRM_TTL_S = 60          # Auto-borra confirm tras 1 min
_PREVIOS = 30               # mensajes del grupo que se miran hacia atrás (todos los temas)
_PREVIOS_TIMEOUT_S = 4.0
THANKS_TTL_S = 5 * 60       # Auto-borra thanks tras 5 min

# Frases alternativas (el bot elige una al azar para no sonar a robot). Viven en los
# paquetes de idioma como claves numeradas `report.confirm.1`, `.2`, ... y cada idioma
# puede aportar SU propio número de frases: ver `i18n.variant_keys`.
_CONFIRM_PREFIX = "report.confirm"
_THANKS_WARN_PREFIX = "report.thanks_warn"
_THANKS_PREFIX = "report.thanks"


def contains_admin_mention(msg: Message) -> bool:
    """True si el mensaje contiene @admin como mención (en texto o entidades)."""
    text = msg.text or msg.caption or ""
    if not text:
        return False
    return bool(_ADMIN_RE.search(text))


async def handle_admin_mention(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    msg: Message,
) -> None:
    """Procesa un mensaje con @admin: responde al reporter y registra el reporte."""
    reporter = msg.from_user
    if not reporter:
        return
    # Ignorar si es el propio admin del bot (no necesita auto-respuesta)
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if reporter.id == cfg.admin_user_id:
        return

    # Una edición del @admin no es otro aviso. Caso real (5-nov-2026): el miembro
    # editó su «@admin» tres horas después y el bot volvió a confirmar en el grupo y
    # a mandar el privado, que llegó como si el aviso fuera de ese momento.
    if getattr(msg, "edit_date", None) and db.admin_report_existe(msg.chat_id, msg.message_id):
        log.info("admin_report: edición de un @admin ya registrado (msg=%s), no se repite", msg.message_id)
        return

    reported = temas.respuesta(msg)
    if reported:
        reported_msg_id = reported.message_id
        reported_user_id = reported.from_user.id if reported.from_user else None
    else:
        reported_msg_id, reported_user_id = await _anterior_del_tema(context, msg)
        if reported_msg_id is None and not getattr(msg.chat, "is_forum", False):
            # Sin cuenta secundaria y en un grupo sin temas: el id anterior, que puede
            # no ser el que se reporta (es solo para el seguimiento del borrado).
            reported_msg_id = msg.message_id - 1 if msg.message_id > 1 else None
        log.info(
            "admin_report sin reply explícito: reportado msg=%s de user=%s (chat=%s, tema=%s)",
            reported_msg_id, reported_user_id, msg.chat_id, temas.tema_bot_api(msg),
        )

    # Reacción ✍️ al mensaje del reporter (feedback visual rápido sin ensuciar)
    try:
        await context.bot.set_message_reaction(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            reaction=["✍"],
        )
    except TelegramError as exc:
        log.debug("set_message_reaction fallo: %s", exc)

    # Confirmar al reporter
    confirm_text = t(random.choice(variant_keys(_CONFIRM_PREFIX)))
    bot_msg_id = None
    try:
        sent = await context.bot.send_message(
            chat_id=msg.chat_id,
            text=confirm_text,
            message_thread_id=temas.hilo(msg),
            reply_to_message_id=msg.message_id,
            disable_notification=True,
            allow_sending_without_reply=True,
        )
        bot_msg_id = sent.message_id
    except TelegramError as exc:
        log.warning("admin_report confirm send fallo: %s", exc)

    # Registrar tracking
    db.add_admin_report(
        chat_id=msg.chat_id,
        reporter_msg_id=msg.message_id,
        reporter_user_id=reporter.id,
        reporter_username=reporter.username,
        reported_msg_id=reported_msg_id,
        reported_user_id=reported_user_id,
        bot_confirm_msg_id=bot_msg_id,
        thread_id=temas.hilo(msg),
    )

    # Auto-delete confirm a 1 min
    if bot_msg_id:
        borrado_diferido.programar(context, msg.chat_id, bot_msg_id, CONFIRM_TTL_S,
                                   nombre=f"del_admin_confirm_{msg.chat_id}_{bot_msg_id}")
    log.info(
        "admin_report registered: reporter=%s msg=%s reported_msg=%s",
        reporter.id, msg.message_id, reported_msg_id,
    )

    # El privado sale SIEMPRE. Antes, sin mensaje reportado no salía, y si la copia
    # fallaba (un mensaje de servicio, uno ya borrado) se perdía también el aviso.
    if not cfg.admin_notify_chat_id:
        return
    if reported_msg_id:
        try:
            await context.bot.copy_message(
                chat_id=cfg.admin_notify_chat_id,
                from_chat_id=msg.chat_id,
                message_id=reported_msg_id,
                disable_notification=notify_prefs.sin_sonido(db, importante=True),
            )
        except TelegramError as exc:
            log.info("admin_report: no se pudo copiar msg=%s al privado: %s", reported_msg_id, exc)
    chat_title = msg.chat.title or str(msg.chat_id)
    reporter_disp = (
        f"@{reporter.username}" if reporter.username
        else (reporter.first_name or f"id {reporter.id}")
    )
    via = t("report.via_reply") if reported else t("report.via_previous")
    # Enlace al mensaje REPORTADO, no al del reportante: la copia que se manda
    # arriba llega sin el hilo alrededor, y lo que hace falta mirar es el contexto
    # en el que se escribió. Si no se sabe cuál es, al propio @admin, que está en
    # su tema y con lo reportado justo encima.
    _url_rep = (enlaces.al_mensaje(msg.chat, reported_msg_id) if reported_msg_id
                else enlaces.al_mensaje(msg.chat, msg.message_id))
    ctx_text = t(
        "report.admin_dm" if reported_msg_id else "report.admin_dm_sin_mensaje",
        enlace=t("hdl.enlace_al_msg", url=_url_rep) if _url_rep else "",
        chat=html.escape(chat_title),
        reporter=html.escape(reporter_disp), reporter_id=reporter.id,
        msg_id=reported_msg_id or "?", via=via,
        author_id=reported_user_id or "?",
    )
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=ctx_text, parse_mode="HTML",
            disable_notification=notify_prefs.sin_sonido(db, importante=True),
        )
    except TelegramError as exc:
        log.warning("admin_report: el aviso al privado falló: %s", exc)


async def _anterior_del_tema(context: ContextTypes.DEFAULT_TYPE, msg: Message) -> tuple[int | None, int | None]:
    """El mensaje anterior al @admin en SU tema, de otra persona: (id, autor) o (None, None).

    Con la cuenta secundaria, porque la Bot API no da el historial. En un grupo con
    temas los ids son del grupo entero y el `id - 1` puede ser de otro tema (caso del
    5-nov-2026, `temas`). Se saltan los mensajes de servicio, los del que avisa y los
    del bot. Ante cualquier fallo, (None, None): mejor sin mensaje que uno equivocado.
    """
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter is not None else None
    if client is None:
        return None, None
    tema = temas.tema_bot_api(msg)
    quien = msg.from_user.id if msg.from_user else None
    try:
        previos = await asyncio.wait_for(
            client.get_messages(msg.chat_id, limit=_PREVIOS, max_id=msg.message_id), _PREVIOS_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — sin esto el aviso sale igual
        log.info("admin_report: no se pudo leer lo anterior al @admin: %s", exc)
        return None, None
    for m in previos or []:
        if getattr(m, "action", None) is not None or temas.tema_mtproto(m) != tema:
            continue
        autor = getattr(m, "sender_id", None)
        if autor in (quien, context.bot.id):
            continue
        return m.id, autor
    return None, None


async def on_reported_message_deleted(
    bot,
    db: DB,
    chat_id: int,
    deleted_msg_id: int,
) -> None:
    """Callback desde telethon_bridge cuando se borra un mensaje.

    Si coincide con algún admin_report no resuelto, hace cascade: borra el
    mensaje del reporter, borra la confirmación inicial y publica thanks.
    """
    report = db.find_admin_report_by_reported(chat_id, deleted_msg_id)
    if not report:
        return
    # Borrar mensaje del reporter (su @admin)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=report["reporter_msg_id"])
    except TelegramError:
        pass
    # Borrar confirmación inicial si sigue
    if report["bot_confirm_msg_id"]:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=report["bot_confirm_msg_id"])
        except TelegramError:
            pass
    # Publicar thanks — usar first_name si lo tenemos guardado, sino "usuario"
    # SIN link al perfil del reporter (no necesita visibilidad pública)
    rep_uid = report["reporter_user_id"]
    # reporter_username puede contener first_name si lo guardamos en su día
    # En este caso solo tenemos username. Si existe, lo usamos como referencia
    # textual (NO clicable, sin @, solo texto plano)
    if report["reporter_username"]:
        # Mostramos como referencia neutra, sin @ que abra perfil
        reporter_label = t(
            "report.reporter_label",
            name=html.escape(report["reporter_username"]), uid=rep_uid,
        )
    else:
        reporter_label = t("report.reporter_label_anon", uid=rep_uid)
    # Elegir template según action_taken (warn/delete → "avisado", ban/kick → "expulsado")
    try:
        action_taken = report["action_taken"]
    except (KeyError, IndexError):
        action_taken = None
    if action_taken in ("warn", "delete"):
        claves = variant_keys(_THANKS_WARN_PREFIX)
    else:
        claves = variant_keys(_THANKS_PREFIX)
    thanks_text = t(random.choice(claves), reporter=reporter_label)
    thanks_msg_id = None
    try:
        sent = await bot.send_message(
            chat_id=chat_id, text=thanks_text, message_thread_id=_hilo_guardado(report),
            parse_mode="HTML", disable_notification=True,
        )
        thanks_msg_id = sent.message_id
        log.info(
            "admin_report thanks publicado: chat=%s reporter_uid=%s",
            chat_id, report["reporter_user_id"],
        )
    except TelegramError as exc:
        log.warning("admin_report thanks fallo: %s", exc)

    db.resolve_admin_report(chat_id, report["reporter_msg_id"])

    # Programar borrado del thanks a los 5 min (lo hace el job_queue del bot)
    # Como esto se llama desde Telethon (sin context), necesitamos otra vía.
    # Solución: lo registramos en gentle_warnings para que el cleanup nightly lo limpie
    # si quedara. Pero mejor: programar via Bot API "deleteMessage" en N segundos
    # vía un job en main_app. Por simplicidad: usar aiohttp con asyncio.sleep en background.
    if thanks_msg_id:
        import asyncio
        # Guardamos la referencia: `asyncio.create_task` sin retenerla permite que
        # CPython recolecte la tarea a medio vuelo (el borrado diferido no ocurriría).
        task = asyncio.create_task(_delayed_delete(bot, chat_id, thanks_msg_id, THANKS_TTL_S))
        _BG_TASKS.add(task)
        task.add_done_callback(_BG_TASKS.discard)


# Referencias vivas a tareas en segundo plano (ver comentario en el create_task).
_BG_TASKS: set = set()


def _hilo_guardado(report) -> int | None:
    """El tema donde se escribió el @admin, si se guardó (los reportes viejos no lo tienen)."""
    try:
        return report["thread_id"]
    except (KeyError, IndexError):
        return None


async def _delayed_delete(bot, chat_id: int, msg_id: int, delay: int) -> None:
    import asyncio
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass
