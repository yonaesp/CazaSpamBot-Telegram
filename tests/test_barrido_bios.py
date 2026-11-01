"""Barrido semanal de bios de los miembros (L49, L50).

El barrido a mano del 31-oct-2026 leyó las 6.534 bios de los 4 grupos: 1.982
miembros no constaban en la base, y entre ellos había una red de 5 cuentas «my blog
18+» y la quinta cuenta de la red de Helen. Y dos veteranos callados desde 2019 y 2022
tenían la bio de spam: cuentas robadas. Ni el join ni el repaso los ven.
"""
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telethon.errors import FloodWaitError

from src import barrido_bios as bb
from src.db import DB

CHAT = -100
DUENO = 999
ADULTO = "my blog 18+ 👉 https://t.me/+87DRutqtYxU1ZDhk"           # 85 sola
CURSWAY_A = "Holidays made simple. Cursway → t.me/+3JVb6dw6WbI0ODk6"  # 55 sola
CURSWAY_B = "Waves, water temp, flights. Cursway → t.me/+3JVb6dw6WbI0ODk6"
SOLO_ENLACE = "https://t.me/+WcrsCd2W0ZZkYjM0"                       # 40
CHINO = "付费广告 https://t.me/ZOGJ001"                               # 25 en bio_spam
NORMAL = "Programador y formador en Granada"


def _u(uid, nombre="X", username=None, bot=False, deleted=False, is_self=False):
    return SimpleNamespace(id=uid, first_name=nombre, last_name=None, username=username,
                           bot=bot, deleted=deleted, is_self=is_self)


def _hace(dias):
    return datetime.fromtimestamp(time.time() - dias * 86400, tz=timezone.utc)


class _Cliente:
    """Lo que el barrido usa de un TelegramClient: listar miembros (también con el
    filtro de admins), `GetFullUser` (la bio llega en `full_user.about`) y los
    mensajes de una persona en un grupo (`iter_messages(from_user=…)`)."""

    def __init__(self, miembros, bios, admins=(), flood_tras=None, roto=(), ultimos=None,
                 historial_roto=False):
        self.miembros, self.bios, self.admins = miembros, bios, set(admins)
        self.flood_tras, self.roto = flood_tras, set(roto)
        self.ultimos = ultimos or {}
        self.historial_roto = historial_roto
        self.leidas: list[int] = []

    async def iter_participants(self, chat_id, filter=None):
        if chat_id in self.roto:
            raise RuntimeError("CHAT_ADMIN_REQUIRED")
        for u in self.miembros.get(chat_id, []):
            if filter is None or u.id in self.admins:
                yield u

    async def iter_messages(self, chat_id, from_user=None, limit=None):
        if self.historial_roto:
            raise RuntimeError("SEARCH_QUERY_EMPTY")
        if from_user.id in self.ultimos:
            yield SimpleNamespace(date=self.ultimos[from_user.id], action=None)

    async def __call__(self, req):
        if self.flood_tras is not None and len(self.leidas) >= self.flood_tras:
            raise FloodWaitError(request=None, capture=300)
        self.leidas.append(req.id.id)
        return SimpleNamespace(full_user=SimpleNamespace(about=self.bios.get(req.id.id)))


class _Bot:
    """Bot API: envíos, bans (los de `federate_ban`) y la ficha de los admins."""

    ADMINS = {DUENO: ("YonaPN", "Yona"), 501: ("ana_mod", "Ana"), 502: (None, "Luis")}

    def __init__(self):
        self.enviados: list[dict] = []
        self.baneos: list[tuple[int, int]] = []

    async def send_message(self, **kw):
        self.enviados.append(kw)
        return SimpleNamespace(message_id=len(self.enviados))

    async def ban_chat_member(self, chat_id, user_id, **kw):
        self.baneos.append((chat_id, user_id))

    async def delete_messages(self, chat_id, message_ids):
        return True

    async def get_chat_member(self, chat_id, user_id):
        uname, nombre = self.ADMINS.get(user_id, (None, "Otro"))
        return SimpleNamespace(user=SimpleNamespace(id=user_id, username=uname, first_name=nombre,
                                                    is_bot=False),
                               status="administrator" if user_id in self.ADMINS else "member")

    async def get_chat_administrators(self, chat_id):
        gente = [SimpleNamespace(user=SimpleNamespace(id=i, is_bot=False), is_anonymous=False)
                 for i in self.ADMINS]
        gente.append(SimpleNamespace(user=SimpleNamespace(id=7, is_bot=True), is_anonymous=False))
        return gente


