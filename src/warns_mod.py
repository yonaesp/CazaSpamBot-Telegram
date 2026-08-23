"""Sistema de warnings estilo Rose.

Comandos:
  /warn (reply)       — añade warn; al alcanzar límite, ejecuta warns_action
  /warns (reply)      — lista warns activos del user
  /rmwarn (reply)     — quita el último warn
  /resetwarns (reply) — borra todos los warns del user
  /warnlimit [N]      — getter/setter del límite del chat
  /warnaction [v]     — getter/setter de la acción (kick|ban|mute)
"""
from __future__ import annotations

from . import fechas
import asyncio
import html
import logging
import time

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import borrado_diferido
from . import permissions
from .config import Config
from . import settings_sync
from .db import DB
from .i18n import t
from .federation import federate_ban

log = logging.getLogger(__name__)


def _warn_admin(func):
    """Poner y quitar warns: los admins del grupo si ese chat lo permite.

    Es moderación del día a día en grupos con varios admins, así que no puede
    depender de que esté el dueño del bot delante. Lo decide el ajuste
    `warn_quien` de cada chat (panel: Warns ▸ Quién puede warnear).

    Los ajustes de warns (`/warnlimit`, `/warnaction`) NO llevan esto: siguen
    siendo del dueño, porque cambian el castigo, no lo aplican.
    """
    return permissions.warn_admin_only(func)


def _admin_only(func):
    """Delega en `permissions.bot_admin_only`, que es la implementación canónica.

    Antes esto era una COPIA byte a byte del wrapper, repetida en dos módulos. Si
    `permissions.py` crece (por ejemplo para admitir más de un admin), las copias
    se quedarían atrás en silencio, y en una comprobación de permisos eso es lo
    último que quieres que pase sin enterarte.
    """
    return permissions.bot_admin_only(func)


def _ban_federado(db: DB, chat_id: int) -> bool:
    """¿El ban por límite de warns se replica a los demás grupos? Defecto: sí.

    Ante cualquier problema leyendo el ajuste se devuelve el defecto: la
    federación es el comportamiento que este bot lleva desde el principio, y un
    ajuste ilegible no puede cambiarlo en silencio.
    """
    try:
        s = db.get_chat_settings(chat_id)
        if s is None:
            return True
        return bool(s["warn_ban_federado"])
    except Exception as exc:  # noqa: BLE001
        log.debug("warn_ban_federado ilegible chat=%s: %s", chat_id, exc)
        return True


async def _get_target(update: Update, context, db) -> tuple[int | None, str | None]:
    """Objetivo de /warns, /rmwarn y /resetwarns.

    Antes SOLO aceptaba respuesta a un mensaje, así que `/warn @usuario` funcionaba
    y `/warns @usuario` contestaba «responde a alguien». Ahora usa la misma
    resolución que /ban: respuesta, @usuario, id o mención de alguien sin username.
    """
    msg = update.effective_message
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, u.username or u.first_name
    from .admin import _resolve_target_user
    uid, _resto, _err = await _resolve_target_user(update, context, db)
    if uid is None:
        return None, None
    nombre = db.username_of(uid) if hasattr(db, "username_of") else None
    return uid, nombre or str(uid)


