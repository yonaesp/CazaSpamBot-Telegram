"""Panel de ajustes por botones (/config) — configurar cada grupo desde el DM.

Flujo:
1. Admin escribe /config (en DM o en un grupo).
2. En DM con varios grupos → selector de grupo (botones). Con uno solo, va directo.
3. Panel con botones que reflejan el estado y se actualizan al pulsar (toggles,
   acción kick/mute, submenú de tiempos, alertas).
4. Para textos libres (bienvenida y reglas) el botón pide que escribas el texto:
   se captura el siguiente mensaje del DM (ver `handle_capture`, un solo uso, con
   botón Cancelar). Solo actúa el ADMIN_USER_ID.

Reutiliza el setter validado `db.update_chat_setting` y el parseo de botones Rose
de `chat_settings_cmd`, así que la persistencia es idéntica a los comandos sueltos.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import custom_terms, quips, rule_explain, settings_sync
from .config import Config
from .db import DB
from .i18n import t

log = logging.getLogger(__name__)

PREFIX = "cfg"

# Toggles booleanos: code de callback corto → columna real en chat_settings.
_TOGGLE_FIELDS = {
    "verification_enabled",
    "verification_review_suspicious",
    "verification_reminders_enabled",
    "welcome_enabled",
    "cleanservice",
    "topweekly_enabled",
}

# Presets de tiempos (dentro de los rangos que valida /verificacion).
_TIME_FIELDS = {
    "sk": ("verification_suspicious_kick_minutes", [15, 30, 60, 120], "min"),
    "rh": ("verification_reminder_hours", [1, 3, 6, 12], "h"),
    "kh": ("verification_kick_after_reminder_hours", [3, 6, 12, 24], "h"),
}

# Textos libres capturables: code → columna.
_EDIT_FIELDS = {"w": "welcome_text", "r": "rules_text"}

# Autoborrado de la bienvenida, en segundos (0 = no se borra nunca).
_WELCOME_TTL_PRESETS = [0, 300, 900, 3600]

# Warns: presets del límite y acciones válidas (las mismas que acepta /warnaction).
_WARN_LIMITS = [1, 3, 5, 10]
_WARN_ACTIONS = ("ban", "kick", "mute")

# --- Palabras bloqueadas (términos propios de las listas negras) ---
#
# Todo lo que viaja en un `callback_data` tiene 64 BYTES de tope, y aquí los datos
# los escribe un humano: un término largo, con acentos o con emojis se pasa de
# largo él solo. Así que el término NUNCA va dentro del callback:
#   - la lista se identifica por su ÍNDICE en `custom_terms.MANAGEABLE_LISTS`;
#   - el término, por un hash corto que se resuelve al recibirlo (`_term_by_hash`).
# El porqué del hash y no de un índice está en `_term_hash`.
_TERM_HASH_LEN = 8

# Cuántas coincidencias en la vista previa se consideran ya un aviso a gritos. Con
# 1 o 2 puede ser spam repetido; a partir de 3, lo normal es que el término esté
# cazando conversación del grupo.
_PREVIEW_LOUD = 3
# Los ejemplos son mensajes de gente real: se enseña lo justo para reconocerlos.
_PREVIEW_SNIPPET = 80

# Códigos de `custom_terms.TermResult` → clave i18n que explica QUÉ pasa. Sin este
# mapa el admin vería «corto» y tendría que adivinar el mínimo.
_TERM_ERR_KEYS = {
    custom_terms.ERR_UNKNOWN_LIST: "cfg.ct.err.lista",
    custom_terms.ERR_EMPTY: "cfg.ct.err.vacio",
    custom_terms.ERR_TOO_SHORT: "cfg.ct.err.corto",
    custom_terms.ERR_TOO_LONG: "cfg.ct.err.largo",
    custom_terms.ERR_NO_TEXT: "cfg.ct.err.sin_texto",
    custom_terms.ERR_SYMBOL_EDGES: "cfg.ct.err.bordes",
    custom_terms.ERR_DUPLICATE: "cfg.ct.err.duplicado",
    custom_terms.ERR_ALREADY_COVERED: "cfg.ct.err.ya_cubierto",
    custom_terms.ERR_LIST_FULL: "cfg.ct.err.llena",
    custom_terms.ERR_NOT_FOUND: "cfg.ct.err.no_encontrado",
    custom_terms.ERR_IO: "cfg.ct.err.escritura",
}

# Un botón de bienvenida con URL inválida hace que Telegram RECHACE el mensaje
# entero: el grupo se queda sin bienvenida y en los logs solo aparece un BadRequest
# que nadie relaciona con el botón. Por eso se valida ANTES de guardar, y solo se
# admite lo que Telegram acepta con seguridad en un botón URL: http/https (y los
# enlaces t.me, que son https). Cualquier otro esquema (tg://, javascript:, mailto:,
# ftp:) se rechaza con un mensaje claro en vez de guardarse.
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]+(:\d+)?$")
_MAX_BTN_TEXT = 64
_MAX_BTN_URL = 512


def validate_button_url(raw: str) -> tuple[str | None, str | None]:
    """Valida (y normaliza) la URL de un botón de bienvenida.

    Devuelve `(url, None)` si es válida o `(None, clave_de_error)` si no. A lo que
    viene sin esquema (`t.me/normas`, `ejemplo.com/reglas`) se le antepone
    `https://`; lo que trae un esquema distinto de http/https se rechaza.
    """
    url = (raw or "").strip()
    if not url:
        return None, "cfg.wb.err_empty"
    if len(url) > _MAX_BTN_URL:
        return None, "cfg.wb.err_long"
    if any(ch.isspace() for ch in url):
        return None, "cfg.wb.err_space"
    if not url.lower().startswith(("http://", "https://")):
        if _SCHEME_RE.match(url):
            return None, "cfg.wb.err_scheme"
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.rsplit("@", 1)[-1]      # descarta el userinfo si lo hubiera
    if not host or not _HOST_RE.match(host) or "." not in host.split(":", 1)[0]:
        return None, "cfg.wb.err_host"
    return url, None


def parse_button_spec(raw: str) -> tuple[str | None, str | None, bool, str | None]:
    """Parsea `Texto | https://url [same]` → (texto, url, misma_fila, error)."""
    spec = (raw or "").strip()
    same = False
    if spec.lower().endswith(" same"):
        same, spec = True, spec[:-5].rstrip()
    if "|" not in spec:
        return None, None, False, "cfg.wb.err_pipe"
    text, url_raw = (p.strip() for p in spec.split("|", 1))
    if not text:
        return None, None, False, "cfg.wb.err_text"
    if len(text) > _MAX_BTN_TEXT:
        return None, None, False, "cfg.wb.err_text_long"
    url, err = validate_button_url(url_raw)
    if err:
        return None, None, False, err
    return text, url, same, None

def _header(title: str) -> str:
    return t("cfg.header", title=title)


def _b(s, field: str) -> bool:
    """Lee un booleano de un Row/dict de settings tolerando NULL."""
    try:
        return bool(s[field])
    except (KeyError, IndexError, TypeError):
        return False


def _num(s, field: str, default: int) -> int:
    try:
        v = s[field]
        return int(v) if v is not None else default
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def _onoff(v: bool) -> str:
    return t("on") if v else t("off")


def _quips_state(db: DB, cfg, chat_id: int) -> bool:
    """Estado REAL de los quips en un chat (lo que verá el grupo).

    NO se lee la columna con `_b()` a propósito: `quips_enabled` es NULL mientras
    nadie la haya tocado en ese chat, y ese NULL significa «hereda
    PUBLIC_QUIP_ENABLED del .env», no «apagado». Con `_b()` el panel enseñaría OFF a
    quien tiene los quips funcionando desde siempre por el .env, y el admin tocaría
    el botón creyendo activarlos cuando en realidad los estaría apagando.
    """
    return quips.quips_on(db, chat_id, cfg)


def _quips_inherited(s) -> bool:
    """True si el chat no ha decidido nada y va con lo que diga el .env."""
    try:
        return s["quips_enabled"] is None
    except (KeyError, IndexError, TypeError):
        return True


def _chat_title(db: DB, chat_id: int) -> str:
    row = next((c for c in db.all_chats() if c["chat_id"] == chat_id), None)
    return (row["title"] if row and row["title"] else str(chat_id))


def _panel_title(db: DB, chat_id: int) -> str:
    """Título del panel: unificado si la sincronización está ON, si no el del grupo."""
    if settings_sync.is_sync_on(db):
        return t("cfg.title_all")
    return _chat_title(db, chat_id)


# --------------------------- construcción de teclados ---------------------------

def build_panel_keyboard(
    chat_id: int, s, sync_on: bool = False, quips_state: bool | None = None,
) -> InlineKeyboardMarkup:
    """Teclado principal del panel. El estado va en la etiqueta (un tap lo invierte).

    `quips_state` viene ya resuelto por quien llama (`_quips_state`, que consulta el
    .env cuando la columna es NULL). Sin él solo queda mirar la columna a pelo, que
    para `quips_enabled` da OFF a quien los hereda activados: por eso el panel real
    siempre lo pasa y el defecto None es solo un respaldo para llamadas sin `cfg`.
    """
    cid = chat_id
    quips_on = _b(s, "quips_enabled") if quips_state is None else quips_state
    sk = _num(s, "verification_suspicious_kick_minutes", 30)
    rh = _num(s, "verification_reminder_hours", 3)
    kh = _num(s, "verification_kick_after_reminder_hours", 6)
    accion = t("cfg.kick") if _b(s, "verification_kick_normal") else t("cfg.mute")
    rows = [
        [InlineKeyboardButton(t("cfg.b.sync", state=_onoff(sync_on)),
                              callback_data=f"{PREFIX}:sync:{cid}")],
        [InlineKeyboardButton(t("cfg.b.verif", state=_onoff(_b(s, "verification_enabled"))),
                              callback_data=f"{PREFIX}:tog:verification_enabled:{cid}")],
        [InlineKeyboardButton(t("cfg.b.review", state=_onoff(_b(s, "verification_review_suspicious"))),
                              callback_data=f"{PREFIX}:tog:verification_review_suspicious:{cid}")],
        [InlineKeyboardButton(t("cfg.b.reminders", state=_onoff(_b(s, "verification_reminders_enabled"))),
                              callback_data=f"{PREFIX}:tog:verification_reminders_enabled:{cid}")],
        [InlineKeyboardButton(t("cfg.b.action", action=accion),
                              callback_data=f"{PREFIX}:accion:{cid}")],
        [InlineKeyboardButton(t("cfg.b.times", sk=sk, rh=rh, kh=kh),
                              callback_data=f"{PREFIX}:times:{cid}")],
        # La bienvenida entera (interruptor, texto, botones y autoborrado) vive en su
        # submenú: son cuatro ajustes y el panel principal ya iba justo de filas.
        [InlineKeyboardButton(t("cfg.b.welcome_menu", state=_onoff(_b(s, "welcome_enabled"))),
                              callback_data=f"{PREFIX}:wsub:{cid}")],
        [InlineKeyboardButton(t("cfg.b.edit_rules"),
                              callback_data=f"{PREFIX}:edit:r:{cid}")],
        [InlineKeyboardButton(t("cfg.b.cleanservice", state=_onoff(_b(s, "cleanservice"))),
                              callback_data=f"{PREFIX}:tog:cleanservice:{cid}")],
        [InlineKeyboardButton(t("cfg.b.warns"), callback_data=f"{PREFIX}:warns:{cid}"),
         InlineKeyboardButton(t("cfg.b.topweekly", state=_onoff(_b(s, "topweekly_enabled"))),
                              callback_data=f"{PREFIX}:tog:topweekly_enabled:{cid}")],
        [InlineKeyboardButton(t("cfg.b.quips", state=_onoff(quips_on)),
                              callback_data=f"{PREFIX}:quips:{cid}")],
        # Comparten fila: las dos son submenús sin estado que enseñar en la etiqueta.
        [InlineKeyboardButton(t("cfg.b.terms"), callback_data=f"{PREFIX}:ct:{cid}"),
         InlineKeyboardButton(t("cfg.b.alerts"), callback_data=f"{PREFIX}:alertas:{cid}")],
        [InlineKeyboardButton(t("cfg.b.close"), callback_data=f"{PREFIX}:close:{cid}")],
    ]
    return InlineKeyboardMarkup(rows)


def build_times_keyboard(chat_id: int, s) -> InlineKeyboardMarkup:
    """Submenú de tiempos: presets por fila, el actual marcado con ✅."""
    cid = chat_id
    rows = []
    for code, (field, presets, unit) in _TIME_FIELDS.items():
        cur = _num(s, field, presets[1])
        row = []
        for val in presets:
            mark = "✅ " if val == cur else ""
            label = f"{mark}{'+' if code == 'kh' else ''}{val}{unit}"
            row.append(InlineKeyboardButton(label, callback_data=f"{PREFIX}:st:{code}:{val}:{cid}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:open:{cid}")])
    return InlineKeyboardMarkup(rows)


def _ttl_label(secs: int) -> str:
    """Etiqueta legible del autoborrado: nunca / N min / N h."""
    if secs <= 0:
        return t("cfg.wd.never")
    if secs < 3600:
        return t("cfg.wd.min", n=secs // 60)
    return t("cfg.wd.hour", n=secs // 3600)


def build_welcome_keyboard(chat_id: int, s, n_buttons: int) -> InlineKeyboardMarkup:
    """Submenú de la bienvenida: interruptor, texto, botones y autoborrado.

    El interruptor reutiliza el callback `tog` de siempre con un sufijo de vista, para
    que al pulsarlo se vuelva a pintar ESTE submenú y no el panel principal.
    """
    cid = chat_id
    ttl = _num(s, "welcome_delete_after_s", 900)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("cfg.b.welcome", state=_onoff(_b(s, "welcome_enabled"))),
                              callback_data=f"{PREFIX}:tog:welcome_enabled:{cid}:w")],
        [InlineKeyboardButton(t("cfg.b.edit_welcome"), callback_data=f"{PREFIX}:edit:w:{cid}")],
        [InlineKeyboardButton(t("cfg.b.welcome_buttons", n=n_buttons),
                              callback_data=f"{PREFIX}:wbtn:{cid}")],
        [InlineKeyboardButton(t("cfg.b.welcome_ttl", value=_ttl_label(ttl)),
                              callback_data=f"{PREFIX}:wdel:{cid}")],
        [InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:open:{cid}")],
    ])


def build_welcome_ttl_keyboard(chat_id: int, s) -> InlineKeyboardMarkup:
    """Presets del autoborrado de la bienvenida (el actual marcado con ✅)."""
    cid = chat_id
    cur = _num(s, "welcome_delete_after_s", 900)
    row = [
        InlineKeyboardButton(("✅ " if v == cur else "") + _ttl_label(v),
                             callback_data=f"{PREFIX}:wdset:{v}:{cid}")
        for v in _WELCOME_TTL_PRESETS
    ]
    return InlineKeyboardMarkup([
        row,
        [InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:wsub:{cid}")],
    ])


def build_welcome_buttons_keyboard(chat_id: int, buttons) -> InlineKeyboardMarkup:
    """Lista de botones de la bienvenida: uno por fila para poder quitarlo, más añadir."""
    cid = chat_id
    rows = [
        [InlineKeyboardButton(t("cfg.b.wb_remove", text=b["text"][:30]),
                              callback_data=f"{PREFIX}:wbdel:{b['id']}:{cid}")]
        for b in buttons
    ]
    rows.append([InlineKeyboardButton(t("cfg.b.wb_add"), callback_data=f"{PREFIX}:wbadd:{cid}")])
    if buttons:
        rows.append([InlineKeyboardButton(t("cfg.b.wb_clear"),
                                          callback_data=f"{PREFIX}:wbclr:{cid}")])
    rows.append([InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:wsub:{cid}")])
    return InlineKeyboardMarkup(rows)


def _warn_action(s) -> str:
    try:
        return (s["warns_action"] or "ban").lower()
    except (KeyError, IndexError, TypeError):
        return "ban"


def build_warns_keyboard(chat_id: int, s) -> InlineKeyboardMarkup:
    """Submenú de warns: fila de límites y fila de acción al alcanzarlo."""
    cid = chat_id
    limit = _num(s, "warns_limit", 3)
    action = _warn_action(s)
    limits = [
        InlineKeyboardButton(("✅ " if v == limit else "") + str(v),
                             callback_data=f"{PREFIX}:wlim:{v}:{cid}")
        for v in _WARN_LIMITS
    ]
    actions = [
        InlineKeyboardButton(("✅ " if a == action else "") + t(f"cfg.warns.{a}"),
                             callback_data=f"{PREFIX}:wact:{a}:{cid}")
        for a in _WARN_ACTIONS
    ]
    return InlineKeyboardMarkup([
        limits, actions,
        [InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:open:{cid}")],
    ])


def build_quips_keyboard(chat_id: int, state_on: bool) -> InlineKeyboardMarkup:
    """Vista de frases al banear: activar / desactivar (✅ = estado actual) y volver."""
    cid = chat_id
    on = ("✅ " if state_on else "") + t("quipcfg.b.on")
    off = ("✅ " if not state_on else "") + t("quipcfg.b.off")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(on, callback_data=f"{PREFIX}:qset:1:{cid}"),
         InlineKeyboardButton(off, callback_data=f"{PREFIX}:qset:0:{cid}")],
        [InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:open:{cid}")],
    ])


def _quips_text(state_on: bool, inherited: bool) -> str:
    """Texto de la vista de quips: estado (propio o heredado) + ejemplo real."""
    estado_key = "quipcfg.state_inherited" if inherited else "quipcfg.state_own"
    estado = t(estado_key, state=_onoff(state_on))
    muestras = quips.demo_samples(1)
    ejemplo = muestras[0][1] if muestras else t("quipcfg.no_example")
    return t("quipcfg.text", state=estado, example=ejemplo)


# --------------------- palabras bloqueadas (términos propios) ---------------------

def _list_code(filename: str) -> int | None:
    """Índice de una lista gestionable, que es lo que viaja en el callback."""
    try:
        return custom_terms.MANAGEABLE_LISTS.index(filename)
    except ValueError:
        return None


def _list_by_code(raw: str) -> str | None:
    """Resuelve el índice recibido en un callback. None si no es una lista válida.

    Es la ÚNICA puerta por la que un nombre de archivo entra desde Telegram: al ser
    un índice sobre una tupla cerrada, no hay forma de colar una ruta arbitraria.
    """
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None
    if not 0 <= idx < len(custom_terms.MANAGEABLE_LISTS):
        return None
    return custom_terms.MANAGEABLE_LISTS[idx]


def _term_hash(term: str) -> str:
    """Identificador corto y estable de un término, para el botón de quitar.

    Se usa un hash y NO la posición en la lista porque los botones ya enviados
    sobreviven a los cambios: si el admin quita el primer término y luego pulsa un
    botón de un mensaje anterior, un índice apuntaría al término equivocado y
    borraría el que no era. El hash o encuentra su término o no encuentra ninguno.
    Se calcula sobre el término normalizado y en minúsculas, igual que compara
    `custom_terms.remove_term`.
    """
    clean = custom_terms.normalize(term).casefold()
    # No es un hash de seguridad: solo un identificador corto para el botón.
    return hashlib.sha1(
        clean.encode("utf-8"), usedforsecurity=False,
    ).hexdigest()[:_TERM_HASH_LEN]


def _term_by_hash(filename: str, h: str) -> str | None:
    """Término de esa lista cuyo hash corto coincide. None si ya no está."""
    return next((tm for tm in custom_terms.list_terms(filename) if _term_hash(tm) == h), None)


def _list_label(filename: str) -> str:
    """Nombre legible de una lista negra ('commercial_work.txt' → 'Ofertas de trabajo')."""
    return t(f"cfg.ct.name.{filename.removesuffix('.txt')}")


def _term_error_text(res: custom_terms.TermResult) -> str:
    """Explica POR QUÉ se rechaza un término, con el número concreto cuando aplica."""
    if res.code == custom_terms.ERR_TOO_SHORT:
        return t("cfg.ct.err.corto", n=custom_terms.MIN_TERM_LEN)
    if res.code == custom_terms.ERR_TOO_LONG:
        return t("cfg.ct.err.largo", n=custom_terms.MAX_TERM_LEN)
    if res.code == custom_terms.ERR_LIST_FULL:
        return t("cfg.ct.err.llena", n=custom_terms.MAX_TERMS_PER_LIST)
    return t(_TERM_ERR_KEYS.get(res.code, "cfg.ct.err.generico"))


def build_term_lists_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Listas negras gestionables, con cuántos términos propios tiene cada una."""
    rows = [
        [InlineKeyboardButton(
            t("cfg.ct.b.list", name=_list_label(fn), n=custom_terms.count_terms(fn)),
            callback_data=f"{PREFIX}:ctl:{i}:{chat_id}")]
        for i, fn in enumerate(custom_terms.MANAGEABLE_LISTS)
    ]
    rows.append([InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:open:{chat_id}")])
    return InlineKeyboardMarkup(rows)


def build_terms_keyboard(chat_id: int, filename: str, terms: list[str]) -> InlineKeyboardMarkup:
    """Términos de una lista: uno por fila para poder quitarlo, más el de añadir."""
    code = _list_code(filename)
    rows = [
        [InlineKeyboardButton(t("cfg.ct.b.remove", term=tm[:30]),
                              callback_data=f"{PREFIX}:ctdel:{code}:{_term_hash(tm)}:{chat_id}")]
        for tm in terms
    ]
    rows.append([InlineKeyboardButton(t("cfg.ct.b.add"),
                                      callback_data=f"{PREFIX}:ctadd:{code}:{chat_id}")])
    rows.append([InlineKeyboardButton(t("cfg.b.back"), callback_data=f"{PREFIX}:ct:{chat_id}")])
    return InlineKeyboardMarkup(rows)


def build_term_confirm_keyboard(chat_id: int, filename: str, risky: bool) -> InlineKeyboardMarkup:
    """Confirmación del alta. El botón cambia de cara si la vista previa pinta mal.

    Que un término que arrasa con el grupo se añada con un botón que pone «Añadir»
    a secas es justo el descuido que hay que evitar: se etiqueta como lo que es.
    """
    code = _list_code(filename)
    etiqueta = t("cfg.ct.b.add_anyway") if risky else t("cfg.ct.b.add_ok")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(etiqueta, callback_data=f"{PREFIX}:ctok:{code}:{chat_id}")],
        [InlineKeyboardButton(t("cfg.b.cancel"), callback_data=f"{PREFIX}:ctl:{code}:{chat_id}")],
    ])


