"""Tipos de aviso INFORMATIVO que el admin puede silenciar o reactivar en runtime
(desde un botón junto al propio aviso, o con /alertas), sin tocar el .env.

No incluye las acciones antispam en sí (esos avisos son el núcleo del bot); solo
los avisos informativos que a algunos no les interesan.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton

from .i18n import t

# clave -> clave i18n de su etiqueta legible. El valor por defecto (si nunca se tocó
# el botón) lo aporta el llamador desde el .env/cfg; aquí solo mapeamos clave -> texto.
# NO se traduce al importar: el idioma se resuelve al arrancar y se puede cambiar en
# caliente con /idioma, así que la etiqueta se pide en cada uso (ver `label`).
NOTIFY_TYPES: dict[str, str] = {
    "self_delete": "notify.self_delete",
    "manual_ban": "notify.manual_ban",
    "bot_removed": "notify.bot_removed",
    "bot_overlap": "notify.bot_overlap",
    "trust_skip": "notify.trust_skip",
}


def label(key: str) -> str:
    """Etiqueta legible del aviso `key`, en el idioma actual."""
    return t(NOTIFY_TYPES.get(key, key))


def is_enabled(db, key: str, default: bool) -> bool:
    """¿Debe enviarse este aviso? Usa la preferencia runtime si existe; si no, el
    default (que viene del .env/cfg)."""
    v = db.get_pref(f"notify_{key}")
    return default if v is None else v


def mute_button(key: str) -> InlineKeyboardButton:
    """Botón '🔕 Silenciar' para adjuntar al aviso del tipo `key`."""
    return InlineKeyboardButton(t("notify.mute_button"), callback_data=f"npref:off:{key}")


def default_for(key: str, cfg=None) -> bool:
    """Valor por defecto de cada aviso (si el admin nunca lo tocó), desde el .env/cfg."""
    import os
    if key == "self_delete":
        return os.getenv("NOTIFY_SELF_DELETES", "false").strip().lower() in ("1", "true", "yes", "on")
    if key == "bot_removed":
        return bool(getattr(cfg, "notify_bot_removed", True))
    return True  # manual_ban y demás: activados por defecto


def effective(db, key: str, cfg=None) -> bool:
    """Estado real de un aviso: preferencia runtime si existe, si no el default."""
    return is_enabled(db, key, default_for(key, cfg))
