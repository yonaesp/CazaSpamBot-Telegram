"""Lo que ve un desconocido: perfil del bot y respuesta por privado.

Motivo (4-oct-2026): gente ajena metía el bot en sus grupos (dos de pesca el
25-sep), donde no puede moderar, y a quien le escribía por privado se le
ignoraba. Ahora se les cuenta que es de código abierto y cómo montarse el suyo.
"""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from telegram.constants import ChatType

from src import admin, publico
from src.i18n import SUPPORTED, t


class _Msg:
    def __init__(self, tipo=ChatType.PRIVATE):
        self.chat = NS(type=tipo)
        self.enviados = []

    async def reply_text(self, text, **kw):
        self.enviados.append(text)


def _upd(uid=99, tipo=ChatType.PRIVATE):
    m = _Msg(tipo)
    return NS(effective_message=m, effective_user=NS(id=uid)), m


@pytest.mark.asyncio
async def test_un_desconocido_recibe_el_enlace_una_vez_al_dia(monkeypatch):
    monkeypatch.delenv("REPO_URL", raising=False)
    ctx = NS(bot_data={})
    upd, m = _upd()
    for _ in range(5):
        await publico.responder_privado(upd, ctx)
    assert len(m.enviados) == 1, "no puede convertirse en un frontón"
    assert publico.REPO_URL_DEFECTO in m.enviados[0]


@pytest.mark.asyncio
async def test_en_un_grupo_no_contesta(monkeypatch):
    upd, m = _upd(tipo=ChatType.SUPERGROUP)
    assert not await publico.responder_privado(upd, NS(bot_data={}))
    assert not m.enviados


@pytest.mark.asyncio
async def test_repo_url_vacio_lo_apaga(monkeypatch):
    monkeypatch.setenv("REPO_URL", "")
    upd, m = _upd()
    assert not await publico.responder_privado(upd, NS(bot_data={}))
    sets = []

    class _Bot:
        async def set_my_description(self, *a, **k):
            sets.append(a)

    await publico.poner_descripcion(_Bot())
    assert not m.enviados and not sets


@pytest.mark.asyncio
async def test_start_de_un_admin_sigue_dando_el_resumen(monkeypatch):
    llamado = []

    async def _start(update, context):
        llamado.append(1)

    monkeypatch.setattr(admin, "cmd_start", _start)
    monkeypatch.setattr(admin.permissions, "is_bot_admin", lambda c, u: True)
    upd, m = _upd()
    await admin.cmd_start_entrada(upd, NS(bot_data={}))
    assert llamado and not m.enviados


@pytest.mark.asyncio
async def test_start_de_un_desconocido_da_el_enlace(monkeypatch):
    async def _no(*a):
        return False

    monkeypatch.setattr(admin.permissions, "is_bot_admin", lambda c, u: False)
    monkeypatch.setattr(admin.permissions, "is_chat_admin_any", _no)
    upd, m = _upd()
    await admin.cmd_start_entrada(upd, NS(bot_data={}))
    assert len(m.enviados) == 1


@pytest.mark.parametrize("lang", sorted(SUPPORTED))
def test_las_descripciones_caben_en_los_topes_de_telegram(lang):
    url = publico.REPO_URL_DEFECTO
    assert len(t("publico.descripcion", _lang=lang, url=url)) <= 512
    assert len(t("publico.descripcion_corta", _lang=lang, url=url)) <= 120
    assert url in t("publico.descripcion_corta", _lang=lang, url=url)


@pytest.mark.parametrize("lang", sorted(SUPPORTED))
def test_avisa_de_que_en_su_grupo_no_funcionara(lang):
    dm = t("publico.dm", _lang=lang, url="U")
    assert "U" in dm
    assert ("no voy a funcionar" in dm) if lang == "es" else ("won't work" in dm)


def test_start_registrado_con_la_entrada_publica():
    assert 'CommandHandler("start", admin.cmd_start_entrada)' in Path("src/main.py").read_text()