def build_term_del_keyboard(chat_id: int, filename: str, term: str) -> InlineKeyboardMarkup:
    """Confirmación de la baja (el término se resuelve por hash, no viaja aquí)."""
    code = _list_code(filename)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("cfg.ct.b.del_ok"),
                              callback_data=f"{PREFIX}:ctdelok:{code}:{_term_hash(term)}:{chat_id}")],
        [InlineKeyboardButton(t("cfg.b.cancel"), callback_data=f"{PREFIX}:ctl:{code}:{chat_id}")],
    ])


def _preview_text(filename: str, pv: custom_terms.PreviewResult) -> str:
    """Mensaje de la vista previa: veredicto graduado + ejemplos reales recortados.

    El orden es deliberado: primero lo que el admin tiene que decidir (esto cazaría
    a X personas), y solo después los ejemplos. Si los ejemplos fueran antes, el
    aviso quedaría empujado fuera de la primera pantalla del móvil.
    """
    cabecera = t("cfg.ct.pv.head",
                 term=html.escape(pv.term), list=html.escape(_list_label(filename)))
    if pv.ham_hits:
        veredicto = t("cfg.ct.pv.ham", n=pv.ham_hits, matches=pv.matches, scanned=pv.scanned)
    elif pv.matches >= _PREVIEW_LOUD:
        veredicto = t("cfg.ct.pv.loud", matches=pv.matches, scanned=pv.scanned)
    elif pv.matches:
        veredicto = t("cfg.ct.pv.some", matches=pv.matches, scanned=pv.scanned)
    else:
        veredicto = t("cfg.ct.pv.clean", scanned=pv.scanned)
    bloques = [cabecera, veredicto]
    if pv.examples:
        ejemplos = [t("cfg.ct.pv.examples")]
        ejemplos += [t("cfg.ct.pv.example", text=html.escape(_cut(ex))) for ex in pv.examples]
        bloques.append("\n".join(ejemplos))
    return "\n\n".join(bloques)


