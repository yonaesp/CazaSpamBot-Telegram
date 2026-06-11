"""Tests del módulo quips."""
from __future__ import annotations

from src import quips


def test_unknown_rule_returns_none():
    assert quips.pick("unknown_rule", "alice", 42, {}) is None


def test_non_allowed_script_includes_chinese():
    """Quip de chino debe mencionar el idioma o transliteración y el id del user (sin link).

    Acepta cualquier referencia a chino: la palabra "chino", la transliteración
    "tzai chien" (adiós), o el primer carácter del placeholder {extra}.
    """
    # Probamos varias veces porque pick elige random; al menos una debe pasar
    found_chinese_ref = False
    for _ in range(40):
        out = quips.pick(
            "non_allowed_script", "alice", 42,
            {"dominant_script": "han", "ratio": 0.8, "first_msg": True},
            first_name="Alice",
        )
        assert out is not None
        assert "id: <code>42</code>" in out
        if any(s in out.lower() for s in ("chino", "tzai chien", "español")):
            found_chinese_ref = True
    assert found_chinese_ref, "Al menos un quip non_allowed_script debe referenciar chino/español"


def test_reaction_farming_includes_numbers():
    out = quips.pick(
        "reaction_farming", None, 999,
        {"reactions": 7, "window_s": 60},
    )
    assert out is not None
    assert "id: <code>999</code>" in out


def test_external_mention_or_link():
    out = quips.pick(
        "external_mention_or_link", "spammer", 1,
        {"external_mentions": [{"u": 1}], "external_tg_links": ["t.me/x"]},
        first_name="SpamLover",
    )
    assert out is not None
    # Debe aparecer el first_name + id, NO el @username (evita visibilidad)
    assert "SpamLover" in out
    assert "@spammer" not in out
    assert "id: <code>1</code>" in out


def test_compound_rule_picks_first_known():
    out = quips.pick(
        "non_allowed_script+external_mention_or_link", "x", 1,
        {"non_allowed_script": {"dominant_script": "cyrillic"}, "external_mention_or_link": {}},
        first_name="Xavi",
    )
    assert out is not None
    assert "Xavi" in out


def test_cas_match():
    out = quips.pick("cas_match", "bot1", 5, {"offenses": 3}, first_name="BotName")
    assert out is not None
    assert "BotName" in out
    assert "@bot1" not in out


def test_no_username_uses_user_id():
    """Sin first_name ni username, fallback 'user (id: N)'."""
    out = quips.pick("manual_admin_ban", None, 123, {})
    assert out is not None
    assert "user" in out
    assert "id: <code>123</code>" in out


def test_no_clickable_link_for_user():
    """Nunca debe aparecer un link tg://user para evitar dar visibilidad al perfil."""
    for rule in ("non_allowed_script", "external_mention_or_link", "cas_match",
                 "first_msg_media", "manual_admin_ban", "federation_known_ban"):
        out = quips.pick(rule, "anyuser", 9999, {"dominant_script": "han"}, first_name="Test")
        if out:
            assert "tg://user" not in out, f"Link tg://user encontrado en {rule}: {out}"
            assert "<a href" not in out, f"Tag <a href> encontrado en {rule}: {out}"
