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

import html
import html as _html
import logging
import os
import random
from pathlib import Path
from typing import Optional

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import user_signals
from .db import DB
from .detectors.unicode_script import non_allowed_ratio
from .i18n import current_lang, t

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




def _verification_footer(settings, suspicious: bool, susp_reasons: list) -> str:
    """Añade debajo del welcome (mismo mensaje) la CONSECUENCIA con los tiempos
    configurados. No repite lo del botón (eso ya va en el welcome, custom o default),
    solo informa de qué pasa si no verifica, siempre con la config real."""
    if suspicious:
        kick_minutes = settings["verification_suspicious_kick_minutes"] or 30
        reasons_str = render_reasons(susp_reasons)
        return t("verif.footer_susp", reasons=html.escape(reasons_str), mins=kick_minutes)
    if settings["verification_kick_normal"]:
        total_h = (settings["verification_reminder_hours"] or 3) + (settings["verification_kick_after_reminder_hours"] or 6)
        return t("verif.footer_kick", hours=total_h)
    return t("verif.footer_mute")


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


_HAN_RE = __import__("re").compile(r'[㐀-䶿一-鿿豈-﫿\U00020000-\U0002a6df]')


def _han_dominant(value: Optional[str]) -> bool:
    """True si el campo está dominado por ideogramas chinos (Han) reales.

    Requiere ≥2 ideogramas Han Y que sean ≥50% de las letras del campo. Así NO
    cuenta el katakana decorativo (ツ, no es Han), ni un símbolo Han suelto en un
    nombre por lo demás latino. NFKC primero por consistencia.
    """
    if not value:
        return False
    import unicodedata
    norm = unicodedata.normalize("NFKC", value)
    letters = [c for c in norm if c.isalpha()]
    if not letters:
        return False
    han = sum(1 for c in letters if _HAN_RE.match(c))
    return han >= 2 and han / len(letters) >= 0.5


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
            reasons.append((REASON_DECORATIVE, {"label": label}))
            continue
        ratio, dominant = non_allowed_ratio(norm, ["latin"])
        if ratio > 0.3:
            non_latin_count += 1
            reasons.append((REASON_NON_LATIN_FIELD,
                            {"label": label, "ratio": f"{ratio:.0%}", "dominant": dominant}))
            if ratio >= 0.7:
                high_ratio_single = True
    # BYPASS de seguridad: si Telethon dice cuenta ≥365d + con foto,
    # NUNCA ban directo por nombre. Es un user bilingüe probable.
    if sig is not None and sig.photo_count >= 1 and (sig.account_age_days or 0) >= 365:
        return False, reasons + [(REASON_BYPASS_OLD, {})]
    # Chino REAL (ideogramas Han) en cualquier campo: señal muy fuerte de spam en
    # grupos hispanos. A diferencia del árabe/cirílico (con users legítimos) o el
    # katakana decorativo (ツ), un nombre dominado por ideogramas Han en un grupo
    # de habla hispana es casi siempre un bot de promo. Un solo campo basta. El
    # bypass de cuenta antigua + foto de arriba protege al chino-hablante real.
    if any(_han_dominant(v) for v in (first_name, last_name, username)):
        return True, reasons + [(REASON_HAN_DOMINANT, {})]
    # 2+ campos non-latín → señal fuerte, ban directo
    if non_latin_count >= 2:
        return True, reasons
    # 1 campo high_ratio (e.g. árabe puro) + cuenta nueva + sin foto → ban
    # Sin las señales Telethon, NO ban (era el caso de FP con users bilingües)
    if (non_latin_count >= 1 or high_ratio_single) and sig is not None:
        if sig.photo_count == 0 and sig.account_age_days is not None and sig.account_age_days < 30:
            reasons.append((REASON_NO_PHOTO_NEW, {"days": sig.account_age_days}))
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


# --- Motivos de sospecha: CÓDIGOS estables (los compara la lógica) + params ---
# Antes eran cadenas en español y _is_review_worthy las comparaba literalmente, así que
# traducirlas habría roto la decisión de avisar EN SILENCIO. Con códigos, la lógica es
# independiente del idioma y el texto se traduce solo al mostrarlo (render_reasons).
REASON_NO_USERNAME = "no_username"
REASON_NO_FIRSTNAME = "no_firstname"
REASON_NON_LATIN_NAME = "non_latin_name"
REASON_NON_LATIN_USERNAME = "non_latin_username"
REASON_NO_PHOTO = "no_photo"
REASON_RECENT_ACCOUNT = "recent_account"
# Motivos de "perfil evidentemente spammer" (solo diagnóstico, pero se PERSISTEN en el
# payload de la acción: guardar códigos y no texto traducido mantiene la BD estable).
REASON_DECORATIVE = "decorative"
REASON_NON_LATIN_FIELD = "non_latin_field"
REASON_BYPASS_OLD = "bypass_old_photo"
REASON_HAN_DOMINANT = "han_dominant"
REASON_NO_PHOTO_NEW = "no_photo_new"


def render_reason_list(reasons) -> list[str]:
    """Códigos de motivo → textos traducidos al idioma activo."""
    return [t(f"reason.{code}", **params) for code, params in reasons]


def render_reasons(reasons) -> str:
    """Motivos ya traducidos y unidos, listos para mostrar."""
    if not reasons:
        return t("review.reason_default")
    return ", ".join(render_reason_list(reasons))