def _cut(text: str, width: int = _PREVIEW_SNIPPET) -> str:
    """Recorta un mensaje ajeno a lo justo para reconocerlo."""
    one = " ".join(str(text or "").split())
    return one if len(one) <= width else f"{one[:width - 1]}…"


async def _show_term_lists(msg_edit, chat_id: int) -> None:
    """Renderiza la pantalla con las listas negras gestionables."""
    total = sum(custom_terms.count_terms(fn) for fn in custom_terms.MANAGEABLE_LISTS)
    try:
        await msg_edit(t("cfg.ct.lists_text", n=total), parse_mode="HTML",
                       reply_markup=build_term_lists_keyboard(chat_id))
    except TelegramError as exc:
        log.debug("no se pudo renderizar la lista de palabras bloqueadas: %s", exc)


async def _show_terms(msg_edit, chat_id: int, filename: str) -> None:
    """Renderiza los términos propios de una lista concreta."""
    terms = custom_terms.list_terms(filename)
    nombre = html.escape(_list_label(filename))
    if terms:
        lineas = [t("cfg.ct.list_text", name=nombre, n=len(terms),
                    max=custom_terms.MAX_TERMS_PER_LIST)]
        lineas += [t("cfg.ct.item", term=html.escape(tm)) for tm in terms]
        txt = "\n".join(lineas)
    else:
        txt = t("cfg.ct.list_empty", name=nombre)
    try:
        await msg_edit(txt, parse_mode="HTML", disable_web_page_preview=True,
                       reply_markup=build_terms_keyboard(chat_id, filename, terms))
    except TelegramError as exc:
        log.debug("no se pudo renderizar los términos de %s: %s", filename, exc)