CFG = SimpleNamespace(is_moderated=lambda c: True, moderated_chat_ids_set=set(),
                      admin_notify_chat_id=DUENO, admin_user_id=DUENO, mode="active",
                      shadow=False, allowed_scripts=["latin"])


@pytest.fixture(autouse=True)
def _sin_pausa(monkeypatch):
    monkeypatch.setattr(bb, "PAUSA_S", 0)


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Domótica", "supergroup", True, True, True)
    return db


def _ctx(bot=None):
    return SimpleNamespace(bot=bot or _Bot(), application=None)


def _veterano(db, uid, msgs=8):
    db.record_join(CHAT, uid, None)
    for _ in range(msgs):
        db.record_message(CHAT, uid, None)


# ------------------------------------------------------------- a quién se lee

@pytest.mark.asyncio
async def test_primero_a_quien_el_bot_no_conoce_y_sin_admins_ni_bots(tmp_path):
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "conocido")
    db.add_ban(4, "spam", "bio_spam", CHAT)
    db.whitelist(CHAT, 5)
    miembros = [_u(1), _u(2), _u(3, bot=True), _u(4), _u(5), _u(7, deleted=True), _u(8),
                _u(9, is_self=True)]
    cliente = _Cliente({CHAT: miembros}, {8: NORMAL, 1: NORMAL}, admins={2})
    r = await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [8, 1]
    assert r == {"leidas": 2, "avisos": 0, "robadas": 0, "pendientes": 0}


@pytest.mark.asyncio
async def test_no_se_relee_hasta_pasada_la_relectura(tmp_path, monkeypatch):
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8)]}, {8: NORMAL})
    await bb.barrer(_ctx(), db, CFG, cliente)
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [8]
    monkeypatch.setattr(bb, "RELECTURA_S", -1)
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [8, 8]


@pytest.mark.asyncio
async def test_un_grupo_sin_permisos_para_moderar_no_se_barre(tmp_path):
    db = _db(tmp_path)
    db.upsert_bot_chat(-200, "Ajeno", "supergroup", False, False, False)
    cliente = _Cliente({-200: [_u(8)]}, {8: ADULTO})
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == []


# ------------------------------------------------------- quien no tiene historial

@pytest.mark.asyncio
async def test_lo_que_caza_va_al_privado_con_botones_y_no_banea(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8, "<b>Martina")]}, {8: ADULTO})
    r = await bb.barrer(_ctx(bot), db, CFG, cliente)
    assert r["avisos"] == 1 and bot.baneos == []
    (aviso,) = bot.enviados
    assert aviso["chat_id"] == DUENO
    datos = [b.callback_data for b in aviso["reply_markup"].inline_keyboard[0]]
    assert datos == [f"susrev:allow:{CHAT}:8", f"susrev:ban:{CHAT}:8"]
    assert "&lt;b&gt;Martina" in aviso["text"] and "<b>Martina" not in aviso["text"]
    assert "no tiene constancia" in aviso["text"]
    assert not db.is_banned(8)
    assert 8 in db.bios_barridas()  # no se vuelve a avisar cada semana
    (fila,) = db.recent_actions(1)
    assert (fila["rule"], fila["action"]) == ("bio_spam", "noop")
    assert db.ultima_bio_vista(8) == ADULTO  # lo que fichará «Banear»


@pytest.mark.asyncio
async def test_enlace_privado_sin_llegar_al_umbral_se_vuelve_a_leer(tmp_path):
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9)]}, {8: SOLO_ENLACE, 9: NORMAL})
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert db.bios_barridas() == {9}
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [8, 9, 8]


