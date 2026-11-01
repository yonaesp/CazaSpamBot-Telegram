"""Cuenta robada: botones del privado, comando /robadas y submenú del panel (L50).

La expulsión en sí (veterano callado con la bio de spam) se prueba en
`test_barrido_bios.py`, que es quien la dispara.
"""
import asyncio
from types import SimpleNamespace

from src import config_panel, cuenta_robada as cr
from src.db import DB

CHAT = -100
DUENO = 999
CFG = SimpleNamespace(admin_user_id=DUENO, admin_notify_chat_id=DUENO, shadow=False, mode="active")


class _Bot:
    def __init__(self, admins=(DUENO, 501)):
        self.admins = set(admins)
        self.desbaneos: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="administrator" if user_id in self.admins else "member",
                               user=SimpleNamespace(id=user_id, username=None, first_name="X"))

    async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
        self.desbaneos.append((chat_id, user_id))


class _Q:
    def __init__(self, data, quien):
        self.data = data
        self.from_user = SimpleNamespace(id=quien, first_name="Ana")
        self.message = SimpleNamespace(text_html="🔒 aviso")
        self.respuestas: list = []
        self.editado = None

    async def answer(self, texto=None, show_alert=False):
        self.respuestas.append(texto)

    async def edit_message_text(self, texto, **kw):
        self.editado = texto


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Domótica", "supergroup", True, True, True)
    db.add_ban(8, "robada", "cuenta_robada", CHAT)
    return db


def _pulsar(db, bot, data, quien):
    q = _Q(data, quien)
    ctx = SimpleNamespace(bot=bot, bot_data={"cfg": CFG, "db": db})
    asyncio.run(cr.on_callback(SimpleNamespace(callback_query=q), ctx))
    return q


def test_ajustes_por_defecto(tmp_path):
    db = _db(tmp_path)
    db.ensure_chat_settings(CHAT)
    s = db.get_chat_settings(CHAT)
    assert (cr.mencion_de(s), cr.privado_de(s), cr.elegidos_de(s)) == ("dueno", True, [])


def test_el_dueno_desbanea_desde_el_privado(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    q = _pulsar(db, bot, f"robada:unban:{CHAT}:8", DUENO)
    assert not db.is_banned(8) and (CHAT, 8) in bot.desbaneos
    assert "Desbaneada por Ana" in q.editado


def test_un_admin_del_grupo_tambien_puede_decidir(tmp_path):
    db = _db(tmp_path)
    q = _pulsar(db, _Bot(), f"robada:ok:{CHAT}:8", 501)
    assert db.is_banned(8) and "Confirmado por Ana" in q.editado


def test_quien_no_es_admin_no_puede(tmp_path):
    db = _db(tmp_path)
    bot = _Bot()
    q = _pulsar(db, bot, f"robada:unban:{CHAT}:8", 12345)
    assert db.is_banned(8) and bot.desbaneos == [] and q.editado is None


def _cmd(db, args, quien=DUENO):
    respuestas = []

    async def reply_text(texto, **kw):
        respuestas.append(texto)

    upd = SimpleNamespace(effective_user=SimpleNamespace(id=quien), effective_chat=SimpleNamespace(id=CHAT),
                          effective_message=SimpleNamespace(reply_text=reply_text, chat=SimpleNamespace(type="supergroup")))
    ctx = SimpleNamespace(args=args, bot_data={"cfg": CFG, "db": db})
    asyncio.run(cr.cmd_robadas(upd, ctx))
    return respuestas


def test_comando_robadas(tmp_path):
    db = _db(tmp_path)
    assert "Solo el dueño" in _cmd(db, [])[0]
    _cmd(db, ["todos"])
    _cmd(db, ["privado", "off"])
    _cmd(db, ["+", "501"])
    s = db.get_chat_settings(CHAT)
    assert (cr.mencion_de(s), cr.privado_de(s), cr.elegidos_de(s)) == ("todos", False, [501])
    _cmd(db, ["-", "501"])
    assert cr.elegidos_de(db.get_chat_settings(CHAT)) == []
    assert "Uso" in _cmd(db, ["cualquiera"])[0]


def test_submenu_del_panel(tmp_path):
    db = _db(tmp_path)
    db.update_chat_setting(CHAT, "robada_mencion", "elegidos")
    db.update_chat_setting(CHAT, "robada_admins", "501")
    s = db.get_chat_settings(CHAT)
    admins = [SimpleNamespace(id=501, first_name="Ana"), SimpleNamespace(id=502, first_name="Luis")]
    kb = config_panel.build_robadas_keyboard(CHAT, s, admins)
    etiquetas = [b.text for fila in kb.inline_keyboard for b in fila]
    assert "✅ Dueño + elegidos" in etiquetas and "✅ Ana" in etiquetas and "Luis" in etiquetas
    assert all(len(b.callback_data.encode()) <= 64 for fila in kb.inline_keyboard for b in fila)


def test_el_panel_principal_lleva_el_submenu_sin_ganar_filas(tmp_path):
    db = _db(tmp_path)
    db.ensure_chat_settings(CHAT)
    kb = config_panel.build_panel_keyboard(CHAT, db.get_chat_settings(CHAT), True)
    datos = [b.callback_data for fila in kb.inline_keyboard for b in fila]
    assert f"cfg:rob:{CHAT}" in datos
    assert len(kb.inline_keyboard) <= 14