def _edit_scope_keyboard(db: DB, code: str, cid: int) -> InlineKeyboardMarkup:
    """Selector de a qué grupo(s) aplicar la edición de texto: Todos o uno concreto."""
    rows = [[InlineKeyboardButton(t("cfg.b.all_groups"),
                                  callback_data=f"{PREFIX}:escope:{code}:all:{cid}")]]
    for c in db.all_chats():
        if not c["am_admin"]:
            continue
        title = (c["title"] or str(c["chat_id"]))[:40]
        rows.append([InlineKeyboardButton(
            f"📝 {title}", callback_data=f"{PREFIX}:escope:{code}:{c['chat_id']}:{cid}")])
    rows.append([InlineKeyboardButton(t("cfg.b.cancel"), callback_data=f"{PREFIX}:open:{cid}")])
    return InlineKeyboardMarkup(rows)


def _scope_label(db: DB, ids: list[int]) -> str:
    """Texto para la confirmación: 'en N grupos' o 'en <grupo>'."""
    if len(ids) > 1:
        return t("cfg.scope_n", n=len(ids))
    if len(ids) == 1:
        return t("cfg.scope_one", title=html.escape(_chat_title(db, ids[0])))
    return ""


def _times_text(db: DB, cid: int, s) -> str:
    return t("cfg.times_text",
             title=html.escape(_chat_title(db, cid)),
             sk=_num(s, "verification_suspicious_kick_minutes", 30),
             rh=_num(s, "verification_reminder_hours", 3),
             kh=_num(s, "verification_kick_after_reminder_hours", 6))


