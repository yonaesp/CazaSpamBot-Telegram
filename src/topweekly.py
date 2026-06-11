"""Top semanal de actividad por chat.

- Cada domingo 20:00 (Europe/Madrid) el bot publica un mensaje en cada chat
  donde `topweekly_enabled = 1` con los top 5 usuarios más activos de los
  últimos 7 días.
- Identificación SIN link clicable: usa first_name + nada de @username.
- Recolección filtra: msgs ≥10 chars, no saludos, cooldown 60s (en
  handlers.on_message + db.record_topweekly_msg).
"""
from __future__ import annotations

import datetime as _dt
import html
import logging
import time
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from .db import DB

log = logging.getLogger(__name__)

TZ_MADRID = ZoneInfo("Europe/Madrid")

WEEK_SECONDS = 7 * 86400

# Thresholds:
# - TOP_MIN_LEADER: si el TOP 1 no llegó a 5 msgs, el grupo está muerto, no publicar.
# - MIN_PER_USER: para aparecer en la lista hace falta >=2 msgs.
# - MIN_LIST_SIZE: si tras filtrar quedan <3 usuarios, mejor no publicar
#   (un "top de 1 persona" queda raro).
TOP_MIN_LEADER = 5
MIN_PER_USER = 2
MIN_LIST_SIZE = 3


def _format_user(row) -> str:
    """Mención clicable al user (reconocimiento positivo, distinto a un quip
    de ban). Usa tg://user?id=N que abre perfil + notifica. Si no hay
    first_name, fallback a 'user N' sin link.
    """
    name = (row["first_name"] or "").strip()[:30]
    if not name:
        return f"user {row['user_id']}"
    safe = html.escape(name)
    return f'<a href="tg://user?id={row["user_id"]}">{safe}</a>'


def _format_period() -> str:
    end = _dt.datetime.now(TZ_MADRID)
    start = end - _dt.timedelta(days=7)
    return f"{start.strftime('%d/%m')} - {end.strftime('%d/%m')}"


async def weekly_top_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Publica el top semanal en cada chat con topweekly_enabled=1.

    Corre cada domingo a las 20:00 Europe/Madrid.
    """
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if cfg.shadow:
        log.info("topweekly skip: shadow mode")
        return
    db: DB = context.bot_data["db"]
    since_ts = time.time() - WEEK_SECONDS

    for chat_row in db.all_chats():
        if not chat_row["am_admin"]:
            continue
        settings = db.get_chat_settings(chat_row["chat_id"])
        if not settings or not settings["topweekly_enabled"]:
            continue
        rows = db.top_weekly(chat_row["chat_id"], since_ts, limit=10)
        # Threshold absoluto: si el líder no llegó a TOP_MIN_LEADER msgs, no publicar
        if not rows or rows[0]["cnt"] < TOP_MIN_LEADER:
            log.info(
                "topweekly chat=%s sin actividad suficiente (líder %d < %d msgs)",
                chat_row["chat_id"],
                rows[0]["cnt"] if rows else 0,
                TOP_MIN_LEADER,
            )
            continue
        # Filtro individual: solo users con >= MIN_PER_USER msgs
        rows = [r for r in rows if r["cnt"] >= MIN_PER_USER][:5]
        if len(rows) < MIN_LIST_SIZE:
            log.info(
                "topweekly chat=%s solo %d users con >=%d msgs (mínimo %d), no publica",
                chat_row["chat_id"], len(rows), MIN_PER_USER, MIN_LIST_SIZE,
            )
            continue

        # Construir mensaje
        period = _format_period()
        lines = [f"🏆 <b>Top semanal de actividad</b> ({period})", ""]
        medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
        for i, r in enumerate(rows):
            medal = medals[i] if i < len(medals) else "•"
            lines.append(f"{medal} {_format_user(r)} — <b>{r['cnt']}</b> mensajes")
        lines.append("")
        lines.append("¡Gracias por mantener el grupo vivo! 👏")
        lines.append("<i>Cuentan mensajes con contenido (texto ≥10 chars o media) sin saludos repetidos, cooldown 10s. Calidad &gt; cantidad.</i>")
        text = "\n".join(lines)

        try:
            await context.bot.send_message(
                chat_id=chat_row["chat_id"],
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            log.info("topweekly publicado chat=%s con %d users", chat_row["chat_id"], len(rows))
        except Exception as exc:
            log.warning("topweekly publish fallo chat=%s: %s", chat_row["chat_id"], exc)


async def render_top(db: DB, chat_id: int) -> str:
    """Genera el texto del top de los últimos 7 días para un chat (uso manual /top).

    Para /top manual NO aplicamos el threshold TOP_MIN_LEADER (queremos verlo
    siempre que se pida), pero sí filtramos por MIN_PER_USER para mantener
    consistencia con el publicado automáticamente.
    """
    since_ts = time.time() - WEEK_SECONDS
    rows = db.top_weekly(chat_id, since_ts, limit=10)
    # /top manual sí muestra aunque haya pocos: el admin lo pide explícitamente
    rows = [r for r in rows if r["cnt"] >= MIN_PER_USER][:5]
    if not rows:
        return (
            "📊 <b>Top semanal</b>\n\n"
            f"Sin actividad suficiente esta semana (mínimo {MIN_PER_USER} mensajes por usuario)."
        )
    period = _format_period()
    lines = [f"🏆 <b>Top semanal de actividad</b> ({period})", ""]
    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
    for i, r in enumerate(rows):
        medal = medals[i] if i < len(medals) else "•"
        lines.append(f"{medal} {_format_user(r)} — <b>{r['cnt']}</b> mensajes")
    return "\n".join(lines)
