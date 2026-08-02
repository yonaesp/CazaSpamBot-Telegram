"""Comandos admin del bot. Solo accesibles desde ADMIN_USER_ID."""
from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from telegram.error import TelegramError

from . import chat_picker, learning, notify_prefs, permissions, quips, settings_sync, trust as _trust
from .config import Config
from .db import DB
from .federation import federate_ban, unfederate_ban
from .i18n import t

log = logging.getLogger(__name__)


def _only_admin(func):
    """Alias retrocompatible: solo bot admin (ADMIN_USER_ID) puede modificar."""
    return permissions.bot_admin_only(func)


def _read_admin(func):
    """Read-only: bot admin O admin de cualquier chat moderado."""
    return permissions.chat_admin_or_bot_admin(func)


@_read_admin
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    s = db.stats()
    mode_emoji = "🌒" if cfg.shadow else "🔴"
    on, off = t("admin.on"), t("admin.off")
    await update.effective_message.reply_text(
        t(
            "admin.start",
            mode_emoji=mode_emoji,
            mode=cfg.mode,
            federation=on if cfg.federation_enabled else off,
            cas=on if cfg.cas_enabled else off,
            reactions=on if cfg.reaction_farming_enabled else off,
            scripts=", ".join(cfg.allowed_scripts),
            chats=s["chats"],
            seen_users=s["seen_users"],
            banned=s["banned"],
            actions_24h=s["actions_24h"],
        ),
        parse_mode="HTML",
    )


@_read_admin
async def cmd_comandos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/comandos: muestra lista completa a admins de chat o bot admin.
    Para users normales: silencio (la info pública está en el mensaje anclado).
    """
    await cmd_help(update, context)


@_read_admin
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guía completa para admins: cómo funciona el bot + referencia de comandos.
    Se envía en varios mensajes para que sea legible. Admins de chat ven todo en
    lectura; solo el bot admin puede ejecutar los que modifican.
    """
    u = update.effective_user
    is_bot_admin_user = permissions.is_bot_admin(context, u.id) if u else False
    msg = update.effective_message

    # --- Mensaje 1: cómo funciona el bot (i18n) ---
    await msg.reply_text(t("help.msg1"), parse_mode="HTML", disable_web_page_preview=True)
    note = "" if is_bot_admin_user else t("help.note")
    # --- Mensaje 2: referencia de comandos (i18n) ---
    await msg.reply_text(t("help.msg2") + note, parse_mode="HTML")


async def _add_sample_with_ux(
    update: Update, context: ContextTypes.DEFAULT_TYPE, label: str,
) -> None:
    """Lógica común para /spam y /legal: añade muestra al clasificador,
    borra el comando del admin (en grupos) y envía confirmación efímera.

    label: 'spam' o 'ham' (legítimo).
    """
    msg = update.effective_message
    is_group = bool(msg and msg.chat and msg.chat.type in ("group", "supergroup"))
    db: DB = context.bot_data["db"]

    cmd = "legal" if label == "ham" else "spam"
    if not msg.reply_to_message:
        usage = t(
            "admin.sample_usage",
            cmd=cmd,
            label=t("sample.label_ham") if label == "ham" else t("sample.label_spam"),
        )
        await msg.reply_text(usage, parse_mode="HTML")
        return

    target = msg.reply_to_message
    text = target.text or target.caption or ""
    if not text or len(text) < 5:
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, t("sample.ignored_ack", cmd=cmd))
        else:
            await msg.reply_text(t("sample.no_text"))
        return

    norm = learning.normalize(text)
    h = learning.text_hash(norm)
    added = db.add_sample(
        text_norm=norm, text_hash=h, label=label,
        added_by=update.effective_user.id, chat_id=msg.chat_id,
        source_user=target.from_user.id if target.from_user else None,
    )
    status = t("sample.status_added") if added else t("sample.status_dup")
    emoji = "🛑" if label == "spam" else "✅"
    label_txt = t("sample.label_spam") if label == "spam" else t("sample.label_ham")

    if is_group:
        # Borrar el comando del admin del grupo y confirmar al admin por DM
        await _delete_command_safely(update)
        ack = t(
            "sample.ack_group",
            emoji=emoji, label=label_txt, status=status,
            chat=msg.chat.title or msg.chat_id, text=text[:200],
        )
        await _notify_admin_ack(context, ack)
    else:
        await msg.reply_text(
            t("sample.ack_dm", emoji=emoji, label=label_txt, status=status),
            parse_mode="HTML",
        )