# ------------------------------- render helpers -------------------------------

async def _show_panel(msg_edit, db: DB, chat_id: int, cfg=None) -> None:
    """Renderiza (editando el mensaje) el panel principal de un chat."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    sync_on = settings_sync.is_sync_on(db)
    title = html.escape(_panel_title(db, chat_id))
    try:
        await msg_edit(
            _header(title),
            parse_mode="HTML",
            reply_markup=build_panel_keyboard(
                chat_id, s, sync_on,
                _quips_state(db, cfg, chat_id) if cfg is not None else None),
        )
    except TelegramError as exc:
        log.debug("no se pudo renderizar panel: %s", exc)


def _welcome_buttons(db: DB, chat_id: int):
    """Botones de la bienvenida de un chat, migrando antes el botón único antiguo."""
    db.migrate_legacy_welcome_button(chat_id)
    return db.list_welcome_buttons(chat_id)


async def _show_welcome(msg_edit, db: DB, chat_id: int) -> None:
    """Renderiza el submenú de la bienvenida."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    buttons = _welcome_buttons(db, chat_id)
    txt = t("cfg.welcome_text",
            title=html.escape(_panel_title(db, chat_id)),
            state=_onoff(_b(s, "welcome_enabled")),
            n=len(buttons),
            ttl=_ttl_label(_num(s, "welcome_delete_after_s", 900)))
    try:
        await msg_edit(txt, parse_mode="HTML",
                       reply_markup=build_welcome_keyboard(chat_id, s, len(buttons)))
    except TelegramError as exc:
        log.debug("no se pudo renderizar el submenú de bienvenida: %s", exc)


async def _show_welcome_buttons(msg_edit, db: DB, chat_id: int) -> None:
    """Renderiza la lista de botones de la bienvenida."""
    buttons = _welcome_buttons(db, chat_id)
    if buttons:
        lineas = [t("cfg.wb.list_header")]
        lineas += [
            t("cfg.wb.item", text=html.escape(b["text"]), url=html.escape(b["url"]))
            for b in buttons
        ]
        txt = "\n".join(lineas)
    else:
        txt = t("cfg.wb.empty")
    try:
        await msg_edit(txt, parse_mode="HTML", disable_web_page_preview=True,
                       reply_markup=build_welcome_buttons_keyboard(chat_id, buttons))
    except TelegramError as exc:
        log.debug("no se pudo renderizar la lista de botones: %s", exc)


async def _show_warns(msg_edit, db: DB, chat_id: int) -> None:
    """Renderiza el submenú de warns."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    accion = _warn_action(s)
    txt = t("cfg.warns_text",
            title=html.escape(_panel_title(db, chat_id)),
            limit=_num(s, "warns_limit", 3),
            action=t(f"cfg.warns.{accion}") if accion in _WARN_ACTIONS else accion)
    try:
        await msg_edit(txt, parse_mode="HTML", reply_markup=build_warns_keyboard(chat_id, s))
    except TelegramError as exc:
        log.debug("no se pudo renderizar el submenú de warns: %s", exc)


async def _show_quips(msg_edit, db: DB, cfg, chat_id: int) -> None:
    """Renderiza la vista de previsualización de quips de un chat."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    estado = _quips_state(db, cfg, chat_id)
    try:
        await msg_edit(
            _quips_text(estado, _quips_inherited(s)),
            parse_mode="HTML",
            reply_markup=build_quips_keyboard(chat_id, estado),
        )
    except TelegramError as exc:
        log.debug("no se pudo renderizar la vista de quips: %s", exc)


