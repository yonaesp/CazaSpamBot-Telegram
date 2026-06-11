"""Sistema de verificación al entrar al grupo.

Comportamiento:
1. Cuando alguien se une → mute total (can_send_messages=False)
2. Bot envía welcome con botón inline "✅ Soy humano"
3. Click → unmute + mark verified
4. Job de limpieza periódico:
   - Si is_suspicious y >12h sin verificar → kick (sin ban)
   - Si NO suspicious → queda muteado eternamente (cero fricción para humanos que vuelvan)

Criterio de "suspicious" (vía Telethon `user_signals`):
  - Sin foto de perfil O foto más reciente <90 días O sin first_name O nombre random
"""
from __future__ import annotations

import datetime as _dt
import html
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import user_signals
from .db import DB
from .detectors.unicode_script import non_allowed_ratio

log = logging.getLogger(__name__)

CALLBACK_PREFIX = "verify"

# Permisos para usuario muteado (NO puede mandar nada)
MUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False, can_send_documents=False, can_send_photos=False,
    can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False,
    can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False, can_invite_users=False, can_pin_messages=False,
    can_manage_topics=False,
)

# Permisos al verificar (todo normal)
VERIFIED_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True, can_send_documents=True, can_send_photos=True,
    can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True,
    can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True,
)

DEFAULT_WELCOME = (
    "👋 Hola {name}, bienvenido/a a <b>{chat}</b>.\n\n"
    "Para evitar spam, los nuevos miembros entran muteados. "
    "<b>Pulsa el botón de abajo para verificar que eres humano</b> y poder escribir.\n\n"
    "<i>Si eres un bot o no pulsas, no podrás participar.</i>"
)


def _name_in_non_latin_script(name: Optional[str]) -> bool:
    """True si el nombre/username contiene >30% de chars en script no latino."""
    if not name:
        return False
    ratio, _ = non_allowed_ratio(name, ["latin"])
    return ratio > 0.3


try:
    from confusable_homoglyphs import confusables as _confusables  # type: ignore
    _HAVE_CONFUSABLES = True
except ImportError:
    _confusables = None  # type: ignore
    _HAVE_CONFUSABLES = False


_SCRIPT_KEYWORDS = (
    "LATIN", "CYRILLIC", "ARABIC", "HEBREW", "GREEK", "THAI",
    "CHEROKEE", "DEVANAGARI", "CJK", "HIRAGANA", "KATAKANA",
    "HANGUL", "GEORGIAN", "ARMENIAN", "BENGALI", "TAMIL",
)


def _unique_scripts(s: str) -> set[str]:
    """Devuelve los scripts unicode presentes en el string. Fallback si no
    está `confusable_homoglyphs` disponible."""
    import unicodedata
    result: set[str] = set()
    for c in s:
        cp = ord(c)
        if cp < 0x80:
            if c.isalpha():
                result.add("LATIN")
            continue
        try:
            name = unicodedata.name(c, "")
        except ValueError:
            continue
        for kw in _SCRIPT_KEYWORDS:
            if kw in name:
                result.add(kw)
                break
    return result


def _is_decorative_mix(s: str) -> bool:
    """True si el nombre es DECORATIVO/HOMOGRÁFICO (no es un nombre real en
    ningún idioma). Casos: MARCOSPG24 estilizado con Thai+Cyrillic+Hebrew+Greek,
    VAPERSEXTREM con Cherokee+Cyrillic+Greek, etc.

    Usa `confusable_homoglyphs.is_dangerous` (UTS#39) — más preciso que contar
    scripts a mano. Si la librería no está disponible, fallback a heurística
    'mezcla de 3+ scripts'.

    IMPORTANTE: aplicamos sobre el string ORIGINAL (antes de NFKC) porque
    NFKC y confusables.txt discrepan en 31 chars (ej. ſ→f vs ſ→s).
    """
    if not s:
        return False
    if _HAVE_CONFUSABLES:
        try:
            # is_dangerous=True cuando el texto contiene caracteres confundibles
            # con OTRO alias preferido (p.ej. Latin) → es decorativo/homógrafo.
            danger = _confusables.is_dangerous(s, preferred_aliases=["latin"])
            return bool(danger)
        except Exception:  # noqa: BLE001
            pass
    # Fallback: heurística 3+ scripts
    import unicodedata
    norm = unicodedata.normalize("NFKC", s)
    return len(_unique_scripts(norm)) >= 3


