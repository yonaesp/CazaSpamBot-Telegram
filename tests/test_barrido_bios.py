"""Barrido semanal de bios de los miembros que el bot no tiene vistos (L49).

El barrido a mano del 31-oct-2026 leyó las 6.534 bios de los 4 grupos: 1.982
miembros no constaban en la base, y entre ellos había una red de 5 cuentas «my blog
18+» y la quinta cuenta de la red de Helen. El repaso de recién llegados no los ve
porque solo mira a quien el bot vio entrar.
"""
from types import SimpleNamespace

import pytest
from telethon.errors import FloodWaitError

from src import barrido_bios as bb
from src.db import DB

CHAT = -100
ADULTO = "my blog 18+ 👉 https://t.me/+87DRutqtYxU1ZDhk"           # 85 sola
CURSWAY_A = "Holidays made simple. Cursway → t.me/+3JVb6dw6WbI0ODk6"  # 55 sola
CURSWAY_B = "Waves, water temp, flights. Cursway → t.me/+3JVb6dw6WbI0ODk6"
SOLO_ENLACE = "https://t.me/+WcrsCd2W0ZZkYjM0"                       # 40
NORMAL = "Programador y formador en Granada"


def _u(uid, nombre="X", username=None, bot=False, deleted=False, is_self=False):
    return SimpleNamespace(id=uid, first_name=nombre, last_name=None, username=username,
                           bot=bot, deleted=deleted, is_self=is_self)


class _Cliente:
    """Lo que el barrido usa de un TelegramClient: listar miembros (también con el
    filtro de admins) y `GetFullUser`, cuya bio llega en `full_user.about`."""

    def __init__(self, miembros, bios, admins=(), flood_tras=None, roto=()):
        self.miembros, self.bios, self.admins = miembros, bios, set(admins)
        self.flood_tras, self.roto = flood_tras, set(roto)
        self.leidas: list[int] = []

    async def iter_participants(self, chat_id, filter=None):
        if chat_id in self.roto:
            raise RuntimeError("CHAT_ADMIN_REQUIRED")
        for u in self.miembros.get(chat_id, []):
            if filter is None or u.id in self.admins:
                yield u

    async def __call__(self, req):
        if self.flood_tras is not None and len(self.leidas) >= self.flood_tras:
            raise FloodWaitError(request=None, capture=300)
        self.leidas.append(req.id.id)
        return SimpleNamespace(full_user=SimpleNamespace(about=self.bios.get(req.id.id)))


class _Bot:
    def __init__(self):
        self.enviados: list[dict] = []

    async def send_message(self, **kw):
        self.enviados.append(kw)


CFG = SimpleNamespace(is_moderated=lambda c: True, moderated_chat_ids_set=set(),
                      admin_notify_chat_id=999, mode="active")


@pytest.fixture(autouse=True)
def _sin_pausa(monkeypatch):
    monkeypatch.setattr(bb, "PAUSA_S", 0)


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Domótica", "supergroup", True, True, True)
    return db


@pytest.mark.asyncio
async def test_solo_lee_a_quien_el_bot_no_conoce(tmp_path):
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "conocido")
    db.add_ban(4, "spam", "bio_spam", CHAT)
    db.whitelist(CHAT, 5)
    db.marcar_bio_barrida(6)
    miembros = [_u(1), _u(2), _u(3, bot=True), _u(4), _u(5), _u(6), _u(7, deleted=True),
                _u(8), _u(9, is_self=True)]
    cliente = _Cliente({CHAT: miembros}, {8: NORMAL}, admins={2})
    r = await bb.barrer(_Bot(), db, CFG, cliente)
    assert cliente.leidas == [8]
    assert r == {"leidas": 1, "avisos": 0, "pendientes": 0}
    assert 8 in db.bios_barridas()


@pytest.mark.asyncio
async def test_un_grupo_sin_permisos_para_moderar_no_se_barre(tmp_path):
    db = _db(tmp_path)
    db.upsert_bot_chat(-200, "Ajeno", "supergroup", False, False, False)
    cliente = _Cliente({-200: [_u(8)]}, {8: ADULTO})
    await bb.barrer(_Bot(), db, CFG, cliente)
    assert cliente.leidas == []