# --------------------------------- comando ---------------------------------

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/config — abre el panel de ajustes por botones (solo admin)."""
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    chat = update.effective_chat
    msg = update.effective_message
    admin_chats = [c for c in db.all_chats() if c["am_admin"]]

    # SINCRONIZACIÓN ON (por defecto): panel unificado, sin selector de grupo. Los
    # cambios se aplican a todos. Representativo = grupo actual o el primero moderado.
    if settings_sync.is_sync_on(db):
        if chat and chat.type in ("group", "supergroup"):
            cid = chat.id
        elif admin_chats:
            cid = admin_chats[0]["chat_id"]
        else:
            await msg.reply_text(t("cfg.no_admin"))
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        await msg.reply_text(
            _header(html.escape(_panel_title(db, cid))),
            parse_mode="HTML",
            reply_markup=build_panel_keyboard(cid, s, True, _quips_state(db, cfg, cid)),
        )
        return

    # SINCRONIZACIÓN OFF: configuración por grupo (grupo actual o selector en DM).
    if chat and chat.type in ("group", "supergroup"):
        db.ensure_chat_settings(chat.id)
        s = db.get_chat_settings(chat.id)
        await msg.reply_text(
            _header(html.escape(_chat_title(db, chat.id))),
            parse_mode="HTML",
            reply_markup=build_panel_keyboard(chat.id, s, False, _quips_state(db, cfg, chat.id)),
        )
        return
    if not admin_chats:
        await msg.reply_text(t("cfg.no_admin"))
        return
    if len(admin_chats) == 1:
        cid = admin_chats[0]["chat_id"]
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        await msg.reply_text(
            _header(html.escape(_chat_title(db, cid))),
            parse_mode="HTML",
            reply_markup=build_panel_keyboard(cid, s, False, _quips_state(db, cfg, cid)),
        )
        return
    rows = [
        [InlineKeyboardButton((c["title"] or str(c["chat_id"]))[:60],
                              callback_data=f"{PREFIX}:open:{c['chat_id']}")]
        for c in admin_chats
    ]
    await msg.reply_text(
        t("cfg.pick_group"),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
    )


# --------------------------------- callbacks ---------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa todos los botones del panel (prefijo cfg:)."""
    q = update.callback_query
    if not q or not q.data or not q.data.startswith(f"{PREFIX}:"):
        return
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    if q.from_user.id != cfg.admin_user_id:
        await q.answer(t("cfg.only_admin"), show_alert=True)
        return
    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    def _cid(idx: int) -> int | None:
        try:
            return int(parts[idx])
        except (IndexError, ValueError):
            return None

    if action == "open":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        await _show_panel(q.edit_message_text, db, cid, cfg)
        return

    if action == "close":
        context.user_data.pop("cfg_await", None)
        await q.answer(t("cfg.closed_toast"))
        try:
            await q.edit_message_text(t("cfg.closed_msg"))
        except TelegramError:
            pass
        return

    if action == "tog":
        field = parts[2] if len(parts) > 2 else ""
        cid = _cid(3)
        # 5º campo OPCIONAL: la vista desde la que se pulsó. Sin él (los botones ya
        # enviados a los chats) se repinta el panel principal, como siempre.
        view = parts[4] if len(parts) > 4 else ""
        if field not in _TOGGLE_FIELDS or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        new_val = 0 if _b(s, field) else 1
        n = settings_sync.apply_setting(db, cid, field, new_val)
        estado = t("cfg.act_on") if new_val else t("cfg.act_off")
        await q.answer(estado + t("cfg.in_n", n=n) if n > 1 else estado)
        if view == "w":
            await _show_welcome(q.edit_message_text, db, cid)
            return
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_reply_markup(
                reply_markup=build_panel_keyboard(cid, s, settings_sync.is_sync_on(db),
                                                 _quips_state(db, cfg, cid)))
        except TelegramError:
            pass
        return

    if action == "accion":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        new_val = 0 if _b(s, "verification_kick_normal") else 1
        n = settings_sync.apply_setting(db, cid, "verification_kick_normal", new_val)
        base = t("cfg.kick") if new_val else t("cfg.mute")
        await q.answer(base + t("cfg.dot_n", n=n) if n > 1 else base)
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_reply_markup(
                reply_markup=build_panel_keyboard(cid, s, settings_sync.is_sync_on(db),
                                                 _quips_state(db, cfg, cid)))
        except TelegramError:
            pass
        return

    if action == "quips":
        # Solo ABRE la previsualización: el ajuste no se toca hasta que el admin
        # pulse activar/desactivar viendo un ejemplo de lo que publicaría el bot.
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        await _show_quips(q.edit_message_text, db, cfg, cid)
        return

    if action == "qset":
        cid = _cid(3)
        val = parts[2] if len(parts) > 2 else ""
        if cid is None or val not in ("0", "1"):
            await q.answer(t("cfg.invalid_opt"))
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, "quips_enabled", int(val))
        estado = t("cfg.act_on") if val == "1" else t("cfg.act_off")
        await q.answer(estado + t("cfg.in_n", n=n) if n > 1 else estado)
        await _show_quips(q.edit_message_text, db, cfg, cid)
        return

    if action == "sync":
        cid = _cid(2)
        new = not settings_sync.is_sync_on(db)
        settings_sync.set_sync(db, new)
        await q.answer(t("cfg.sync_on") if new else t("cfg.sync_off"))
        if new:
            rep = cid if cid is not None else (settings_sync.moderated_chat_ids(db) or [None])[0]
            if rep is not None:
                await _show_panel(q.edit_message_text, db, rep, cfg)
        else:
            try:
                await q.edit_message_text(t("cfg.sync_off_msg"), parse_mode="HTML")
            except TelegramError:
                pass
        return

    if action == "times":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        txt = _times_text(db, cid, s)
        try:
            await q.edit_message_text(txt, parse_mode="HTML",
                                      reply_markup=build_times_keyboard(cid, s))
        except TelegramError:
            pass
        return

    if action == "st":
        code = parts[2] if len(parts) > 2 else ""
        cid = _cid(4)
        if code not in _TIME_FIELDS or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        field, presets, unit = _TIME_FIELDS[code]
        try:
            val = int(parts[3])
        except (IndexError, ValueError):
            await q.answer(t("cfg.invalid_val"))
            return
        if val not in presets:
            await q.answer(t("cfg.val_range"))
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, field, val)
        await q.answer(f"✅ {val}{unit}" + (t("cfg.dot_n", n=n) if n > 1 else ""))
        s = db.get_chat_settings(cid)
        txt = _times_text(db, cid, s)
        try:
            await q.edit_message_text(txt, parse_mode="HTML",
                                      reply_markup=build_times_keyboard(cid, s))
        except TelegramError:
            pass
        return

    if action == "edit":
        # Paso 1: elegir a qué grupo(s) aplicar la edición (Todos o uno concreto).
        code = parts[2] if len(parts) > 2 else ""
        cid = _cid(3)
        if code not in _EDIT_FIELDS or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        await q.answer()
        que = t("cfg.which_welcome") if code == "w" else t("cfg.which_rules")
        try:
            await q.edit_message_text(
                t("cfg.edit_which", what=que),
                parse_mode="HTML", reply_markup=_edit_scope_keyboard(db, code, cid))
        except TelegramError:
            pass
        return

    if action == "escope":
        # Paso 2: scope elegido → pedir el texto con un ejemplo.
        code = parts[2] if len(parts) > 2 else ""
        scope = parts[3] if len(parts) > 3 else ""
        cid = _cid(4)
        if code not in _EDIT_FIELDS or cid is None or not scope:
            await q.answer(t("cfg.invalid_opt"))
            return
        await q.answer()
        context.user_data["cfg_await"] = {"field": _EDIT_FIELDS[code], "scope": scope}
        destino = t("cfg.dest_all") if scope == "all" else html.escape(
            _chat_title(db, int(scope)) if scope.lstrip("-").isdigit() else scope)
        prompt = t("cfg.prompt_welcome" if code == "w" else "cfg.prompt_rules", dest=destino)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t("cfg.b.cancel"),
                                    callback_data=f"{PREFIX}:open:{cid}")]])
        try:
            await q.edit_message_text(prompt, parse_mode="HTML", reply_markup=kb)
        except TelegramError:
            pass
        return

    if action == "wsub":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        await _show_welcome(q.edit_message_text, db, cid)
        return

    if action == "wdel":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_text(
                t("cfg.wd.text", title=html.escape(_panel_title(db, cid)),
                  value=_ttl_label(_num(s, "welcome_delete_after_s", 900))),
                parse_mode="HTML", reply_markup=build_welcome_ttl_keyboard(cid, s))
        except TelegramError:
            pass
        return

    if action == "wdset":
        cid = _cid(3)
        try:
            val = int(parts[2])
        except (IndexError, ValueError):
            await q.answer(t("cfg.invalid_val"))
            return
        if cid is None or val not in _WELCOME_TTL_PRESETS:
            await q.answer(t("cfg.invalid_opt"))
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, "welcome_delete_after_s", val)
        etiqueta = f"✅ {_ttl_label(val)}"
        await q.answer(etiqueta + (t("cfg.dot_n", n=n) if n > 1 else ""))
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_text(
                t("cfg.wd.text", title=html.escape(_panel_title(db, cid)),
                  value=_ttl_label(_num(s, "welcome_delete_after_s", 900))),
                parse_mode="HTML", reply_markup=build_welcome_ttl_keyboard(cid, s))
        except TelegramError:
            pass
        return

    if action == "wbtn":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        await _show_welcome_buttons(q.edit_message_text, db, cid)
        return

    if action == "wbadd":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        context.user_data["cfg_await"] = {"field": "welcome_button", "chat_id": cid}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            t("cfg.b.cancel"), callback_data=f"{PREFIX}:wbtn:{cid}")]])
        try:
            await q.edit_message_text(t("cfg.wb.prompt"), parse_mode="HTML", reply_markup=kb)
        except TelegramError:
            pass
        return

    if action == "wbdel":
        cid = _cid(3)
        try:
            bid = int(parts[2])
        except (IndexError, ValueError):
            await q.answer(t("cfg.invalid_val"))
            return
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        n = settings_sync.apply_welcome_button_delete(db, cid, bid)
        await q.answer(t("cfg.wb.removed") if n else t("cfg.wb.not_found"))
        await _show_welcome_buttons(q.edit_message_text, db, cid)
        return

    if action == "wbclr":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        n = settings_sync.apply_welcome_buttons_clear(db, cid)
        await q.answer(t("cfg.wb.cleared") + (t("cfg.dot_n", n=n) if n > 1 else ""))
        await _show_welcome_buttons(q.edit_message_text, db, cid)
        return

    if action == "warns":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        await _show_warns(q.edit_message_text, db, cid)
        return

    if action == "wlim":
        cid = _cid(3)
        try:
            val = int(parts[2])
        except (IndexError, ValueError):
            await q.answer(t("cfg.invalid_val"))
            return
        if cid is None or val not in _WARN_LIMITS:
            await q.answer(t("cfg.invalid_opt"))
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, "warns_limit", val)
        await q.answer(f"✅ {val}" + (t("cfg.dot_n", n=n) if n > 1 else ""))
        await _show_warns(q.edit_message_text, db, cid)
        return

    if action == "wact":
        accion_warn = parts[2] if len(parts) > 2 else ""
        cid = _cid(3)
        if cid is None or accion_warn not in _WARN_ACTIONS:
            await q.answer(t("cfg.invalid_opt"))
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, "warns_action", accion_warn)
        etiqueta = f"✅ {t('cfg.warns.' + accion_warn)}"
        await q.answer(etiqueta + (t("cfg.dot_n", n=n) if n > 1 else ""))
        await _show_warns(q.edit_message_text, db, cid)
        return

    if action == "ct":
        cid = _cid(2)
        if cid is None:
            await q.answer(t("cfg.invalid_chat"))
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        context.user_data.pop("cfg_term", None)
        await _show_term_lists(q.edit_message_text, cid)
        return

    if action == "ctl":
        filename = _list_by_code(parts[2] if len(parts) > 2 else "")
        cid = _cid(3)
        if filename is None or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        context.user_data.pop("cfg_term", None)
        await _show_terms(q.edit_message_text, cid, filename)
        return

    if action == "ctadd":
        filename = _list_by_code(parts[2] if len(parts) > 2 else "")
        cid = _cid(3)
        if filename is None or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        await q.answer()
        # Solo se pide el texto: lo que llegue pasará SIEMPRE por la vista previa
        # antes de tocar el archivo (ver `handle_capture`).
        context.user_data["cfg_term"] = {"list": filename, "chat_id": cid}
        context.user_data["cfg_await"] = {"field": "custom_term", "chat_id": cid}
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            t("cfg.b.cancel"), callback_data=f"{PREFIX}:ctl:{_list_code(filename)}:{cid}")]])
        try:
            await q.edit_message_text(
                t("cfg.ct.prompt", name=html.escape(_list_label(filename)),
                  min=custom_terms.MIN_TERM_LEN),
                parse_mode="HTML", reply_markup=kb)
        except TelegramError:
            pass
        return

    if action == "ctok":
        # Confirmación del alta. El término NO viaja en el callback (no cabe): se
        # recupera el que la vista previa dejó guardado, y si no está se rehace el
        # flujo desde el principio en vez de guardar algo a ciegas.
        filename = _list_by_code(parts[2] if len(parts) > 2 else "")
        cid = _cid(3)
        pending = context.user_data.get("cfg_term") or {}
        term = pending.get("term")
        if filename is None or cid is None:
            await q.answer(t("cfg.invalid_opt"))
            return
        if not term or pending.get("list") != filename:
            await q.answer(t("cfg.ct.expired"), show_alert=True)
            await _show_terms(q.edit_message_text, cid, filename)
            return
        context.user_data.pop("cfg_term", None)
        res = custom_terms.add_term(filename, term)
        if not res.ok:
            await q.answer(t("cfg.ct.not_added"), show_alert=True)
            try:
                await q.edit_message_text(_term_error_text(res), parse_mode="HTML")
            except TelegramError:
                pass
            return
        await q.answer(t("cfg.ct.added_toast"))
        await _show_terms(q.edit_message_text, cid, filename)
        return

    if action == "ctdel":
        filename = _list_by_code(parts[2] if len(parts) > 2 else "")
        h = parts[3] if len(parts) > 3 else ""
        cid = _cid(4)
        if filename is None or cid is None or not h:
            await q.answer(t("cfg.invalid_opt"))
            return
        term = _term_by_hash(filename, h)
        if term is None:
            await q.answer(t("cfg.ct.gone"))
            await _show_terms(q.edit_message_text, cid, filename)
            return
        await q.answer()
        try:
            await q.edit_message_text(
                t("cfg.ct.del_confirm", term=html.escape(term),
                  name=html.escape(_list_label(filename))),
                parse_mode="HTML",
                reply_markup=build_term_del_keyboard(cid, filename, term))
        except TelegramError:
            pass
        return

    if action == "ctdelok":
        filename = _list_by_code(parts[2] if len(parts) > 2 else "")
        h = parts[3] if len(parts) > 3 else ""
        cid = _cid(4)
        if filename is None or cid is None or not h:
            await q.answer(t("cfg.invalid_opt"))
            return
        term = _term_by_hash(filename, h)
        if term is None:
            await q.answer(t("cfg.ct.gone"))
        else:
            res = custom_terms.remove_term(filename, term)
            await q.answer(t("cfg.ct.removed") if res.ok else _term_error_text(res))
        await _show_terms(q.edit_message_text, cid, filename)
        return

    if action == "alertas":
        # Abre el panel de avisos como mensaje aparte (reutiliza /alertas), sin
        # perder el panel de config.
        from . import admin
        await q.answer()
        try:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text=t("cfg.alerts_short"),
                parse_mode="HTML",
                reply_markup=admin._alertas_keyboard(db, cfg),
            )
        except TelegramError:
            pass
        return

    await q.answer()