async def _spam_combo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/spam` en reply: combo de máxima confianza (lo ordena un admin humano):
    ban federado al autor + reporte oficial vía la cuenta Telethon + muestra al
    clasificador + borrado del mensaje + quip público.

    Necesita un reply: el autor a banear y el texto a aprender salen del mensaje.
    Para banear por @usuario sin un mensaje, usa /ban.
    """
    msg = update.effective_message
    is_group = bool(msg and msg.chat and msg.chat.type in ("group", "supergroup"))
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]

    if not msg.reply_to_message:
        await msg.reply_text(t("spam.usage"), parse_mode="HTML")
        return

    target = msg.reply_to_message
    text = target.text or target.caption or ""
    author = target.from_user

    # 1) Aprender (solo si hay texto suficiente)
    sample_note = t("admin.spam.note_no_text")
    if text and len(text) >= 5:
        norm = learning.normalize(text)
        added = db.add_sample(
            text_norm=norm, text_hash=learning.text_hash(norm), label="spam",
            added_by=update.effective_user.id, chat_id=msg.chat_id,
            source_user=author.id if author else None,
        )
        sample_note = t("admin.spam.note_saved") if added else t("admin.spam.note_dup")

    # Borrar el comando del admin del grupo cuanto antes
    if is_group:
        await _delete_command_safely(update)

    # Sin autor resoluble (forward anónimo / post de canal): solo aprende.
    if author is None or author.is_bot:
        ack = t("admin.spam.no_author", note=sample_note)
        if is_group:
            await _notify_admin_ack(context, ack)
        else:
            await msg.reply_text(ack)
        return

    # GUARD: no banear admins de ningún chat federado
    from telegram.constants import ChatMemberStatus
    for chat_row in db.all_chats():
        if not chat_row["am_admin"]:
            continue
        try:
            member = await context.bot.get_chat_member(
                chat_id=chat_row["chat_id"], user_id=author.id,
            )
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                warn = t(
                    "admin.spam.is_admin",
                    name=author.first_name, uid=author.id,
                    chat=chat_row["title"], note=sample_note,
                )
                if is_group:
                    await _notify_admin_ack(context, warn)
                else:
                    await msg.reply_text(warn, parse_mode="HTML")
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("/spam admin-guard fallo chat=%s: %s", chat_row["chat_id"], exc)

    # 2) Reporte oficial ANTES del ban (no bloquea; el msg aún existe). Manual
    # del admin = máxima confianza, así que reporta sin pasar por la whitelist
    # de reglas automáticas (el rate-limit del reporter sigue aplicando).
    if not cfg.shadow:
        reporter = context.bot_data.get("reporter")
        if reporter is not None and reporter.reporting_ready():
            reporter.enqueue(
                chat_id=msg.chat_id, user_id=author.id,
                message_id=target.message_id, reason="spam",
                # El marcador [regla] va FUERA del i18n: es el formato técnico que
                # usa el resto de reportes (handlers._apply_action), no texto a leer.
                detail="[manual_admin_spam] " + t("reason.manual_admin_spam_report"),
            )

    # 3) Ban federado
    results = await federate_ban(
        context.bot, db, user_id=author.id,
        reason=t("reason.manual_admin_spam"),
        rule="manual_admin_ban",
        triggered_in_chat=msg.chat_id, shadow=cfg.shadow,
    )
    ok = sum(1 for v in results.values() if v == "ok")
    shadow = sum(1 for v in results.values() if v == "shadow")
    err = sum(1 for v in results.values() if v.startswith("error"))

    # 4) Borrar el mensaje original del spammer + welcome huérfano
    if not cfg.shadow:
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=target.message_id)
        except TelegramError:
            pass
        await _cleanup_welcome_on_ban(context, db, author.id)

    # 5) Quip público SOLO en el chat actual
    if is_group and not cfg.shadow and quips.quips_on(db, msg.chat_id, cfg):
        quip = quips.pick(
            rule="manual_admin_ban", username=author.username,
            user_id=author.id, payload={}, first_name=author.first_name,
        )
        if quip:
            await _post_ban_quip_to_chats(
                context, chats=[msg.chat_id], text=quip,
                delete_after=cfg.public_quip_delete_after_s,
            )

    # 6) Ack al admin
    ack = t(
        "admin.spam.ack",
        name=author.first_name, uid=author.id,
        ok=ok, shadow=shadow, err=err, note=sample_note,
    )
    if is_group:
        await _notify_admin_ack(context, ack)
    else:
        await msg.reply_text(ack)


@permissions.bot_admin_only
async def cmd_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/spam` (reply): ban federado + reporte oficial + muestra al clasificador.

    Solo el admin del bot: banea y reporta (escritura), no es comando de lectura.
    """
    await _spam_combo(update, context)


@permissions.bot_admin_only
async def cmd_legal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marca el mensaje al que responde como LEGÍTIMO (alias antes era /ham).

    Solo el admin del bot: modifica el clasificador (escritura).
    """
    await _add_sample_with_ux(update, context, label="ham")


# Alias retro: /ham → mismo comportamiento que /legal
cmd_ham = cmd_legal