def _is_suspicious_profile(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
) -> tuple[bool, list[str]]:
    """Cuenta sospechosa = pinta de cuenta recién creada o desechable.

    Devuelve (es_sospechoso, razones).
    """
    reasons: list[tuple[str, dict]] = []
    if not username:
        reasons.append((REASON_NO_USERNAME, {}))
    if not first_name:
        reasons.append((REASON_NO_FIRSTNAME, {}))
    # Nombre o username en script no-latino (cirílico, chino, árabe, etc.)
    if _name_in_non_latin_script(first_name) or _name_in_non_latin_script(last_name):
        reasons.append((REASON_NON_LATIN_NAME, {}))
    if _name_in_non_latin_script(username):
        reasons.append((REASON_NON_LATIN_USERNAME, {}))
    if sig is not None:
        if sig.photo_count == 0:
            reasons.append((REASON_NO_PHOTO, {}))
        else:
            age = sig.account_age_days
            if age is not None and age < 90:
                reasons.append((REASON_RECENT_ACCOUNT, {"days": age}))
    return (bool(reasons), reasons)


# Razones "fuertes": por sí solas justifican avisar al admin en el modo revisión.
_STRONG_SUSP_REASONS = {
    REASON_NON_LATIN_NAME, REASON_NON_LATIN_USERNAME, REASON_NO_PHOTO, REASON_RECENT_ACCOUNT,
}

# Señales que de verdad correlacionan con spam, no con «usuario discreto». Muchísima
# gente legítima no tiene foto ni @username, así que esas DOS no entran aquí: en el
# nivel alto avisar por ellas convierte el aviso en ruido y se acaba ignorando, que
# es peor que no tenerlo. Lo que sí es raro es el nombre en otro alfabeto, el nombre
# decorativo (homoglifos) o una cuenta recién creada sin ninguna foto.
_ALARMANTES = {
    REASON_NON_LATIN_NAME, REASON_NON_LATIN_USERNAME, REASON_DECORATIVE,
    REASON_NON_LATIN_FIELD, REASON_HAN_DOMINANT, REASON_NO_PHOTO_NEW,
}

# Niveles de aviso. El defecto es el más callado: quien monte el bot por primera vez
# no debe encontrarse el privado lleno el primer día.
NIVEL_ALTO = "alto"      # solo señales alarmantes de verdad
NIVEL_MEDIO = "medio"    # una señal fuerte, o dos cualesquiera
NIVEL_BAJO = "bajo"      # cualquier indicio
NIVELES = (NIVEL_ALTO, NIVEL_MEDIO, NIVEL_BAJO)


def nivel_de(settings) -> str:
    """Nivel de aviso de este chat. NULL = el más callado."""
    try:
        v = settings["review_level"] if settings is not None else None
    except (KeyError, IndexError, TypeError):
        return NIVEL_ALTO
    return v if v in NIVELES else NIVEL_ALTO


def han_requiere_decision(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
) -> bool:
    """¿Nombre con ideogramas Han que SOLO se libra por el salvoconducto?

    `_is_obvious_spam_profile` banea al entrar por un nombre en Han, salvo que
    Telegram diga que la cuenta tiene más de un año y foto: ese salvoconducto está
    para no expulsar a un chino-hablante real con cuenta asentada.

    El problema medido: un spammer usó justo eso. Cuenta antigua con foto, pasó a
    la verificación normal, **pulsó el botón a los 3 segundos** y entró; dos días
    después soltó el spam. Pulsar un botón no demuestra nada frente a un bot.

    Así que en ese caso concreto no se banea ni se deja pasar: se deja MUDO y
    decide el admin desde su privado. Cero falsos positivos (si es legítimo, el
    admin lo deja entrar) y cero coladas (si no hace nada, no puede escribir).
    """
    if not any(_han_dominant(v) for v in (first_name, last_name, username)):
        return False
    # Sin señales de Telethon el salvoconducto no aplica: ahí `_is_obvious_spam_profile`
    # ya banea solo, y este camino no debe pisarlo.
    if sig is None:
        return False
    return sig.photo_count >= 1 and (sig.account_age_days or 0) >= 365


def _is_review_worthy(
    sig: Optional[user_signals.UserSignals],
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str] = None,
    nivel: str = NIVEL_ALTO,
) -> tuple[bool, list[str]]:
    """¿Merece un aviso privado de revisión? Depende del NIVEL elegido en el chat.

    - `alto` (defecto): solo señales alarmantes de verdad. Nombre o usuario en otro
      alfabeto, nombre decorativo con homoglifos, o cuenta recién creada sin foto.
    - `medio`: el comportamiento anterior. Una señal fuerte, o dos cualesquiera.
    - `bajo`: cualquier indicio, por débil que sea.

    El nivel existe porque en `medio` bastaba con «sin foto de perfil» para avisar, y
    eso lo cumple muchísima gente legítima: el privado se llenaba y el aviso acababa
    ignorándose, que es peor que no tenerlo.
    """
    suspicious, reasons = _is_suspicious_profile(sig, username, first_name, last_name)
    if not suspicious:
        return (False, [])
    codigos = [code for code, _ in reasons]

    if nivel == NIVEL_BAJO:
        return (True, reasons)

    if nivel == NIVEL_ALTO:
        # Solo lo que de verdad huele a spam. «Sin foto» y «sin @username» sueltas
        # NO bastan: las cumple muchísima gente legítima y llenaban el privado.
        return (any(c in _ALARMANTES for c in codigos), reasons)

    strong = [c for c in codigos if c in _STRONG_SUSP_REASONS]
    if strong or len(reasons) >= 2:
        return (True, reasons)
    return (False, reasons)