def _is_obvious_spam_profile(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """Perfil EVIDENTEMENTE de spammer al hacer JOIN — ban directo sin verificación.

    Criterios (más conservadores tras incidente Cherokee 2026-05-29):
      - 2+ campos (first_name, last_name, username) con >30% chars no-latín
      - 1+ campo no-latín + cuenta sin foto + <30 días (si Telethon disponible)

    Lo que YA NO dispara ban directo (era FP):
      - 1 solo campo con ≥70% chars no-latín (mucha gente real con nombre
        en árabe/hebreo/cirílico es legítima si tiene username latino).
      - Nombres decorativos que mezclan 3+ scripts (Cherokee/Mathematical/Thai
        estilizado para emular letras latinas). Estos se ignoran.

    Para esos casos, on_chat_member ya aplica verification con botón.
    """
    import unicodedata
    reasons: list[str] = []
    non_latin_count = 0
    high_ratio_single = False
    for value, label in [(first_name, "first_name"), (last_name, "last_name"), (username, "username")]:
        if not value:
            continue
        # 1) NFKC: normaliza Mathematical Alphanumeric, Fullwidth Latin → Latin estándar
        norm = unicodedata.normalize("NFKC", value)
        # 2) Si es mezcla decorativa (≥3 scripts), NO contar como non-latin
        if _is_decorative_mix(norm):
            reasons.append(f"{label} decorativo (mezcla scripts, ignorado)")
            continue
        ratio, dominant = non_allowed_ratio(norm, ["latin"])
        if ratio > 0.3:
            non_latin_count += 1
            reasons.append(f"{label} {ratio:.0%} non-latin ({dominant})")
            if ratio >= 0.7:
                high_ratio_single = True
    # BYPASS de seguridad: si Telethon dice cuenta ≥365d + con foto,
    # NUNCA ban directo por nombre. Es un user bilingüe probable.
    if sig is not None and sig.photo_count >= 1 and (sig.account_age_days or 0) >= 365:
        return False, reasons + ["bypass: cuenta antigua + foto"]
    # 2+ campos non-latín → señal fuerte, ban directo
    if non_latin_count >= 2:
        return True, reasons
    # 1 campo high_ratio (e.g. árabe puro) + cuenta nueva + sin foto → ban
    # Sin las señales Telethon, NO ban (era el caso de FP con users bilingües)
    if (non_latin_count >= 1 or high_ratio_single) and sig is not None:
        if sig.photo_count == 0 and sig.account_age_days is not None and sig.account_age_days < 30:
            reasons.append(f"sin foto + {sig.account_age_days}d cuenta")
            return True, reasons
    return False, reasons


def _is_very_legit_profile(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """Perfil claramente legítimo: skip verification, welcome amistoso.

    Requiere TODAS estas condiciones:
      - ≥2 fotos de perfil (foto_count)
      - Cuenta ≥365 días
      - Nombre y username en script latino (sin caracteres no-latín relevantes)
      - Sin marcas Telegram scam/fake/restricted (no se expone aquí, se chequea aparte)
    """
    if sig is None:
        return False, []
    reasons: list[str] = []
    if sig.photo_count < 2:
        return False, []
    reasons.append(f"{sig.photo_count} fotos")
    if sig.account_age_days is None or sig.account_age_days < 365:
        return False, []
    reasons.append(f"{sig.account_age_days}d antigüedad")
    if _name_in_non_latin_script(first_name) or _name_in_non_latin_script(last_name):
        return False, []
    if _name_in_non_latin_script(username):
        return False, []
    reasons.append("nombre/username latino")
    return True, reasons


def _is_suspicious_profile(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """Cuenta sospechosa = pinta de cuenta recién creada o desechable.

    Devuelve (es_sospechoso, razones).
    """
    reasons: list[str] = []
    if not username:
        reasons.append("sin username")
    if not first_name:
        reasons.append("sin first_name")
    # Nombre o username en script no-latino (cirílico, chino, árabe, etc.)
    if _name_in_non_latin_script(first_name) or _name_in_non_latin_script(last_name):
        reasons.append("nombre en script no-latino")
    if _name_in_non_latin_script(username):
        reasons.append("username en script no-latino")
    if sig is not None:
        if sig.photo_count == 0:
            reasons.append("sin foto")
        else:
            age = sig.account_age_days
            if age is not None and age < 90:
                reasons.append(f"foto reciente ({age}d)")
    return (bool(reasons), reasons)


FRIENDLY_WELCOME_DELETE_AFTER_S = 900  # 15 min (igual que el welcome normal)


# Welcomes graciosos para perfiles legítimos. Se cargan de archivos editables
# en config/welcomes/ (una frase por línea, # para comentarios, {name} para el
# nombre). Orden de búsqueda por chat:
#   1. config/welcomes/<chat_id>.txt  → frases temáticas de ESE grupo
#   2. config/welcomes/generic.txt    → genérico editable (versionado)
#   3. _DEFAULT_WELCOMES              → fallback en código (2 frases)
# Los archivos por chat_id están en .gitignore (cada quien pone los suyos sin
# subirlos); el repo solo trae generic.txt como ejemplo. También se pueden
# desactivar del todo con FRIENDLY_WELCOMES_ENABLED=false.
_WELCOMES_DIR = Path(__file__).resolve().parent.parent / "config" / "welcomes"

_DEFAULT_WELCOMES = [
    "👋 Bienvenido/a {name}. Echa un vistazo al grupo.",
    "🤝 ¡Hola {name}! Bienvenido/a.",
]

_WELCOME_FIXED_FOOTER = "Las normas y el mensaje anclado lo tienen todo."


def _read_phrase_file(path: Path) -> list[str]:
    """Lee un archivo de frases: una por línea, ignora vacías y comentarios (#)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _load_welcome_pack(chat_id: int) -> list[str]:
    """Frases de bienvenida para un chat (archivo del grupo → genérico → fallback)."""
    pack = _read_phrase_file(_WELCOMES_DIR / f"{chat_id}.txt")
    if not pack:
        pack = _read_phrase_file(_WELCOMES_DIR / "generic.txt")
    return pack or _DEFAULT_WELCOMES


def friendly_welcomes_enabled() -> bool:
    """Toggle de los saludos simpáticos (FRIENDLY_WELCOMES_ENABLED, default true)."""
    return os.getenv("FRIENDLY_WELCOMES_ENABLED", "true").strip().lower() not in ("false", "0", "no")


async def _send_friendly_welcome(context, db, chat, user, settings) -> None:
    """Welcome amistoso para cuentas legítimas: sin mute, sin botón verify.
    Incluye solo los botones URL configurados del chat (anclado, normas, etc.).
    Auto-borrado a los 15 min para no ensuciar el chat.
    """
    if user.username:
        name = f"@{user.username}"
    else:
        display = html.escape(user.first_name or str(user.id))
        name = f'<a href="tg://user?id={user.id}">{display}</a>'
    catalog = _load_welcome_pack(chat.id)
    greeting = random.choice(catalog).format(name=name)
    text = f"{greeting}\n\n<i>{_WELCOME_FIXED_FOOTER}</i>"
    rows: list[list[InlineKeyboardButton]] = []
    db.migrate_legacy_welcome_button(chat.id)
    buttons = db.list_welcome_buttons(chat.id)
    if buttons:
        current_row: list[InlineKeyboardButton] = []
        for b in buttons:
            btn = InlineKeyboardButton(b["text"], url=b["url"])
            if b["same_row"] and current_row:
                current_row.append(btn)
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [btn]
        if current_row:
            rows.append(current_row)
    keyboard = InlineKeyboardMarkup(rows) if rows else None
    try:
        sent = await context.bot.send_message(
            chat_id=chat.id, text=text, parse_mode="HTML",
            reply_markup=keyboard, disable_notification=True,
        )
    except TelegramError as exc:
        log.warning("friendly_welcome send fallo chat=%s: %s", chat.id, exc)
        return
    # Registrar pending SOLO para poder limpiar el welcome si lo banean luego.
    # Lo marcamos verified_at AL INSTANTE: este user NO está en el flujo de
    # verificación (no tiene mute ni botón), así que los jobs de reminder/kick
    # NO deben tocarlo. Sin esto, el job de recordatorios le mandaba aviso a
    # las 3h pese a ser legítimo (bug @Alexgaliza 2026-06-05).
    if sent is not None:
        db.add_pending_verification(
            chat_id=chat.id, user_id=user.id, welcome_msg_id=sent.message_id,
            is_suspicious=False,
        )
        db.mark_verified(chat.id, user.id)
    # Auto-borrar a los 15 min para no ensuciar el chat
    jq = context.application.job_queue
    if jq is not None and sent is not None:
        jq.run_once(
            _delete_friendly_welcome_job, when=FRIENDLY_WELCOME_DELETE_AFTER_S,
            data={"chat_id": chat.id, "message_id": sent.message_id, "user_id": user.id},
            name=f"del_friendly_welcome_{chat.id}_{sent.message_id}",
        )


async def _delete_friendly_welcome_job(context) -> None:
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except TelegramError:
        pass
    # Limpia también el registro pending_verification (ya no tiene sentido)
    db = context.bot_data.get("db")
    if db is not None and "user_id" in data:
        try:
            db.delete_pending_verification(data["chat_id"], data["user_id"])
        except Exception:  # noqa: BLE001
            pass


async def on_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat,
    user,
    prefetched_sig: Optional[user_signals.UserSignals] = None,
) -> None:
    """Procesa un join detectado en on_chat_member.

    Si el caller ya hizo `user_signals.fetch` (ej. handlers.on_chat_member para
    chequear obvious_spam_profile), puede pasarlo como `prefetched_sig` para
    evitar una segunda llamada Telethon innecesaria.
    """
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]

    if cfg.shadow:
        log.info("[SHADOW] verification skip user=%s chat=%s", user.id, chat.id)
        return

    db.ensure_chat_settings(chat.id)
    settings = db.get_chat_settings(chat.id)
    if not settings or not settings["verification_enabled"]:
        return

    # Señales del perfil: reutiliza prefetched si lo hay, o pide a Telethon.
    sig = prefetched_sig
    if sig is None:
        reporter = context.bot_data.get("reporter")
        client = reporter.get_client() if reporter else None
        if client is not None:
            try:
                sig = await user_signals.fetch(client, user.id, chat_id=chat.id, first_name=user.first_name)
            except Exception as exc:
                log.debug("user_signals fetch user=%s exc: %s", user.id, exc)
    suspicious, susp_reasons = _is_suspicious_profile(sig, user.username, user.first_name, user.last_name)

    # Si el perfil es claramente legítimo, saltar verificación y publicar
    # un welcome amistoso (sin botón SOY HUMANO, sin mute) con los botones
    # configurados del chat (anclado, normas, etc.).
    very_legit, legit_reasons = _is_very_legit_profile(sig, user.username, user.first_name, user.last_name)
    if very_legit:
        log.info(
            "verification SKIP user=%s chat=%s: perfil legítimo (%s)",
            user.id, chat.id, ", ".join(legit_reasons),
        )
        # Perfil legítimo: nunca se le mutea. El saludo simpático es opcional.
        if friendly_welcomes_enabled():
            await _send_friendly_welcome(context, db, chat, user, settings)
        return

    # 1) Mute
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id, user_id=user.id,
            permissions=MUTED_PERMISSIONS,
        )
    except TelegramError as exc:
        log.warning("verification mute fallo chat=%s user=%s: %s", chat.id, user.id, exc)
        return

    # 2) Welcome con botón
    welcome_text = settings["welcome_text"] or DEFAULT_WELCOME
    # Mención preferente con @username (más natural). Fallback tg://user?id=N si no.
    if user.username:
        name = f"@{user.username}"
    else:
        display = html.escape(user.first_name or str(user.id))
        name = f'<a href="tg://user?id={user.id}">{display}</a>'
    chat_name = html.escape(chat.title or "el grupo")
    text = welcome_text.format(name=name, chat=chat_name)
    if suspicious:
        reasons_str = ", ".join(susp_reasons)
        kick_minutes = settings["verification_suspicious_kick_minutes"] or 30
        text += (
            f"\n\n⏰ <i>Cuenta sospechosa ({html.escape(reasons_str)}). "
            f"Si no verificas en <b>{kick_minutes} minutos</b> serás expulsado.</i>"
        )

    callback_data = f"{CALLBACK_PREFIX}:{chat.id}:{user.id}"
    rows = [[InlineKeyboardButton(
        "✅ SOY HUMANO (PULSA PARA ENTRAR)",
        callback_data=callback_data,
    )]]
    # Migración legacy + lectura múltiples botones URL
    db.migrate_legacy_welcome_button(chat.id)
    buttons = db.list_welcome_buttons(chat.id)
    if buttons:
        current_row: list[InlineKeyboardButton] = []
        for b in buttons:
            btn = InlineKeyboardButton(b["text"], url=b["url"])
            if b["same_row"] and current_row:
                current_row.append(btn)
            else:
                if current_row:
                    rows.append(current_row)
                current_row = [btn]
        if current_row:
            rows.append(current_row)
    keyboard = InlineKeyboardMarkup(rows)

    try:
        sent = await context.bot.send_message(
            chat_id=chat.id, text=text, parse_mode="HTML",
            reply_markup=keyboard, disable_notification=False,
        )
    except TelegramError as exc:
        log.warning("verification welcome send fallo chat=%s: %s", chat.id, exc)
        sent = None

    msg_id = sent.message_id if sent else None
    db.add_pending_verification(
        chat_id=chat.id, user_id=user.id,
        welcome_msg_id=msg_id, is_suspicious=suspicious,
    )
    log.info(
        "verification iniciada user=%s chat=%s suspicious=%s msg=%s",
        user.id, chat.id, suspicious, msg_id,
    )
    # Auto-delete del welcome tras N segundos (default 600 = 10 min)
    delete_after = settings["welcome_delete_after_s"] or 0
    if sent and delete_after > 0:
        jq = context.application.job_queue
        if jq:
            jq.run_once(
                _delete_welcome_job, when=delete_after,
                data={"chat_id": chat.id, "message_id": sent.message_id},
                name=f"del_welcome_{chat.id}_{sent.message_id}",
            )


async def _delete_welcome_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Borra el welcome tras el timeout configurado (no afecta al estado del user)."""
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except TelegramError:
        pass


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa el click en el botón "Soy humano"."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith(f"{CALLBACK_PREFIX}:"):
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Botón inválido.")
        return
    try:
        chat_id = int(parts[1])
        target_user_id = int(parts[2])
    except ValueError:
        await query.answer("Botón inválido.")
        return

    if query.from_user.id != target_user_id:
        await query.answer("Este botón no es para ti.", show_alert=True)
        return

    db: DB = context.bot_data["db"]
    row = db.get_pending(chat_id, target_user_id)
    if not row:
        await query.answer("Ya estás verificado o el botón ha expirado.")
        return

    # Unmute
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_user_id,
            permissions=VERIFIED_PERMISSIONS,
        )
    except TelegramError as exc:
        log.warning("verification unmute fallo chat=%s user=%s: %s", chat_id, target_user_id, exc)
        await query.answer("Error desmuteando, contacta admin.")
        return

    db.mark_verified(chat_id, target_user_id)
    await query.answer("✅ Verificado, ya puedes escribir.")

    # Borrar el mensaje welcome para no ensuciar el chat
    if row["welcome_msg_id"]:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=row["welcome_msg_id"])
        except TelegramError:
            pass
    log.info("verification OK user=%s chat=%s", target_user_id, chat_id)


REMINDER_TEXT = (
    "⏰ <b>Recordatorio para {name}</b>\n\n"
    "Llevas {hours}h en <b>{chat}</b> y aún no has verificado que eres humano. "
    "Te quedan <b>{remaining_hours}h</b> para pulsar el botón o serás "
    "<b>expulsado</b> por considerarte posible bot.\n\n"
    "👇 Pulsa el botón para poder escribir."
)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periódico (cada 30 min):
    - Para suspicious con >12h sin verificar → kick (sin ban)
    - Para CUALQUIER pending con >6h sin verificar y sin reminder → recordatorio
    """
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if cfg.shadow:
        return
    db: DB = context.bot_data["db"]

    chats = {row["chat_id"]: row for row in db.all_chats() if row["am_admin"]}
    for chat_id, chat_row in chats.items():
        settings = db.get_chat_settings(chat_id)
        # Granularidad fina: minutos para sospechosos
        kick_minutes = (settings["verification_suspicious_kick_minutes"] if settings else 30) or 30
        reminder_hours = (settings["verification_reminder_hours"] if settings else 3) or 3
        kick_after_reminder_h = (settings["verification_kick_after_reminder_hours"] if settings else 6) or 6
        welcome_ttl = (settings["welcome_delete_after_s"] if settings else 900) or 900

        # 0) Barrido de welcomes vencidos (robusto ante reinicios del bot, que
        # pierden los jobs jq.run_once en memoria). DB-driven.
        for row in db.pending_welcomes_past_ttl(welcome_ttl):
            if row["chat_id"] != chat_id:
                continue
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=row["welcome_msg_id"])
                log.info("welcome vencido borrado (barrido DB) user=%s chat=%s", row["user_id"], chat_id)
            except TelegramError:
                pass
            db.clear_welcome_msg_id(chat_id, row["user_id"])

        # 1) Kick suspicious expirados (default 10 min)
        # Usar _apply_action para que pase por pipeline completo:
        # reporter Telethon + log + notif admin DM + quip público + cleanup pending.
        from .handlers import _apply_action  # lazy import (evita circular)
        from .scoring import Decision
        for row in db.expired_suspicious_pending_minutes(kick_minutes):
            if row["chat_id"] != chat_id:
                continue
            decision = Decision(
                action="kick", score=80,
                rule="verification_suspicious_timeout",
                reason=f"No verificó en {kick_minutes} min siendo cuenta sospechosa",
                payload={},
            )
            try:
                # Intentar obtener username actual
                try:
                    member = await context.bot.get_chat_member(chat_id=chat_id, user_id=row["user_id"])
                    username = member.user.username
                except Exception:
                    username = None
                await _apply_action(
                    context, db, cfg,
                    chat_id=chat_id, chat_title=chat_row["title"],
                    user_id=row["user_id"], username=username, message_id=None,
                    decision=decision, original_text=None,
                )
                log.info("verification kick sospechoso user=%s chat=%s tras %dmin", row["user_id"], chat_id, kick_minutes)
            except Exception as exc:
                log.warning("verification kick fallo user=%s: %s", row["user_id"], exc)
                # Por si _apply_action falla, limpiar manualmente
                db.delete_pending(chat_id, row["user_id"])

        # 2) Reminder: pending sin verificar tras N horas (default 3h)
        for row in db.pending_needing_reminder(reminder_hours):
            if row["chat_id"] != chat_id:
                continue
            await _send_reminder(context, db, chat_row, row, reminder_hours)

        # 3) Kick post-reminder: pending normales con reminder enviado hace >N horas (default 6h).
        # Cierra el loop del tier 'normal': 3h → reminder, +6h sin verificar → kick.
        for row in db.pending_kick_after_reminder(kick_after_reminder_h):
            if row["chat_id"] != chat_id:
                continue
            total_h = reminder_hours + kick_after_reminder_h
            decision = Decision(
                action="kick", score=70,
                rule="verification_reminder_timeout",
                reason=f"No verificó en {total_h}h ({reminder_hours}h + {kick_after_reminder_h}h tras recordatorio)",
                payload={},
            )
            try:
                try:
                    member = await context.bot.get_chat_member(chat_id=chat_id, user_id=row["user_id"])
                    username = member.user.username
                except Exception:
                    username = None
                await _apply_action(
                    context, db, cfg,
                    chat_id=chat_id, chat_title=chat_row["title"],
                    user_id=row["user_id"], username=username, message_id=None,
                    decision=decision, original_text=None,
                )
                log.info("verification kick post-reminder user=%s chat=%s tras %dh", row["user_id"], chat_id, total_h)
            except Exception as exc:
                log.warning("verification kick post-reminder fallo user=%s: %s", row["user_id"], exc)
                db.delete_pending(chat_id, row["user_id"])


async def _send_reminder(
    context: ContextTypes.DEFAULT_TYPE,
    db: DB,
    chat_row,
    pending_row,
    hours: int,
) -> None:
    """Borra el welcome viejo y envía uno nuevo con tono de recordatorio."""
    chat_id = pending_row["chat_id"]
    user_id = pending_row["user_id"]

    # Race guard: si el user se verificó entre que se agendó esta tarea y ahora,
    # abortar para no dejar welcome huérfano.
    fresh = db.get_pending(chat_id, user_id)
    if not fresh:
        log.debug("reminder abortado: pending ya no existe user=%s chat=%s", user_id, chat_id)
        return

    # Borrar welcome anterior
    if pending_row["welcome_msg_id"]:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=pending_row["welcome_msg_id"])
        except TelegramError:
            pass

    # Obtener info del user para la mención
    try:
        member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        u = member.user
        if u.username:
            name = f"@{u.username}"
        else:
            display = html.escape(u.first_name or str(u.id))
            name = f'<a href="tg://user?id={u.id}">{display}</a>'
    except TelegramError:
        name = f'<a href="tg://user?id={user_id}">usuario</a>'

    chat_name = html.escape(chat_row["title"] or "el grupo")
    settings = db.get_chat_settings(chat_id)
    remaining_hours = (settings["verification_kick_after_reminder_hours"] if settings else 6) or 6
    text = REMINDER_TEXT.format(name=name, hours=hours, chat=chat_name, remaining_hours=remaining_hours)

    callback_data = f"{CALLBACK_PREFIX}:{chat_id}:{user_id}"
    rows = [[InlineKeyboardButton(
        "✅ SOY HUMANO (PULSA PARA ENTRAR)",
        callback_data=callback_data,
    )]]
    # Repetir botones extra del welcome configurado
    for b in db.list_welcome_buttons(chat_id):
        rows.append([InlineKeyboardButton(b["text"], url=b["url"])])

    new_msg_id = None
    try:
        sent = await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
            disable_notification=False,
        )
        new_msg_id = sent.message_id
        log.info("verification reminder enviado user=%s chat=%s tras %dh", user_id, chat_id, hours)
    except TelegramError as exc:
        log.warning("verification reminder send fallo: %s", exc)

    db.mark_reminder_sent(chat_id, user_id, new_msg_id)
