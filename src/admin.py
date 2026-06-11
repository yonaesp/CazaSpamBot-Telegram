"""Comandos admin del bot. Solo accesibles desde ADMIN_USER_ID."""
from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.ext import ContextTypes

from telegram.error import TelegramError

from . import chat_picker, learning, permissions, quips
from .config import Config
from .db import DB
from .federation import federate_ban, unfederate_ban

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
    await update.effective_message.reply_text(
        f"🤖 <b>CazaSpamBot operativo</b>\n\n"
        f"{mode_emoji} <b>Modo:</b> <code>{cfg.mode}</code>\n"
        f"🌐 <b>Federación:</b> {'✅ on' if cfg.federation_enabled else '❌ off'}\n"
        f"🛡️ <b>CAS:</b> {'✅ on' if cfg.cas_enabled else '❌ off'}\n"
        f"❤️ <b>Reacciones:</b> {'✅ on' if cfg.reaction_farming_enabled else '❌ off'}\n"
        f"📜 <b>Scripts permitidos:</b> {', '.join(cfg.allowed_scripts)}\n\n"
        f"📊 <b>Stats</b>\n"
        f"  Chats: <b>{s['chats']}</b> · Usuarios vistos: <b>{s['seen_users']}</b>\n"
        f"  Bans activos: <b>{s['banned']}</b> · Acciones 24h: <b>{s['actions_24h']}</b>\n\n"
        f"Usa /help para ver todos los comandos.",
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

    # --- Mensaje 1: cómo funciona el bot ---
    await msg.reply_text(
        "<b>🤖 CazaSpamBot — cómo funciona</b>\n\n"
        "Soy un bot antispam que protege todos los grupos donde soy "
        "admin. <b>Un ban en uno = ban en todos.</b>\n\n"

        "<b>🛡️ Capas de protección (en orden)</b>\n\n"

        "<b>1. Al entrar alguien nuevo</b>\n"
        "  • Si ya lo baneé antes en cualquiera de tus grupos → re-ban (bans sincronizados).\n"
        "  • Reviso su perfil (vía cuenta secundaria): nombre, foto, bio, antigüedad.\n"
        "  • Si el perfil es <b>claramente spam</b> (nombre en otro alfabeto, bio con enlaces porno/promo, fotos subidas todas de golpe = identidad robada) → <b>ban directo, sin avisar</b>.\n"
        "  • Si aparece en listas anti-spam globales (CAS, lols.bot) → ban.\n"
        "  • Si es un <b>bot</b> añadido al grupo → lo expulso y te aviso.\n"
        "  • Si el perfil es muy legítimo (foto + cuenta antigua + nombre normal) → entra directo, sin verificación.\n"
        "  • El resto → mensaje de bienvenida con botón <b>SOY HUMANO</b> (muteado hasta pulsarlo). Sospechosos: kick a los 30 min. Normales: recordatorio a las 3h.\n\n"

        "<b>2. En cada mensaje</b>\n"
        "  Detecto: texto en otro alfabeto, menciones/enlaces a otros grupos, acortadores, deep-links, anuncios comerciales (sueldos, ofertas), forwards de canales en el primer mensaje, mensajes con botones (típico de bots spam), inundación de mensajes (antiflood), y patrones que he aprendido de tus <code>/spam</code>.\n\n"

        "<b>3. Casos especiales que ya cubro</b>\n"
        "  • Bots posteando spam (botones porno) → ban.\n"
        "  • Cuentas dormidas >1 año que reaparecen citando un bot → ban (cuenta hackeada/vendida).\n"
        "  • Mensajes posteados vía bots inline → borro + te aviso.\n\n"

        "<b>⚖️ Niveles de confianza (anti-falsos-positivos)</b>\n"
        "  Cada usuario tiene un <b>nivel de confianza del 1 al 10</b> (10 = veterano de fiar, 1 = recién llegado). Lo calculo así:\n"
        "  • <b>Sube</b> con: mensajes escritos en el grupo, antigüedad de la cuenta en el grupo, y que yo le viera entrar (trayectoria limpia).\n"
        "  • <b>Baja</b> con: warns activos. Y si lo pones en whitelist, va directo a 10.\n"
        "  Según el nivel actúo distinto:\n"
        "  • <b>Nivel 7-10</b> (confianza alta) → casi nunca les actúo.\n"
        "  • <b>Nivel 4-6</b> (media) + algo sospechoso → <b>te pregunto a ti por privado</b> con botones ✅Legítimo / ❌Spam, y aprendo de tu respuesta.\n"
        "  • <b>Nivel 1-3</b> (nuevo/sin historial) → trato normal según las reglas.\n"
        "  En cada mensaje sospechoso verás también un <b>nivel de spam 1-10</b> (10 = clarísimamente spam).\n"
        "  • <i>Mi filosofía: mejor dejar pasar un spam que banear a alguien legítimo.</i>\n\n"

        "<b>🔕 Mensajes en el grupo</b>\n"
        "  Los bans automáticos son <b>silenciosos</b> (no ensucian el chat). Solo tus bans manuales publican un mensajito gracioso, que se borra a las 3h.\n\n"

        "<i>👇 Te paso la lista de comandos en el siguiente mensaje.</i>",
        parse_mode="HTML", disable_web_page_preview=True,
    )

    note = "" if is_bot_admin_user else (
        "\n\n<i>🔒 Eres admin de uno de los grupos pero no el bot admin principal. "
        "Puedes ver toda la información (lectura). Los comandos que modifican "
        "(ban/setwelcome/warn/etc.) los ejecuta solo el bot admin.</i>"
    )
    # --- Mensaje 2: referencia de comandos ---
    await msg.reply_text(
        "<b>🛠️ Comandos del bot — referencia</b>\n\n"

        "<b>📊 Ver información</b>\n"
        "  /start — estado del bot y stats rápidas\n"
        "  /stats — métricas (en DM te pregunta de qué grupo)\n"
        "  /chats — lista de grupos donde el bot opera\n"
        "  /recent — últimas 10 acciones. Ejemplo: <code>/recent 30</code> para ver las últimas 30\n"
        "  /comandos — esta misma guía\n\n"

        "<b>🔧 Moderación</b> (reply al mensaje o usando @usuario)\n"
        "  <code>/ban @usuario razón</code> — banea en todos tus grupos a la vez\n"
        "  <code>/unban @usuario</code> — quita el ban\n"
        "  <code>/whitelist @usuario</code> — marca como inmune en el chat actual\n"
        "  <code>/notspam 42</code> — revierte falso positivo (el número es el id que ves en /recent)\n\n"

        "<b>⚠️ Warns</b> (avisos progresivos: por defecto 3 = ban)\n"
        "  <code>/warn @usuario razón</code> o reply al mensaje\n"
        "  /warns (reply al user) — ver sus warns activos\n"
        "  /rmwarn (reply) — quita el último warn\n"
        "  /resetwarns (reply) — borra todos los warns\n"
        "  <code>/warnlimit 3</code> — cambia el límite (sin número solo lo muestra)\n"
        "  <code>/warnaction ban</code> — qué hacer al llegar al límite: <code>ban</code>, <code>kick</code> o <code>mute</code>\n\n"

        "<b>📚 Entrenar el clasificador</b> (responde a un mensaje)\n"
        "  /spam — banea al autor (en todos los grupos) + reporta el mensaje + lo añade al clasificador.\n"
        "  /legal — marca el mensaje como LEGÍTIMO (anti-falsos positivos, solo aprende).\n"
        "  El bot borra tu comando del grupo y te confirma por DM.\n"
        "  /samples — cuántas muestras hay. Ejemplo: <code>/samples spam 30</code> lista 30 spam\n"
        "  <code>/forget 5</code> — borra la muestra número 5 (id que ves en /samples)\n\n"

        "<b>🌹 Welcome, reglas y servicios</b>\n"
        "  /welcome — ver el mensaje de bienvenida del grupo actual\n"
        "  <code>/setwelcome texto</code> — cambia el welcome (acepta sintaxis Rose con botones)\n"
        "  /resetwelcome — vuelve al welcome por defecto\n"
        "  /rules — ver reglas | <code>/setrules texto</code> — cambiarlas\n"
        "  /cleanservice on / off — borrar mensajes 'X se ha unido' automáticamente\n"
        "  /testwelcome — vista previa del welcome (te lo enseña como si fueras nuevo)\n\n"

        "<b>🔘 Botones del welcome</b>\n"
        "  /welcomebuttons — lista los botones configurados\n"
        "  <code>/setwelcomebutton Texto | https://url</code> — añade botón\n"
        "  <code>/setwelcomebutton Texto | https://url same</code> — botón en la misma fila\n"
        "  <code>/rmwelcomebutton 3</code> — quita el botón con id 3 (lo ves en /welcomebuttons)\n"
        "  /clearwelcomebuttons — quita todos\n\n"

        "<b>🏆 Top semanal de actividad</b>\n"
        "  /top — muestra el top 5 de los últimos 7 días (en DM te pregunta de qué grupo)\n"
        "  /topweekly on / off — activar o desactivar el anuncio automático (domingo 20:00)\n"
        "  Filtros: texto ≥10 chars o mensajes con media (foto/video/sticker/audio), sin saludos repetidos, cooldown 10s.\n\n"

        "<b>🫡 Greeters (reacciones a saludos)</b>\n"
        "  /listgreeters — usuarios marcados como amables\n"
        "  <code>/setgreeter @usuario 🫡 🤝</code> — añade greeter con reacciones (ej.)\n"
        "  <code>/rmgreeter @usuario</code> — quítalo\n\n"

        "<b>👥 Reportes con @admin</b> (lo usan los miembros del grupo)\n"
        "  Cualquier user responde a un mensaje con <code>@admin</code>; el bot le confirma. "
        "Si tú actúas (warn/ban/borrar), el bot borra también el reporte original y publica un agradecimiento al reporter. Sin warns para el que reporta.\n\n"

        "<b>⚙️ Modo de operación</b>\n"
        "  /shadow on — solo loggea, no actúa (modo prueba)\n"
        "  /shadow off — modo ACTIVO (ban/kick/delete reales)\n"
        "  El cambio es inmediato pero no persiste al reiniciar el bot; "
        "para que sea permanente edita MODE en el .env del servidor.\n\n"

        "<b>ℹ️ Tips útiles</b>\n"
        "  · Los <i>números id</i> (de muestra, acción, botón, etc.) los ves siempre en el listado correspondiente: /recent, /samples, /welcomebuttons...\n"
        "  · Los <i>user_id numéricos</i> los obtienes en las notificaciones que llegan a Casa_Yona, o usando @userinfobot.\n"
        "  · En DM al bot, los comandos de consulta (/stats /welcome /rules) muestran botones para elegir grupo si estás en varios."
        + note,
        parse_mode="HTML",
    )


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
        usage = (
            f"📚 <b>/{cmd}</b>: Responde a un mensaje con este comando para que el bot lo "
            f"añada al clasificador como muestra <b>{'legítima' if label=='ham' else 'spam'}</b>.\n\n"
            f"Esto enseña al bot qué tipo de mensajes son normales en tu grupo "
            f"y reduce falsos positivos en el futuro."
        )
        await msg.reply_text(usage, parse_mode="HTML")
        return

    target = msg.reply_to_message
    text = target.text or target.caption or ""
    if not text or len(text) < 5:
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, f"⚠️ /{cmd} ignorado: mensaje sin texto suficiente.")
        else:
            await msg.reply_text("Mensaje sin texto suficiente. No se guarda.")
        return

    norm = learning.normalize(text)
    h = learning.text_hash(norm)
    added = db.add_sample(
        text_norm=norm, text_hash=h, label=label,
        added_by=update.effective_user.id, chat_id=msg.chat_id,
        source_user=target.from_user.id if target.from_user else None,
    )
    status = "añadida" if added else "ya estaba registrada"
    emoji = "🛑" if label == "spam" else "✅"
    label_es = "spam" if label == "spam" else "legítima"

    if is_group:
        # Borrar el comando del admin del grupo y confirmar al admin por DM
        await _delete_command_safely(update)
        ack = (
            f"{emoji} Muestra <b>{label_es}</b> {status} en {msg.chat.title or msg.chat_id}.\n"
            f"<i>Texto:</i> <pre>{(text[:200])}</pre>"
        )
        await _notify_admin_ack(context, ack)
    else:
        await msg.reply_text(
            f"{emoji} Muestra <b>{label_es}</b> {status} al clasificador.",
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
        await msg.reply_text(
            "🛑 <b>/spam</b>: responde al mensaje de un spammer con este comando.\n\n"
            "Banea al autor en todos tus grupos, reporta el mensaje a Telegram "
            "y lo añade al clasificador.\n"
            "Para banear por <code>@usuario</code> sin un mensaje, usa <code>/ban</code>.",
            parse_mode="HTML",
        )
        return

    target = msg.reply_to_message
    text = target.text or target.caption or ""
    author = target.from_user

    # 1) Aprender (solo si hay texto suficiente)
    sample_note = "sin texto para aprender"
    if text and len(text) >= 5:
        norm = learning.normalize(text)
        added = db.add_sample(
            text_norm=norm, text_hash=learning.text_hash(norm), label="spam",
            added_by=update.effective_user.id, chat_id=msg.chat_id,
            source_user=author.id if author else None,
        )
        sample_note = "sample spam guardada" if added else "sample spam ya existía"

    # Borrar el comando del admin del grupo cuanto antes
    if is_group:
        await _delete_command_safely(update)

    # Sin autor resoluble (forward anónimo / post de canal): solo aprende.
    if author is None or author.is_bot:
        ack = f"⚠️ /spam: no pude identificar al autor (anónimo o canal). {sample_note}."
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
                warn = (
                    f"⚠️ {author.first_name} (id: {author.id}) es admin en "
                    f"<b>{chat_row['title']}</b>. No lo baneo. {sample_note}."
                )
                if is_group:
                    await _notify_admin_ack(context, warn)
                else:
                    await msg.reply_text(warn, parse_mode="HTML")
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("/spam admin-guard fallo chat=%s: %s", chat_row.get("chat_id"), exc)

    # 2) Reporte oficial ANTES del ban (no bloquea; el msg aún existe). Manual
    # del admin = máxima confianza, así que reporta sin pasar por la whitelist
    # de reglas automáticas (el rate-limit del reporter sigue aplicando).
    if not cfg.shadow:
        reporter = context.bot_data.get("reporter")
        if reporter is not None and reporter.is_ready():
            reporter.enqueue(
                chat_id=msg.chat_id, user_id=author.id,
                message_id=target.message_id, reason="spam",
                detail="[manual_admin_spam] reporte manual del admin (/spam)",
            )

    # 3) Ban federado
    results = await federate_ban(
        context.bot, db, user_id=author.id,
        reason="Spam confirmado manualmente por admin (/spam)",
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
    if cfg.public_quip_enabled and not cfg.shadow and is_group:
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
    ack = (
        f"🛑 /spam → ban federado {author.first_name} (id: {author.id}): "
        f"{ok} ok · {shadow} shadow · {err} err. Reporte encolado. {sample_note}."
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
            f"📚 <b>Muestras del clasificador</b>\n"
            f"🛑 spam: <b>{c['spam']}</b>\n"
            f"✅ ham: <b>{c['ham']}</b>\n\n"
            f"<code>/samples spam 20</code> · <code>/samples ham 20</code>\n"
            f"<code>/forget &lt;sample_id&gt;</code> para borrar",
            parse_mode="HTML",
        )
        return
    label = context.args[0].lower()
    if label not in ("spam", "ham"):
        await update.effective_message.reply_text("Uso: /samples spam|ham [N]")
        return
    n = 20
    if len(context.args) > 1 and context.args[1].isdigit():
        n = max(1, min(50, int(context.args[1])))
    rows = db.list_samples(label=label, limit=n)
    if not rows:
        await update.effective_message.reply_text(f"Sin muestras {label}.")
        return
    import datetime as _dt
    import html as _html
    lines = [f"📚 Últimas {n} muestras <b>{label}</b>:\n"]
    for r in rows:
        ts = _dt.datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        txt = (r["text_norm"] or "")[:80]
        lines.append(f"<code>#{r['id']}</code> [{ts}] {_html.escape(txt)}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_only_admin
async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra una muestra del clasificador."""
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /forget <sample_id>")
        return
    sid = int(context.args[0])
    db: DB = context.bot_data["db"]
    ok = db.delete_sample(sid)
    if ok:
        await update.effective_message.reply_text(f"🗑️ Muestra #{sid} borrada.")
    else:
        await update.effective_message.reply_text(f"No existe #{sid}.")


async def on_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mensajes no-comando en DM: si soy el admin → hint suave; si no → ignorar."""
    cfg: Config = context.bot_data["cfg"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return  # silent ignore para no-admins
    await update.effective_message.reply_text(
        "👋 Hola. Soy <b>CazaSpamBot</b>, tu bot de moderación.\n\n"
        "Solo respondo a comandos. Usa /help para ver la lista completa,\n"
        "o /start para un resumen rápido del estado.",
        parse_mode="HTML",
    )


async def _render_chat_stats(db: DB, chat_id: int | None = None) -> str:
    """Si chat_id=None devuelve stats globales. Si no, stats de ese chat."""
    if chat_id is None:
        s = db.stats()
        return (
            f"<b>📊 Stats globales</b>\n"
            f"Chats activos: {s['chats']}\n"
            f"Usuarios vistos: {s['seen_users']}\n"
            f"Baneados (en todos los grupos): {s['banned']}\n"
            f"Acciones 24h: {s['actions_24h']}"
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
    return (
        f"<b>📊 Stats — {_h.escape(title)}</b>\n"
        f"<code>{chat_id}</code>\n\n"
        f"👥 Usuarios vistos: <b>{users}</b>\n"
        f"💬 Mensajes registrados: <b>{msgs}</b>\n"
        f"⚠️ Warns activos: <b>{warns}</b>\n"
        f"🔒 Pendientes verificación: <b>{pending}</b>\n"
        f"🔨 Acciones 24h: <b>{actions24}</b>"
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
        await update.effective_message.reply_text("Sin chats registrados todavía.")
        return
    lines = ["<b>Chats:</b>"]
    for r in rows:
        admin_mark = "✅" if r["am_admin"] else "❌"
        perms = []
        if r["can_restrict"]:
            perms.append("restrict")
        if r["can_delete"]:
            perms.append("delete")
        lines.append(
            f"{admin_mark} <code>{r['chat_id']}</code> · {html.escape(r['title'] or '?')} ({r['type']}) [{','.join(perms) or 'sin perms'}]"
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
        await update.effective_message.reply_text("Sin acciones registradas.")
        return
    lines = [f"<b>Últimas {n} acciones</b>"]
    import datetime as _dt
    for r in rows:
        ts = _dt.datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        lines.append(
            f"[{ts}] <code>{r['action']}</code> user=<code>{r['user_id']}</code> "
            f"chat=<code>{r['chat_id']}</code> rule={html.escape(r['rule'])} "
            f"score={r['score']} mode={r['mode']}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


@_only_admin
async def cmd_shadow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0] not in ("on", "off"):
        await update.effective_message.reply_text("Uso: /shadow on|off")
        return
    cfg: Config = context.bot_data["cfg"]
    new_mode = "shadow" if context.args[0] == "on" else "active"
    # Hot-swap del Config (no es frozen idealmente, pero replicamos atributo)
    object.__setattr__(cfg, "mode", new_mode)
    await update.effective_message.reply_text(f"Modo cambiado a <b>{new_mode}</b>", parse_mode="HTML")
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
        return None, args, "Argumento vacío."
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
    return None, args, f"No pude resolver @{uname} (ni Bot API ni Telethon). Usa el user_id numérico."


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
    """Tras un ban manual, borra el mensaje de bienvenida del user si sigue
    pendiente en algún chat federado, y limpia la fila pending_verifications.
    Evita welcomes huérfanos con botón SOY HUMANO de un user ya baneado."""
    for chat_row in db.all_chats():
        if not chat_row["am_admin"]:
            continue
        chat_id = chat_row["chat_id"]
        pending = db.get_pending(chat_id, user_id)
        if pending and pending["welcome_msg_id"]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=pending["welcome_msg_id"])
                log.info("welcome borrado tras ban manual user=%s chat=%s", user_id, chat_id)
            except TelegramError:
                pass
        if pending:
            db.delete_pending(chat_id, user_id)


async def _notify_admin_ack(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Envía el ack técnico (resultado del ban/unban) al admin via Casa_Yona DM."""
    notifier = context.bot_data.get("notifier")
    if notifier:
        try:
            await notifier.send_text(text)
        except Exception as exc:  # noqa: BLE001
            log.warning("notifier ack falló: %s", exc)


@_only_admin
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban federado (replica a TODOS los chats donde el bot es admin) + quip público con autoborrado.

    Si se ejecuta en grupo: borra el comando del admin, publica solo el quip (con motivo
    si se dio) y manda el resumen técnico por DM al admin (Casa_Yona).
    """
    db: DB = context.bot_data["db"]
    is_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    user_id, args_remaining, resolve_err = await _resolve_target_user(update, context, db)
    if user_id is None:
        # Error de resolución: si grupo, borrar comando + avisar admin por DM; si DM, contestar inline.
        usage = (
            "Uso: <code>/ban &lt;user_id | @username&gt; [razón]</code>\n"
            "  · También puedes responder a un mensaje del user con <code>/ban [razón]</code>.\n"
            "Banea en TODOS los chats federados y publica un mensaje en cada grupo.\n"
            + (f"\n⚠️ {resolve_err}" if resolve_err else "")
        )
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, f"❌ /ban inválido: {resolve_err or 'argumento ausente'}")
        else:
            await update.effective_message.reply_text(usage, parse_mode="HTML")
        return
    reason_raw = " ".join(args_remaining).strip()
    reason = reason_raw or "Ban manual del admin"
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
                warn = (
                    f"⚠️ <code>{user_id}</code> es admin en <b>{chat_row['title']}</b>. "
                    f"No baneo admins automáticamente. Quítale el admin primero."
                )
                if is_group:
                    await _delete_command_safely(update)
                    await _notify_admin_ack(context, warn)
                else:
                    await update.effective_message.reply_text(warn, parse_mode="HTML")
                return
        except Exception as exc:  # noqa: BLE001
            log.debug("ban admin-guard get_chat_member fallo chat=%s user=%s: %s",
                      chat_row.get("chat_id"), user_id, exc)

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
    if is_group:
        await _delete_command_safely(update)

    results = await federate_ban(
        context.bot, db, user_id=user_id, reason=reason, rule="manual_admin_ban",
        triggered_in_chat=update.effective_chat.id if update.effective_chat else None,
        shadow=cfg.shadow,
    )
    ok = sum(1 for v in results.values() if v == "ok")
    shadow = sum(1 for v in results.values() if v == "shadow")
    err = sum(1 for v in results.values() if v.startswith("error"))
    ack = f"🔨 Ban federado user <code>{user_id}</code>: {ok} ok · {shadow} shadow · {err} err"
    # Borrar welcome huérfano del baneado si seguía pendiente
    if not cfg.shadow:
        await _cleanup_welcome_on_ban(context, db, user_id)
    if is_group:
        await _notify_admin_ack(context, ack)
    else:
        await update.effective_message.reply_text(ack, parse_mode="HTML")

    # Quip público SOLO en el chat donde se ejecutó /ban (no en todos los federados).
    # Si /ban se ejecuta desde DM con el bot → ban silencioso sin publicar en grupos.
    if cfg.public_quip_enabled and not cfg.shadow and is_group:
        quip = quips.pick(
            rule="manual_admin_ban", username=username, user_id=user_id,
            payload={"reason": reason}, first_name=first_name,
        )
        if quip:
            text = quip
            if has_explicit_reason:
                text += f"\n<i>Motivo:</i> {reason}"
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


async def _delete_msg_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except TelegramError:
        pass


@_only_admin
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    is_group = bool(update.effective_chat and update.effective_chat.type in ("group", "supergroup"))
    user_id, args_remaining, resolve_err = await _resolve_target_user(update, context, db)
    if user_id is None:
        usage = (
            "Uso: <code>/unban &lt;user_id | @username&gt; [razón]</code>"
            + (f"\n⚠️ {resolve_err}" if resolve_err else "")
        )
        if is_group:
            await _delete_command_safely(update)
            await _notify_admin_ack(context, f"❌ /unban inválido: {resolve_err or 'argumento ausente'}")
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
    ack = f"🔓 Unban federado user <code>{user_id}</code>: {ok} ok · {err} err"
    if is_group:
        await _notify_admin_ack(context, ack)
    else:
        await update.effective_message.reply_text(ack, parse_mode="HTML")

    # Quip público de unban en el chat donde se ejecutó
    if cfg.public_quip_enabled and not cfg.shadow and is_group:
        quip = quips.pick(
            rule="manual_admin_unban", username=username, user_id=user_id,
            payload={"reason": reason_raw}, first_name=first_name,
        )
        if quip:
            text = quip
            if has_explicit_reason:
                text += f"\n<i>Motivo:</i> {reason_raw}"
            await _post_ban_quip_to_chats(
                context, chats=[update.effective_chat.id],
                text=text,
                delete_after=cfg.public_quip_delete_after_s,
            )


@_only_admin
async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.effective_message.reply_text("Uso: /whitelist <user_id>")
        return
    user_id = int(context.args[0])
    db: DB = context.bot_data["db"]
    db.whitelist(update.effective_chat.id, user_id)
    await update.effective_message.reply_text(
        f"Usuario <code>{user_id}</code> whitelisted en este chat.",
        parse_mode="HTML",
    )


# ----- Callbacks de los botones inline en notificaciones Casa_Yona -----
# Estos NO llegan a este bot, llegan a Casa_Yona. Casa_Yona necesitaría
# un handler propio o un endpoint REST. Para no acoplar, exponemos también
# comandos manuales: /notspam <action_id> y /confirm <action_id>.

@_only_admin
async def cmd_setgreeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Marca un user como "greeter amigable" para que el bot reaccione a sus saludos.
    Uso: /setgreeter @username emoji1 emoji2 ...  | /setgreeter user_id emoji1 ...
    """
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text(
            "Uso: <code>/setgreeter @username 🫡 🤝</code> o <code>/setgreeter user_id 🫡</code>\n"
            "Reactions sugeridas: 🫡 🤝 🤗 ❤️ 👏 🎉 🌚 🔥",
            parse_mode="HTML",
        )
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
        await update.effective_message.reply_text(f"No pude resolver {target}.")
        return
    db.upsert_friendly_greeter(target_id, username, list(reactions), update.effective_user.id)
    await update.effective_message.reply_text(
        f"✅ Greeter añadido: <code>{target_id}</code> "
        f"({'@'+username if username else 'sin username'}) con reacciones: {' '.join(reactions)}",
        parse_mode="HTML",
    )


@_only_admin
async def cmd_rmgreeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Uso: /rmgreeter @username | user_id")
        return
    db: DB = context.bot_data["db"]
    target = context.args[0]
    target_id = None
    if target.lstrip("-").isdigit():
        target_id = int(target)
    elif target.startswith("@"):
        target_id = db.resolve_username(target[1:])
    if not target_id:
        await update.effective_message.reply_text("No pude resolver el usuario.")
        return
    ok = db.remove_friendly_greeter(target_id)
    await update.effective_message.reply_text("✅ Eliminado." if ok else "No estaba en la lista.")


@_read_admin
async def cmd_listgreeters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import json as _j
    db: DB = context.bot_data["db"]
    rows = db.list_friendly_greeters()
    if not rows:
        await update.effective_message.reply_text("No hay greeters configurados.")
        return
    lines = ["<b>🫡 Friendly greeters configurados</b>"]
    for r in rows:
        try:
            reactions = " ".join(_j.loads(r["reactions_json"]))
        except Exception as exc:  # noqa: BLE001
            log.debug("listgreeters parse reactions user=%s: %s", r["user_id"], exc)
            reactions = "?"
        uname = "@" + r["username"] if r["username"] else "(sin username)"
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


def _topweekly_keyboard(db: DB) -> "InlineKeyboardMarkup":
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
            "🏆 <b>Top semanal de actividad — gestión</b>\n\n"
            "Pulsa un grupo para alternar su estado.\n"
            "✅ = activado (publica cada domingo 20:00)\n"
            "⛔ = desactivado\n\n"
            "<i>Filtros activos: texto ≥10 chars o con media, sin saludos, cooldown 10s.</i>",
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
            f"Top semanal automático en este chat: <b>{state}</b>\n"
            f"Uso: <code>/topweekly on</code> o <code>/topweekly off</code>",
            parse_mode="HTML",
        )
        return
    val = context.args[0].lower()
    if val in ("on", "true", "yes", "1"):
        db.update_chat_setting(chat_id, "topweekly_enabled", 1)
        await update.effective_message.reply_text("✅ Top semanal ACTIVADO. Próxima publicación: domingo 20:00.")
    elif val in ("off", "false", "no", "0"):
        db.update_chat_setting(chat_id, "topweekly_enabled", 0)
        await update.effective_message.reply_text("⛔ Top semanal DESACTIVADO en este chat.")
    else:
        await update.effective_message.reply_text("Uso: /topweekly on|off")


async def on_topweekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback del picker: hace toggle del estado y edita el keyboard."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("twk:"):
        return
    cfg: Config = context.bot_data["cfg"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer("Solo el bot admin.", show_alert=True)
        return
    try:
        chat_id = int(q.data.split(":", 1)[1])
    except ValueError:
        await q.answer("Botón inválido.")
        return
    db: DB = context.bot_data["db"]
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    new_value = 0 if s["topweekly_enabled"] else 1
    db.update_chat_setting(chat_id, "topweekly_enabled", new_value)
    await q.answer(f"Top semanal {'ACTIVADO' if new_value else 'DESACTIVADO'}")
    try:
        await q.edit_message_reply_markup(reply_markup=_topweekly_keyboard(db))
    except Exception as exc:  # noqa: BLE001
        log.debug("topweekly callback edit_reply_markup fallo: %s", exc)


@_only_admin
async def cmd_notspam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /notspam <action_id>")
        return
    aid = int(context.args[0])
    db: DB = context.bot_data["db"]
    cfg: Config = context.bot_data["cfg"]
    row = db.get_action(aid)
    if not row:
        await update.effective_message.reply_text("action_id no encontrado.")
        return
    if row["user_id"]:
        await unfederate_ban(
            context.bot, db, user_id=row["user_id"],
            revoked_by=update.effective_user.id, shadow=cfg.shadow,
        )
        db.suppress(row["user_id"], row["rule"], seconds=7 * 24 * 3600)
    await update.effective_message.reply_text(
        f"Acción {aid} marcada como falso positivo. Ban revocado y regla suprimida 7 días."
    )