@pytest.mark.asyncio
async def test_la_red_salta_cuando_crece(tmp_path):
    """La primera cuenta de una red se queda en 55; cuando aparece la segunda con el
    mismo enlace, salta la segunda y, a la semana siguiente, también la primera."""
    db = _db(tmp_path)
    bot = _Bot()
    bios = {8: CURSWAY_A, 9: CURSWAY_B}
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8)]}, bios))
    assert bot.enviados == []
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8), _u(9)]}, bios))
    assert [a["reply_markup"].inline_keyboard[0][1].callback_data for a in bot.enviados] == \
        [f"susrev:ban:{CHAT}:9"]
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8), _u(9)]}, bios))
    assert len(bot.enviados) == 2 and "id <code>8</code>" in bot.enviados[1]["text"]


@pytest.mark.asyncio
async def test_bio_en_otro_alfabeto_con_enlace_da_positivo(tmp_path):
    """«付费广告 https://t.me/ZOGJ001» se quedaba en 25 en `bio_spam`."""
    db = _db(tmp_path)
    bot = _Bot()
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8)]}, {8: CHINO}))
    (aviso,) = bot.enviados
    assert "otro alfabeto" in aviso["text"]


@pytest.mark.asyncio
async def test_enlace_a_un_canal_que_se_anuncia_como_spam(tmp_path, monkeypatch):
    """Lo mismo que con los enlaces de un mensaje: se lee la ficha del destino."""
    from src import link_reader
    leidos = []

    async def leer(context, urls, es_moderado=None):
        leidos.extend(urls)
        titulo = "Packs caseros exclusivos" if "packs" in urls[0] else "Fondos de pantalla"
        return link_reader.Destino(titulo=titulo, descripcion="", url=urls[0])

    monkeypatch.setattr(link_reader, "leer", leer)
    db = _db(tmp_path)
    bot = _Bot()
    bios = {8: "Mi canal https://t.me/packsCaseros💋", 9: "https://t.me/dreamswallpapers fondos"}
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8), _u(9)]}, bios))
    assert leidos == ["https://t.me/packsCaseros", "https://t.me/dreamswallpapers"]
    (aviso,) = bot.enviados
    assert "id <code>8</code>" in aviso["text"]


@pytest.mark.asyncio
async def test_bio_en_otro_alfabeto_sin_enlace_no(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    await bb.barrer(_ctx(bot), db, CFG, _Cliente({CHAT: [_u(8)]}, {8: "我爱我的家人和朋友"}))
    assert bot.enviados == []


# ---------------------------------------------------------- cuenta robada (L50)

@pytest.mark.asyncio
async def test_veterano_callado_con_bio_de_spam_es_cuenta_robada(tmp_path):
    db = _db(tmp_path)
    _veterano(db, 8)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8, "Jorge")]}, {8: ADULTO}, ultimos={8: _hace(700)})
    r = await bb.barrer(_ctx(bot), db, CFG, cliente)
    assert r["robadas"] == 1 and r["avisos"] == 0
    assert (CHAT, 8) in bot.baneos and db.is_banned(8)
    grupo = [e for e in bot.enviados if e["chat_id"] == CHAT]
    (aviso,) = grupo
    assert "Jorge (id: 8)" in aviso["text"] and "@YonaPN" in aviso["text"]
    assert "tg://user?id=8" not in aviso["text"]  # sin enlace al perfil en público
    privados = [e for e in bot.enviados if e["chat_id"] == DUENO]
    (dm,) = privados
    datos = [b.callback_data for b in dm["reply_markup"].inline_keyboard[0]]
    assert datos == [f"robada:ok:{CHAT}:8", f"robada:unban:{CHAT}:8"]
    assert db.recent_actions(1)[0]["rule"] == "cuenta_robada"
    assert "t.me/+87drutqtyxu1zdhk" in db.destinos_fichados()


@pytest.mark.asyncio
async def test_veterano_que_escribe_a_menudo_no_se_banea_solo(tmp_path):
    db = _db(tmp_path)
    _veterano(db, 8)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, ultimos={8: _hace(10)})
    r = await bb.barrer(_ctx(bot), db, CFG, cliente)
    assert r["robadas"] == 0 and bot.baneos == []
    (dm,) = bot.enviados
    assert "escribió hace poco" in dm["text"]


@pytest.mark.asyncio
async def test_sin_poder_leer_su_historial_no_se_banea_a_un_veterano(tmp_path):
    db = _db(tmp_path)
    _veterano(db, 8)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, historial_roto=True)
    await bb.barrer(_ctx(bot), db, CFG, cliente)
    assert bot.baneos == []
    assert "no se ha podido saber" in bot.enviados[0]["text"]


