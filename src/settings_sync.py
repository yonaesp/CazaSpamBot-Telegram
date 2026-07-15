"""Sincronización de ajustes entre todos los grupos moderados.

Preferencia global `config_sync` (por defecto ON): si está activa, CUALQUIER cambio
de ajuste se aplica a TODOS los grupos donde el bot es admin, para que estén
idénticos. Si está OFF, cada cambio afecta solo al grupo indicado (config individual
por grupo, con selector de grupo en el panel).

Todo el que escriba un ajuste de chat debe pasar por `apply_setting` / `apply_welcome`
en vez de `db.update_chat_setting` directo, para respetar el modo sync.
"""
from __future__ import annotations

from .db import DB

SYNC_PREF = "config_sync"


def is_sync_on(db: DB) -> bool:
    """True si la sincronización global está activa (por defecto sí)."""
    v = db.get_pref(SYNC_PREF)
    return True if v is None else bool(v)


def set_sync(db: DB, on: bool) -> None:
    db.set_pref(SYNC_PREF, on)


def moderated_chat_ids(db: DB) -> list[int]:
    """Grupos donde el bot es admin (los que se sincronizan)."""
    return [c["chat_id"] for c in db.all_chats() if c["am_admin"]]


def target_ids(db: DB, chat_id: int) -> list[int]:
    """Chats a los que aplicar un cambio: todos si sync ON, si no solo el indicado."""
    if is_sync_on(db):
        return moderated_chat_ids(db) or [chat_id]
    return [chat_id]


def apply_setting(db: DB, chat_id: int, field: str, value) -> int:
    """Escribe un ajuste escalar respetando el modo sync. Devuelve nº de chats afectados."""
    ids = target_ids(db, chat_id)
    for cid in ids:
        db.update_chat_setting(cid, field, value)
    return len(ids)


def apply_welcome(db: DB, chat_id: int, clean_text, buttons) -> int:
    """Escribe el texto de bienvenida (+ botones Rose) respetando el modo sync.

    `buttons=None` deja los botones existentes intactos; una lista (posiblemente
    vacía) los reemplaza.
    """
    ids = target_ids(db, chat_id)
    for cid in ids:
        db.update_chat_setting(cid, "welcome_text", clean_text)
        if buttons is not None:
            db.clear_welcome_buttons(cid)
            for b in buttons:
                db.add_welcome_button(cid, b["text"], b["url"], same_row=b["same_row"])
    return len(ids)
