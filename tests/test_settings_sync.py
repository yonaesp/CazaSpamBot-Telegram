"""Tests de la sincronización de ajustes entre grupos (settings_sync)."""
from __future__ import annotations

from unittest.mock import MagicMock

from src import settings_sync as ss


def _db(pref=None, chats=None):
    db = MagicMock()
    db.get_pref.return_value = pref
    db.all_chats.return_value = chats if chats is not None else [
        {"chat_id": -1, "am_admin": True},
        {"chat_id": -2, "am_admin": True},
        {"chat_id": -3, "am_admin": False},  # no admin → no se sincroniza
    ]
    return db


def test_sync_on_por_defecto():
    assert ss.is_sync_on(_db(pref=None)) is True


def test_sync_off_si_pref_false():
    assert ss.is_sync_on(_db(pref=False)) is False


def test_moderated_chat_ids_solo_admin():
    assert ss.moderated_chat_ids(_db()) == [-1, -2]


def test_target_ids_sync_on_todos():
    assert ss.target_ids(_db(pref=None), -99) == [-1, -2]


def test_target_ids_sync_off_solo_uno():
    assert ss.target_ids(_db(pref=False), -99) == [-99]


def test_apply_setting_sync_on_escribe_en_todos():
    db = _db(pref=None)
    n = ss.apply_setting(db, -99, "welcome_enabled", 1)
    assert n == 2
    calls = {c.args for c in db.update_chat_setting.call_args_list}
    assert calls == {(-1, "welcome_enabled", 1), (-2, "welcome_enabled", 1)}


def test_apply_setting_sync_off_escribe_en_uno():
    db = _db(pref=False)
    n = ss.apply_setting(db, -99, "welcome_enabled", 1)
    assert n == 1
    db.update_chat_setting.assert_called_once_with(-99, "welcome_enabled", 1)


def test_apply_welcome_sync_on_texto_y_botones_en_todos():
    db = _db(pref=None)
    buttons = [{"text": "Normas", "url": "https://t.me/x", "same_row": False}]
    n = ss.apply_welcome(db, -99, "Hola {name}", buttons)
    assert n == 2
    # texto en los 2 grupos
    text_calls = {c.args for c in db.update_chat_setting.call_args_list}
    assert text_calls == {(-1, "welcome_text", "Hola {name}"), (-2, "welcome_text", "Hola {name}")}
    # botones limpiados y añadidos en los 2 grupos
    assert db.clear_welcome_buttons.call_count == 2
    assert db.add_welcome_button.call_count == 2


def test_apply_welcome_buttons_none_no_toca_botones():
    db = _db(pref=False)
    ss.apply_welcome(db, -5, "Hola", None)
    db.clear_welcome_buttons.assert_not_called()
    db.add_welcome_button.assert_not_called()