@_read_admin
async def cmd_samples(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/samples` muestra stats. `/samples spam 20` lista últimas 20 spam."""
    db: DB = context.bot_data["db"]
    if not context.args:
        c = db.sample_count()
        await update.effective_message.reply_text(
            t("samples.stats", spam=c["spam"], ham=c["ham"]),
            parse_mode="HTML",
        )
        return
    label = context.args[0].lower()
    if label not in ("spam", "ham"):
        await update.effective_message.reply_text(t("samples.usage"))
        return
    n = 20
    if len(context.args) > 1 and context.args[1].isdigit():
        n = max(1, min(50, int(context.args[1])))
    rows = db.list_samples(label=label, limit=n)
    if not rows:
        await update.effective_message.reply_text(t("samples.empty", label=label))
        return
    import datetime as _dt
    import html as _html
    lines = [t("samples.list_header", n=n, label=label)]
    for r in rows:
        ts = _dt.datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        txt = (r["text_norm"] or "")[:80]
        lines.append(f"<code>#{r['id']}</code> [{ts}] {_html.escape(txt)}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_only_admin
async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra una muestra del clasificador."""
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(t("forget.usage"))
        return
    sid = int(context.args[0])
    db: DB = context.bot_data["db"]
    ok = db.delete_sample(sid)
    if ok:
        await update.effective_message.reply_text(t("forget.done", sid=sid))
    else:
        await update.effective_message.reply_text(t("forget.notfound", sid=sid))


async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mensajes no-comando en DM: si soy el admin → hint suave; si no → ignorar."""
    cfg: Config = context.bot_data["cfg"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return  # silent ignore para no-admins
    # ¿Hay una edición de texto pendiente del panel /config? (botón ✏️/📜)
    from . import config_panel
    if await config_panel.handle_capture(update, context):
        return
    # ¿Un /scan esperando el mensaje? Va DESPUÉS del panel: una edición pendiente es
    # más específica (el admin acaba de pulsar un botón concreto) y no debe perderse.
    from . import scan_cmd
    if await scan_cmd.handle_capture(update, context):
        return
    await update.effective_message.reply_text(t("dm.hint"), parse_mode="HTML")


async def _render_chat_stats(db: DB, chat_id: int | None = None) -> str:
    """Si chat_id=None devuelve stats globales. Si no, stats de ese chat."""
    if chat_id is None:
        s = db.stats()
        return t(
            "admin.stats.global",
            chats=s["chats"], seen_users=s["seen_users"],
            banned=s["banned"], actions_24h=s["actions_24h"],
        )
    # Por chat
    chat_row = next((c for c in db.all_chats() if c["chat_id"] == chat_id), None)
    title = (chat_row["title"] if chat_row else str(chat_id))
    import time as _t
    import html as _h
    with db._cur() as c:
        users = c.execute("SELECT COUNT(*) AS n FROM seen_users WHERE chat_id=?", (chat_id,)).fetchone()["n"]
        msgs = c.execute("SELECT COALESCE(SUM(msg_count),0) AS n FROM seen_users WHERE chat_id=?", (chat_id,)).fetchone()["n"]
        actions24 = c.execute(
            "SELECT COUNT(*) AS n FROM moderation_log WHERE chat_id=? AND ts>=?",
            (chat_id, _t.time() - 86400),
        ).fetchone()["n"]
        warns = c.execute("SELECT COUNT(*) AS n FROM user_warns WHERE chat_id=?", (chat_id,)).fetchone()["n"]
        pending = c.execute(
            "SELECT COUNT(*) AS n FROM pending_verifications WHERE chat_id=? AND verified_at IS NULL",
            (chat_id,),
        ).fetchone()["n"]
    return t(
        "admin.stats.chat",
        title=_h.escape(title), chat_id=chat_id,
        users=users, msgs=msgs, warns=warns,
        pending=pending, actions24=actions24,
    )


async def _stats_picker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    text = await _render_chat_stats(db, chat_id)
    await update.callback_query.edit_message_text(text, parse_mode="HTML")


@_read_admin
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if chat_picker.is_dm(update) and not context.args:
        await chat_picker.show_chat_picker(update, context, "stats")
        return
    # En grupo o con arg explícito: stats del chat actual
    chat_id = update.effective_chat.id if not chat_picker.is_dm(update) else None
    if context.args and context.args[0].lstrip("-").isdigit():
        chat_id = int(context.args[0])
    text = await _render_chat_stats(db, chat_id)
    await update.effective_message.reply_text(text, parse_mode="HTML")


@_read_admin
async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    rows = db.all_chats()
    if not rows:
        await update.effective_message.reply_text(t("chats.empty"))
        return
    lines = [t("chats.header")]
    for r in rows:
        admin_mark = "✅" if r["am_admin"] else "❌"
        perms = []
        if r["can_restrict"]:
            perms.append("restrict")
        if r["can_delete"]:
            perms.append("delete")
        lines.append(
            f"{admin_mark} <code>{r['chat_id']}</code> · {html.escape(r['title'] or '?')} ({r['type']}) [{','.join(perms) or t('chats.no_perms')}]"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_read_admin
async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    n = 10
    if context.args and context.args[0].isdigit():
        n = max(1, min(50, int(context.args[0])))
    rows = db.recent_actions(limit=n)
    if not rows:
        await update.effective_message.reply_text(t("recent.empty"))
        return
    lines = [t("recent.header", n=n)]
    import datetime as _dt
    for r in rows:
        ts = _dt.datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        lines.append(
            f"[{ts}] <code>{r['action']}</code> user=<code>{r['user_id']}</code> "
            f"chat=<code>{r['chat_id']}</code> rule={html.escape(r['rule'])} "
            f"spam={_trust.render_spam(r['score'])} mode={r['mode']}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_only_admin
async def cmd_shadow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] not in ("on", "off"):
        await update.effective_message.reply_text(t("shadow.usage"))
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    new_mode = "shadow" if context.args[0] == "on" else "active"
    # Hot-swap del Config (no es frozen idealmente, pero replicamos atributo)
    object.__setattr__(cfg, "mode", new_mode)
    # Y PERSISTIR: sin esto el cambio vivía solo en memoria y el siguiente reinicio
    # devolvía el bot al modo del .env sin avisar. Alguien que pasara a activo y
    # reiniciara se quedaba sin moderación creyendo que la tenía.
    db.set_pref("mode_shadow", new_mode == "shadow")
    await update.effective_message.reply_text(t("shadow.changed", mode=new_mode), parse_mode="HTML")
    log.warning("Modo cambiado en runtime a %s por admin %s", new_mode, update.effective_user.id)


async def _resolve_target_user(
    update: Update, context: ContextTypes.DEFAULT_TYPE, db: DB,
) -> tuple[int | None, list[str], str | None]:
    """Resuelve el user objetivo de un comando admin (/ban, /unban).

    Acepta:
      1. Reply a un mensaje → user_id del autor del mensaje respondido.
      2. text_mention entity → user SIN username mencionado con @nombre
         (Telegram incrusta el objeto User con su id en la entidad).
      3. Primer arg numérico (con o sin signo) → user_id directo.
      4. Primer arg @username → cache local → Bot API → Telethon.

    Devuelve (user_id_o_None, args_restantes, error_msg_o_None).
    """
    msg = update.effective_message
    args = list(context.args or [])

    # 1) Reply
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        # Cachear username si vino con uno
        if target.username:
            db.remember_username(target.username, target.id)
        return target.id, args, None

    # 2) text_mention: usuarios SIN username. Al escribir @nombre y elegirlos
    # del autocompletado, Telegram incrusta una entidad text_mention con el
    # objeto User (id incluido). Es la forma fiable de resolverlos.
    entities = getattr(msg, "entities", None) if msg else None
    if entities:
        for ent in entities:
            if ent.type == "text_mention" and ent.user:
                if ent.user.username:
                    db.remember_username(ent.user.username, ent.user.id)
                # rest = args sin el texto mencionado (aprox: quitamos el primero)
                return ent.user.id, args[1:] if args else [], None

    if not args:
        return None, args, None

    first = args[0]
    rest = args[1:]

    # 2) Numérico
    if first.lstrip("-").isdigit():
        return int(first), rest, None

    # 3) Username (@nombre o nombre pelado)
    uname = first.lstrip("@").strip()
    if not uname:
        return None, args, t("admin.resolve.empty_arg")
    # 3a) Cache local
    uid = db.resolve_username(uname)
    if uid is not None:
        return uid, rest, None
    # 3b) Fallback Bot API (solo resuelve usernames públicos que el bot ya vio)
    try:
        chat = await context.bot.get_chat(f"@{uname}")
        if chat and chat.id:
            db.remember_username(uname, chat.id)
            return chat.id, rest, None
    except TelegramError as exc:
        log.debug("get_chat(@%s) fallo, intento Telethon: %s", uname, exc)
    # 3c) Fallback Telethon: resuelve usernames que la Bot API no puede
    # (la Bot API solo resuelve los que el bot ya ha encontrado; Telethon
    # resuelve cualquier @username público fiablemente).
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is not None:
        try:
            entity = await client.get_entity(f"@{uname}")
            if entity and getattr(entity, "id", None):
                db.remember_username(uname, entity.id)
                return int(entity.id), rest, None
        except Exception as exc:  # noqa: BLE001
            log.debug("Telethon get_entity(@%s) fallo: %s", uname, exc)
    return None, args, t("admin.resolve.unresolved", username=uname)


async def _delete_command_safely(update: Update) -> None:
    """Borra el mensaje del comando del admin (solo aplica en grupos)."""
    msg = update.effective_message
    if not msg:
        return
    try:
        await msg.delete()
    except TelegramError as exc:
        log.debug("No pude borrar comando admin msg=%s: %s", msg.message_id, exc)


async def _cleanup_welcome_on_ban(context: ContextTypes.DEFAULT_TYPE, db: DB, user_id: int) -> None:
    """Borra la bienvenida del baneado. Delega en la limpieza compartida.

    Antes esta función solo miraba `pending_verifications`, así que con la
    verificación desactivada (que es el modo por defecto) no encontraba nada y la
    bienvenida se quedaba en el grupo saludando a alguien ya expulsado.
    """
    from . import verification
    await verification.limpiar_bienvenidas(context, db, user_id)


async def _notify_admin_ack(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Ack técnico al admin (resultado de /ban, /unban, /spam...). SIEMPRE debe llegar.

    Antes salía ÚNICAMENTE por el notificador externo, que es OPCIONAL: sin
    configurar, `send_text` devuelve False sin enviar nada y el admin se quedaba a
    ciegas. Caso real: un `/ban` en respuesta a un mensaje baneó y federó
    correctamente, pero desde fuera solo se vio desaparecer el comando. Con los
    quips desactivados por defecto tampoco salía nada en el grupo, así que el
    moderador no tenía forma de saber si había funcionado o si el bot estaba roto.

    Ahora hay respaldo: si el notificador externo no está o falla, escribe el
    propio bot por privado. Un comando de moderación sin respuesta es un fallo,
    aunque la acción se haya ejecutado bien.
    """
    notifier = context.bot_data.get("notifier")
    if notifier is not None:
        try:
            if await notifier.send_text(text):
                return
        except Exception as exc:  # noqa: BLE001
            log.warning("notifier ack falló, se usa el propio bot: %s", exc)

    cfg = context.bot_data.get("cfg")
    destino = (getattr(cfg, "admin_notify_chat_id", None)
               or getattr(cfg, "admin_user_id", None))
    if not destino:
        log.warning("ack sin destino: ni notificador externo ni admin_notify_chat_id")
        return
    try:
        await context.bot.send_message(
            chat_id=destino, text=text, parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.warning("ack por el propio bot falló: %s", exc)


@_only_admin
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban federado (replica a TODOS los chats donde el bot es admin) + quip público con autoborrado.

    Si se ejecuta en grupo: borra el comando del admin, publica solo el quip (con motivo
    si se dio) y manda el resumen técnico por DM al admin (bot de notificaciones externo).
    """
    db: DB = context.bot_data["db"]
    is_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    user_id, args_remaining, resolve_err = await _resolve_target_user(update, context, db)
    if user_id is None:
        # Error de resolución: si grupo, borrar comando + avisar admin por DM; si DM, contestar inline.
        usage = (
            t("admin.ban.usage")
            + (f"\n⚠️ {resolve_err}" if resolve_err else "")
        )
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, t(
                "admin.cmd_invalid", cmd="ban",
                error=resolve_err or t("admin.resolve.missing_arg"),
            ))
        else:
            await update.effective_message.reply_text(usage, parse_mode="HTML")
        return
    reason_raw = " ".join(args_remaining).strip()
    reason = reason_raw or t("reason.manual_ban_admin")
    has_explicit_reason = bool(reason_raw)
    cfg: Config = context.bot_data["cfg"]

    # GUARD: no banear admins de NINGÚN chat federado
    from telegram.constants import ChatMemberStatus
    for chat_row in db.all_chats():
        if not chat_row["am_admin"]:
            continue
        try:
            member = await context.bot.get_chat_member(
                chat_id=chat_row["chat_id"], user_id=user_id,
            )
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                warn = t("admin.ban.is_admin", uid=user_id, chat=chat_row["title"])
                if is_group:
                    await _delete_command_safely(update)
                    await _notify_admin_ack(context, warn)
                else:
                    await update.effective_message.reply_text(warn, parse_mode="HTML")
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("ban admin-guard get_chat_member fallo chat=%s user=%s: %s",
                      chat_row["chat_id"], user_id, exc)

    # Resolver nombre amigable
    username = None
    first_name = None
    seen = db.get_seen(update.effective_chat.id, user_id) if update.effective_chat else None
    if seen:
        username = seen["username"]
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id, user_id=user_id,
        )
        if chat_member and chat_member.user:
            first_name = chat_member.user.first_name
            username = username or chat_member.user.username
    except Exception as exc:  # noqa: BLE001
        log.debug("ban resolve name get_chat_member fallo user=%s: %s", user_id, exc)

    # Borrar el comando del admin (en grupo) ANTES de ejecutar el ban para
    # que el grupo no vea el "/ban @x razón" mientras se procesa
    objetivo_msg = update.effective_message.reply_to_message if update.effective_message else None
    if is_group:
        await _delete_command_safely(update)
        # Borrar TAMBIÉN el mensaje al que se respondió: banear al spammer y dejar
        # su spam a la vista no tiene sentido. Solo con reply, claro: con /ban por
        # @usuario no hay ningún mensaje concreto que borrar.
        if objetivo_msg is not None and not cfg.shadow:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id, message_id=objetivo_msg.message_id)
            except TelegramError as exc:
                log.debug("no se pudo borrar el mensaje baneado: %s", exc)

    results = await federate_ban(
        context.bot, db, user_id=user_id, reason=reason, rule="manual_admin_ban",
        triggered_in_chat=update.effective_chat.id if update.effective_chat else None,
        shadow=cfg.shadow,
    )
    ok = sum(1 for v in results.values() if v == "ok")
    shadow = sum(1 for v in results.values() if v == "shadow")
    err = sum(1 for v in results.values() if v.startswith("error"))
    ack = t("admin.ban.ack", uid=user_id, ok=ok, shadow=shadow, err=err)
    # Auditoría obligatoria: sin esto un ban manual quedaba en `banned_users` pero
    # NO en `moderation_log`, así que no salía en /recent ni contaba en /stats.
    # La regla del proyecto pide persistir TODA acción de moderación, shadow o real.
    db.log_action(
        chat_id=(update.effective_chat.id if update.effective_chat else 0),
        user_id=user_id, username=username,
        message_id=(update.effective_message.message_id if update.effective_message else 0),
        rule="manual_admin_ban", action="ban", score=0,
        mode=("shadow" if cfg.shadow else "active"),
        payload={"reason": reason, "chats_ok": ok, "chats_error": err},
    )
    # Borrar welcome huérfano del baneado si seguía pendiente
    if not cfg.shadow:
        await _cleanup_welcome_on_ban(context, db, user_id)
    if is_group:
        await _notify_admin_ack(context, ack)
    else:
        await update.effective_message.reply_text(ack, parse_mode="HTML")

    # Aviso público con el MOTIVO. Va aparte de los quips a propósito: los quips
    # son la capa de humor, opaca por diseño y desactivada por defecto. Escribir un
    # motivo a mano es otra cosa: es el admin decidiendo que el grupo lo sepa. Por
    # eso el motivo actúa como consentimiento, y sin motivo el ban sigue mudo.
    # Sin enlace al perfil (regla 6): nombre + id, para no dar visibilidad al spammer.
    if is_group and not cfg.shadow and has_explicit_reason:
        nombre = html.escape(first_name or username or str(user_id))
        await _post_ban_quip_to_chats(
            context, chats=[update.effective_chat.id],
            text=t("admin.ban.public_notice", name=nombre, uid=user_id,
                   reason=html.escape(reason)),
            delete_after=cfg.ban_notice_delete_after_s,
        )

    # Quip público SOLO en el chat donde se ejecutó /ban (no en todos los federados).
    # Si /ban se ejecuta desde DM con el bot → ban silencioso sin publicar en grupos.
    elif is_group and not cfg.shadow and quips.quips_on(db, update.effective_chat.id, cfg):
        quip = quips.pick(
            rule="manual_admin_ban", username=username, user_id=user_id,
            payload={"reason": reason}, first_name=first_name,
        )
        if quip:
            text = quip
            if has_explicit_reason:
                text += t("admin.quip_reason", reason=reason)
            await _post_ban_quip_to_chats(
                context, chats=[update.effective_chat.id],
                text=text,
                delete_after=cfg.public_quip_delete_after_s,
            )


async def _post_ban_quip_to_chats(
    context: ContextTypes.DEFAULT_TYPE,
    chats: list[int],
    text: str,
    delete_after: int,
) -> None:
    """Publica el quip de ban con consolidación de ráfaga (vía ban_announce)."""
    from . import ban_announce
    for chat_id in chats:
        await ban_announce.announce_ban(
            context, chat_id=chat_id, quip_text=text, delete_after=delete_after,
        )


@_only_admin
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    is_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    user_id, args_remaining, resolve_err = await _resolve_target_user(update, context, db)
    if user_id is None:
        usage = (
            t("admin.unban.usage")
            + (f"\n⚠️ {resolve_err}" if resolve_err else "")
        )
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, t(
                "admin.cmd_invalid", cmd="unban",
                error=resolve_err or t("admin.resolve.missing_arg"),
            ))
        else:
            await update.effective_message.reply_text(usage, parse_mode="HTML")
        return
    reason_raw = " ".join(args_remaining).strip()
    has_explicit_reason = bool(reason_raw)
    # Resolver nombre amigable (mismo patrón que /ban)
    username = None
    first_name = None
    seen = db.get_seen(update.effective_chat.id, user_id) if update.effective_chat else None
    if seen:
        username = seen["username"]
        first_name = seen["first_name"] if "first_name" in seen.keys() else None
    if is_group:
        await _delete_command_safely(update)
    results = await unfederate_ban(
        context.bot, db, user_id=user_id,
        revoked_by=update.effective_user.id, shadow=cfg.shadow,
    )
    ok = sum(1 for v in results.values() if v == "ok")
    err = sum(1 for v in results.values() if v.startswith("error"))
    ack = t("admin.unban.ack", uid=user_id, ok=ok, err=err)
    # Misma auditoría obligatoria que el ban: levantar un ban es una acción de
    # moderación, y sin registro no hay forma de saber quién ni cuándo.
    db.log_action(
        chat_id=(update.effective_chat.id if update.effective_chat else 0),
        user_id=user_id, username=None,
        message_id=(update.effective_message.message_id if update.effective_message else 0),
        rule="manual_admin_unban", action="noop", score=0,
        mode="active", payload={"chats_ok": ok, "chats_error": err},
    )
    if is_group:
        await _notify_admin_ack(context, ack)
    else:
        await update.effective_message.reply_text(ack, parse_mode="HTML")

    # Quip público de unban en el chat donde se ejecutó
    if is_group and not cfg.shadow and quips.quips_on(db, update.effective_chat.id, cfg):
        quip = quips.pick(
            rule="manual_admin_unban", username=username, user_id=user_id,
            payload={"reason": reason_raw}, first_name=first_name,
        )
        if quip:
            text = quip
            if has_explicit_reason:
                text += t("admin.quip_reason", reason=reason_raw)
            await _post_ban_quip_to_chats(
                context, chats=[update.effective_chat.id],
                text=text,
                delete_after=cfg.public_quip_delete_after_s,
            )


@_only_admin
async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text(t("whitelist.usage"))
        return
    user_id = int(context.args[0])
    db: DB = context.bot_data["db"]
    db.whitelist(update.effective_chat.id, user_id)
    await update.effective_message.reply_text(
        t("whitelist.done", uid=user_id), parse_mode="HTML",
    )


# ----- Callbacks de los botones inline en las notificaciones al admin -----
# Estos NO llegan a este bot, llegan al bot de notificaciones externo, que necesitaría
# un handler propio o un endpoint REST. Para no acoplar, exponemos también
# comandos manuales: /notspam <action_id> y /confirm <action_id>.

@_only_admin
async def cmd_setgreeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marca un user como "greeter amigable" para que el bot reaccione a sus saludos.
    Uso: /setgreeter @username emoji1 emoji2 ...  | /setgreeter user_id emoji1 ...
    """
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(t("greeter.usage"), parse_mode="HTML")
        return
    db: DB = context.bot_data["db"]
    target = context.args[0]
    reactions = context.args[1:]
    target_id = None
    username = None
    if target.lstrip("-").isdigit():
        target_id = int(target)
    elif target.startswith("@"):
        username = target[1:]
        target_id = db.resolve_username(username)
        if target_id is None:
            try:
                chat_obj = await context.bot.get_chat(target)
                target_id = chat_obj.id
                username = chat_obj.username or username
            except Exception as exc:  # noqa: BLE001
                log.debug("setgreeter get_chat(%s) fallo: %s", target, exc)
    if not target_id:
        await update.effective_message.reply_text(t("greeter.unresolved", target=target))
        return
    db.upsert_friendly_greeter(target_id, username, list(reactions), update.effective_user.id)
    await update.effective_message.reply_text(
        t(
            "greeter.added",
            uid=target_id,
            uname="@" + username if username else t("greeter.no_username"),
            reactions=" ".join(reactions),
        ),
        parse_mode="HTML",
    )


@_only_admin
async def cmd_rmgreeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text(t("rmgreeter.usage"))
        return
    db: DB = context.bot_data["db"]
    target = context.args[0]
    target_id = None
    if target.lstrip("-").isdigit():
        target_id = int(target)
    elif target.startswith("@"):
        target_id = db.resolve_username(target[1:])
    if not target_id:
        await update.effective_message.reply_text(t("greeter.unresolved_user"))
        return
    ok = db.remove_friendly_greeter(target_id)
    await update.effective_message.reply_text(
        t("greeter.removed") if ok else t("greeter.not_in_list"))


@_read_admin
async def cmd_listgreeters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import json as _j
    db: DB = context.bot_data["db"]
    rows = db.list_friendly_greeters()
    if not rows:
        await update.effective_message.reply_text(t("greeters.empty"))
        return
    lines = [t("greeters.header")]
    for r in rows:
        try:
            reactions = " ".join(_j.loads(r["reactions_json"]))
        except Exception as exc:  # noqa: BLE001
            log.debug("listgreeters parse reactions user=%s: %s", r["user_id"], exc)
            reactions = "?"
        uname = "@" + r["username"] if r["username"] else "(" + t("greeter.no_username") + ")"
        lines.append(f"  <code>{r['user_id']}</code> {uname} → {reactions}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_read_admin
async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el top semanal ad-hoc. DM con picker, grupo en el actual."""
    from . import chat_picker, topweekly
    db: DB = context.bot_data["db"]
    if chat_picker.is_dm(update):
        await chat_picker.show_chat_picker(update, context, "top")
        return
    text = await topweekly.render_top(db, update.effective_chat.id)
    await update.effective_message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def _top_picker_handler(update, context, chat_id: int, args: str) -> None:
    from . import topweekly
    db: DB = context.bot_data["db"]
    text = await topweekly.render_top(db, chat_id)
    await update.callback_query.edit_message_text(text, parse_mode="HTML", disable_web_page_preview=True)


def _topweekly_keyboard(db: DB):
    """Genera el keyboard con un botón por grupo mostrando estado on/off."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for c in db.all_chats():
        if not c["am_admin"]:
            continue
        db.ensure_chat_settings(c["chat_id"])
        s = db.get_chat_settings(c["chat_id"])
        on = bool(s and s["topweekly_enabled"])
        emoji = "✅" if on else "⛔"
        title = (c["title"] or str(c["chat_id"]))[:40]
        rows.append([InlineKeyboardButton(
            f"{emoji} {title}",
            callback_data=f"twk:{c['chat_id']}",
        )])
    return InlineKeyboardMarkup(rows)


@_only_admin
async def cmd_topweekly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activa/desactiva el anuncio automático del top semanal.

    En DM al bot → muestra picker con todos los grupos y su estado actual,
      pulsa para hacer toggle.
    En grupo → comportamiento clásico: /topweekly on|off afecta el chat actual.
    """
    db: DB = context.bot_data["db"]

    from . import chat_picker
    if chat_picker.is_dm(update):
        await update.effective_message.reply_text(
            t("topweekly.panel"),
            parse_mode="HTML",
            reply_markup=_topweekly_keyboard(db),
        )
        return

    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        state = "ON" if s["topweekly_enabled"] else "OFF"
        await update.effective_message.reply_text(
            t("topweekly.state", state=state), parse_mode="HTML",
        )
        return
    val = context.args[0].lower()
    if val in ("on", "true", "yes", "1"):
        settings_sync.apply_setting(db, chat_id, "topweekly_enabled", 1)
        await update.effective_message.reply_text(t("topweekly.on"))
    elif val in ("off", "false", "no", "0"):
        settings_sync.apply_setting(db, chat_id, "topweekly_enabled", 0)
        await update.effective_message.reply_text(t("topweekly.off"))
    else:
        await update.effective_message.reply_text(t("topweekly.usage"))


async def on_topweekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback del picker: hace toggle del estado y edita el keyboard."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("twk:"):
        return
    cfg: Config = context.bot_data["cfg"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("admin.only_bot_admin"), show_alert=True)
        return
    try:
        chat_id = int(q.data.split(":", 1)[1])
    except ValueError:
        await q.answer(t("admin.invalid_button"))
        return
    db: DB = context.bot_data["db"]
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    new_value = 0 if s["topweekly_enabled"] else 1
    settings_sync.apply_setting(db, chat_id, "topweekly_enabled", new_value)
    await q.answer(t("topweekly.toast_on") if new_value else t("topweekly.toast_off"))
    try:
        await q.edit_message_reply_markup(reply_markup=_topweekly_keyboard(db))
    except Exception as exc:  # noqa: BLE001
        log.debug("topweekly callback edit_reply_markup fallo: %s", exc)


@_only_admin
async def cmd_notspam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(t("notspam.usage"))
        return
    aid = int(context.args[0])
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    row = db.get_action(aid)
    if not row:
        await update.effective_message.reply_text(t("notspam.notfound"))
        return
    if row["user_id"]:
        await unfederate_ban(
            context.bot, db, user_id=row["user_id"],
            revoked_by=update.effective_user.id, shadow=cfg.shadow,
        )
        db.suppress(row["user_id"], row["rule"], seconds=7 * 24 * 3600)
    await update.effective_message.reply_text(t("notspam.done", aid=aid))


# ===== Gestión de avisos informativos (silenciar/activar sin tocar el .env) =====

def _alertas_keyboard(db: DB, cfg: Config):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for key in notify_prefs.NOTIFY_TYPES:
        on = notify_prefs.effective(db, key, cfg)
        estado = t("alerts.b.on") if on else t("alerts.b.off")
        rows.append([InlineKeyboardButton(f"{estado} · {notify_prefs.label(key)}",
                                          callback_data=f"npref:tog:{key}")])
    return InlineKeyboardMarkup(rows)


@_only_admin
async def cmd_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ver y activar/silenciar los avisos informativos (borrados, bans de otros admins...)."""
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    await update.effective_message.reply_text(
        t("alerts.panel"),
        parse_mode="HTML", reply_markup=_alertas_keyboard(db, cfg),
    )


async def on_notifpref_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botones de preferencias de aviso: '🔕 Silenciar' (junto al aviso) y toggles de /alertas."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("npref:"):
        return
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("admin.only_bot_admin_change"), show_alert=True)
        return
    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    key = parts[2] if len(parts) > 2 else ""
    if key not in notify_prefs.NOTIFY_TYPES:
        await q.answer(t("alerts.unknown"))
        return
    if action == "off":  # botón "silenciar" junto al aviso
        db.set_pref(f"notify_{key}", False)
        await q.answer(t("alerts.muted_toast"))
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except TelegramError:
            pass
        return
    if action == "tog":  # toggle desde /alertas
        new_val = not notify_prefs.effective(db, key, cfg)
        db.set_pref(f"notify_{key}", new_val)
        await q.answer(t("alerts.toast_on") if new_val else t("alerts.toast_off"))
        try:
            await q.edit_message_reply_markup(reply_markup=_alertas_keyboard(db, cfg))
        except TelegramError:
            pass


async def on_suspicious_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Modo revisión de sospechosos: botones ✅ Permitir / 🔨 Banear del aviso privado."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("susrev:"):
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("admin.only_bot_admin_decide"), show_alert=True)
        return
    from . import settings_sync, verification
    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    try:
        chat_id, user_id = int(parts[-2]), int(parts[-1])  # siempre los dos últimos
    except (IndexError, ValueError):
        await q.answer(t("review.invalid_callback"))
        return
    base = q.message.text_html if q.message else ""

    # ⚙️ Tuerca: abre el panel de ajustes; "collapse" vuelve a la vista de decisión.
    if action == "gear":
        await q.answer()
        try:
            await q.edit_message_reply_markup(
                reply_markup=verification.build_review_settings_keyboard(db, chat_id, user_id))
        except TelegramError:
            pass
        return
    if action == "collapse":
        await q.answer()
        try:
            await q.edit_message_reply_markup(
                reply_markup=verification.build_review_keyboard(db, chat_id, user_id))
        except TelegramError:
            pass
        return

    # Toggles del panel (verificación / avisos / recordatorios). Respetan el sync y
    # re-renderizan el panel abierto.
    _TOG = {
        "togverif": ("verification_enabled", "toast.verif"),
        "togreview": ("verification_review_suspicious", "toast.alerts"),
        "togremind": ("verification_reminders_enabled", "toast.reminders"),
    }
    if action in _TOG:
        field, nombre_key = _TOG[action]
        db.ensure_chat_settings(chat_id)
        s = db.get_chat_settings(chat_id)
        new_val = 0 if (s and s[field]) else 1
        n = settings_sync.apply_setting(db, chat_id, field, new_val)
        scope = t("cfg.dot_n", n=n) if n > 1 else ""
        await q.answer(f"{t(nombre_key)}: {'ON' if new_val else 'OFF'}{scope}")
        try:
            await q.edit_message_reply_markup(
                reply_markup=verification.build_review_settings_keyboard(db, chat_id, user_id))
        except TelegramError:
            pass
        return

    # ⏱️ Tiempos: submenú de presets y fijar valor.
    if action == "times":
        await q.answer()
        try:
            await q.edit_message_reply_markup(
                reply_markup=verification.build_review_times_keyboard(db, chat_id, user_id))
        except TelegramError:
            pass
        return
    if action == "st":  # susrev:st:{code}:{val}:{chat}:{user}
        code = parts[2] if len(parts) > 2 else ""
        info = verification._REVIEW_TIME_FIELDS.get(code)
        try:
            val = int(parts[3])
        except (IndexError, ValueError):
            await q.answer(t("cfg.invalid_val"))
            return
        if not info or val not in info[1]:
            await q.answer(t("cfg.invalid_opt"))
            return
        field, _presets, unit = info
        n = settings_sync.apply_setting(db, chat_id, field, val)
        await q.answer(f"✅ {val}{unit}" + (t("cfg.dot_n", n=n) if n > 1 else ""))
        try:
            await q.edit_message_reply_markup(
                reply_markup=verification.build_review_times_keyboard(db, chat_id, user_id))
        except TelegramError:
            pass
        return

    if action == "allow":
        await q.answer(t("toast.allowed"))
        try:
            await q.edit_message_text(base + t("review.allowed"), parse_mode="HTML")
        except TelegramError:
            pass
        return
    if action == "ban":
        res = await federate_ban(
            context.bot, db, user_id=user_id,
            reason=t("reason.manual_review_ban"), rule="manual_review_ban",
            triggered_in_chat=chat_id, shadow=cfg.shadow,
        )
        ok = sum(1 for v in (res or {}).values() if v == "ok")
        await q.answer(t("toast.banned", n=ok))
        try:
            await q.edit_message_text(base + t("review.banned", n=ok), parse_mode="HTML")
        except TelegramError:
            pass
        return