def _int_env(name: str, default: int) -> int:
    """Lee un entero de entorno; si falta o es inválido, usa el default (no crashea
    el arranque por un valor mal puesto en .env)."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        log.warning("%s inválido en .env, usando default %s", name, default)
        return default


# Duración en el chat del welcome amistoso (confianza alta, sin verificación).
# 15 min por defecto. Configurable en .env.
FRIENDLY_WELCOME_DELETE_AFTER_S = _int_env("FRIENDLY_WELCOME_DELETE_AFTER_S", 900)
# Duración del mensaje de "verificación correcta + welcome" tras pulsar SOY HUMANO.
# 5 min: suficiente para leer el saludo y pulsar el botón del anclado sin dejar el
# chat lleno de bienvenidas viejas. Es el DEFECTO GLOBAL: cada chat puede cambiarlo
# desde /config (columna verified_ttl_s), y 0 significa no borrarlo nunca.
VERIFIED_WELCOME_DELETE_AFTER_S = _int_env("VERIFIED_WELCOME_DELETE_AFTER_S", 300)


def _verified_ttl(settings) -> int:
    """Segundos que dura el mensaje de «verificación correcta» en este chat.

    `chat_settings.verified_ttl_s` manda; su NULL significa «no se ha decidido
    aquí» y hereda el .env. OJO: 0 es un valor VÁLIDO (no borrar nunca), así que
    no se puede tratar como «sin definir» con un `or`, que es el error fácil aquí.
    """
    try:
        v = settings["verified_ttl_s"] if settings is not None else None
    except (KeyError, IndexError, TypeError):
        return VERIFIED_WELCOME_DELETE_AFTER_S
    if v is None:
        return VERIFIED_WELCOME_DELETE_AFTER_S
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return VERIFIED_WELCOME_DELETE_AFTER_S


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

def _default_welcomes() -> list[str]:
    """Fallback en código de los saludos amistosos, en el idioma activo.
    Son PLANTILLAS: su {name} lo formatea después quien las envía."""
    return [t("welcome.friendly1"), t("welcome.friendly2")]



def _read_phrase_file(path: Path) -> list[str]:
    """Lee un archivo de frases: una por línea, ignora vacías y comentarios (#)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln.strip() for ln in raw.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def _load_welcome_pack(chat_id: int) -> list[str]:
    """Frases de bienvenida para un chat, por orden de preferencia:
    archivo del grupo → genérico DEL IDIOMA → genérico → fallback traducido.

    El genérico por idioma (`generic.en.txt`) va ANTES que `generic.txt` a
    propósito: `generic.txt` viene en español en el repo, así que sin este paso
    quien instalara el bot en inglés recibiría bienvenidas en español (el archivo
    existe, luego gana al fallback traducido y nadie se explica por qué).
    """
    pack = _read_phrase_file(_WELCOMES_DIR / f"{chat_id}.txt")
    if not pack:
        pack = _read_phrase_file(_WELCOMES_DIR / f"generic.{current_lang()}.txt")
    if not pack:
        pack = _read_phrase_file(_WELCOMES_DIR / "generic.txt")
    return pack or _default_welcomes()


def friendly_welcomes_enabled() -> bool:
    """Toggle de los saludos simpáticos (FRIENDLY_WELCOMES_ENABLED, default true)."""
    return os.getenv("FRIENDLY_WELCOMES_ENABLED", "true").strip().lower() not in ("false", "0", "no")


def _user_name_html(user) -> str:
    """Nombre clicable del user para el welcome (@username o link tg://user)."""
    if user.username:
        return f"@{user.username}"
    display = html.escape(user.first_name or str(user.id))
    return f'<a href="tg://user?id={user.id}">{display}</a>'


def _build_welcome_content(db, chat_id: int, name_html: str, verified: bool = False):
    """Devuelve (texto, teclado) del welcome amistoso: quip aleatorio + footer +
    botones URL configurados del chat (anclado, normas...). Si verified=True añade
    una cabecera de 'verificación correcta'. Reutilizado por el welcome de
    confianza alta y por el mensaje editado tras pulsar SOY HUMANO."""
    catalog = _load_welcome_pack(chat_id)
    greeting = random.choice(catalog).format(name=name_html)
    # La cabecera NO saluda: el propio quip del catálogo ya dice "Bienvenido/a {name}"
    # (si no, saldría "Bienvenido/a" dos veces).
    header = t("verif.ok_header") if verified else ""
    text = f"{header}{greeting}" + t("welcome.footer_wrap", footer=t("welcome.footer_fixed"))
    rows: list[list[InlineKeyboardButton]] = []
    db.migrate_legacy_welcome_button(chat_id)
    buttons = db.list_welcome_buttons(chat_id)
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
    return text, keyboard


async def _send_friendly_welcome(context, db, chat, user, settings) -> None:
    """Welcome amistoso para cuentas legítimas: sin mute, sin botón verify.
    Incluye solo los botones URL configurados del chat (anclado, normas, etc.).
    Auto-borrado a los 15 min para no ensuciar el chat.
    """
    text, keyboard = _build_welcome_content(db, chat.id, _user_name_html(user))
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
        # Duplicado a propósito en seen_users: la fila de `pending_verifications`
        # se limpia al verificar, y a partir de ahí un ban posterior ya no sabría
        # qué mensaje borrar.
        try:
            db.set_welcome_msg(chat.id, user.id, sent.message_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("no se pudo recordar el welcome chat=%s user=%s: %s", chat.id, user.id, exc)
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
            db.delete_pending(data["chat_id"], data["user_id"])
        except Exception:  # noqa: BLE001
            pass


# Presets de tiempos del panel de revisión (mismos que /config).
_REVIEW_TIME_FIELDS = {
    "sk": ("verification_suspicious_kick_minutes", [15, 30, 60, 120], "min"),
    "rh": ("verification_reminder_hours", [1, 3, 6, 12], "h"),
    "kh": ("verification_kick_after_reminder_hours", [3, 6, 12, 24], "h"),
}


def _rv_onoff(v) -> str:
    return t("on") if v else t("off")


def _rv_decide_row(chat_id: int, user_id: int) -> list:
    return [
        InlineKeyboardButton(t("btn.allow"), callback_data=f"susrev:allow:{chat_id}:{user_id}"),
        InlineKeyboardButton(t("btn.ban"), callback_data=f"susrev:ban:{chat_id}:{user_id}"),
    ]


def build_muted_review_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Botones del aviso de «entró y está mudo esperando tu decisión».

    Acción `allowu` en vez de `allow` porque aquí Permitir tiene que DESMUTEAR: en
    el flujo normal el usuario ya estaba dentro y no había nada que deshacer.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("btn.allow"), callback_data=f"susrev:allowu:{chat_id}:{user_id}"),
        InlineKeyboardButton(t("btn.ban"), callback_data=f"susrev:ban:{chat_id}:{user_id}"),
    ]])