@_warn_admin
async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Warna a un usuario. Acepta:
    - /warn [razón]  responding a un mensaje
    - /warn @username [razón]
    - /warn <user_id> [razón]

    Si hay reply, borra el msg warneado + el comando del admin.
    Si no hay reply, solo borra el comando admin y publica el warn.
    Si el msg warneado tenía un reporte @admin → marca action_taken='warn'.
    """
    from telegram.constants import ChatMemberStatus

    msg = update.effective_message
    db: DB = context.bot_data["db"]

    # Resolver target: reply || arg @username || arg user_id
    target_id: int | None = None
    target_user = None
    target_msg = msg.reply_to_message
    reason_parts = list(context.args) if context.args else []

    if target_msg and target_msg.from_user:
        target_user = target_msg.from_user
        target_id = target_user.id
    elif reason_parts:
        first = reason_parts[0]
        if first.lstrip("-").isdigit():
            target_id = int(first)
            reason_parts = reason_parts[1:]
        elif first.startswith("@"):
            uname = first[1:]
            target_id = db.resolve_username(uname)
            if target_id is None:
                # Fallback: getChat via API (solo si es @username público)
                try:
                    chat_obj = await context.bot.get_chat(first)
                    target_id = chat_obj.id
                except Exception as exc:  # noqa: BLE001
                    log.debug("warn get_chat(@%s) fallo: %s", uname, exc)
            reason_parts = reason_parts[1:]
        if target_id:
            try:
                member = await context.bot.get_chat_member(chat_id=msg.chat_id, user_id=target_id)
                target_user = member.user
            except Exception as exc:  # noqa: BLE001
                log.debug("warn get_chat_member chat=%s user=%s fallo: %s", msg.chat_id, target_id, exc)

    if not target_id:
        await msg.reply_text(
            t("warn.usage"), parse_mode="HTML",
        )
        return

    # GUARD: nunca warnear a un admin del chat
    try:
        member = await context.bot.get_chat_member(chat_id=msg.chat_id, user_id=target_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await msg.reply_text(
                t("warn.is_admin"), parse_mode="HTML",
            )
            return
    except Exception as exc:  # noqa: BLE001
        log.debug("warn admin-guard get_chat_member fallo chat=%s user=%s: %s",
                  msg.chat_id, target_id, exc)

    reason = " ".join(reason_parts) if reason_parts else None

    # Borrar el comando /warn del admin (esto sí es propio del comando)
    try:
        await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
    except TelegramError:
        pass

    await aplicar_warn(
        context, chat_id=msg.chat_id, target_id=target_id, target_user=target_user,
        by_admin=update.effective_user.id, reason=reason,
        target_msg_id=(target_msg.message_id if target_msg else None),
    )


async def aplicar_warn(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    target_id: int,
    target_user,
    by_admin: int,
    reason: str | None,
    target_msg_id: int | None = None,
) -> int:
    """Pone un warn y hace TODO lo que conlleva: contar, borrar el mensaje
    infractor, publicarlo en el grupo y ejecutar la acción configurada al llegar
    al límite. Devuelve el número de warns que tiene ya el usuario.

    Está extraído de `cmd_warn` para que cualquier otra vía (por ejemplo el botón
    «⚠️ Avisar» del aviso de usuario de confianza) haga EXACTAMENTE lo mismo. Antes
    ese botón solo llamaba a `db.add_warn`: el usuario no se enteraba de nada y no
    se comprobaba el límite, así que su tercer warn de tres no ejecutaba la sanción
    configurada y el contador seguía subiendo.
    """

    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    db.ensure_chat_settings(chat_id)
    settings = db.get_chat_settings(chat_id)

    n = db.add_warn(target_id, chat_id, by_admin, reason)
    limit = settings["warns_limit"] or 3
    action = settings["warns_action"] or "ban"

    # Marcar admin_report si existía → cascade usará template warn-específico
    if target_msg_id:
        db.mark_admin_report_action(chat_id, target_msg_id, "warn")

    # Mención clicable al user warneado
    if target_user and getattr(target_user, "username", None):
        mention = f"@{target_user.username}"
    elif target_user:
        display = html.escape(getattr(target_user, "first_name", None) or str(target_id))
        mention = f'<a href="tg://user?id={target_id}">{display}</a>'
    else:
        mention = f'<a href="tg://user?id={target_id}">user</a>'

    # Borrar el mensaje infractor, si se sabe cuál es
    if target_msg_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=target_msg_id)
        except TelegramError:
            pass

    # `sancion_ok` se inicializa AQUÍ y no dentro de cada rama. Antes solo lo hacían
    # kick y mute, así que con la acción por defecto (ban) la lectura de más abajo
    # lanzaba NameError: el ban se ejecutaba, pero el contador no se reseteaba, el
    # grupo no veía el aviso y al admin le llegaba un «error interno del bot».
    sancion_ok = True

    if n >= limit:
        if action == "ban":
            motivo_ban = t("reason.warns_limit", n=n, limit=limit,
                           last_reason=reason or t("reason.no_reason"))
            # ¿El ban sale de este grupo? Por defecto sí: quien acumula warns por
            # spam los acumularía igual en los demás. Se puede dejar en local
            # desde el panel (Warns ▸ Alcance del ban), que es lo prudente si los
            # admins de los grupos pueden warnear y no todos son de tu confianza.
            if _ban_federado(db, chat_id):
                results = await federate_ban(
                    context.bot, db, user_id=target_id, reason=motivo_ban,
                    rule="warns_limit", triggered_in_chat=chat_id, shadow=cfg.shadow,
                )
            else:
                results = {chat_id: "shadow"}
                if not cfg.shadow:
                    try:
                        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
                        results = {chat_id: "ok"}
                        db.add_ban(user_id=target_id, reason=motivo_ban, rule="warns_limit",
                                   banned_in_chat=chat_id, federated=False)
                    except TelegramError as exc:
                        log.warning("warn ban local fallo chat=%s: %s", chat_id, exc)
                        results = {chat_id: f"error: {exc}"}
            ok = sum(1 for v in results.values() if v == "ok")
            sancion_ok = ok > 0
            text = t("warn.limit_ban", mention=mention, n=n, limit=limit, ok=ok)
            if reason:
                text += t("warn.last_reason", reason=html.escape(reason))
        elif action == "kick":
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
                await asyncio.sleep(0.5)
                await context.bot.unban_chat_member(
                    chat_id=chat_id, user_id=target_id, only_if_banned=True,
                )
            except TelegramError as exc:
                sancion_ok = False
                log.warning("warn kick fallo: %s", exc)
            text = t("warn.limit_kick" if sancion_ok else "warn.limit_kick_fail",
                     mention=mention, n=n, limit=limit)
        elif action == "mute":
            from telegram import ChatPermissions
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id, user_id=target_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=int(time.time()) + 86400,
                )
            except TelegramError as exc:
                sancion_ok = False
                log.warning("warn mute fallo: %s", exc)
            text = t("warn.limit_mute" if sancion_ok else "warn.limit_mute_fail",
                     mention=mention, n=n, limit=limit)
        else:
            text = t("warn.counter", mention=mention, n=n, limit=limit)
        # Solo se limpian los warns si la sanción se aplicó de verdad. Si no, el
        # grupo veía «Kick» y el contador volvía a 0 sin haber sancionado a nadie.
        if sancion_ok:
            db.reset_warns(target_id, chat_id)
    else:
        text = t("warn.counter", mention=mention, n=n, limit=limit)
        if reason:
            text += t("warn.reason_line", reason=html.escape(reason))

    try:
        sent = await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML", disable_notification=False,
        )
    except TelegramError as exc:
        log.warning("warn publish fallo: %s", exc)
        return n
    # Auto-borrado, para no ensuciar el chat con el histórico de warns.
    delete_after = getattr(cfg, "public_quip_delete_after_s", 10800) if cfg else 10800
    jq = context.application.job_queue
    if jq is not None and delete_after > 0:
        jq.run_once(
            borrado_diferido.borrar_mensaje_job, when=delete_after,
            data={"chat_id": chat_id, "message_id": sent.message_id},
            name=f"del_warn_{chat_id}_{sent.message_id}",
        )
    return n


@_warn_admin
async def cmd_warns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, target_name = await _get_target(update, context, context.bot_data["db"])
    if not target_id:
        await msg.reply_text(t("warns.reply_needed"))
        return
    db: DB = context.bot_data["db"]
    warns = db.list_warns(target_id, msg.chat_id)
    if not warns:
        await msg.reply_text(t("warns.none", name=html.escape(target_name or str(target_id))))
        return
    db.ensure_chat_settings(msg.chat_id)
    settings = db.get_chat_settings(msg.chat_id)
    limit = settings["warns_limit"] or 3
    lines = [f"⚠️ <b>{html.escape(target_name or str(target_id))}</b>: {len(warns)}/{limit} warns"]
    for w in warns:
        ts = fechas.cuando(w["ts"], "%Y-%m-%d %H:%M")
        r = w["reason"] or "(sin razón)"
        lines.append(f"  [{ts}] {html.escape(r)}")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")


@_warn_admin
async def cmd_rmwarn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, _ = await _get_target(update, context, context.bot_data["db"])
    if not target_id:
        await msg.reply_text(t("rmwarn.reply_needed"))
        return
    db: DB = context.bot_data["db"]
    ok = db.remove_last_warn(target_id, msg.chat_id)
    if ok:
        await msg.reply_text(t("rmwarn.done"))
    else:
        await msg.reply_text(t("rmwarn.none"))


@_warn_admin
async def cmd_resetwarns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    target_id, _ = await _get_target(update, context, context.bot_data["db"])
    if not target_id:
        await msg.reply_text(t("resetwarns.reply_needed"))
        return
    db: DB = context.bot_data["db"]
    n = db.reset_warns(target_id, msg.chat_id)
    await msg.reply_text(t("resetwarns.done", n=n))


@_admin_only
async def cmd_warnlimit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        await update.effective_message.reply_text(t("warnlimit.current", limit=s["warns_limit"]), parse_mode="HTML")
        return
    if not context.args[0].isdigit():
        await update.effective_message.reply_text(t("warnlimit.usage"))
        return
    n = max(1, min(20, int(context.args[0])))
    # Vía settings_sync, no `db.update_chat_setting` directo: con /sync ON el
    # panel propaga a todos los grupos y el comando no lo hacía, así que el MISMO
    # ajuste acababa en sitios distintos según por dónde lo tocaras.
    settings_sync.apply_setting(db, chat_id, "warns_limit", n)
    await update.effective_message.reply_text(t("warnlimit.set", n=n))


@_admin_only
async def cmd_warnaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        await update.effective_message.reply_text(t("warnaction.current", action=s["warns_action"]), parse_mode="HTML")
        return
    action = context.args[0].lower()
    if action not in ("ban", "kick", "mute"):
        await update.effective_message.reply_text(t("warnaction.usage"))
        return
    # Vía settings_sync, no `db.update_chat_setting` directo: con /sync ON el
    # panel propaga a todos los grupos y el comando no lo hacía, así que el MISMO
    # ajuste acababa en sitios distintos según por dónde lo tocaras.
    settings_sync.apply_setting(db, chat_id, "warns_action", action)
    await update.effective_message.reply_text(t("warnaction.set", action=action))