@pytest.mark.asyncio
async def test_con_warns_no_es_cuenta_robada(tmp_path):
    db = _db(tmp_path)
    _veterano(db, 8)
    db.add_warn(8, CHAT, DUENO, "insultos")
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, ultimos={8: _hace(700)})
    await bb.barrer(_ctx(bot), db, CFG, cliente)
    assert bot.baneos == [] and "1 warn" in bot.enviados[0]["text"]


@pytest.mark.asyncio
async def test_menciona_a_todos_los_admins_y_les_avisa_por_privado(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(CHAT, "robada_mencion", "todos")
    _veterano(db, 8)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, ultimos={8: _hace(700)})
    await bb.barrer(_ctx(bot), db, CFG, cliente)
    (aviso,) = [e for e in bot.enviados if e["chat_id"] == CHAT]
    assert "@YonaPN" in aviso["text"] and "@ana_mod" in aviso["text"]
    assert "tg://user?id=502" in aviso["text"]  # Luis no tiene @: su nombre enlazado
    assert "id=7" not in aviso["text"]          # el bot admin no se menciona
    assert {e["chat_id"] for e in bot.enviados if "reply_markup" in e} == {DUENO, 501, 502}


@pytest.mark.asyncio
async def test_sin_privado_solo_se_entera_el_dueno(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(CHAT, "robada_mencion", "elegidos")
    db.update_chat_setting(CHAT, "robada_admins", "501")
    db.update_chat_setting(CHAT, "robada_privado", 0)
    _veterano(db, 8)
    bot = _Bot()
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, ultimos={8: _hace(700)})
    await bb.barrer(_ctx(bot), db, CFG, cliente)
    (aviso,) = [e for e in bot.enviados if e["chat_id"] == CHAT]
    assert "@YonaPN" in aviso["text"] and "@ana_mod" in aviso["text"]
    assert [e["chat_id"] for e in bot.enviados if "reply_markup" in e] == [DUENO]


@pytest.mark.asyncio
async def test_en_modo_shadow_no_hay_aviso_publico_ni_se_ficha(tmp_path):
    db = _db(tmp_path)
    _veterano(db, 8)
    bot = _Bot()
    cfg = SimpleNamespace(**{**vars(CFG), "shadow": True, "mode": "shadow"})
    cliente = _Cliente({CHAT: [_u(8)]}, {8: ADULTO}, ultimos={8: _hace(700)})
    await bb.barrer(_ctx(bot), db, cfg, cliente)
    assert bot.baneos == [] and not [e for e in bot.enviados if e["chat_id"] == CHAT]
    assert db.destinos_fichados() == set()


# ------------------------------------------------------------------- límites

@pytest.mark.asyncio
async def test_un_floodwait_corta_la_pasada_y_lo_que_falta_sigue(tmp_path):
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9), _u(10)]}, {}, flood_tras=1)
    r = await bb.barrer(_ctx(), db, CFG, cliente)
    assert r == {"leidas": 1, "avisos": 0, "robadas": 0, "pendientes": 2}
    assert db.bios_barridas() == {8}


@pytest.mark.asyncio
async def test_tope_por_pasada(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "MAX_POR_PASADA", 2)
    db = _db(tmp_path)
    cliente = _Cliente({CHAT: [_u(8), _u(9), _u(10)]}, {})
    r = await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [8, 9] and r["pendientes"] == 1


@pytest.mark.asyncio
async def test_un_grupo_que_no_se_puede_listar_no_para_los_demas(tmp_path):
    db = _db(tmp_path)
    db.upsert_bot_chat(-200, "Otro", "supergroup", True, True, True)
    cliente = _Cliente({CHAT: [_u(8)], -200: [_u(9)]}, {}, roto={CHAT})
    await bb.barrer(_ctx(), db, CFG, cliente)
    assert cliente.leidas == [9]


@pytest.mark.asyncio
async def test_sin_telethon_no_hace_nada(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    ctx = SimpleNamespace(bot=bot, bot_data={"db": db, "cfg": CFG, "reporter": None})
    await bb.barrido_job(ctx)
    assert bot.enviados == [] and db.bios_barridas() == set()
