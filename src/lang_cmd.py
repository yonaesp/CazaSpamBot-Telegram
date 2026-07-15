"""Comando /idioma — idioma global del bot (persiste). También resuelve el idioma
al arrancar: pref guardada > env BOT_LANG / locale del sistema > 'es'."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from . import i18n
from .db import DB

LANG_PREF = "lang"


def resolve_and_apply(db: DB) -> str:
    """Fija el idioma global al arrancar y devuelve el código efectivo."""
    stored = db.get_text_pref(LANG_PREF)
    lang = stored if i18n.is_supported(stored) else i18n.detect_system_lang()
    return i18n.set_lang(lang)


async def cmd_idioma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/idioma [es|en] — ver o cambiar el idioma del bot (solo admin)."""
    cfg = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    args = context.args or []
    if not args:
        await update.effective_message.reply_text(
            i18n.t("lang.current", lang=i18n.current_lang()), parse_mode="HTML")
        return
    want = args[0].strip().lower()[:2]
    if not i18n.is_supported(want):
        await update.effective_message.reply_text(i18n.t("lang.invalid"), parse_mode="HTML")
        return
    db.set_text_pref(LANG_PREF, want)
    i18n.set_lang(want)
    # Re-publica el menú de comandos de Telegram en el nuevo idioma.
    from . import group_clean
    try:
        await group_clean.apply_command_menu(context.bot, cfg, db)
    except Exception:  # noqa: BLE001 — no debe impedir el cambio de idioma
        pass
    await update.effective_message.reply_text(i18n.t("lang.set", lang=want), parse_mode="HTML")
