"""Tipos de aviso INFORMATIVO que el admin puede silenciar o reactivar en runtime
(desde un botón junto al propio aviso, o con /alertas), sin tocar el .env.

No incluye las acciones antispam en sí (esos avisos son el núcleo del bot); solo
los avisos informativos que a algunos no les interesan.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton

# clave -> etiqueta legible. El valor por defecto (si nunca se tocó el botón) lo
# aporta el llamador desde el .env/cfg; aquí solo mapeamos clave -> texto.
NOTIFY_TYPES: dict[str, str] = {
    "self_delete": "Alguien borra su propio mensaje",
    "manual_ban": "Otro admin banea o expulsa a alguien",
    "bot_removed": "Me expulsan de un grupo",
}


def is_enabled(db, key: str, default: bool) -> bool:
    """¿Debe enviarse este aviso? Usa la preferencia runtime si existe; si no, el
    default (que viene del .env/cfg)."""
    v = db.get_pref(f"notify_{key}")
    return default if v is None else v


def mute_button(key: str) -> InlineKeyboardButton:
    """Botón '🔕 Silenciar' para adjuntar al aviso del tipo `key`."""
    return InlineKeyboardButton("🔕 Silenciar estos avisos", callback_data=f"npref:off:{key}")


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
