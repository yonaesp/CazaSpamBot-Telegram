"""Tests de la internacionalización (i18n): t(), set_lang, detección, paridad es/en,
y el comando /idioma."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import i18n, lang_cmd
from src.locales import STRINGS


def test_t_espanol_por_defecto():
    i18n.set_lang("es")
    assert "sospechoso" in i18n.t("review.title").lower()


def test_t_ingles():
    assert "suspicious" in i18n.t("review.title", lang="en").lower()


def test_t_clave_inexistente_devuelve_clave():
    assert i18n.t("no.existe.esta.clave") == "no.existe.esta.clave"


def test_t_formatea_placeholders():
    out = i18n.t("review.banned", lang="en", n=3)
    assert "3" in out


def test_t_fallback_a_es_si_falta_en(monkeypatch):
    monkeypatch.setitem(STRINGS["en"], "solo_en_es", None)
    STRINGS["es"]["solo_en_es"] = "valor español"
    try:
        # en.py no tiene la clave (None) → cae a español
        assert i18n.t("solo_en_es", lang="en") == "valor español"
    finally:
        STRINGS["es"].pop("solo_en_es", None)
        STRINGS["en"].pop("solo_en_es", None)


def test_set_lang_normaliza_y_rechaza():
    assert i18n.set_lang("EN") == "en"
    assert i18n.set_lang("pt") == i18n.DEFAULT   # no soportado → default
    assert i18n.set_lang(None) == i18n.DEFAULT


def test_is_supported():
    assert i18n.is_supported("es") and i18n.is_supported("en")
    assert not i18n.is_supported("fr")


def test_detect_system_lang_env(monkeypatch):
    monkeypatch.setenv("BOT_LANG", "en")
    assert i18n.detect_system_lang() == "en"
    monkeypatch.setenv("BOT_LANG", "zz")   # no soportado
    # cae al locale/def; en cualquier caso, uno soportado
    assert i18n.detect_system_lang() in i18n.SUPPORTED


def test_paridad_de_claves_es_en():
    """Meta-test: es.py y en.py deben tener EXACTAMENTE las mismas claves."""
    faltan_en = set(STRINGS["es"]) - set(STRINGS["en"])
    sobran_en = set(STRINGS["en"]) - set(STRINGS["es"])
    assert not faltan_en, f"Claves sin traducir en en.py: {sorted(faltan_en)}"
    assert not sobran_en, f"Claves de más en en.py: {sorted(sobran_en)}"


# --------------------------- comando /idioma ---------------------------

def test_resolve_usa_pref_guardada(tmp_db):
    tmp_db.set_text_pref("lang", "en")
    assert lang_cmd.resolve_and_apply(tmp_db) == "en"


def test_resolve_sin_pref_devuelve_soportado(tmp_db):
    assert lang_cmd.resolve_and_apply(tmp_db) in i18n.SUPPORTED


def _ctx(tmp_db, args, uid=999):
    cfg = SimpleNamespace(admin_user_id=999)
    context = SimpleNamespace(bot_data={"cfg": cfg, "db": tmp_db}, args=args)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
    )
    return update, context


@pytest.mark.asyncio
async def test_cmd_idioma_cambia_y_persiste(tmp_db):
    update, context = _ctx(tmp_db, ["en"])
    await lang_cmd.cmd_idioma(update, context)
    assert tmp_db.get_text_pref("lang") == "en"
    assert i18n.current_lang() == "en"


@pytest.mark.asyncio
async def test_cmd_idioma_invalido_no_cambia(tmp_db):
    i18n.set_lang("es")
    update, context = _ctx(tmp_db, ["fr"])
    await lang_cmd.cmd_idioma(update, context)
    assert i18n.current_lang() == "es"
    assert tmp_db.get_text_pref("lang") is None


@pytest.mark.asyncio
async def test_cmd_idioma_solo_admin(tmp_db):
    update, context = _ctx(tmp_db, ["en"], uid=12345)
    await lang_cmd.cmd_idioma(update, context)
    assert tmp_db.get_text_pref("lang") is None
