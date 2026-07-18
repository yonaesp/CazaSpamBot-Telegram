"""Comandos para gestionar settings de cada chat: welcome, rules, etc."""
from __future__ import annotations

import html
import logging

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from . import chat_picker, i18n, settings_sync
from .config import Config
from .db import DB
from .i18n import t

# Sintaxis Rose: [Texto del botón](buttonurl://https://url.com)
# Variante misma fila: [Texto2](buttonurl://https://url2.com:same)
ROSE_BUTTON_RE = re.compile(
    r"\[([^\]]+)\]\(buttonurl://([^\s\)]+?)(:same)?\)",
    re.IGNORECASE,
)


def _parse_rose_buttons(text: str) -> tuple[str, list[dict]]:
    """Extrae botones del texto en sintaxis Rose. Devuelve (texto_limpio, lista_botones)."""
    buttons = []
    for m in ROSE_BUTTON_RE.finditer(text):
        buttons.append({
            "text": m.group(1).strip(),
            "url": m.group(2).strip(),
            "same_row": bool(m.group(3)),
        })
    clean = ROSE_BUTTON_RE.sub("", text).strip()
    # Limpia líneas vacías sobrantes
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean, buttons

log = logging.getLogger(__name__)


def _admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg: Config = context.bot_data["cfg"]
        u = update.effective_user
        if not u or u.id != cfg.admin_user_id:
            return
        return await func(update, context)
    return wrapper


async def _render_welcome(db: DB, chat_id: int) -> str:
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    if not s or not s["welcome_text"]:
        return t("welcome.none", name="{name}", chat="{chat}")
    enabled = t("cfg.act_on") if s["welcome_enabled"] else t("cfg.act_off")
    btn_part = ""
    if s["welcome_button_text"]:
        btn_part = t("welcome.btn_line", text=html.escape(s["welcome_button_text"]))
        if s["welcome_button_url"]:
            btn_part += t("welcome.btn_url", url=html.escape(s["welcome_button_url"]))
    return t(
        "welcome.current",
        state=enabled,
        text=html.escape(s["welcome_text"]),
        buttons=btn_part,
    )


async def _welcome_picker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    text = await _render_welcome(db, chat_id)
    await update.callback_query.edit_message_text(text, parse_mode="HTML")


async def _rules_picker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    if not s or not s["rules_text"]:
        await update.callback_query.edit_message_text(t("rules.none_chat"))
        return
    await update.callback_query.edit_message_text(
        t("rules.show", rules=s["rules_text"]), parse_mode="HTML",
    )


@_admin_only
async def cmd_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if chat_picker.is_dm(update):
        await chat_picker.show_chat_picker(update, context, "welcome")
        return
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    if not s["welcome_text"]:
        await update.effective_message.reply_text(t("welcome.none", name="{name}", chat="{chat}"), parse_mode="HTML")
        return
    enabled = t("cfg.act_on") if s["welcome_enabled"] else t("cfg.act_off")
    btn_part = ""
    if s['welcome_button_text']:
        btn_part = t("welcome.btn_line", text=html.escape(s["welcome_button_text"]))
        if s['welcome_button_url']:
            btn_part += t("welcome.btn_url", url=html.escape(s["welcome_button_url"]))
    await update.effective_message.reply_text(
        t(
            "welcome.current",
            state=enabled,
            text=html.escape(s["welcome_text"]),
            buttons=btn_part,
        ),
        parse_mode="HTML",
    )


@_admin_only
async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text(
            t("welcome.usage_set", name="{name}", chat="{chat}"), parse_mode="HTML",
        )
        return
    raw = " ".join(context.args)
    chat_id = update.effective_chat.id
    clean_text, buttons = _parse_rose_buttons(raw)
    n = settings_sync.apply_welcome(db, chat_id, clean_text, buttons if buttons else None)
    scope = t("cfg.in_n", n=n) if n > 1 else ""
    if buttons:
        await update.effective_message.reply_text(
            t("welcome.updated_buttons", n=len(buttons), scope=scope),
            parse_mode="HTML",
        )
    else:
        await update.effective_message.reply_text(t("welcome.updated_nobuttons", scope=scope))


