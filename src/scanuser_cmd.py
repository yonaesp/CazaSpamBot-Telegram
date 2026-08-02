"""/scanuser — radiografía de UN usuario. Solo informa, nunca actúa.

Es el hermano de `/scan`: aquel mira un MENSAJE, este mira a la PERSONA. Sirve
para el caso que no cubría nada: «este de aquí me da mala espina, ¿qué sabes de
él?», sin tener que banear para averiguarlo.

Reúne en un sitio lo que hoy está repartido: lo que el bot ha visto de él en el
grupo (mensajes, cuándo entró, su trust), lo que dice su perfil vía Telethon
(fotos, antigüedad de la cuenta, bio, canal personal) y lo que opinan las listas
externas (CAS, lols.bot). Y termina con lo único que de verdad se pregunta el
admin: **qué haría el bot con él si entrara hoy**.

Tres decisiones de diseño:

- **No actúa jamás.** Ni banea, ni marca, ni escribe en `moderation_log`. Consultar
  a alguien no es moderarlo, y si consultar tuviera efectos secundarios nadie lo
  usaría por miedo.
- **Degrada bien sin Telethon.** Sin cuenta secundaria no hay fotos, ni bio, ni
  edad de cuenta; se dice claramente en vez de fingir que el perfil está limpio,
  que es el mismo error que cometía `/scan` con las historias.
- **Sin enlaces al perfil** (regla 6): nombre + id, para no dar visibilidad a un
  spammer desde el propio informe.
"""
from __future__ import annotations

import html as _h
import time

from telegram import Update
from telegram.ext import ContextTypes

from . import user_signals, verification
from . import trust as _trust
from .config import Config
from .db import DB
from .detectors import cas as cas_det
from .detectors import lols_bot as lols_det
from .i18n import t


def _edad(ts: float | None) -> str:
    """Segundos epoch → «hace 3 días» en lenguaje llano."""
    if not ts:
        return t("scanuser.unknown")
    dias = (time.time() - ts) / 86400
    if dias < 1:
        return t("scanuser.age_hours", n=max(1, int(dias * 24)))
    if dias < 30:
        return t("scanuser.age_days", n=int(dias))
    if dias < 365:
        return t("scanuser.age_months", n=int(dias / 30))
    return t("scanuser.age_years", n=round(dias / 365, 1))


async def _listas_externas(context, cfg: Config, user_id: int) -> list[str]:
    """CAS y lols.bot. Best-effort: si no hay red, se dice, no se inventa."""
    session = context.bot_data.get("http")
    if session is None:
        return [t("scanuser.lists_unavailable")]
    lineas = []
    if cfg.cas_enabled:
        try:
            hit = await cas_det.check(user_id, session,
                                      context.bot_data["db"], cfg.cas_cache_ttl_seconds)
            lineas.append(t("scanuser.cas_hit") if hit else t("scanuser.cas_clean"))
        except Exception:  # noqa: BLE001
            lineas.append(t("scanuser.cas_error"))
    if cfg.lols_enabled:
        try:
            hit = await lols_det.check(user_id, session)
            lineas.append(t("scanuser.lols_hit") if hit else t("scanuser.lols_clean"))
        except Exception:  # noqa: BLE001
            lineas.append(t("scanuser.lols_error"))
    return lineas


async def cmd_scanuser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    msg = update.effective_message
    chat_id = msg.chat_id if msg else 0

    # Se reutiliza la resolución de /ban: acepta reply, @usuario, id numérico y
    # menciones de usuarios sin username. Duplicarla aquí sería la cuarta copia.
    from .admin import _resolve_target_user
    user_id, _resto, err = await _resolve_target_user(update, context, db)
    if user_id is None:
        await msg.reply_text(t("scanuser.usage") + (f"\n⚠️ {err}" if err else ""),
                             parse_mode="HTML")
        return

    objetivo = None
    try:
        miembro = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        objetivo = miembro.user
    except Exception:  # noqa: BLE001
        pass

    nombre = _h.escape((getattr(objetivo, "first_name", None) or str(user_id))[:40])
    seen = db.get_seen(chat_id, user_id)
    lineas = [t("scanuser.header", name=nombre, uid=user_id), ""]

    # --- Lo que el bot ha visto de él AQUÍ ---
    if seen is None:
        lineas.append(t("scanuser.never_seen"))
    else:
        lineas.append(t(
            "scanuser.seen",
            msgs=seen["msg_count"] or 0,
            joined=(_edad(seen["join_ts"]) if seen["join_ts"]
                    else t("scanuser.join_unknown")),
            first_seen=_edad(seen["first_seen_ts"]),
        ))
    trust = db.user_trust_score(chat_id, user_id)
    lineas.append(t("scanuser.trust", trust=_trust.render_trust(trust), n=trust))
    if db.is_whitelisted(chat_id, user_id):
        lineas.append(t("scanuser.whitelisted"))
    if db.is_banned(user_id):
        lineas.append(t("scanuser.banned"))

    # --- Perfil (Telethon) ---
    lineas.append("")
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    sig = None
    if client is not None:
        try:
            sig = await user_signals.fetch(
                client, user_id, chat_id=chat_id,
                first_name=getattr(objetivo, "first_name", None))
        except Exception:  # noqa: BLE001
            sig = None
    if sig is None:
        # Se dice, no se finge. Sin Telethon el perfil es un punto ciego, igual que
        # el contenido de una historia, y dar por limpio lo que no se ha mirado es
        # peor que no mirarlo.
        lineas.append(t("scanuser.no_profile"))
    else:
        lineas.append(t("scanuser.profile_header"))
        rendered = user_signals.render_markup(sig)
        if rendered:
            lineas.append(rendered)

    # --- Listas externas ---
    externas = await _listas_externas(context, cfg, user_id)
    if externas:
        lineas.append("")
        lineas.append(t("scanuser.lists_header"))
        lineas.extend(f"  {x}" for x in externas)

    # --- Qué haría el bot si entrara hoy ---
    lineas.append("")
    sospechoso, motivos = verification._is_suspicious_profile(
        sig, getattr(objetivo, "username", None),
        getattr(objetivo, "first_name", None), getattr(objetivo, "last_name", None),
    )
    if sig is None:
        lineas.append(t("scanuser.verdict_unknown"))
    elif sospechoso:
        detalle = ", ".join(verification.render_reason_list(motivos)[:3])
        lineas.append(t("scanuser.verdict_suspicious", details=_h.escape(detalle)))
    else:
        lineas.append(t("scanuser.verdict_clean"))
    lineas.append(t("scanuser.footer"))

    await msg.reply_text("\n".join(lineas), parse_mode="HTML",
                         disable_web_page_preview=True)
