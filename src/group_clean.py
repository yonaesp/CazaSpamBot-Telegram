"""Limpieza en grupos: mantener los grupos lo más limpios posible.

Dos preferencias globales (por defecto ON):
  - `hide_group_commands`: oculta el menú de comandos del bot en los grupos (no salen
    al teclear "/"), para que los usuarios no los vean ni los toqueteen. En el DM del
    admin y en privados siguen visibles.
  - `clean_group_commands`: borra en los grupos los mensajes que invocan un comando del
    bot (los escriba el admin o los toque un usuario re-enviándolos), para no ensuciar.

También aloja el menú de comandos de Telegram y el panel visual `/limpieza`.
"""
from __future__ import annotations

import logging

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .db import DB
from .i18n import t

log = logging.getLogger(__name__)

HIDE_PREF = "hide_group_commands"
CLEAN_PREF = "clean_group_commands"

# Menú de comandos de Telegram (el que sale al teclear "/"). Cada entrada es
# (nombre_comando, clave_i18n); la descripción se traduce con t() según el idioma.
# Los admin-only se muestran solo en el DM del admin; a todos los demás /help y /comandos.
_ADMIN_MENU = [
    ("help", "cmd.help"),
    ("comandos", "cmd.comandos"),
    ("stats", "cmd.stats"),
    ("chats", "cmd.chats"),
    ("recent", "cmd.recent"),
    ("ban", "cmd.ban"),
    ("unban", "cmd.unban"),
    ("whitelist", "cmd.whitelist"),
    ("notspam", "cmd.notspam"),
    ("warn", "cmd.warn"),
    ("warns", "cmd.warns"),
    ("warnlimit", "cmd.warnlimit"),
    ("warnaction", "cmd.warnaction"),
    ("spam", "cmd.spam"),
    ("legal", "cmd.legal"),
    ("samples", "cmd.samples"),
    ("forget", "cmd.forget"),
    ("scan", "cmd.scan"),
    ("config", "cmd.config"),
    ("sync", "cmd.sync"),
    ("quips", "cmd.quips"),
    ("limpieza", "cmd.limpieza"),
    ("idioma", "cmd.idioma"),
    ("verificacion", "cmd.verificacion"),
    ("welcome", "cmd.welcome"),
    ("setwelcome", "cmd.setwelcome"),
    ("rules", "cmd.rules"),
    ("setrules", "cmd.setrules"),
    ("cleanservice", "cmd.cleanservice"),
    ("alertas", "cmd.alertas"),
    ("shadow", "cmd.shadow"),
    ("top", "cmd.top"),
    ("topweekly", "cmd.topweekly"),
]
_PUBLIC_MENU = [
    ("help", "cmd.help"),
    ("comandos", "cmd.comandos"),
]


def hide_on(db: DB) -> bool:
    v = db.get_pref(HIDE_PREF)
    return True if v is None else bool(v)


def clean_on(db: DB) -> bool:
    v = db.get_pref(CLEAN_PREF)
    return True if v is None else bool(v)


def set_hide(db: DB, on: bool) -> None:
    db.set_pref(HIDE_PREF, on)


def set_clean(db: DB, on: bool) -> None:
    db.set_pref(CLEAN_PREF, on)


async def apply_command_menu(bot, cfg, db: DB) -> None:
    """Publica el menú de comandos: público (privados), admin (su DM) y grupos
    (ocultos o solo público según la preferencia). No debe impedir el arranque."""
    pub = [BotCommand(c, t(k)) for c, k in _PUBLIC_MENU]
    try:
        await bot.set_my_commands(pub, scope=BotCommandScopeDefault())
        if cfg.admin_user_id:
            await bot.set_my_commands(
                [BotCommand(c, t(k)) for c, k in _ADMIN_MENU],
                scope=BotCommandScopeChat(chat_id=cfg.admin_user_id))
        if hide_on(db):
            await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        else:
            await bot.set_my_commands(pub, scope=BotCommandScopeAllGroupChats())
        log.info("Menú de comandos publicado (%d admin, %d público; grupos: %s).",
                 len(_ADMIN_MENU), len(_PUBLIC_MENU), "ocultos" if hide_on(db) else "visibles")
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo publicar el menú de comandos: %s", exc)


async def on_group_command_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler (grupo aparte): borra en grupos los mensajes que invocan un comando del
    bot, si la limpieza está activa. Evita que queden y que los usuarios los toquen."""
    db: DB = context.bot_data["db"]
    if not clean_on(db):
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return
    token = msg.text.split(maxsplit=1)[0].lstrip("/").split("@")[0].lower()
    if token and token in context.bot_data.get("command_names", set()):
        try:
            await context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.message_id)
        except TelegramError:
            pass


# ------------------------------ panel /limpieza ------------------------------

def _clean_keyboard(db: DB) -> InlineKeyboardMarkup:
    def onoff(v: bool) -> str:
        return t("on") if v else t("off")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("clean.b.hide", state=onoff(hide_on(db))),
                              callback_data="clean:hide")],
        [InlineKeyboardButton(t("clean.b.autodel", state=onoff(clean_on(db))),
                              callback_data="clean:autodel")],
    ])


async def cmd_limpieza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/limpieza — panel para ocultar los comandos en grupos y auto-borrarlos."""
    cfg = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    await update.effective_message.reply_text(
        t("clean.panel"), parse_mode="HTML", reply_markup=_clean_keyboard(db))


async def on_clean_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("clean:"):
        return
    cfg = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("cfg.only_admin"), show_alert=True)
        return
    action = q.data.split(":")[1]
    if action == "hide":
        set_hide(db, not hide_on(db))
        await apply_command_menu(context.bot, cfg, db)  # re-publica el menú
        await q.answer(t("clean.hidden") if hide_on(db) else t("clean.visible"))
    elif action == "autodel":
        set_clean(db, not clean_on(db))
        await q.answer(t("clean.autodel_on") if clean_on(db) else t("clean.autodel_off"))
    else:
        await q.answer()
        return
    try:
        await q.edit_message_reply_markup(reply_markup=_clean_keyboard(db))
    except TelegramError:
        pass