# ----------------------------- captura de texto -----------------------------

async def handle_capture(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Si hay una edición de texto pendiente (botón ✏️/📜), captura este mensaje.

    Devuelve True si lo consumió (el llamador debe hacer return), False si no.
    Se asume que el llamador ya verificó que es el admin en DM.
    """
    pending = context.user_data.get("cfg_await")
    if not pending:
        return False
    msg = update.effective_message
    raw = (msg.text or msg.caption or "").strip() if msg else ""
    if not raw:
        await msg.reply_text(t("cfg.empty_text"))
        context.user_data.pop("cfg_await", None)
        return True
    db: DB = context.bot_data["db"]
    field = pending["field"]
    scope = pending.get("scope")        # 'all' | chat_id (str) | None (legacy)
    chat_id = pending.get("chat_id")    # legacy (sin scope elegido)
    context.user_data.pop("cfg_await", None)  # un solo uso (aunque falle luego)
    if field == "welcome_button":
        # Se valida ANTES de tocar la BD: una URL que Telegram no acepte tumbaría el
        # mensaje de bienvenida entero del grupo (ver `validate_button_url`).
        text, url, same, err = parse_button_spec(raw)
        if chat_id is None:                       # sin grupo no hay dónde escribir
            await msg.reply_text(t("cfg.invalid_chat"))
            return True
        if err:
            await msg.reply_text(t(err), parse_mode="HTML", disable_web_page_preview=True)
            return True
        n = settings_sync.apply_welcome_button_add(db, chat_id, text, url, same_row=same)
        ids = settings_sync.target_ids(db, chat_id)
        await msg.reply_text(
            t("cfg.wb.added", text=html.escape(text), url=html.escape(url),
              scope=_scope_label(db, ids) if n > 1 else ""),
            parse_mode="HTML", disable_web_page_preview=True)
        return True
    if field == "custom_term":
        # Paso 2 del alta: NO se guarda nada todavía. Se valida, se enseña lo que
        # cazaría entre mensajes reales y se pide confirmar. Es la red de seguridad
        # del sistema: aquí es donde el admin ve que su «oferta» se llevaría por
        # delante media conversación del grupo.
        pending_term = context.user_data.get("cfg_term") or {}
        filename = pending_term.get("list")
        cid_term = chat_id if chat_id is not None else pending_term.get("chat_id")
        if not filename or not custom_terms.is_manageable(filename) or cid_term is None:
            context.user_data.pop("cfg_term", None)
            await msg.reply_text(t("cfg.ct.expired"))
            return True
        # La vista previa mira TODOS los grupos (chat_id=None) a propósito: las
        # listas negras son globales, así que un término añadido desde el panel de
        # un grupo actúa también en los demás.
        pv = custom_terms.preview_term(db, filename, raw)
        if not pv.valid.ok:
            context.user_data.pop("cfg_term", None)
            await msg.reply_text(_term_error_text(pv.valid), parse_mode="HTML",
                                 disable_web_page_preview=True)
            return True
        context.user_data["cfg_term"] = {
            "list": filename, "term": pv.term, "chat_id": cid_term,
        }
        await msg.reply_text(
            _preview_text(filename, pv), parse_mode="HTML", disable_web_page_preview=True,
            reply_markup=build_term_confirm_keyboard(cid_term, filename, pv.risky))
        return True
    if field == "welcome_text":
        from .chat_settings_cmd import _parse_rose_buttons
        clean, buttons = _parse_rose_buttons(raw)
        btns = buttons if buttons else None
        if scope is not None:
            ids = settings_sync.apply_welcome_scope(db, scope, clean, btns)
        else:
            settings_sync.apply_welcome(db, chat_id, clean, btns)
            ids = settings_sync.target_ids(db, chat_id)
        extra = t("cfg.btn_extra", n=len(buttons)) if buttons else ""
        await msg.reply_text(t("cfg.welcome_updated", extra=extra, scope=_scope_label(db, ids)))
    else:  # rules_text
        if scope is not None:
            ids = settings_sync.apply_setting_scope(db, scope, "rules_text", raw)
        else:
            settings_sync.apply_setting(db, chat_id, "rules_text", raw)
            ids = settings_sync.target_ids(db, chat_id)
        await msg.reply_text(t("cfg.rules_updated", scope=_scope_label(db, ids)))
    return True


# ------------------------------- comando /quips -------------------------------

def _rep_chat_id(db: DB, chat) -> int | None:
    """Chat representativo para consultar el estado: el actual si es grupo, si no el
    primer grupo moderado. None si el bot no es admin en ninguno."""
    if chat is not None and getattr(chat, "type", None) in ("group", "supergroup"):
        return chat.id
    ids = settings_sync.moderated_chat_ids(db)
    return ids[0] if ids else None


async def cmd_quips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/quips — enseña ejemplos del catálogo de frases. NO cambia ningún ajuste."""
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    muestras = quips.demo_samples(4)
    if not muestras:
        await update.effective_message.reply_text(t("quipcfg.no_example"))
        return
    partes = [t("quipcfg.cmd_title")]
    for rule, frase in muestras:
        etiqueta = rule_explain.explain(rule) or rule
        partes.append(t("quipcfg.cmd_item", rule=html.escape(etiqueta), quip=frase))
    cid = _rep_chat_id(db, update.effective_chat)
    if cid is not None:
        partes.append(t("quipcfg.cmd_footer", state=_onoff(_quips_state(db, cfg, cid))))
    await update.effective_message.reply_text(
        "\n\n".join(partes), parse_mode="HTML", disable_web_page_preview=True)


# ------------------------------- comando /sync -------------------------------

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/sync [on|off] — sincronizar (o no) los ajustes entre todos los grupos."""
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    user = update.effective_user
    if not user or user.id != cfg.admin_user_id:
        return
    args = context.args or []
    if args and args[0].lower() in ("on", "off"):
        settings_sync.set_sync(db, args[0].lower() == "on")
    state = settings_sync.is_sync_on(db)
    n = len(settings_sync.moderated_chat_ids(db))
    detalle = t("cfg.sync_detail_on", n=n) if state else t("cfg.sync_detail_off")
    await update.effective_message.reply_text(
        t("cfg.sync_status", state=("ON" if state else "OFF"), detail=detalle),
        parse_mode="HTML",
    )
