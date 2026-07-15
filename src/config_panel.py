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

import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from . import settings_sync
from .config import Config
from .db import DB

log = logging.getLogger(__name__)

PREFIX = "cfg"

# Toggles booleanos: code de callback corto → columna real en chat_settings.
_TOGGLE_FIELDS = {
    "verification_enabled",
    "verification_review_suspicious",
    "verification_reminders_enabled",
    "welcome_enabled",
    "cleanservice",
}

# Presets de tiempos (dentro de los rangos que valida /verificacion).
_TIME_FIELDS = {
    "sk": ("verification_suspicious_kick_minutes", [15, 30, 60, 120], "min"),
    "rh": ("verification_reminder_hours", [1, 3, 6, 12], "h"),
    "kh": ("verification_kick_after_reminder_hours", [3, 6, 12, 24], "h"),
}

# Textos libres capturables: code → columna.
_EDIT_FIELDS = {"w": "welcome_text", "r": "rules_text"}

_HEADER = (
    "⚙️ <b>Ajustes · {title}</b>\n"
    "Pulsa para cambiar. Los cambios se guardan al instante."
)


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
    return "✅ ON" if v else "❌ OFF"


def _chat_title(db: DB, chat_id: int) -> str:
    row = next((c for c in db.all_chats() if c["chat_id"] == chat_id), None)
    return (row["title"] if row and row["title"] else str(chat_id))


def _panel_title(db: DB, chat_id: int) -> str:
    """Título del panel: unificado si la sincronización está ON, si no el del grupo."""
    if settings_sync.is_sync_on(db):
        return "Todos los grupos (sincronizado)"
    return _chat_title(db, chat_id)


# --------------------------- construcción de teclados ---------------------------

