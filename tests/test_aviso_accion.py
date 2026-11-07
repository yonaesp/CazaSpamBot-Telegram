"""El aviso de «Acción antispam» al privado del admin.

Caso real (7-nov-2026, 04:45, Windows 11): «Chelsea» (8686388890) escribió su
primer mensaje mencionando a tres bots invitados. El bot la baneó por
`external_mention_or_link` y baneó a los tres bots. Al admin le llegaron los tres
avisos de los bots, pero no el de ella:

1. `federate_ban` retira al final los mensajes del baneado, y el mensaje que se
   estaba juzgando ya está en `moderation_log` (se audita antes de actuar). La
   limpieza lo borró, `_apply_action` fue a copiarlo al privado, la copia falló y,
   como la copia y el aviso iban en el mismo `try`, el aviso se perdió. Pasaba en
   todo ban decidido sobre un mensaje desde el 26-sep (6 en la última semana).
2. Los avisos de los bots decían «sincronizado en todos los grupos» (eran solo de
   ese grupo), «Chat: -1001190184646» y no decían quién los había llamado.

Los dobles imitan a Telegram: lo borrado ya no se puede copiar ni borrar.
"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest
from telegram.error import BadRequest

from src import federation, handlers
from tests.test_protecciones_criticas import _cfg, _db

ADMIN_DM = 345
CHAT = -100100
CHELSEA, MSG = 8686388890, 61715


class _Telegram:
    """Un grupo con mensajes: lo borrado desaparece de verdad."""

    def __init__(self, mensajes):
        self.vivos = {CHAT: set(mensajes)}
        self.copiados: list[int] = []
        self.enviados: list[dict] = []
        self.baneados: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id, user_id):
        return NS(status="member")

    async def ban_chat_member(self, chat_id, user_id, **kw):
        self.baneados.append((chat_id, user_id))
        return True

    async def delete_messages(self, chat_id, message_ids):
        self.vivos.setdefault(chat_id, set()).difference_update(message_ids)
        return True

    async def delete_message(self, chat_id, message_id):
        if message_id not in self.vivos.get(chat_id, set()):
            raise BadRequest("Message to delete not found")
        self.vivos[chat_id].discard(message_id)
        return True

    async def copy_message(self, chat_id, from_chat_id, message_id, **kw):
        if message_id not in self.vivos.get(from_chat_id, set()):
            raise BadRequest("Message to copy not found")
        self.copiados.append(message_id)
        return NS(message_id=1)

    async def send_message(self, chat_id, text, **kw):
        self.enviados.append({"chat_id": chat_id, "text": text, **kw})
        return NS(message_id=len(self.enviados))


def _ctx(db, cfg, tg):
    ctx = MagicMock()
    ctx.bot = tg
    notifier = MagicMock()
    notifier.is_configured.return_value = False
    ctx.bot_data = {"cfg": cfg, "db": db, "notifier": notifier}
    ctx.application = MagicMock()
    ctx.application.job_queue = None
    ctx.application.create_task = lambda coro, **kw: coro.close()
    return ctx


def _avisos(tg):
    return [e["text"] for e in tg.enviados if e["chat_id"] == ADMIN_DM]


@pytest.fixture
def db(tmp_path):
    d = _db(tmp_path, n_chats=3)
    d.upsert_bot_chat(CHAT, "💻 Windows 11 en Español", "supergroup", True, True, True, username="Windows11ESP")
    return d


@pytest.mark.asyncio
async def test_el_ban_federado_de_chelsea_llega_con_su_mensaje(db, monkeypatch):
    monkeypatch.setattr(handlers.notify_prefs, "sin_sonido", lambda db, importante: True)
    cfg = _cfg(admin_notify_chat_id=ADMIN_DM)
    tg = _Telegram([MSG])
    # Lo que hace on_message antes de actuar: el mensaje ya está apuntado.
    db.guardar_mensaje_reciente(CHAT, CHELSEA, MSG, "@amsoslbot @ybjsibot @tbjsibot")
    decision = NS(action="ban", rule="external_mention_or_link", score=130,
                  reason="Mención sin contexto (3 externo/s)", payload={})
    await handlers._apply_action(_ctx(db, cfg, tg), db, cfg, chat_id=CHAT, chat_title="💻 Windows 11 en Español",
                                 user_id=CHELSEA, username=None, message_id=MSG, decision=decision,
                                 original_text="@amsoslbot @ybjsibot @tbjsibot", first_name="Chelsea")
    assert tg.copiados == [MSG], "la limpieza borró el mensaje antes de copiarlo al aviso"
    assert len(_avisos(tg)) == 1, "el aviso del ban no salió"
    assert "sincronizado en todos" in _avisos(tg)[0]
    assert MSG not in tg.vivos[CHAT], "el mensaje se quedó en el grupo"
    assert {c for c, u in tg.baneados} == {CHAT, -100100 - 1, -100100 - 2}


@pytest.mark.asyncio
async def test_si_la_copia_falla_el_aviso_sale_igual(db, monkeypatch):
    monkeypatch.setattr(handlers.notify_prefs, "sin_sonido", lambda db, importante: True)
    cfg = _cfg(admin_notify_chat_id=ADMIN_DM)
    tg = _Telegram([])            # el mensaje ya no existe (lo borró su autor, otro bot…)
    decision = NS(action="ban", rule="external_mention_or_link", score=130, reason="x", payload={})
    await handlers._apply_action(_ctx(db, cfg, tg), db, cfg, chat_id=CHAT, chat_title="G", user_id=CHELSEA,
                                 username=None, message_id=MSG, decision=decision, original_text="x")
    assert tg.copiados == []
    assert len(_avisos(tg)) == 1


@pytest.mark.asyncio
async def test_el_aviso_del_bot_invitado_dice_quien_lo_llamo_y_que_fue_solo_aqui(db, monkeypatch):
    monkeypatch.setattr(handlers.notify_prefs, "sin_sonido", lambda db, importante: True)
    db.record_message(CHAT, CHELSEA, None)
    with db._cur() as c:
        c.execute("UPDATE seen_users SET first_name='Chelsea' WHERE user_id=?", (CHELSEA,))
    cfg = _cfg(admin_notify_chat_id=ADMIN_DM)
    tg = _Telegram([61716])
    decision = NS(action="ban", rule="bot_invitado", score=100, reason="x",
                  payload={"is_bot": True, "llamado_por": CHELSEA, "via": "mtproto", "solo_aqui": True})
    # Por la cuenta secundaria no llega el título del grupo.
    await handlers._apply_action(_ctx(db, cfg, tg), db, cfg, chat_id=CHAT, chat_title=None, user_id=9298708505,
                                 username="tbjsibot", message_id=61716, decision=decision,
                                 original_text="新手也能做一单500", first_name="新手也能做一单500")
    aviso = _avisos(tg)[0]
    assert "solo en este grupo" in aviso and "sincronizado" not in aviso
    assert f"Chelsea</a> (<code>{CHELSEA}</code>)" in aviso, aviso
    assert "Windows 11 en Español" in aviso and "https://t.me/Windows11ESP" in aviso
    assert str(CHAT) not in aviso
    assert tg.baneados == [(CHAT, 9298708505)]


@pytest.mark.asyncio
async def test_sin_federacion_el_aviso_no_dice_que_se_sincronizo(db, monkeypatch):
    monkeypatch.setattr(handlers.notify_prefs, "sin_sonido", lambda db, importante: True)
    cfg = _cfg(admin_notify_chat_id=ADMIN_DM, federation_enabled=False)
    tg = _Telegram([MSG])
    decision = NS(action="ban", rule="external_mention_or_link", score=130, reason="x", payload={})
    await handlers._apply_action(_ctx(db, cfg, tg), db, cfg, chat_id=CHAT, chat_title="G", user_id=CHELSEA,
                                 username=None, message_id=MSG, decision=decision, original_text="x")
    assert "solo en este grupo" in _avisos(tg)[0]


def test_sin_llamante_no_hay_linea(db):
    assert handlers._linea_llamante(db, CHAT, {"is_bot": True}) == ""
    assert handlers._linea_llamante(db, CHAT, None) == ""


def test_un_desconocido_sale_con_su_id(db):
    linea = handlers._linea_llamante(db, CHAT, {"llamado_por": 42})
    assert "tg://user?id=42" in linea and "<code>42</code>" in linea


@pytest.mark.asyncio
async def test_retirar_mensajes_respeta_el_que_se_conserva(db):
    for mid in (10, 11, MSG):
        db.guardar_mensaje_reciente(CHAT, CHELSEA, mid, "")
    tg = _Telegram([10, 11, MSG])
    await federation._retirar_mensajes(tg, db, CHELSEA, [CHAT], conservar=(CHAT, MSG))
    assert tg.vivos[CHAT] == {MSG}
