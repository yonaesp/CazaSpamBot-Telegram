"""/scanuser — radiografía de UN usuario. Solo informa, nunca actúa.

Es el hermano de `/scan`: aquel mira un MENSAJE, este mira a la PERSONA. Sirve
para el caso que no cubría nada: «este de aquí me da mala espina, ¿qué sabes de
él?», sin tener que banear para averiguarlo.

Reúne en un sitio lo que estaba repartido: cuándo se creó la cuenta, cuándo entró
al grupo, sus fotos de perfil, cuánto escribe (en total y en el último mes), lo
que dicen las listas externas y, lo que de verdad se pregunta el admin, **qué
haría el bot con él si entrara hoy**.

Cuatro decisiones de diseño:

- **No actúa jamás.** Ni banea, ni marca, ni escribe en `moderation_log`. Consultar
  a alguien no es moderarlo, y si consultar tuviera efectos secundarios nadie lo
  usaría por miedo.
- **Responde por privado y borra el comando** cuando se usa en un grupo. Es un
  informe para el admin, no algo que deba ver el grupo, y menos con el nombre de
  alguien a quien se está mirando con lupa.
- **Degrada bien sin Telethon.** Sin cuenta secundaria no hay fotos, ni bio, ni
  canal personal; se dice claramente en vez de fingir que el perfil está limpio,
  que es el mismo error que cometía `/scan` con las historias.
- **Sin enlaces al perfil** (regla 6): nombre + id, para no dar visibilidad a un
  spammer desde el propio informe.
"""
from __future__ import annotations

from . import fechas
import datetime as _dt
import html as _h
import time

from telegram import Update
from telegram.ext import ContextTypes

from . import account_age, user_signals, verification
from . import trust as _trust
from .config import Config
from .db import DB
from .detectors import cas as cas_det
from .detectors import lols_bot as lols_det
from .i18n import t

# Cuánto espera el bot el objetivo tras un `/scanuser` a secas. Mismo criterio que
# `/scan`: corto, para que un despiste no acabe escaneando al siguiente que escriba.
ESPERA_TTL_S = 300


def _fecha(ts: float | None) -> str:
    return fechas.dia(ts)


def _fecha_dt(d) -> str:
    return fechas.dia(d)


