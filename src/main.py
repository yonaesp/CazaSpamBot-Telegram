"""Bot Antispam Telegram (CazaSpamBot) — entry point."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    filters,
)

from . import admin, chat_picker, chat_settings_cmd, maintenance, telethon_bridge, topweekly, verification, warns_mod
from .config import load_config
from .db import DB
from .handlers import (
    on_chat_member,
    on_edited_message,
    on_message,
    on_message_reaction,
    on_my_chat_member,
    on_service_message,
)
from .notifier import Notifier
from .reporter import SpamReporter


def _warn_telethon_requirements(cfg, telethon_ready: bool) -> None:
    """Avisa si hay opciones ACTIVADAS que requieren la cuenta Telethon (opcional)
    pero Telethon no está disponible. Esas opciones se quedan desactivadas de facto.

    Es el momento "al querer activarlas se avisa": el usuario pone la opción en
    .env, arranca, y ve el aviso de que falta configurar Telethon.
    """
    if telethon_ready:
        return
    log = logging.getLogger("antispam")
    faltan: list[str] = []
    if cfg.report_before_ban:
        faltan.append("REPORT_BEFORE_BAN (reportes oficiales de spam)")
    if os.getenv("NOTIFY_SELF_DELETES", "false").strip().lower() in ("1", "true", "yes", "on"):
        faltan.append("NOTIFY_SELF_DELETES (saber quién borró un mensaje, vía admin_log)")
    if not faltan:
        return
    log.warning(
        "OPCIONES QUE REQUIEREN LA CUENTA TELETHON (opcional) están activadas pero "
        "Telethon no está disponible → se quedan DESACTIVADAS: %s. Para usarlas: pon "
        "TELETHON_ENABLED=true, configura TG_API_ID/TG_API_HASH y genera la sesión con "
        "scripts/telethon_login.py (crea data/telethon.session).",
        "; ".join(faltan),
    )


async def _post_init(app: Application) -> None:
    cfg = app.bot_data["cfg"]
    app.bot_data["http"] = aiohttp.ClientSession()
    app.bot_data["notifier"] = Notifier(
        casa_yona_token=cfg.casa_yona_token,
        notify_chat_id=cfg.admin_notify_chat_id or cfg.casa_yona_chat_yona,
        enabled=cfg.notify_via_casa_yona,
    )
    # Master switch: si TELETHON_ENABLED=false, el reporter NO conecta el cliente
    # Telethon. Todo lo que dependa de él (bio_spam, photos_batch, señales de
    # perfil, reportes oficiales, get_participants, bridge) degrada vía los
    # guards `if client is not None`. Los detectores Bot-API siguen activos.
    reporter = SpamReporter(
        telethon_enabled=cfg.telethon_enabled,
        reporting_enabled=cfg.report_before_ban,
        rate_per_hour=cfg.reporter_rate_per_hour,
        rate_per_day=cfg.reporter_rate_per_day,
    )
    if cfg.telethon_enabled:
        await reporter.start()
    else:
        logging.getLogger("antispam").warning(
            "TELETHON_ENABLED=false → bot SOLO con Bot API. Desactivadas las funciones "
            "que requieren la cuenta Telethon (opcional): bio_spam, photos_batch, señales "
            "de perfil, reportes oficiales, aviso de quién borró un mensaje, get_participants."
        )
    app.bot_data["reporter"] = reporter

    # Avisos claros si hay opciones que REQUIEREN Telethon activadas sin que esté
    # disponible (se quedan desactivadas de facto).
    _warn_telethon_requirements(cfg, telethon_ready=reporter.is_ready())

    # Telethon bridge: listener MessageDeleted para borrar avisos en cascada.
    # get_client() devuelve el cliente aunque los reportes estén desactivados.
    client = reporter.get_client()
    if client is not None:
        try:
            telethon_bridge.attach(client, app.bot, app.bot_data["db"])
            logging.getLogger("antispam").info("Telethon bridge MessageDeleted listener atachado")
        except Exception as exc:
            logging.getLogger("antispam").warning("Telethon bridge falló: %s", exc)

    me = await app.bot.get_me()
    logging.getLogger("antispam").info(
        "Bot @%s (id=%s) listo. Modo=%s. Privacy=%s. Telethon=%s. Reportes=%s",
        me.username, me.id, cfg.mode,
        "off" if me.can_read_all_group_messages else "ON (¡desactiva en BotFather!)",
        "conectado" if reporter.is_ready() else "off",
        "activos" if reporter.reporting_ready() else "off",
    )
    if app.job_queue:
        app.job_queue.run_repeating(_heartbeat_job, interval=30, first=1)
        # Cada 15 min: cleanup verificaciones (3 tiers: kick suspicious 30min +
        # reminder normal 3h + kick post-reminder +6h). 15min basta: el plazo mínimo es 30min.
        app.job_queue.run_repeating(verification.cleanup_job, interval=900, first=60)
        # Cada 24h: cleanup nightly de tablas viejas (reaction_events, gentle_warnings,
        # pending_verifications, cas_cache, suppressions)
        app.job_queue.run_repeating(maintenance.cleanup_nightly_job, interval=86400, first=3600)
        # Top semanal: domingo 20:00 Europe/Madrid (weekday 6)
        from datetime import time as _dt_time
        app.job_queue.run_daily(
            topweekly.weekly_top_job,
            time=_dt_time(hour=20, minute=0, tzinfo=topweekly.TZ_MADRID),
            days=(6,),  # 6 = domingo en PTB JobQueue
            name="topweekly",
        )


async def _post_shutdown(app: Application) -> None:
    rep = app.bot_data.get("reporter")
    if rep:
        await rep.stop()
    sess = app.bot_data.get("http")
    if sess:
        await sess.close()
    db = app.bot_data.get("db")
    if db:
        db.close()


_HEARTBEAT_PATH = Path("/app/data/heartbeat")


async def _heartbeat_job(context) -> None:
    """Toca un fichero cada 30s para el healthcheck del docker-compose."""
    try:
        _HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _HEARTBEAT_PATH.touch()
    except OSError:
        pass


async def _on_error(update: object, context) -> None:
    """Error handler global: captura excepciones NO atrapadas en handlers y jobs.

    - Red transitoria (NetworkError/TimedOut/RetryAfter): el bot se recupera solo
      con el polling; log breve sin traceback para no ensuciar.
    - Error inesperado: traceback completo + aviso al admin con cooldown de 10 min
      (para no spamear si algo entra en bucle). El bot sigue vivo.
    """
    from telegram.error import NetworkError, RetryAfter, TimedOut
    elog = logging.getLogger("antispam")
    err = context.error
    if isinstance(err, (NetworkError, TimedOut, RetryAfter)):
        elog.warning("Red transitoria (%s): %s", type(err).__name__, err)
        return
    elog.error("Excepción no capturada en handler/job", exc_info=err)
    try:
        cfg = context.bot_data.get("cfg")
        admin_id = getattr(cfg, "admin_user_id", 0) if cfg else 0
        if not admin_id:
            return
        import time as _t
        now = _t.time()
        if now - context.bot_data.get("_last_error_dm", 0) < 600:
            return
        context.bot_data["_last_error_dm"] = now
        import html as _html
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                "⚠️ <b>Error interno del bot</b>\n"
                f"<code>{_html.escape(type(err).__name__)}: {_html.escape(str(err))[:300]}</code>\n\n"
                "<i>Capturado (el bot sigue vivo). Revisa los logs para el detalle.</i>"
            ),
            parse_mode="HTML",
        )
    except Exception:  # noqa: BLE001 — nunca dejar que el error handler lance
        pass


def main() -> int:
    cfg = load_config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    log = logging.getLogger("antispam")
    log.info("CazaSpamBot arrancando en modo=%s", cfg.mode)

    db = DB(cfg.db_path)

    app = (
        Application.builder()
        .token(cfg.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["cfg"] = cfg
    app.bot_data["db"] = db

    # Comandos admin (en DMs y grupos, solo admin pasa).
    app.add_handler(CommandHandler("start", admin.cmd_start))
    app.add_handler(CommandHandler("help", admin.cmd_help))
    # /comandos: comando público accesible para CUALQUIER usuario (no solo admin)
    app.add_handler(CommandHandler("comandos", admin.cmd_comandos))
    app.add_handler(CommandHandler("stats", admin.cmd_stats))
    app.add_handler(CommandHandler("chats", admin.cmd_chats))
    app.add_handler(CommandHandler("recent", admin.cmd_recent))
    app.add_handler(CommandHandler("shadow", admin.cmd_shadow))
    app.add_handler(CommandHandler("ban", admin.cmd_ban))
    app.add_handler(CommandHandler("federban", admin.cmd_ban))  # alias retrocompatible
    app.add_handler(CommandHandler("unban", admin.cmd_unban))
    app.add_handler(CommandHandler("whitelist", admin.cmd_whitelist))
    app.add_handler(CommandHandler("notspam", admin.cmd_notspam))
    app.add_handler(CommandHandler("spam", admin.cmd_spam))
    app.add_handler(CommandHandler("legal", admin.cmd_legal))
    app.add_handler(CommandHandler("ham", admin.cmd_ham))  # alias retro
    app.add_handler(CommandHandler("samples", admin.cmd_samples))
    app.add_handler(CommandHandler("forget", admin.cmd_forget))
    app.add_handler(CommandHandler("setgreeter", admin.cmd_setgreeter))
    app.add_handler(CommandHandler("rmgreeter", admin.cmd_rmgreeter))
    app.add_handler(CommandHandler("listgreeters", admin.cmd_listgreeters))
    app.add_handler(CommandHandler("greeters", admin.cmd_listgreeters))  # alias
    app.add_handler(CommandHandler("top", admin.cmd_top))
    app.add_handler(CommandHandler("topweekly", admin.cmd_topweekly))

    # Welcome / rules / cleanservice
    app.add_handler(CommandHandler("welcome", chat_settings_cmd.cmd_welcome))
    app.add_handler(CommandHandler("setwelcome", chat_settings_cmd.cmd_setwelcome))
    app.add_handler(CommandHandler("resetwelcome", chat_settings_cmd.cmd_resetwelcome))
    app.add_handler(CommandHandler("rules", chat_settings_cmd.cmd_rules))
    app.add_handler(CommandHandler("setrules", chat_settings_cmd.cmd_setrules))
    app.add_handler(CommandHandler("cleanservice", chat_settings_cmd.cmd_cleanservice))
    app.add_handler(CommandHandler("setwelcomebutton", chat_settings_cmd.cmd_setwelcomebutton))
    app.add_handler(CommandHandler("welcomebuttons", chat_settings_cmd.cmd_welcomebuttons))
    app.add_handler(CommandHandler("rmwelcomebutton", chat_settings_cmd.cmd_rmwelcomebutton))
    app.add_handler(CommandHandler("clearwelcomebuttons", chat_settings_cmd.cmd_clearwelcomebuttons))
    app.add_handler(CommandHandler("testwelcome", chat_settings_cmd.cmd_testwelcome))

    # Warns (estilo Rose)
    app.add_handler(CommandHandler("warn", warns_mod.cmd_warn))
    app.add_handler(CommandHandler("warns", warns_mod.cmd_warns))
    app.add_handler(CommandHandler("rmwarn", warns_mod.cmd_rmwarn))
    app.add_handler(CommandHandler("resetwarns", warns_mod.cmd_resetwarns))
    app.add_handler(CommandHandler("warnlimit", warns_mod.cmd_warnlimit))
    app.add_handler(CommandHandler("warnaction", warns_mod.cmd_warnaction))

    # Callback de verificación
    app.add_handler(CallbackQueryHandler(verification.on_callback, pattern=r"^verify:"))
    # Callback del chat picker (comandos por DM)
    chat_picker.register("stats", admin._stats_picker_handler)
    chat_picker.register("welcome", chat_settings_cmd._welcome_picker_handler)
    chat_picker.register("rules", chat_settings_cmd._rules_picker_handler)
    chat_picker.register("welcomebuttons", chat_settings_cmd._welcomebuttons_picker_handler)
    chat_picker.register("testwelcome", chat_settings_cmd._testwelcome_picker_handler)
    chat_picker.register("top", admin._top_picker_handler)
    app.add_handler(CallbackQueryHandler(chat_picker.on_pick_callback, pattern=r"^pick:"))
    app.add_handler(CallbackQueryHandler(admin.on_topweekly_callback, pattern=r"^twk:"))
    # Callback de review de spam (botones ✅ Legítimo / ❌ Spam en DM admin)
    from .handlers import on_pending_review_callback
    app.add_handler(CallbackQueryHandler(on_pending_review_callback, pattern=r"^prev:"))
    # Callback de antiflood (botones ✅ No es bot / ❌ Es bot en DM admin)
    from .handlers import on_flood_callback
    app.add_handler(CallbackQueryHandler(on_flood_callback, pattern=r"^flood:"))

    # Tracking de membership del bot.
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    # Tracking de joins de otros usuarios.
    app.add_handler(ChatMemberHandler(on_chat_member, ChatMemberHandler.CHAT_MEMBER))

    # Mensajes de servicio (X se unió, X salió, etc.) — cleanservice
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP)
        & filters.StatusUpdate.ALL,
        on_service_message,
    ))
    # Mensajes en grupos (excluye comandos, ya capturados arriba).
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP)
        & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
        on_message,
    ))
    # Mensajes EDITADOS — anti edit-attack
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP)
        & ~filters.COMMAND & ~filters.StatusUpdate.ALL
        & filters.UpdateType.EDITED_MESSAGE,
        on_edited_message,
    ))
    # Mensajes privados no-comando: admin recibe hint, otros se ignoran silenciosamente.
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        admin.on_private_message,
    ))

    # Reacciones.
    app.add_handler(MessageReactionHandler(on_message_reaction))

    # Error handler global: captura excepciones no atrapadas en cualquier handler
    # o job (red transitoria → log breve; error real → traceback + aviso al admin).
    app.add_error_handler(_on_error)

    # Lanza el polling pidiendo TODOS los update types relevantes.
    allowed = [
        "message", "edited_message",
        "callback_query", "chat_member", "my_chat_member",
        "message_reaction", "message_reaction_count",
    ]
    log.info("Polling con allowed_updates=%s", allowed)
    app.run_polling(allowed_updates=allowed, drop_pending_updates=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