def build_panel_keyboard(chat_id: int, s, sync_on: bool = False) -> InlineKeyboardMarkup:
    """Teclado principal del panel. El estado va en la etiqueta (un tap lo invierte)."""
    cid = chat_id
    sk = _num(s, "verification_suspicious_kick_minutes", 30)
    rh = _num(s, "verification_reminder_hours", 3)
    kh = _num(s, "verification_kick_after_reminder_hours", 6)
    accion = "Expulsar" if _b(s, "verification_kick_normal") else "Silenciar"
    rows = [
        [InlineKeyboardButton(
            f"🔗 Sincronizar todos los grupos: {_onoff(sync_on)}",
            callback_data=f"{PREFIX}:sync:{cid}")],
        [InlineKeyboardButton(f"🛡️ Verificación: {_onoff(_b(s, 'verification_enabled'))}",
                              callback_data=f"{PREFIX}:tog:verification_enabled:{cid}")],
        [InlineKeyboardButton(f"👁️ Revisar sospechosos en privado: {_onoff(_b(s, 'verification_review_suspicious'))}",
                              callback_data=f"{PREFIX}:tog:verification_review_suspicious:{cid}")],
        [InlineKeyboardButton(f"🔔 Recordatorios: {_onoff(_b(s, 'verification_reminders_enabled'))}",
                              callback_data=f"{PREFIX}:tog:verification_reminders_enabled:{cid}")],
        [InlineKeyboardButton(f"🚪 Al no verificar: {accion}",
                              callback_data=f"{PREFIX}:accion:{cid}")],
        [InlineKeyboardButton(f"⏱️ Tiempos: {sk}min · {rh}h · +{kh}h ▸",
                              callback_data=f"{PREFIX}:times:{cid}")],
        [InlineKeyboardButton(f"👋 Bienvenida: {_onoff(_b(s, 'welcome_enabled'))}",
                              callback_data=f"{PREFIX}:tog:welcome_enabled:{cid}")],
        [InlineKeyboardButton("✏️ Editar texto de bienvenida ▸",
                              callback_data=f"{PREFIX}:edit:w:{cid}")],
        [InlineKeyboardButton("📜 Editar reglas ▸",
                              callback_data=f"{PREFIX}:edit:r:{cid}")],
        [InlineKeyboardButton(f"🧹 Limpiar mensajes de servicio: {_onoff(_b(s, 'cleanservice'))}",
                              callback_data=f"{PREFIX}:tog:cleanservice:{cid}")],
        [InlineKeyboardButton("🔔 Avisos informativos ▸", callback_data=f"{PREFIX}:alertas:{cid}")],
        [InlineKeyboardButton("✖️ Cerrar", callback_data=f"{PREFIX}:close:{cid}")],
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
    rows.append([InlineKeyboardButton("⬅️ Volver", callback_data=f"{PREFIX}:open:{cid}")])
    return InlineKeyboardMarkup(rows)


_TIMES_TEXT = (
    "⏱️ <b>Tiempos de verificación · {title}</b>\n\n"
    "1ª fila · <b>sospechoso</b>: minutos hasta expulsar si no verifica.\n"
    "2ª fila · <b>recordatorio</b>: horas hasta avisar al que no verifica.\n"
    "3ª fila · <b>expulsión</b>: horas tras el recordatorio para expulsar.\n\n"
    "Actual: <b>{sk}min · {rh}h · +{kh}h</b>"
)


# ------------------------------- render helpers -------------------------------

async def _show_panel(msg_edit, db: DB, chat_id: int) -> None:
    """Renderiza (editando el mensaje) el panel principal de un chat."""
    db.ensure_chat_settings(chat_id)
    s = db.get_chat_settings(chat_id)
    sync_on = settings_sync.is_sync_on(db)
    title = html.escape(_panel_title(db, chat_id))
    try:
        await msg_edit(
            _HEADER.format(title=title),
            parse_mode="HTML",
            reply_markup=build_panel_keyboard(chat_id, s, sync_on),
        )
    except TelegramError as exc:
        log.debug("no se pudo renderizar panel: %s", exc)


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
            await msg.reply_text("No estoy de admin en ningún grupo todavía.")
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        await msg.reply_text(
            _HEADER.format(title=html.escape(_panel_title(db, cid))),
            parse_mode="HTML", reply_markup=build_panel_keyboard(cid, s, True),
        )
        return

    # SINCRONIZACIÓN OFF: configuración por grupo (grupo actual o selector en DM).
    if chat and chat.type in ("group", "supergroup"):
        db.ensure_chat_settings(chat.id)
        s = db.get_chat_settings(chat.id)
        await msg.reply_text(
            _HEADER.format(title=html.escape(_chat_title(db, chat.id))),
            parse_mode="HTML", reply_markup=build_panel_keyboard(chat.id, s, False),
        )
        return
    if not admin_chats:
        await msg.reply_text("No estoy de admin en ningún grupo todavía.")
        return
    if len(admin_chats) == 1:
        cid = admin_chats[0]["chat_id"]
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        await msg.reply_text(
            _HEADER.format(title=html.escape(_chat_title(db, cid))),
            parse_mode="HTML", reply_markup=build_panel_keyboard(cid, s, False),
        )
        return
    rows = [
        [InlineKeyboardButton((c["title"] or str(c["chat_id"]))[:60],
                              callback_data=f"{PREFIX}:open:{c['chat_id']}")]
        for c in admin_chats
    ]
    await msg.reply_text(
        "⚙️ <b>Ajustes</b> — ¿qué grupo quieres configurar?\n"
        "<i>(La sincronización está OFF: cada grupo por separado.)</i>",
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
        await q.answer("Solo el admin del bot puede configurar.", show_alert=True)
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
            await q.answer("Chat inválido.")
            return
        await q.answer()
        context.user_data.pop("cfg_await", None)
        await _show_panel(q.edit_message_text, db, cid)
        return

    if action == "close":
        context.user_data.pop("cfg_await", None)
        await q.answer("Cerrado.")
        try:
            await q.edit_message_text("⚙️ Panel cerrado. Escribe /config para volver a abrirlo.")
        except TelegramError:
            pass
        return

    if action == "tog":
        field = parts[2] if len(parts) > 2 else ""
        cid = _cid(3)
        if field not in _TOGGLE_FIELDS or cid is None:
            await q.answer("Opción inválida.")
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        new_val = 0 if _b(s, field) else 1
        n = settings_sync.apply_setting(db, cid, field, new_val)
        estado = "✅ Activado" if new_val else "❌ Desactivado"
        await q.answer(f"{estado} en {n} grupos" if n > 1 else estado)
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_reply_markup(
                reply_markup=build_panel_keyboard(cid, s, settings_sync.is_sync_on(db)))
        except TelegramError:
            pass
        return

    if action == "accion":
        cid = _cid(2)
        if cid is None:
            await q.answer("Chat inválido.")
            return
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        new_val = 0 if _b(s, "verification_kick_normal") else 1
        n = settings_sync.apply_setting(db, cid, "verification_kick_normal", new_val)
        base = "Expulsar" if new_val else "Silenciar"
        await q.answer(f"{base} · {n} grupos" if n > 1 else base)
        s = db.get_chat_settings(cid)
        try:
            await q.edit_message_reply_markup(
                reply_markup=build_panel_keyboard(cid, s, settings_sync.is_sync_on(db)))
        except TelegramError:
            pass
        return

    if action == "sync":
        cid = _cid(2)
        new = not settings_sync.is_sync_on(db)
        settings_sync.set_sync(db, new)
        await q.answer("🔗 Sincronización ON" if new else "Sincronización OFF")
        if new:
            rep = cid if cid is not None else (settings_sync.moderated_chat_ids(db) or [None])[0]
            if rep is not None:
                await _show_panel(q.edit_message_text, db, rep)
        else:
            try:
                await q.edit_message_text(
                    "🔗 <b>Sincronización desactivada.</b>\nAhora cada grupo se configura "
                    "por separado: escribe /config para elegir grupo.",
                    parse_mode="HTML")
            except TelegramError:
                pass
        return

    if action == "times":
        cid = _cid(2)
        if cid is None:
            await q.answer("Chat inválido.")
            return
        await q.answer()
        db.ensure_chat_settings(cid)
        s = db.get_chat_settings(cid)
        txt = _TIMES_TEXT.format(
            title=html.escape(_chat_title(db, cid)),
            sk=_num(s, "verification_suspicious_kick_minutes", 30),
            rh=_num(s, "verification_reminder_hours", 3),
            kh=_num(s, "verification_kick_after_reminder_hours", 6),
        )
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
            await q.answer("Opción inválida.")
            return
        field, presets, unit = _TIME_FIELDS[code]
        try:
            val = int(parts[3])
        except (IndexError, ValueError):
            await q.answer("Valor inválido.")
            return
        if val not in presets:
            await q.answer("Valor fuera de rango.")
            return
        db.ensure_chat_settings(cid)
        n = settings_sync.apply_setting(db, cid, field, val)
        await q.answer(f"✅ {val}{unit}" + (f" · {n} grupos" if n > 1 else ""))
        s = db.get_chat_settings(cid)
        txt = _TIMES_TEXT.format(
            title=html.escape(_chat_title(db, cid)),
            sk=_num(s, "verification_suspicious_kick_minutes", 30),
            rh=_num(s, "verification_reminder_hours", 3),
            kh=_num(s, "verification_kick_after_reminder_hours", 6),
        )
        try:
            await q.edit_message_text(txt, parse_mode="HTML",
                                      reply_markup=build_times_keyboard(cid, s))
        except TelegramError:
            pass
        return

    if action == "edit":
        code = parts[2] if len(parts) > 2 else ""
        cid = _cid(3)
        if code not in _EDIT_FIELDS or cid is None:
            await q.answer("Opción inválida.")
            return
        await q.answer()
        context.user_data["cfg_await"] = {"chat_id": cid, "field": _EDIT_FIELDS[code]}
        if code == "w":
            prompt = (
                "✏️ <b>Envíame el nuevo texto de bienvenida.</b>\n\n"
                "Placeholders: <code>{name}</code>, <code>{chat}</code>. "
                "HTML permitido (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;...).\n"
                "Botones inline (sintaxis Rose): "
                "<code>[Texto](buttonurl://https://url.com)</code>."
            )
        else:
            prompt = "📜 <b>Envíame el nuevo texto de las reglas.</b>\nHTML permitido."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Cancelar",
                                    callback_data=f"{PREFIX}:open:{cid}")]])
        try:
            await q.edit_message_text(prompt, parse_mode="HTML", reply_markup=kb)
        except TelegramError:
            pass
        return

    if action == "alertas":
        # Abre el panel de avisos como mensaje aparte (reutiliza /alertas), sin
        # perder el panel de config.
        from . import admin
        await q.answer()
        try:
            await context.bot.send_message(
                chat_id=q.message.chat_id,
                text="🔔 <b>Avisos informativos</b>\nPulsa para activar o silenciar.",
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
        await msg.reply_text("El texto está vacío. Cancelado. Abre /config para reintentar.")
        context.user_data.pop("cfg_await", None)
        return True
    db: DB = context.bot_data["db"]
    chat_id = pending["chat_id"]
    field = pending["field"]
    context.user_data.pop("cfg_await", None)  # un solo uso (aunque falle luego)
    scope = " en todos los grupos" if settings_sync.is_sync_on(db) else ""
    if field == "welcome_text":
        from .chat_settings_cmd import _parse_rose_buttons
        clean, buttons = _parse_rose_buttons(raw)
        settings_sync.apply_welcome(db, chat_id, clean, buttons if buttons else None)
        extra = f" + {len(buttons)} botón(es)" if buttons else ""
        await msg.reply_text(
            f"✅ Bienvenida actualizada{extra}{scope}. Escribe /config para seguir ajustando.")
    else:  # rules_text
        settings_sync.apply_setting(db, chat_id, "rules_text", raw)
        await msg.reply_text(
            f"✅ Reglas actualizadas{scope}. Escribe /config para seguir ajustando.")
    return True


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
    detalle = (
        f"Cada cambio de ajuste se aplica a los <b>{n} grupos</b> a la vez y el panel "
        "/config no pide elegir grupo."
        if state else
        "Cada grupo se configura por separado; /config te deja elegir grupo."
    )
    await update.effective_message.reply_text(
        f"🔗 <b>Sincronización de ajustes: {'ON' if state else 'OFF'}</b>\n{detalle}\n"
        "Cambia con <code>/sync on</code> o <code>/sync off</code> (o desde /config).",
        parse_mode="HTML",
    )
