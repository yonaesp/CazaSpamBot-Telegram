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

log = logging.getLogger(__name__)

HIDE_PREF = "hide_group_commands"
CLEAN_PREF = "clean_group_commands"

# Menú de comandos de Telegram (el que sale al teclear "/"). Los admin-only se
# muestran solo en el DM del admin; a todos los demás solo /help y /comandos.
_ADMIN_MENU = [
    ("help", "Guía y lista de comandos"),
    ("comandos", "Lista de comandos"),
    ("stats", "Métricas del grupo"),
    ("chats", "Grupos donde opero"),
    ("recent", "Últimas acciones antispam"),
    ("ban", "Banear (reply o @usuario) en todos los grupos"),
    ("unban", "Quitar el ban a un usuario"),
    ("whitelist", "Marcar un usuario como inmune"),
    ("notspam", "Revertir un falso positivo (id de /recent)"),
    ("warn", "Avisar a un usuario (warn)"),
    ("warns", "Ver los warns de un usuario"),
    ("warnlimit", "Límite de warns antes de sancionar"),
    ("warnaction", "Acción al llegar al límite (ban/kick/mute)"),
    ("spam", "Aprender: marcar mensaje como spam + banear"),
    ("legal", "Aprender: marcar mensaje como legítimo"),
    ("samples", "Ver muestras aprendidas"),
    ("forget", "Olvidar una muestra aprendida"),
    ("scan", "Analizar un mensaje: ¿lo detectaría? (responde al mensaje)"),
    ("config", "Panel de ajustes del grupo con botones"),
    ("sync", "Sincronizar ajustes iguales en todos los grupos (on/off)"),
    ("limpieza", "Ocultar/auto-borrar comandos del bot en grupos"),
    ("verificacion", "Ajustar verificación humana del grupo"),
    ("welcome", "Ver la bienvenida"),
    ("setwelcome", "Cambiar la bienvenida"),
    ("rules", "Ver las reglas"),
    ("setrules", "Cambiar las reglas"),
    ("cleanservice", "Borrar mensajes de 'X se ha unido'"),
    ("alertas", "Activar o silenciar avisos informativos"),
    ("shadow", "Ver o cambiar el modo shadow"),
    ("top", "Ranking de mensajes"),
    ("topweekly", "Ranking semanal"),
]
_PUBLIC_MENU = [
    ("help", "Cómo funciona el bot y comandos"),
    ("comandos", "Ver los comandos disponibles"),
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
    try:
        await bot.set_my_commands(
            [BotCommand(c, d) for c, d in _PUBLIC_MENU], scope=BotCommandScopeDefault())
        if cfg.admin_user_id:
            await bot.set_my_commands(
                [BotCommand(c, d) for c, d in _ADMIN_MENU],
                scope=BotCommandScopeChat(chat_id=cfg.admin_user_id))
        if hide_on(db):
            await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        else:
            await bot.set_my_commands(
                [BotCommand(c, d) for c, d in _PUBLIC_MENU], scope=BotCommandScopeAllGroupChats())
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
        return "✅ ON" if v else "❌ OFF"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🙈 Ocultar comandos en grupos: {onoff(hide_on(db))}",
                              callback_data="clean:hide")],
        [InlineKeyboardButton(f"🧽 Auto-borrar comandos en grupos: {onoff(clean_on(db))}",
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
        "🧹 <b>Limpieza en grupos</b>\n"
        "Para mantener los grupos limpios: que los comandos del bot no salgan al teclear "
        "«/» y que no queden escritos en el chat.",
        parse_mode="HTML", reply_markup=_clean_keyboard(db))


async def on_clean_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.data.startswith("clean:"):
        return
    cfg = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer("Solo el admin del bot puede configurar.", show_alert=True)
        return
    action = q.data.split(":")[1]
    if action == "hide":
        set_hide(db, not hide_on(db))
        await apply_command_menu(context.bot, cfg, db)  # re-publica el menú
        await q.answer("Comandos en grupos: " + ("ocultos" if hide_on(db) else "visibles"))
    elif action == "autodel":
        set_clean(db, not clean_on(db))
        await q.answer("Auto-borrado: " + ("ON" if clean_on(db) else "OFF"))
    else:
        await q.answer()
        return
    try:
        await q.edit_message_reply_markup(reply_markup=_clean_keyboard(db))
    except TelegramError:
        pass