@_admin_only
async def cmd_setwelcomebutton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Añade un botón individual: /setwelcomebutton Texto | https://url [same]"""
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text(
            t("welcomebtn.usage_set"),
            parse_mode="HTML",
        )
        return
    raw = " ".join(context.args)
    same = False
    if raw.rstrip().endswith(" same"):
        same = True
        raw = raw.rstrip()[:-5].rstrip()
    if "|" not in raw:
        await update.effective_message.reply_text(t("welcomebtn.missing_pipe"), parse_mode="HTML")
        return
    text, url = (s.strip() for s in raw.split("|", 1))
    if not text or not url:
        await update.effective_message.reply_text(t("welcomebtn.missing_fields"))
        return
    if not url.startswith(("http://", "https://", "tg://")):
        url = "https://" + url
    bid = db.add_welcome_button(update.effective_chat.id, text, url, same_row=same)
    await update.effective_message.reply_text(
        f"✅ Botón #{bid} añadido: <code>{html.escape(text)}</code> → {html.escape(url)}"
        + (" (misma fila)" if same else ""),
        parse_mode="HTML",
    )


@_admin_only
async def cmd_welcomebuttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if chat_picker.is_dm(update):
        await chat_picker.show_chat_picker(update, context, "welcomebuttons")
        return
    chat_id = update.effective_chat.id
    db.migrate_legacy_welcome_button(chat_id)
    btns = db.list_welcome_buttons(chat_id)
    if not btns:
        await update.effective_message.reply_text(t("welcomebtn.none"))
        return
    lines = [t("welcomebtn.list_header")]
    for b in btns:
        row_tag = t("welcomebtn.same_row") if b["same_row"] else ""
        lines.append(f"#{b['id']} — <code>{html.escape(b['text'])}</code> → <code>{html.escape(b['url'])}</code>{row_tag}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def _welcomebuttons_picker_handler(update: Update, context, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    db.migrate_legacy_welcome_button(chat_id)
    btns = db.list_welcome_buttons(chat_id)
    if not btns:
        await update.callback_query.edit_message_text(t("welcomebtn.none_chat"))
        return
    lines = [t("welcomebtn.list_header")]
    for b in btns:
        row_tag = t("welcomebtn.same_row") if b["same_row"] else ""
        lines.append(f"#{b['id']} — <code>{html.escape(b['text'])}</code> → <code>{html.escape(b['url'])}</code>{row_tag}")
    await update.callback_query.edit_message_text("\n".join(lines), parse_mode="HTML")


@_admin_only
async def cmd_rmwelcomebutton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text(t("welcomebtn.usage_rm"))
        return
    db: DB = context.bot_data["db"]
    ok = db.delete_welcome_button(int(context.args[0]))
    await update.effective_message.reply_text("✅ Botón eliminado." if ok else "No existe ese ID.")


@_admin_only
async def cmd_clearwelcomebuttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    n = db.clear_welcome_buttons(update.effective_chat.id)
    await update.effective_message.reply_text(t("welcomebtn.cleared", n=n))


@_admin_only
async def cmd_testwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía al admin el welcome configurado tal como lo vería un nuevo miembro."""
    if chat_picker.is_dm(update):
        await chat_picker.show_chat_picker(update, context, "testwelcome")
        return
    await _render_test_welcome(update, context, update.effective_chat.id)


async def _testwelcome_picker_handler(update: Update, context, chat_id: int, args: str) -> None:
    await update.callback_query.answer()
    await _render_test_welcome(update, context, chat_id)


async def _render_test_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    db: DB = context.bot_data["db"]
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    db.migrate_legacy_welcome_button(chat_id)
    btns = db.list_welcome_buttons(chat_id)
    chat_row = next((c for c in db.all_chats() if c["chat_id"] == chat_id), None)
    chat_title = chat_row["title"] if chat_row else str(chat_id)
    welcome_text = s["welcome_text"] or i18n.t("welcome.default")
    user = update.effective_user
    name = html.escape(user.first_name or user.username or str(user.id))
    text = welcome_text.format(name=name, chat=html.escape(chat_title))
    # Mostramos también el botón "Soy humano" (no funcional aquí)
    rows = [[InlineKeyboardButton("✅ SOY HUMANO (PULSA PARA ENTRAR)", callback_data="verify:test:0")]]
    if btns:
        current_row = []
        for b in btns:
            btn = InlineKeyboardButton(b["text"], url=b["url"])
            if b["same_row"] and current_row:
                current_row.append(btn)
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [btn]
        if current_row:
            rows.append(current_row)
    header = t("welcome.preview_header", chat=html.escape(chat_title))
    target_chat = update.effective_chat.id
    await context.bot.send_message(
        chat_id=target_chat, text=header + text,
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
    )


@_admin_only
async def cmd_resetwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    settings_sync.apply_setting(db, update.effective_chat.id, "welcome_text", None)
    settings_sync.apply_setting(db, update.effective_chat.id, "welcome_button_text", None)
    settings_sync.apply_setting(db, update.effective_chat.id, "welcome_button_url", None)
    await update.effective_message.reply_text(t("welcome.reset"))


@_admin_only
async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if chat_picker.is_dm(update):
        await chat_picker.show_chat_picker(update, context, "rules")
        return
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    if not s["rules_text"]:
        await update.effective_message.reply_text(t("rules.none"), parse_mode="HTML")
        return
    await update.effective_message.reply_text(
        t("rules.show", rules=s["rules_text"]),
        parse_mode="HTML",
    )


@_admin_only
async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text(t("rules.usage_set"))
        return
    text = " ".join(context.args)
    settings_sync.apply_setting(db, update.effective_chat.id, "rules_text", text)
    await update.effective_message.reply_text(t("rules.updated"))


@_admin_only
async def cmd_cleanservice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        state = "ON" if s["cleanservice"] else "OFF"
        await update.effective_message.reply_text(
            t("cleanservice.status", state=state),
            parse_mode="HTML",
        )
        return
    val = context.args[0].lower()
    if val in ("on", "true", "yes", "1"):
        settings_sync.apply_setting(db, chat_id, "cleanservice", 1)
        await update.effective_message.reply_text(t("cleanservice.on"))
    elif val in ("off", "false", "no", "0"):
        settings_sync.apply_setting(db, chat_id, "cleanservice", 0)
        await update.effective_message.reply_text(t("cleanservice.off"))
    else:
        await update.effective_message.reply_text(t("cleanservice.usage"))


_ON = ("on", "true", "yes", "sí", "si", "1")
_OFF = ("off", "false", "no", "0")


@_admin_only
async def cmd_verificacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestiona la verificación humana del chat: on/off (con el welcome), recordatorios,
    qué pasa al no verificar (kick o quedar muteado) y los tiempos."""
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    args = [a.lower() for a in (context.args or [])]
    reply = update.effective_message.reply_text

    # --- Sin argumentos: estado completo + ayuda de subcomandos ---
    if not args:
        s = db.get_chat_settings(chat_id)
        accion = "expulsar (kick)" if s["verification_kick_normal"] else "dejar MUTEADO para siempre"
        await reply(
            "🧩 <b>Verificación del chat</b>\n"
            f"• Verificación + bienvenida: <b>{'ON' if s['verification_enabled'] else 'OFF'}</b>\n"
            f"• Revisión privada de sospechosos: <b>{'ON' if s['verification_review_suspicious'] else 'OFF'}</b>\n"
            f"• Recordatorios a los normales: <b>{'ON' if s['verification_reminders_enabled'] else 'OFF'}</b>\n"
            f"• Al no verificar (normales): <b>{accion}</b>\n"
            f"• Tiempos: sospechosos kick a <b>{s['verification_suspicious_kick_minutes']} min</b> · "
            f"recordatorio a las <b>{s['verification_reminder_hours']} h</b> · "
            f"kick <b>+{s['verification_kick_after_reminder_hours']} h</b> tras el recordatorio\n\n"
            "<b>Ajustes</b> (solo en este grupo):\n"
            "<code>/verificacion on|off</code> — activa/desactiva verificación Y bienvenida\n"
            "<code>/verificacion revisar on|off</code> — sin verificar en grupo: aviso PRIVADO de "
            "cada sospechoso con botones Permitir/Banear (entra permitido por defecto)\n"
            "<code>/verificacion avisos on|off</code> — recordatorio antes de expulsar\n"
            "<code>/verificacion accion kick|mute</code> — al no verificar: expulsar o quedar muteado\n"
            "<code>/verificacion tiempos &lt;susp_min&gt; &lt;recordatorio_h&gt; &lt;kick_h&gt;</code>\n"
            "   ej. <code>/verificacion tiempos 30 3 6</code> (sospechoso 30min, recordatorio 3h, kick +6h)\n\n"
            "<i>Los sospechosos (perfil dudoso) siempre se expulsan al pasar su tiempo; el resto "
            "de opciones aplican a los usuarios normales. La moderación de mensajes es aparte.</i>",
            parse_mode="HTML",
        )
        return

    sub = args[0]

    # --- on/off (verificación + welcome) ---
    if sub in _ON or sub in _OFF:
        val = 1 if sub in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_enabled", val)
        if val:
            await reply("✅ Verificación + bienvenida <b>ON</b>.", parse_mode="HTML")
        else:
            await reply(
                "✅ Verificación + bienvenida <b>OFF</b>. Los nuevos entran directos, sin "
                "verificación ni bienvenida. La moderación de mensajes sigue activa.",
                parse_mode="HTML",
            )
        return

    # --- revisar (revisión privada de sospechosos) on/off ---
    if sub == "revisar" and len(args) >= 2:
        val = 1 if args[1] in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_review_suspicious", val)
        if val:
            await reply(
                "✅ Revisión privada de sospechosos <b>ON</b>. Los perfiles sospechosos entran "
                "al grupo (sin verificación) y te llega un aviso privado con botones "
                "<b>Permitir</b> / <b>Banear</b>. Por defecto quedan permitidos.\n"
                "<i>Consejo: combínalo con <code>/verificacion off</code> si no quieres NINGUNA "
                "verificación en el grupo.</i>", parse_mode="HTML",
            )
        else:
            await reply("✅ Revisión privada de sospechosos <b>OFF</b>.", parse_mode="HTML")
        return

    # --- avisos (recordatorios) on/off ---
    if sub == "avisos" and len(args) >= 2:
        val = 1 if args[1] in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_reminders_enabled", val)
        await reply(f"✅ Recordatorios a los normales: <b>{'ON' if val else 'OFF'}</b>.", parse_mode="HTML")
        return

    # --- accion kick|mute ---
    if sub in ("accion", "acción") and len(args) >= 2:
        if args[1] == "kick":
            settings_sync.apply_setting(db, chat_id, "verification_kick_normal", 1)
            await reply("✅ Al no verificar, los normales serán <b>expulsados</b> (kick).", parse_mode="HTML")
        elif args[1] == "mute":
            settings_sync.apply_setting(db, chat_id, "verification_kick_normal", 0)
            await reply(
                "✅ Al no verificar, los normales quedarán <b>muteados para siempre</b> (sin kick, "
                "sin recordatorio). Podrán verificar cuando quieran.", parse_mode="HTML",
            )
        else:
            await reply("Uso: /verificacion accion kick|mute")
        return

    # --- tiempos <susp_min> <recordatorio_h> <kick_h> ---
    if sub == "tiempos" and len(args) >= 4:
        try:
            susp, rem, kick = int(args[1]), int(args[2]), int(args[3])
        except ValueError:
            await reply("Números inválidos. Ej: /verificacion tiempos 30 3 6")
            return
        if not (0 < susp <= 1440 and 0 < rem <= 168 and 0 < kick <= 168):
            await reply("Fuera de rango. susp_min 1-1440, horas 1-168. Ej: /verificacion tiempos 30 3 6")
            return
        settings_sync.apply_setting(db, chat_id, "verification_suspicious_kick_minutes", susp)
        settings_sync.apply_setting(db, chat_id, "verification_reminder_hours", rem)
        settings_sync.apply_setting(db, chat_id, "verification_kick_after_reminder_hours", kick)
        await reply(
            f"✅ Tiempos: sospechosos kick a <b>{susp} min</b> · recordatorio a las <b>{rem} h</b> · "
            f"kick <b>+{kick} h</b> tras el recordatorio (total normales: {rem + kick} h).",
            parse_mode="HTML",
        )
        return

    await reply("Uso: /verificacion  (sin nada muestra el estado y las opciones)")
