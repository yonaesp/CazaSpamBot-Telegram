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
        t("welcomebtn.added", id=bid, text=html.escape(text), url=html.escape(url),
          same=t("welcomebtn.same_row") if same else ""),
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
    await update.effective_message.reply_text(t("welcomebtn.removed") if ok else t("welcomebtn.not_found"))


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
    rows = [[InlineKeyboardButton(t("verif.btn_human"), callback_data="verify:test:0")]]
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
        state = t("common.on") if s["cleanservice"] else t("common.off")
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
        # El bloque entero va en UNA clave: el HTML abre y cierra dentro del mismo texto,
        # así que trocearlo por líneas dejaría etiquetas desbalanceadas al traducir y
        # Telegram rechazaría el mensaje completo.
        await reply(
            t(
                "verifcfg.status",
                verif=t("common.on") if s["verification_enabled"] else t("common.off"),
                review=t("common.on") if s["verification_review_suspicious"] else t("common.off"),
                reminders=t("common.on") if s["verification_reminders_enabled"] else t("common.off"),
                action=t("verifcfg.action_kick") if s["verification_kick_normal"] else t("verifcfg.action_mute"),
                susp_min=s["verification_suspicious_kick_minutes"],
                rem_h=s["verification_reminder_hours"],
                kick_h=s["verification_kick_after_reminder_hours"],
            ),
            parse_mode="HTML",
        )
        return

    sub = args[0]

    # --- on/off (verificación + welcome) ---
    if sub in _ON or sub in _OFF:
        val = 1 if sub in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_enabled", val)
        await reply(t("verifcfg.set_on") if val else t("verifcfg.set_off"), parse_mode="HTML")
        return

    # --- revisar (revisión privada de sospechosos) on/off ---
    if sub == "revisar" and len(args) >= 2:
        val = 1 if args[1] in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_review_suspicious", val)
        await reply(t("verifcfg.review_on") if val else t("verifcfg.review_off"), parse_mode="HTML")
        return

    # --- avisos (recordatorios) on/off ---
    if sub == "avisos" and len(args) >= 2:
        val = 1 if args[1] in _ON else 0
        settings_sync.apply_setting(db, chat_id, "verification_reminders_enabled", val)
        await reply(
            t("verifcfg.reminders_set", state=t("common.on") if val else t("common.off")),
            parse_mode="HTML",
        )
        return

    # --- accion kick|mute ---
    if sub in ("accion", "acción") and len(args) >= 2:
        if args[1] == "kick":
            settings_sync.apply_setting(db, chat_id, "verification_kick_normal", 1)
            await reply(t("verifcfg.action_set_kick"), parse_mode="HTML")
        elif args[1] == "mute":
            settings_sync.apply_setting(db, chat_id, "verification_kick_normal", 0)
            await reply(t("verifcfg.action_set_mute"), parse_mode="HTML")
        else:
            await reply(t("verifcfg.usage_action"))
        return

    # --- tiempos <susp_min> <recordatorio_h> <kick_h> ---
    if sub == "tiempos" and len(args) >= 4:
        try:
            susp, rem, kick = int(args[1]), int(args[2]), int(args[3])
        except ValueError:
            await reply(t("verifcfg.times_invalid"))
            return
        if not (0 < susp <= 1440 and 0 < rem <= 168 and 0 < kick <= 168):
            await reply(t("verifcfg.times_range"))
            return
        settings_sync.apply_setting(db, chat_id, "verification_suspicious_kick_minutes", susp)
        settings_sync.apply_setting(db, chat_id, "verification_reminder_hours", rem)
        settings_sync.apply_setting(db, chat_id, "verification_kick_after_reminder_hours", kick)
        await reply(
            t("verifcfg.times_set", susp_min=susp, rem_h=rem, kick_h=kick, total_h=rem + kick),
            parse_mode="HTML",
        )
        return

    await reply(t("verifcfg.usage"))
