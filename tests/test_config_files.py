"""Tests de los archivos editables: welcomes y listas negras."""
from __future__ import annotations

import re

from src import trust
from src import verification as v
from src import wordlists


# ---------- wordlists (listas negras) ----------

def test_load_terms_lee_archivo(tmp_path, monkeypatch):
    f = tmp_path / "lista.txt"
    f.write_text("# comentario\n\ncasino\nbet\n  forex  \n", encoding="utf-8")
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    terms = wordlists.load_terms("lista.txt", ["fallback"])
    assert terms == ["casino", "bet", "forex"]  # ignora vacías y comentarios, hace strip


def test_load_terms_fallback_si_no_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    assert wordlists.load_terms("no_existe.txt", ["a", "b"]) == ["a", "b"]


def test_load_terms_fallback_si_vacio(tmp_path, monkeypatch):
    f = tmp_path / "vacio.txt"
    f.write_text("# solo comentarios\n\n", encoding="utf-8")
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    assert wordlists.load_terms("vacio.txt", ["def"]) == ["def"]


def test_compile_alternation_palabra_completa():
    rx = wordlists.compile_alternation(["casino", "forex"])
    assert rx.search("juega al casino ya")
    assert not rx.search("casinopolis")  # boundary: no es palabra completa


def test_compile_alternation_admite_regex():
    rx = wordlists.compile_alternation([r"inversi[oó]n\s+garantizada"])
    assert rx.search("ofrezco inversión garantizada hoy")
    assert rx.search("inversion garantizada")


def test_compile_alternation_vacio_no_casa_nada():
    rx = wordlists.compile_alternation([])
    assert not rx.search("cualquier cosa")


# ---------- welcomes ----------

def test_welcome_pack_por_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "_WELCOMES_DIR", tmp_path)
    (tmp_path / "-100123.txt").write_text("# tema\nHola {name}, bienvenido al grupo X\n", encoding="utf-8")
    (tmp_path / "generic.txt").write_text("Generico {name}\n", encoding="utf-8")
    assert v._load_welcome_pack(-100123) == ["Hola {name}, bienvenido al grupo X"]


def test_welcome_pack_cae_a_generic(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "_WELCOMES_DIR", tmp_path)
    (tmp_path / "generic.txt").write_text("Generico1 {name}\nGenerico2 {name}\n", encoding="utf-8")
    assert v._load_welcome_pack(-999) == ["Generico1 {name}", "Generico2 {name}"]


def test_welcome_pack_cae_a_default_en_codigo(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "_WELCOMES_DIR", tmp_path)  # dir vacío, sin generic.txt
    assert v._load_welcome_pack(-999) == v._DEFAULT_WELCOMES


def test_friendly_welcomes_toggle(monkeypatch):
    monkeypatch.setenv("FRIENDLY_WELCOMES_ENABLED", "false")
    assert v.friendly_welcomes_enabled() is False
    monkeypatch.setenv("FRIENDLY_WELCOMES_ENABLED", "true")
    assert v.friendly_welcomes_enabled() is True
    monkeypatch.delenv("FRIENDLY_WELCOMES_ENABLED", raising=False)
    assert v.friendly_welcomes_enabled() is True  # default true


def test_welcome_phrases_usan_name_placeholder():
    """Las frases genéricas versionadas deben usar {name} y formatear sin error."""
    for phrase in v._read_phrase_file(v._WELCOMES_DIR / "generic.txt") or v._DEFAULT_WELCOMES:
        phrase.format(name="@test")  # no debe lanzar KeyError


# ---------- niveles 1-10 ----------

def test_trust_level_rango():
    assert trust.trust_level(0) == 1
    assert trust.trust_level(100) == 10
    assert trust.trust_level(70) == 7
    assert trust.trust_level(30) == 3
    assert all(1 <= trust.trust_level(s) <= 10 for s in range(0, 101))


def test_spam_level_satura_a_10():
    assert trust.spam_level(100) == 10
    assert trust.spam_level(230) == 10  # scores altos se capan a 10
    assert trust.spam_level(40) == 4
    assert trust.spam_level(0) == 1


def test_render_no_revela_score_crudo():
    assert "/10" in trust.render_trust(80)
    assert "/10" in trust.render_spam(150)
    # confianza alta = verde, spam alto = rojo
    assert "🟢" in trust.render_trust(90)
    assert "🔴" in trust.render_spam(120)