def _humano(dias) -> str:
    """Días → «3 años y 2 meses», que es como lo lee una persona."""
    dias = int(dias)
    if dias < 1:
        return t("scanuser.today")
    if dias < 31:
        return t("scanuser.day_one") if dias == 1 else t("scanuser.n_days", n=dias)
    if dias < 365:
        n = max(1, dias // 30)
        return t("scanuser.month_one") if n == 1 else t("scanuser.n_months", n=n)
    anios, resto = divmod(dias, 365)
    meses = resto // 30
    # Singular y plural bien: «1 año y 4 meses», no «1 años y 4 meses».
    a = t("scanuser.year_one") if anios == 1 else t("scanuser.n_years", n=anios)
    if not meses:
        return a
    m = t("scanuser.month_one") if meses == 1 else t("scanuser.n_months", n=meses)
    return t("scanuser.join_two", a=a, b=m)


def _explicar_trust(n: int) -> str:
    """El número no le dice nada a nadie: lo que importa es qué implica."""
    if n >= 70:
        return t("scanuser.trust_high")
    if n >= 40:
        return t("scanuser.trust_mid")
    return t("scanuser.trust_low")


async def _listas_externas(context, cfg: Config, user_id: int) -> list[str]:
    """CAS y lols.bot. Best-effort: si no hay red, se dice, no se inventa."""
    session = context.bot_data.get("http")
    if session is None:
        return [t("scanuser.lists_unavailable")]
    lineas = []
    if cfg.cas_enabled:
        try:
            hit = await cas_det.check(user_id, session, context.bot_data["db"],
                                      cfg.cas_cache_ttl_seconds)
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


async def _componer(context, cfg: Config, db: DB, chat_id: int, user_id: int) -> str:
    """El informe entero, ya formateado. Separado del comando para poder llamarlo
    también desde la captura pendiente sin duplicar nada."""
    objetivo = None
    try:
        miembro = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        objetivo = miembro.user
    except Exception:  # noqa: BLE001
        pass

    nombre = _h.escape((getattr(objetivo, "first_name", None) or str(user_id))[:40])
    uname = getattr(objetivo, "username", None)
    seen = db.get_seen(chat_id, user_id)
    trust = db.user_trust_score(chat_id, user_id)

    L = [t("scanuser.header", name=nombre, uid=user_id)]
    if uname:
        L.append(t("scanuser.username", u=_h.escape(uname)))

    # --- La cuenta ---
    L += ["", t("scanuser.sec_account")]
    est = account_age.estimar(user_id)
    if est is None:
        L.append(t("scanuser.created_unknown"))
    else:
        fecha, precision = est
        dias = (_dt.date.today() - fecha).days
        L.append(t("scanuser.created", date=fechas.dia(fecha),
                   age=_humano(dias),
                   note=(t("scanuser.created_rough") if precision == "baja" else "")))

    # --- En este grupo ---
    L += ["", t("scanuser.sec_group")]
    if seen is None:
        L.append(t("scanuser.never_seen"))
    else:
        if seen["join_ts"]:
            L.append(t("scanuser.joined", date=_fecha(seen["join_ts"]),
                       age=_humano((time.time() - seen["join_ts"]) / 86400)))
        else:
            L.append(t("scanuser.joined_unknown", date=_fecha(seen["first_seen_ts"])))
        total = seen["msg_count"] or 0
        recientes = db.mensajes_ultimos_dias(chat_id, user_id, 30)
        L.append(t("scanuser.messages", total=total, last30=recientes))
        if total and not recientes:
            L.append(t("scanuser.messages_quiet"))
    if db.is_whitelisted(chat_id, user_id):
        L.append(t("scanuser.whitelisted"))
    if db.is_banned(user_id):
        L.append(t("scanuser.banned"))

    # --- Perfil (Telethon) ---
    L += ["", t("scanuser.sec_profile")]
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
        # Se dice, no se finge. Dar por limpio lo que no se ha mirado es peor que
        # no mirarlo: es el error que cometía /scan con las historias.
        L.append(t("scanuser.no_profile"))
    else:
        if sig.photo_count == 0:
            L.append(t("scanuser.no_photos"))
        elif sig.photo_count == 1 or not sig.oldest_photo or not sig.newest_photo:
            L.append(t("scanuser.one_photo",
                       date=_fecha_dt(sig.newest_photo or sig.oldest_photo)))
        else:
            L.append(t("scanuser.photos", n=sig.photo_count,
                       first=_fecha_dt(sig.oldest_photo),
                       last=_fecha_dt(sig.newest_photo)))
        L.append(t("scanuser.bio_yes", bio=_h.escape((sig.bio or "")[:120]))
                 if sig.bio else t("scanuser.bio_no"))
        if sig.personal_channel_title:
            L.append(t("scanuser.channel",
                       title=_h.escape(sig.personal_channel_title[:60])))
        if sig.is_premium:
            L.append(t("scanuser.premium"))

    # --- Lo primero que dijo ---
    # El último mensaje se pisa con cada uno nuevo; el primero explica POR QUÉ entró
    # y es lo que hace falta para entender a posteriori por qué el bot no lo vio.
    if seen is not None and seen["first_msg_text"]:
        L += ["", t("scanuser.first_msg",
                    text=_h.escape(str(seen["first_msg_text"])[:200]))]

    # --- Listas externas ---
    externas = await _listas_externas(context, cfg, user_id)
    if externas:
        L += ["", t("scanuser.sec_lists")]
        L += [f"  {x}" for x in externas]

    # --- Confianza, en lenguaje llano ---
    L += ["", t("scanuser.sec_trust"),
          t("scanuser.trust", trust=_trust.render_trust(trust), n=trust),
          "  " + _explicar_trust(trust)]

    # --- Qué haría el bot si entrara hoy ---
    L.append("")
    sospechoso, motivos = verification._is_suspicious_profile(
        sig, uname, getattr(objetivo, "first_name", None),
        getattr(objetivo, "last_name", None),
    )
    if sig is None:
        L.append(t("scanuser.verdict_unknown"))
    elif sospechoso:
        detalle = ", ".join(verification.render_reason_list(motivos)[:3])
        L.append(t("scanuser.verdict_suspicious", details=_h.escape(detalle)))
    else:
        L.append(t("scanuser.verdict_clean"))
    L.append(t("scanuser.footer"))
    return "\n".join(L)


async def _entregar(context, update, texto: str, cfg: Config) -> None:
    """Manda el informe. En grupo: borra el comando y contesta al PRIVADO.

    Un informe con el nombre de alguien a quien se está mirando con lupa no pinta
    nada en el grupo, y así el admin no tiene que borrarlo a mano después.
    """
    from telegram.error import TelegramError
    msg = update.effective_message
    en_grupo = bool(msg and msg.chat and msg.chat.type in ("group", "supergroup"))
    if not en_grupo:
        await msg.reply_text(texto, parse_mode="HTML", disable_web_page_preview=True)
        return

    try:
        await msg.delete()
    except TelegramError:
        pass
    destino = cfg.admin_notify_chat_id or cfg.admin_user_id
    try:
        await context.bot.send_message(chat_id=destino, text=texto, parse_mode="HTML",
                                       disable_web_page_preview=True)
    except TelegramError:
        # Si el privado no está disponible (nunca escribió al bot), mejor en el
        # grupo que perderlo: un informe que no llega no sirve de nada.
        await context.bot.send_message(chat_id=msg.chat_id, text=texto,
                                       parse_mode="HTML", disable_web_page_preview=True)


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
        # Sin objetivo: el bot se queda esperando, igual que /scan. El orden natural
        # es escribir el comando y DESPUÉS pasarle el usuario o su mensaje.
        en_grupo = bool(msg.chat and msg.chat.type in ("group", "supergroup"))
        if en_grupo:
            from telegram.error import TelegramError
            try:
                await msg.delete()
            except TelegramError:
                pass
        context.user_data["scanuser_await"] = {"t": time.time(), "chat": chat_id}
        destino = (cfg.admin_notify_chat_id or cfg.admin_user_id) if en_grupo else chat_id
        await context.bot.send_message(chat_id=destino, text=t("scanuser.await"),
                                       parse_mode="HTML")
        return

    await _entregar(context, update, await _componer(context, cfg, db, chat_id, user_id), cfg)


async def handle_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Si un `/scanuser` está esperando objetivo, lo resuelve de este mensaje.

    Acepta el reenvío de un mensaje suyo o su @usuario escrito a pelo. Mismo
    contrato que las otras capturas: quien llama ya comprobó que es el admin en su
    DM, y si devolvemos True debe hacer return.
    """
    pedido = context.user_data.get("scanuser_await")
    if not pedido:
        return False
    context.user_data.pop("scanuser_await", None)   # de un solo uso
    if time.time() - pedido["t"] > ESPERA_TTL_S:
        return False
    msg = update.effective_message
    if msg is None:
        return False

    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    chat_id = pedido.get("chat") or msg.chat_id

    # 1) Reenvío: el autor original. 2) Texto: @usuario o id pelado.
    user_id = None
    origen = getattr(msg, "forward_origin", None)
    if origen is not None and getattr(origen, "sender_user", None) is not None:
        user_id = origen.sender_user.id
    elif getattr(msg, "forward_from", None) is not None:
        user_id = msg.forward_from.id
    else:
        crudo = (msg.text or "").strip()
        if crudo.lstrip("-").isdigit():
            user_id = int(crudo)
        elif crudo.startswith("@"):
            user_id = db.resolve_username(crudo[1:])
            if user_id is None:
                try:
                    chat_obj = await context.bot.get_chat(crudo)
                    user_id = chat_obj.id
                except Exception:  # noqa: BLE001
                    user_id = None

    if user_id is None:
        await msg.reply_text(t("scanuser.capture_failed"), parse_mode="HTML")
        return True

    texto = await _componer(context, cfg, db, chat_id, user_id)
    await msg.reply_text(texto, parse_mode="HTML", disable_web_page_preview=True)
    return True
