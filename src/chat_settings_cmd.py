"""Comandos para gestionar settings de cada chat: welcome, rules, etc."""
from __future__ import annotations

import html
import logging

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from . import chat_picker, verification
from .config import Config
from .db import DB

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
        return (
            "ℹ️ Sin welcome custom — se usa el default. Para configurar:\n"
            "<code>/setwelcome &lt;texto&gt;</code> (placeholders {name} {chat})"
        )
    enabled = "✅ activado" if s["welcome_enabled"] else "❌ desactivado"
    btn_part = ""
    if s["welcome_button_text"]:
        btn_part = f"\n\n🔘 Botón: <code>{html.escape(s['welcome_button_text'])}</code>"
        if s["welcome_button_url"]:
            btn_part += f" → <code>{html.escape(s['welcome_button_url'])}</code>"
    return f"<b>Welcome actual</b> ({enabled}):\n\n<pre>{html.escape(s['welcome_text'])}</pre>{btn_part}"


async def _welcome_picker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    text = await _render_welcome(db, chat_id)
    await update.callback_query.edit_message_text(text, parse_mode="HTML")


async def _rules_picker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    if not s or not s["rules_text"]:
        await update.callback_query.edit_message_text("ℹ️ Sin reglas configuradas para ese chat.")
        return
    await update.callback_query.edit_message_text(
        f"📜 <b>Reglas</b>\n\n{s['rules_text']}", parse_mode="HTML",
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
        await update.effective_message.reply_text(
            "ℹ️ Sin welcome custom — se usa el default. Para configurar:\n"
            "<code>/setwelcome &lt;texto&gt;</code> (usa {name} y {chat} como placeholders)",
            parse_mode="HTML",
        )
        return
    enabled = "✅ activado" if s["welcome_enabled"] else "❌ desactivado"
    btn_part = ""
    if s['welcome_button_text']:
        btn_part = f"\n\n🔘 Botón: <code>{html.escape(s['welcome_button_text'])}</code>"
        if s['welcome_button_url']:
            btn_part += f" → <code>{html.escape(s['welcome_button_url'])}</code>"
    await update.effective_message.reply_text(
        f"<b>Welcome actual</b> ({enabled}):\n\n<pre>{html.escape(s['welcome_text'])}</pre>{btn_part}",
        parse_mode="HTML",
    )


@_admin_only
async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text(
            "Uso: <code>/setwelcome &lt;texto&gt;</code>\n\n"
            "<b>Placeholders</b>: <code>{name}</code>, <code>{chat}</code>\n"
            "<b>HTML</b> permitido: &lt;b&gt; &lt;i&gt; &lt;code&gt; etc.\n\n"
            "<b>Botones inline</b> (sintaxis Rose):\n"
            "<code>[Texto](buttonurl://https://url.com)</code> — botón en fila propia\n"
            "<code>[Texto](buttonurl://https://url.com:same)</code> — botón en la misma fila que el anterior",
            parse_mode="HTML",
        )
        return
    raw = " ".join(context.args)
    chat_id = update.effective_chat.id
    clean_text, buttons = _parse_rose_buttons(raw)
    db.update_chat_setting(chat_id, "welcome_text", clean_text)
    if buttons:
        db.clear_welcome_buttons(chat_id)
        for b in buttons:
            db.add_welcome_button(chat_id, b["text"], b["url"], same_row=b["same_row"])
        await update.effective_message.reply_text(
            f"✅ Welcome actualizado + <b>{len(buttons)} botón(es)</b> inline configurados.",
            parse_mode="HTML",
        )
    else:
        await update.effective_message.reply_text("✅ Welcome actualizado (sin botones).")


@_admin_only
async def cmd_setwelcomebutton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Añade un botón individual: /setwelcomebutton Texto | https://url [same]"""
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text(
            "Uso: <code>/setwelcomebutton Texto del botón | https://url.com [same]</code>\n"
            "<code>same</code> al final = mismo renglón que el botón anterior.",
            parse_mode="HTML",
        )
        return
    raw = " ".join(context.args)
    same = False
    if raw.rstrip().endswith(" same"):
        same = True
        raw = raw.rstrip()[:-5].rstrip()
    if "|" not in raw:
        await update.effective_message.reply_text("Falta el <code>|</code> separando texto y URL.", parse_mode="HTML")
        return
    text, url = (s.strip() for s in raw.split("|", 1))
    if not text or not url:
        await update.effective_message.reply_text("Texto y URL requeridos.")
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
        await update.effective_message.reply_text("Sin botones configurados.")
        return
    lines = ["<b>Botones welcome</b>"]
    for b in btns:
        row_tag = " <i>(misma fila)</i>" if b["same_row"] else ""
        lines.append(f"#{b['id']} — <code>{html.escape(b['text'])}</code> → <code>{html.escape(b['url'])}</code>{row_tag}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def _welcomebuttons_picker_handler(update: Update, context, chat_id: int, args: str) -> None:
    db: DB = context.bot_data["db"]
    db.migrate_legacy_welcome_button(chat_id)
    btns = db.list_welcome_buttons(chat_id)
    if not btns:
        await update.callback_query.edit_message_text("Sin botones configurados en ese chat.")
        return
    lines = ["<b>Botones welcome</b>"]
    for b in btns:
        row_tag = " <i>(misma fila)</i>" if b["same_row"] else ""
        lines.append(f"#{b['id']} — <code>{html.escape(b['text'])}</code> → <code>{html.escape(b['url'])}</code>{row_tag}")
    await update.callback_query.edit_message_text("\n".join(lines), parse_mode="HTML")


@_admin_only
async def cmd_rmwelcomebutton(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Uso: /rmwelcomebutton <id> (ID visible con /welcomebuttons)")
        return
    db: DB = context.bot_data["db"]
    ok = db.delete_welcome_button(int(context.args[0]))
    await update.effective_message.reply_text("✅ Botón eliminado." if ok else "No existe ese ID.")


@_admin_only
async def cmd_clearwelcomebuttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    n = db.clear_welcome_buttons(update.effective_chat.id)
    await update.effective_message.reply_text(f"✅ {n} botón(es) eliminados.")


@_admin_only
async def cmd_testwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía al admin el welcome configurado tal como lo vería un nuevo miembro."""
    db: DB = context.bot_data["db"]
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
    welcome_text = s["welcome_text"] or verification.DEFAULT_WELCOME
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
    header = f"🧪 <b>Preview del welcome — {html.escape(chat_title)}</b>\n<i>(Así lo verá un nuevo miembro)</i>\n\n"
    target_chat = update.effective_chat.id
    await context.bot.send_message(
        chat_id=target_chat, text=header + text,
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
    )


@_admin_only
async def cmd_resetwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    db.update_chat_setting(update.effective_chat.id, "welcome_text", None)
    db.update_chat_setting(update.effective_chat.id, "welcome_button_text", None)
    db.update_chat_setting(update.effective_chat.id, "welcome_button_url", None)
    await update.effective_message.reply_text("✅ Welcome resetado al default.")


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
        await update.effective_message.reply_text("ℹ️ Sin reglas configuradas. Usa <code>/setrules</code>", parse_mode="HTML")
        return
    await update.effective_message.reply_text(
        f"📜 <b>Reglas</b>\n\n{s['rules_text']}",
        parse_mode="HTML",
    )


@_admin_only
async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if not context.args:
        await update.effective_message.reply_text("Uso: /setrules <texto>")
        return
    text = " ".join(context.args)
    db.update_chat_setting(update.effective_chat.id, "rules_text", text)
    await update.effective_message.reply_text("✅ Reglas actualizadas.")


@_admin_only
async def cmd_cleanservice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    chat_id = update.effective_chat.id
    db.ensure_chat_settings(chat_id)
    if not context.args:
        s = db.get_chat_settings(chat_id)
        state = "ON" if s["cleanservice"] else "OFF"
        await update.effective_message.reply_text(
            f"Cleanservice actual: <b>{state}</b>\nUso: /cleanservice on|off",
            parse_mode="HTML",
        )
        return
    val = context.args[0].lower()
    if val in ("on", "true", "yes", "1"):
        db.update_chat_setting(chat_id, "cleanservice", 1)
        await update.effective_message.reply_text("✅ Cleanservice ON")
    elif val in ("off", "false", "no", "0"):
        db.update_chat_setting(chat_id, "cleanservice", 0)
        await update.effective_message.reply_text("✅ Cleanservice OFF")
    else:
        await update.effective_message.reply_text("Uso: /cleanservice on|off")