@pytest.mark.asyncio
async def test_lo_que_caza_va_al_privado_con_botones_y_no_banea(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8, "<b>Martina")]}, {8: ADULTO})
    r = await bb.barrer(bot, db, CFG, cliente)
    assert r["avisos"] == 1
    (aviso,) = bot.enviados
    assert aviso["chat_id"] == 999
    datos = [b.callback_data for b in aviso["reply_markup"].inline_keyboard[0]]
    assert datos == [f"susrev:allow:{CHAT}:8", f"susrev:ban:{CHAT}:8"]
    assert "&lt;b&gt;Martina" in aviso["text"] and "<b>Martina" not in aviso["text"]
    assert "t.me/+87DRutqtYxU1ZDhk" in aviso["text"]
    assert not db.is_banned(8)
    assert 8 in db.bios_barridas()  # no se vuelve a avisar cada semana
    (fila,) = db.recent_actions(1)
    assert (fila["rule"], fila["action"]) == ("bio_spam", "noop")
    assert '"via": "barrido_bios"' in fila["payload_json"]


@pytest.mark.asyncio
async def test_enlace_privado_sin_llegar_al_umbral_se_vuelve_a_leer(tmp_path):
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9)]}, {8: SOLO_ENLACE, 9: NORMAL})
    await bb.barrer(_Bot(), db, CFG, cliente)
    assert db.bios_barridas() == {9}
    await bb.barrer(_Bot(), db, CFG, cliente)
    assert cliente.leidas == [8, 9, 8]


@pytest.mark.asyncio
async def test_la_red_salta_cuando_crece(tmp_path):
    """La primera cuenta de una red se queda en 55; cuando aparece la segunda con el
    mismo enlace, salta la segunda y, a la semana siguiente, también la primera."""
    db = _db(tmp_path)
    bot = _Bot()
    bios = {8: CURSWAY_A, 9: CURSWAY_B}
    await bb.barrer(bot, db, CFG, _Cliente({CHAT: [_u(8)]}, bios))
    assert bot.enviados == []
    await bb.barrer(bot, db, CFG, _Cliente({CHAT: [_u(8), _u(9)]}, bios))
    assert [a["reply_markup"].inline_keyboard[0][1].callback_data for a in bot.enviados] == \
        [f"susrev:ban:{CHAT}:9"]
    await bb.barrer(bot, db, CFG, _Cliente({CHAT: [_u(8), _u(9)]}, bios))
    assert len(bot.enviados) == 2 and bot.enviados[1]["text"].count("id <code>8</code>") == 1


@pytest.mark.asyncio
async def test_un_floodwait_corta_la_pasada_y_lo_que_falta_sigue(tmp_path):
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9), _u(10)]}, {}, flood_tras=1)
    r = await bb.barrer(_Bot(), db, CFG, cliente)
    assert r == {"leidas": 1, "avisos": 0, "pendientes": 2}
    assert db.bios_barridas() == {8}


@pytest.mark.asyncio
async def test_tope_por_pasada(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "MAX_POR_PASADA", 2)
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9), _u(10)]}, {})
    r = await bb.barrer(_Bot(), db, CFG, cliente)
    assert cliente.leidas == [8, 9] and r["pendientes"] == 1


@pytest.mark.asyncio
async def test_un_grupo_que_no_se_puede_listar_no_para_los_demas(tmp_path):
    db = _db(tmp_path)
    db.upsert_bot_chat(-200, "Otro", "supergroup", True, True, True)
    cliente = _Cliente({CHAT: [_u(8)], -200: [_u(9)]}, {}, roto={CHAT})
    await bb.barrer(_Bot(), db, CFG, cliente)
    assert cliente.leidas == [9]


@pytest.mark.asyncio
async def test_sin_telethon_no_hace_nada(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    ctx = SimpleNamespace(bot=bot, bot_data={"db": db, "cfg": CFG, "reporter": None})
    await bb.barrido_job(ctx)
    assert bot.enviados == [] and db.bios_barridas() == set()