def build_review_keyboard(db: DB, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Vista COLAPSADA del aviso: decidir sobre el usuario + ⚙️ tuerca de ajustes."""
    return InlineKeyboardMarkup([
        _rv_decide_row(chat_id, user_id),
        [InlineKeyboardButton(t("btn.gear"), callback_data=f"susrev:gear:{chat_id}:{user_id}")],
    ])


def build_review_settings_keyboard(db: DB, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Panel de ajustes tras pulsar la tuerca: verificación, avisos, recordatorios y
    (si están activos) los tiempos. Los cambios respetan el modo de sincronización."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    remind = bool(s and s["verification_reminders_enabled"])
    rows = [
        _rv_decide_row(chat_id, user_id),
        [InlineKeyboardButton(t("btn.verif", state=_rv_onoff(s and s["verification_enabled"])),
                              callback_data=f"susrev:togverif:{chat_id}:{user_id}")],
        [InlineKeyboardButton(t("btn.alerts", state=_rv_onoff(s and s["verification_review_suspicious"])),
                              callback_data=f"susrev:togreview:{chat_id}:{user_id}")],
        [InlineKeyboardButton(t("btn.reminders", state=_rv_onoff(remind)),
                              callback_data=f"susrev:togremind:{chat_id}:{user_id}")],
    ]
    if remind:
        sk = (s["verification_suspicious_kick_minutes"] if s else None) or 30
        rh = (s["verification_reminder_hours"] if s else None) or 3
        kh = (s["verification_kick_after_reminder_hours"] if s else None) or 6
        rows.append([InlineKeyboardButton(t("btn.times", sk=sk, rh=rh, kh=kh),
                                          callback_data=f"susrev:times:{chat_id}:{user_id}")])
    rows.append([InlineKeyboardButton(t("btn.hide"),
                                      callback_data=f"susrev:collapse:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(rows)


def build_review_times_keyboard(db: DB, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    """Submenú de tiempos del aviso: presets por fila, el actual marcado con ✅."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    rows = []
    for code, (field, presets, unit) in _REVIEW_TIME_FIELDS.items():
        cur = (s[field] if s else None) or presets[1]
        row = []
        for val in presets:
            mark = "✅ " if val == cur else ""
            label = f"{mark}{'+' if code == 'kh' else ''}{val}{unit}"
            row.append(InlineKeyboardButton(
                label, callback_data=f"susrev:st:{code}:{val}:{chat_id}:{user_id}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(t("btn.back"), callback_data=f"susrev:gear:{chat_id}:{user_id}")])
    return InlineKeyboardMarkup(rows)


async def _send_suspicious_review(context, db, cfg, chat, user, reasons, sig) -> None:
    """Modo revisión: avisa al admin (DM o canal) de un sospechoso que ha ENTRADO,
    con botones Permitir / Banear. El user ya está dentro (permitido por defecto)."""
    if not cfg.admin_notify_chat_id:
        return
    label = f"@{user.username}" if user.username else (user.first_name or str(user.id))
    reasons_str = render_reasons(reasons)
    extra = ""
    if sig is not None:
        try:
            extra = "\n" + user_signals.render_markup(sig)
        except Exception:  # noqa: BLE001
            pass
    kb = build_review_keyboard(db, chat.id, user.id)
    text = (
        t("review.title") + "\n"
        + t("review.chat", title=html.escape(chat.title or str(chat.id))) + "\n"
        + t("review.user", uid=user.id, label=html.escape(label)) + "\n"
        + t("review.reason", reasons=html.escape(reasons_str))
        + f"{extra}\n\n"
        + t("review.footer")
    )
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=text, parse_mode="HTML",
            reply_markup=kb, disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.debug("suspicious review send fallo user=%s: %s", user.id, exc)


# Default del welcome en modo limpio (sin instrucción de "pulsa el botón").


async def _send_clean_welcome(context, db, chat, user, settings) -> None:
    """Welcome en MODO LIMPIO: saluda al recién llegado con el texto configurado del
    grupo, SIN botón SOY HUMANO ni mute. Se autoborra tras welcome_delete_after_s.
    Incluye los botones URL configurados del chat (anclado, normas...)."""
    welcome_text = (settings["welcome_text"] if settings else None) or t("welcome.clean_default")
    if user.username:
        name = f"@{user.username}"
    else:
        display = html.escape(user.first_name or str(user.id))
        name = f'<a href="tg://user?id={user.id}">{display}</a>'
    chat_name = html.escape(chat.title or "el grupo")
    try:
        text = welcome_text.format(name=name, chat=chat_name)
    except (KeyError, IndexError, ValueError):
        text = welcome_text  # texto con llaves raras: se manda tal cual, sin romper
    # Botones URL configurados del chat (sin SOY HUMANO).
    db.migrate_legacy_welcome_button(chat.id)
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for b in db.list_welcome_buttons(chat.id):
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
        log.warning("clean welcome send fallo chat=%s: %s", chat.id, exc)
        return
    # Recordar cuál es su bienvenida: si luego lo banean (a mano o con /ban), hay
    # que poder borrarla. Sin esto se quedaba en el grupo saludando a alguien ya
    # expulsado, que es justo lo que veía el admin.
    if sent:
        try:
            db.set_welcome_msg(chat.id, user.id, sent.message_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("no se pudo recordar el welcome chat=%s user=%s: %s", chat.id, user.id, exc)
    delete_after = (settings["welcome_delete_after_s"] if settings else 0) or 0
    if sent and delete_after > 0:
        jq = context.application.job_queue
        if jq:
            jq.run_once(
                _delete_welcome_job, when=delete_after,
                data={"chat_id": chat.id, "message_id": sent.message_id},
                name=f"del_clean_welcome_{chat.id}_{sent.message_id}",
            )


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
    verification_on = bool(settings and settings["verification_enabled"])
    review_suspicious = bool(settings and settings["verification_review_suspicious"])

    async def _unmute(reason: str) -> None:
        # Deshace el mute provisional que on_chat_member aplica a todo recién llegado.
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=user.id, permissions=VERIFIED_PERMISSIONS,
            )
        except TelegramError as exc:
            log.debug("unmute (%s) fallo user=%s: %s", reason, user.id, exc)

    welcome_on = bool(settings and settings["welcome_enabled"])

    # Señales del perfil: solo hacen falta si hay verificación o revisión activas.
    # (En modo puramente limpio con o sin welcome no se molesta a Telethon.)
    sig = prefetched_sig
    if sig is None and (verification_on or review_suspicious):
        reporter = context.bot_data.get("reporter")
        client = reporter.get_client() if reporter else None
        if client is not None:
            try:
                sig = await user_signals.fetch(client, user.id, chat_id=chat.id, first_name=user.first_name)
            except Exception as exc:
                log.debug("user_signals fetch user=%s exc: %s", user.id, exc)
    suspicious, susp_reasons = _is_suspicious_profile(sig, user.username, user.first_name, user.last_name)
    review_worthy, review_reasons = _is_review_worthy(
        sig, user.username, user.first_name, user.last_name,
        nivel=nivel_de(settings))

    # MODO REVISIÓN: perfil claramente dudoso + review activo → aviso privado al admin
    # con Permitir/Banear (sin mute ni botón en el grupo); entra permitido por defecto.
    # Aplica tanto en modo limpio como con verificación. Indicio débil suelto no avisa.
    if review_suspicious and review_worthy:
        await _unmute("modo revisión")
        await _send_suspicious_review(context, db, cfg, chat, user, review_reasons, sig)
        return

    # MODO LIMPIO (verificación off): el user entra sin gate. Si la bienvenida está
    # activa en el grupo, se le saluda (sin botón SOY HUMANO ni mute; se autoborra).
    if not verification_on:
        await _unmute("modo limpio")
        if welcome_on:
            await _send_clean_welcome(context, db, chat, user, settings)
        return

    # Si el perfil es claramente legítimo, saltar verificación y publicar
    # un welcome amistoso (sin botón SOY HUMANO, sin mute) con los botones
    # configurados del chat (anclado, normas, etc.).
    very_legit, legit_reasons = _is_very_legit_profile(sig, user.username, user.first_name, user.last_name)
    if very_legit:
        log.info(
            "verification SKIP user=%s chat=%s: perfil legítimo (%s)",
            user.id, chat.id, ", ".join(legit_reasons),
        )
        # Perfil legítimo: no pasa por verificación. Como en on_chat_member se
        # aplica un mute provisional a todo recién llegado (trust<70), aquí hay
        # que DESMUTEARLO para que pueda escribir de inmediato.
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id, user_id=user.id, permissions=VERIFIED_PERMISSIONS,
            )
        except TelegramError as exc:
            log.debug("unmute legítimo fallo user=%s: %s", user.id, exc)
        # El saludo simpático es opcional.
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
    welcome_text = settings["welcome_text"] or t("welcome.default")
    # Mención preferente con @username (más natural). Fallback tg://user?id=N si no.
    if user.username:
        name = f"@{user.username}"
    else:
        display = html.escape(user.first_name or str(user.id))
        name = f'<a href="tg://user?id={user.id}">{display}</a>'
    chat_name = html.escape(chat.title or "el grupo")
    # CRÍTICO: el usuario YA está muteado (arriba). Si el welcome del admin trae una
    # llave que no sea {name}/{chat} (p.ej. "{algo}", "{}", ":-{"), .format() lanza y
    # la excepción escaparía de on_join SIN llegar a add_pending_verification: el
    # usuario quedaría muteado para siempre y sin fila pendiente, invisible para
    # cleanup_job (que se apoya en esa tabla). Mismo guard que _send_clean_welcome.
    try:
        text = welcome_text.format(name=name, chat=chat_name)
    except (KeyError, IndexError, ValueError):
        text = welcome_text  # texto con llaves raras: se manda tal cual, sin romper
    text += _verification_footer(settings, suspicious, susp_reasons)

    callback_data = f"{CALLBACK_PREFIX}:{chat.id}:{user.id}"
    rows = [[InlineKeyboardButton(
        t("verif.btn_human"),
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
    # También en seen_users: la fila pending se limpia al verificar y a partir de
    # ahí un ban posterior no sabría qué borrar. Ver `limpiar_bienvenidas`.
    if msg_id:
        try:
            db.set_welcome_msg(chat.id, user.id, msg_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("no se pudo recordar el welcome chat=%s user=%s: %s", chat.id, user.id, exc)
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
        await query.answer(t("verif.bad_button"))
        return
    try:
        chat_id = int(parts[1])
        target_user_id = int(parts[2])
    except ValueError:
        await query.answer(t("verif.bad_button"))
        return

    if query.from_user.id != target_user_id:
        await query.answer(t("verif.not_for_you"), show_alert=True)
        return

    db: DB = context.bot_data["db"]
    row = db.get_pending(chat_id, target_user_id)
    if not row:
        await query.answer(t("verif.already_or_expired"))
        return

    # Unmute. Vía `restringir_seguro`: si el usuario fue baneado mientras su
    # verificación seguía pendiente, pulsar el botón lo habría devuelto al grupo.
    # La fila pendiente se limpia al banear, pero eso es una protección indirecta;
    # esta es explícita y no depende de que ningún otro camino se acuerde.
    if not await restringir_seguro(context.bot, db, chat_id, target_user_id,
                                   VERIFIED_PERMISSIONS, "verificación correcta"):
        await query.answer(t("verif.unmute_error"))
        return

    db.mark_verified(chat_id, target_user_id)
    await query.answer(t("verif.done"))

    # En vez de BORRAR el mensaje de verificación, lo EDITAMOS a "verificación
    # correcta" + welcome gracioso con los botones del chat (anclado, normas...),
    # igual que el welcome de un miembro de confianza alta. Y lo dejamos más rato
    # (VERIFIED_WELCOME_DELETE_AFTER_S) para que dé tiempo a leerlo.
    welcome_msg_id = row["welcome_msg_id"]
    if welcome_msg_id:
        jq = context.application.job_queue
        # Cancelar el auto-borrado CORTO que se programó al enviar la verificación
        # (si no, borraría el welcome antes de tiempo).
        if jq is not None:
            for job in jq.get_jobs_by_name(f"del_welcome_{chat_id}_{welcome_msg_id}"):
                job.schedule_removal()
        try:
            text, keyboard = _build_welcome_content(
                db, chat_id, _user_name_html(query.from_user), verified=True,
            )
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=welcome_msg_id,
                text=text, parse_mode="HTML", reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            # Borrado contado desde AHORA (no desde el envío del prompt). El TTL es
            # el del chat, y 0 significa dejarlo para siempre: no se programa nada.
            ttl = _verified_ttl(db.get_chat_settings(chat_id))
            if jq is not None and ttl > 0:
                jq.run_once(
                    _delete_friendly_welcome_job, when=ttl,
                    data={"chat_id": chat_id, "message_id": welcome_msg_id, "user_id": target_user_id},
                    name=f"del_verified_welcome_{chat_id}_{welcome_msg_id}",
                )
        except TelegramError as exc:
            # "message is not modified" = doble callback con el mismo quip: el
            # mensaje YA muestra un welcome (lo editó el otro click), NO lo borramos.
            # Otros fallos (mensaje viejo/borrado): lo borramos para no dejar el
            # prompt colgado (el barrido DB también lo cubre tras un restart).
            if "not modified" not in str(exc).lower():
                log.debug("edit verificación→welcome fallo chat=%s: %s", chat_id, exc)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=welcome_msg_id)
                except TelegramError:
                    pass
        except Exception as exc:  # noqa: BLE001 — catálogo mal formado, etc.
            # No romper la verificación: el user ya está desmuteado y verificado.
            log.warning("welcome tras verificar falló chat=%s: %s", chat_id, exc)
    log.info("verification OK user=%s chat=%s", target_user_id, chat_id)





async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periódico (cada 15 min):
    - Para suspicious con >12h sin verificar → kick (sin ban)
    - Para CUALQUIER pending con >6h sin verificar y sin reminder → recordatorio
    """
    from .config import Config
    cfg: Config = context.bot_data["cfg"]
    if cfg.shadow:
        return
    db: DB = context.bot_data["db"]

    # Red de seguridad: bienvenidas de usuarios ya baneados que siguen ahí. El
    # borrado normal se programa a un minuto del ban, pero ese job vive en memoria:
    # si el bot se reinicia antes, se pierde y el saludo se queda para siempre.
    for chat_id, user_id, msg_id in db.bienvenidas_de_baneados():
        soltar = True
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            log.info("barrido: bienvenida huérfana borrada user=%s chat=%s", user_id, chat_id)
        except TelegramError as exc:
            # Solo se suelta el registro si el mensaje YA NO ESTÁ. Ante un fallo
            # transitorio (flood control, corte de red) hay que conservarlo: si no,
            # había un único reintento y la bienvenida del baneado se quedaba en el
            # grupo para siempre, que es justo lo que este barrido viene a evitar.
            texto = str(exc).lower()
            soltar = ("not found" in texto or "message to delete" in texto
                      or "message can't be deleted" in texto)
            log.debug("barrido: no se pudo borrar chat=%s msg=%s (%s), %s",
                      chat_id, msg_id, exc, "se olvida" if soltar else "se reintentará")
        if soltar:
            try:
                db.set_welcome_msg(chat_id, user_id, None)
            except Exception:  # noqa: BLE001
                pass

    chats = {row["chat_id"]: row for row in db.all_chats() if row["am_admin"]}
    for chat_id, chat_row in chats.items():
        settings = db.get_chat_settings(chat_id)
        # Granularidad fina: minutos para sospechosos
        kick_minutes = (settings["verification_suspicious_kick_minutes"] if settings else 30) or 30
        reminder_hours = (settings["verification_reminder_hours"] if settings else 3) or 3
        kick_after_reminder_h = (settings["verification_kick_after_reminder_hours"] if settings else 6) or 6
        welcome_ttl = (settings["welcome_delete_after_s"] if settings else 900) or 900

        # 0) Barrido de welcomes vencidos (robusto ante reinicios del bot, que
        # pierden los jobs jq.run_once en memoria). DB-driven. Los ya verificados
        # (welcome editado / amistoso) usan su TTL propio desde verified_at, no el
        # del prompt desde joined_at (si no, se borraban antes de tiempo).
        #
        # Si el chat pidió «no borrar nunca» (0), este barrido DEBE respetarlo: es
        # el otro sitio donde se borra, y sin esta guarda el mensaje sobrevivía
        # hasta el siguiente reinicio y luego desaparecía sin que nadie entendiera
        # por qué.
        ttl_verificado = _verified_ttl(settings)
        sweep_verified = ttl_verificado > 0
        verified_ttl = max(FRIENDLY_WELCOME_DELETE_AFTER_S, ttl_verificado)
        for row in db.pending_welcomes_past_ttl(welcome_ttl, verified_ttl):
            if row["chat_id"] != chat_id:
                continue
            if row["verified_at"] is not None and not sweep_verified:
                continue  # este chat quiere el mensaje de verificación para siempre
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
                reason=t("reason.verif_timeout_suspicious", mins=kick_minutes),
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

        # Ajustes del tier 'normal' (no suspicious):
        #   - kick_normal: si el que no verifica se EXPULSA (1) o se queda muteado
        #     para siempre (0).
        #   - reminders_on: si antes del kick se le envía un recordatorio.
        reminders_on = bool(settings["verification_reminders_enabled"]) if settings else True
        kick_normal = bool(settings["verification_kick_normal"]) if settings else True
        total_h = reminder_hours + kick_after_reminder_h

        # 2) Recordatorio: solo si están activados Y vamos a expulsar (el texto avisa
        # del kick; no tiene sentido si van a quedarse muteados). Tras N horas (3h).
        if reminders_on and kick_normal:
            for row in db.pending_needing_reminder(reminder_hours):
                if row["chat_id"] != chat_id:
                    continue
                await _send_reminder(context, db, chat_row, row, reminder_hours)

        # 3) Kick de normales que no verificaron — solo si kick_normal=1. Con
        # recordatorio: a reminder_hours + kick_after_reminder_h. Sin recordatorio:
        # directo a ese mismo total desde el join. Si kick_normal=0 → NO se toca
        # (quedan muteados para siempre).
        if kick_normal:
            if reminders_on:
                rows = db.pending_kick_after_reminder(kick_after_reminder_h)
                motivo = t("reason.verif_timeout_reminder", total_h=total_h,
                           reminder_h=reminder_hours, after_h=kick_after_reminder_h)
            else:
                rows = db.pending_normal_past_hours(total_h)
                motivo = t("reason.verif_timeout_no_reminder", total_h=total_h)
            for row in rows:
                if row["chat_id"] != chat_id:
                    continue
                decision = Decision(
                    action="kick", score=70,
                    rule="verification_reminder_timeout", reason=motivo, payload={},
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
                    log.info("verification kick normal user=%s chat=%s tras %dh", row["user_id"], chat_id, total_h)
                except Exception as exc:
                    log.warning("verification kick normal fallo user=%s: %s", row["user_id"], exc)
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
    text = t("verif.reminder", name=name, hours=hours, chat=chat_name,
             remaining_hours=remaining_hours)

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


async def limpiar_bienvenidas(context, db, user_id: int) -> int:
    """Borra las bienvenidas vivas de un usuario en TODOS los chats federados.

    Se llama al banear, venga el ban de donde venga: `/ban`, el combo de `/spam`,
    una regla automática o un ban a mano desde la propia app de Telegram. Sin esto,
    la bienvenida se quedaba en el grupo saludando a alguien ya expulsado.

    Mira los DOS sitios donde puede estar el id, porque ninguno cubre todos los
    casos: `pending_verifications` solo existe si la verificación está activa y
    desaparece al verificar, y `seen_users.welcome_msg_id` cubre el resto
    (incluido el modo limpio, que es el que viene por defecto).

    Se borra AL MOMENTO del ban: es lo más limpio para el grupo y lo más simple
    de razonar. Devuelve cuántos se borraron. Best-effort: un fallo de Telegram
    (mensaje ya borrado, sin permisos) nunca interrumpe el ban, y deja el
    registro puesto para que el barrido del `cleanup_job` lo reintente.
    """
    borrados = 0
    vistos: set[tuple[int, int]] = set()

    async def _borrar(chat_id: int, msg_id: int) -> bool:
        """Borra ya. Si Telegram falla, se CONSERVA el registro a propósito: el
        barrido del cleanup_job lo reintentará dentro de un rato. Soltarlo aquí
        dejaría el saludo en el grupo para siempre y sin rastro de que quedó."""
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except TelegramError as exc:
            log.debug("bienvenida no borrada chat=%s msg=%s (se reintentará): %s",
                      chat_id, msg_id, exc)
            return False
        try:
            db.set_welcome_msg(chat_id, user_id, None)
        except Exception:  # noqa: BLE001
            pass
        return True

    for chat_id, msg_id in db.welcomes_pendientes(user_id):
        if not msg_id or (chat_id, msg_id) in vistos:
            continue
        vistos.add((chat_id, msg_id))
        if await _borrar(chat_id, msg_id):
            borrados += 1

    for chat_row in db.all_chats():
        if not chat_row["am_admin"]:
            continue
        chat_id = chat_row["chat_id"]
        pending = db.get_pending(chat_id, user_id)
        if not pending:
            continue
        msg_id = pending["welcome_msg_id"]
        if msg_id and (chat_id, msg_id) not in vistos:
            vistos.add((chat_id, msg_id))
            if await _borrar(chat_id, msg_id):
                borrados += 1
        db.delete_pending(chat_id, user_id)

    if borrados:
        log.info("bienvenidas borradas tras ban user=%s: %d", user_id, borrados)
    return borrados


async def avisar_han_mudo(context, db, cfg, chat, user, sig) -> None:
    """Aviso al admin: alguien con nombre en Han ha entrado y está MUDO.

    Se manda aunque los avisos de sospechosos estén apagados: no es el aviso
    informativo de «perfil dudoso», es una decisión pendiente que bloquea a una
    persona. Silenciarlo dejaría a alguien mudo indefinidamente sin que nadie lo sepa.
    """
    if not cfg.admin_notify_chat_id:
        return
    etiqueta = f"@{user.username}" if user.username else (user.first_name or str(user.id))
    extra = ""
    if sig is not None:
        try:
            extra = "\n" + user_signals.render_markup(sig)
        except Exception:  # noqa: BLE001
            pass
    texto = t("han.muted_review", name=_html.escape(etiqueta), uid=user.id,
              chat=_html.escape(str(chat.title or chat.id))) + extra
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_notify_chat_id, text=texto, parse_mode="HTML",
            reply_markup=build_muted_review_keyboard(chat.id, user.id),
            disable_web_page_preview=True,
        )
    except TelegramError as exc:
        log.warning("aviso han mudo falló: %s", exc)


async def restringir_seguro(bot, db, chat_id: int, user_id: int, permissions,
                            motivo: str = "", until_date=None) -> bool:
    """Aplica permisos a alguien SOLO si no está baneado. Devuelve si se aplicó.

    En Telegram, `restrictChatMember` sobre alguien EXPULSADO **lo devuelve al
    grupo** como restringido: pasa de estar fuera a estar dentro y callado. O sea
    que cualquier mute aplicado por descuido a un baneado deshace el ban en
    silencio, y encima deja el registro diciendo que sigue baneado.

    Esa es exactamente la transición que costó día y medio detectar en agosto de
    2026 (un usuario baneado apareció como `restricted` y siguió escribiendo). Allí
    la causó la app de Telegram, no el bot, pero el bot tenía SEIS sitios que
    podían provocar lo mismo sin ninguna comprobación: el botón SOY HUMANO, el
    mute del antiflood, el de la acción de moderación y el mute provisional al
    entrar. Este helper cierra todos de una vez.
    """
    try:
        if db is not None and db.is_banned(user_id):
            log.warning(
                "restricción ABORTADA sobre un baneado user=%s chat=%s (%s): "
                "aplicarla lo habría readmitido en el grupo", user_id, chat_id, motivo)
            return False
    except Exception as exc:  # noqa: BLE001
        log.debug("no se pudo comprobar el ban de %s: %s", user_id, exc)
    try:
        # `until_date` importa: sin él un mute temporal (antiflood 24 h) se
        # convertiría en permanente, y nadie lo notaría hasta que el usuario se
        # quejara de seguir mudo días después.
        kw = {"until_date": until_date} if until_date else {}
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id,
                                       permissions=permissions, **kw)
        return True
    except TelegramError as exc:
        log.debug("restrict (%s) falló chat=%s user=%s: %s", motivo, chat_id, user_id, exc)
        return False
