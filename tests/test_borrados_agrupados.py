"""Un lote de borrados = UN aviso, y con todos los mensajes dentro.

Reportado por el admin (23-ago-2026): *«cuando un admin borra varios mensajes de
golpe, solo llega el aviso de que se ha borrado uno de ellos… confunde»*. Tenía
razón, y por dos motivos que se sumaban:

1. Se llamaba a la notificación **una vez por cada `msg_id`** del evento, así que
   varios borrados podían dar varios mensajes sueltos al privado.
2. El contenido se recupera de `seen_users`, que guarda **solo el último mensaje
   de cada persona**. De ocho borrados, siete no tenían texto y se descartaban
   con un `return` silencioso: el admin veía «se borró 1» sin saber que faltaban.

Ahora sale un solo aviso con los que tienen texto y, debajo, los ids de los que
no. Se sigue callando cuando NINGUNO tiene contenido: una lista de ids pelados no
informa de nada.
"""
import time
from types import SimpleNamespace as NS

import pytest

from src import telethon_bridge as tb
from src.db import DB

CHAT = -1001234567890


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Windows 11", "supergroup", True, True, True)
    return db


def _con_mensaje(db, user_id, nombre, msg_id, texto):
    db.record_join(CHAT, user_id, nombre, join_ts=time.time() - 3600)
    db.update_last_message(CHAT, user_id, msg_id, texto)


class _Bot:
    id = 100

    def __init__(self):
        self.enviados = []

    async def send_message(self, chat_id, text, **kw):
        self.enviados.append(text)
        return NS(message_id=1)


class _Cliente:
    """Telethon con un registro de administración que atribuye el borrado."""

    def __init__(self, actor_id=555, actor_user="YonaPN", ids=()):
        self.actor_id, self.actor_user, self.ids = actor_id, actor_user, set(ids)
        self.pasadas = 0

    async def get_entity(self, x):
        return NS(id=x)

    def iter_admin_log(self, entity, limit=50, delete=False):
        self.pasadas += 1
        actor = NS(id=self.actor_id, username=self.actor_user, first_name="Yona")
        entradas = [NS(action=NS(message=NS(id=i)), user=actor, user_id=self.actor_id)
                    for i in sorted(self.ids)]

        async def gen():
            for e in entradas:
                yield e
        return gen()


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_ID", "777")
    monkeypatch.setenv("SKIP_DELETE_NOTIF_BOTS", "")


# ------------------------------------------------------------ el caso reportado

@pytest.mark.asyncio
async def test_varios_borrados_dan_un_solo_aviso(tmp_path):
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 60347, "mensaje de Ana")
    _con_mensaje(db, 2, "Luis", 60348, "mensaje de Luis")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(ids=[60347, 60348]), bot, db, CHAT,
                                 [60347, 60348])
    assert len(bot.enviados) == 1, "un lote no puede dar varios avisos"
    assert "60347" in bot.enviados[0] and "60348" in bot.enviados[0]
    assert "mensaje de Ana" in bot.enviados[0]
    assert "mensaje de Luis" in bot.enviados[0]


@pytest.mark.asyncio
async def test_los_que_no_tienen_texto_se_mencionan_igual(tmp_path):
    """El corazón de la queja: `seen_users` solo guarda el último mensaje de cada
    persona, así que la mayoría de un lote no tiene texto. Antes desaparecían."""
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 500, "el único con texto")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(ids=[500, 501, 502, 503]), bot, db, CHAT,
                                 [500, 501, 502, 503])
    aviso = bot.enviados[0]
    assert "4" in aviso, "debería decir cuántos se borraron en total"
    for ident in ("501", "502", "503"):
        assert ident in aviso, f"falta el mensaje {ident}, que es lo que confundía"


@pytest.mark.asyncio
async def test_uno_solo_conserva_el_aviso_de_siempre(tmp_path):
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 60347, "Nah fue un análisis rápido con VT free")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(ids=[60347]), bot, db, CHAT, [60347])
    aviso = bot.enviados[0]
    assert "Mensaje borrado manualmente" in aviso
    assert "60347" in aviso and "análisis rápido" in aviso


# ------------------------------------------------------------ lo que se calla

@pytest.mark.asyncio
async def test_si_no_hay_nada_que_ensenar_no_se_avisa(tmp_path):
    """Una lista de ids pelados no informa de nada: sería ruido puro."""
    db = _db(tmp_path)
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(ids=[9, 10]), bot, db, CHAT, [9, 10])
    assert not bot.enviados


@pytest.mark.asyncio
async def test_lo_que_borra_el_propio_bot_moderando_no_se_avisa(tmp_path):
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Spammer", 700, "spam")
    db.log_action(chat_id=CHAT, user_id=1, username=None, message_id=700,
                  rule="commercial_ad", action="delete", score=100, mode="active")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(ids=[700]), bot, db, CHAT, [700])
    assert not bot.enviados


@pytest.mark.asyncio
async def test_un_bot_de_automatizacion_conocido_no_genera_ruido(tmp_path, monkeypatch):
    monkeypatch.setenv("SKIP_DELETE_NOTIF_BOTS", "999")
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 800, "enlace de amazon")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(actor_id=999, ids=[800]), bot, db, CHAT, [800])
    assert not bot.enviados


@pytest.mark.asyncio
async def test_el_autoborrado_respeta_su_ajuste(tmp_path, monkeypatch):
    """Actor desconocido = el propio autor borrando lo suyo. Silenciado por
    defecto, y con botón para silenciarlo cuando sí se manda."""
    monkeypatch.setenv("NOTIFY_SELF_DELETES", "false")
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 900, "algo")
    bot = _Bot()
    await tb._notificar_borrados(_Cliente(actor_id=None, ids=[]), bot, db, CHAT, [900])
    assert not bot.enviados

    monkeypatch.setenv("NOTIFY_SELF_DELETES", "true")
    await tb._notificar_borrados(_Cliente(actor_id=None, ids=[]), bot, db, CHAT, [900])
    assert bot.enviados


# ------------------------------------------------------------ coste y tamaño

@pytest.mark.asyncio
async def test_el_registro_de_admin_se_recorre_una_sola_vez(tmp_path):
    """Antes se recorría una vez POR MENSAJE: diez borrados, diez recorridos
    idénticos. Son una misma acción, así que el actor es el mismo para todos."""
    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 1000, "texto")
    cli = _Cliente(ids=list(range(1000, 1010)))
    await tb._notificar_borrados(cli, _Bot(), db, CHAT, list(range(1000, 1010)))
    assert cli.pasadas == 1


@pytest.mark.asyncio
async def test_un_lote_enorme_no_pasa_del_limite_de_telegram(tmp_path):
    """Telegram corta en 4096 caracteres, y perder el final sería volver al
    problema de origen: un aviso que no cuenta todo."""
    db = _db(tmp_path)
    for i in range(30):
        _con_mensaje(db, i + 1, f"U{i}", 2000 + i, "x" * 600)
    bot = _Bot()
    ids = list(range(2000, 2030))
    await tb._notificar_borrados(_Cliente(ids=ids), bot, db, CHAT, ids)
    assert len(bot.enviados[0]) <= 4096


@pytest.mark.asyncio
async def test_un_fallo_leyendo_el_registro_no_impide_el_aviso(tmp_path):
    """Sin admin_log no se sabe quién borró, pero el contenido sí se puede dar."""
    class Rota:
        async def get_entity(self, x):
            raise RuntimeError("sin permisos de admin")

        def iter_admin_log(self, *a, **k):
            raise RuntimeError("sin permisos")

    db = _db(tmp_path)
    _con_mensaje(db, 1, "Ana", 3000, "contenido")
    bot = _Bot()
    import os
    os.environ["NOTIFY_SELF_DELETES"] = "true"      # actor desconocido
    await tb._notificar_borrados(Rota(), bot, db, CHAT, [3000])
    assert bot.enviados and "contenido" in bot.enviados[0]


def test_el_handler_avisa_una_vez_por_lote_no_por_mensaje():
    """La costura: si alguien vuelve a meter la notificación dentro del bucle,
    reaparecen los avisos sueltos que originaron la queja.

    Se mira el ÁRBOL del código, no la sangría: la llamada está dentro de un
    `try`, así que contar espacios daba un falso positivo."""
    import ast
    from pathlib import Path

    arbol = ast.parse(Path("src/telethon_bridge.py").read_text())
    handlers = [n for n in ast.walk(arbol)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "_on_deleted"]
    assert handlers, "no se encontró el handler"
    for bucle in [n for n in ast.walk(handlers[0]) if isinstance(n, ast.For)]:
        dentro = [n for n in ast.walk(bucle)
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "id", None) == "_notificar_borrados"]
        assert not dentro, "la notificación volvió a estar dentro del bucle"


# ---------------------------------------------------------------------------
# La raíz: guardar más de un mensaje por persona
#
# `seen_users` retiene solo el ÚLTIMO. Por eso de ocho borrados llegaban siete
# sin texto y el aviso salía casi vacío. `mensajes_recientes` guarda los últimos
# de cada persona en cada chat, y el aviso ya puede enseñarlos todos.
# ---------------------------------------------------------------------------

def test_se_guardan_varios_mensajes_por_persona(tmp_path):
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "Ana", join_ts=time.time())
    for i in range(5):
        db.update_last_message(CHAT, 1, 100 + i, f"mensaje {i}")
    for i in range(5):
        assert db.mensaje_reciente(CHAT, 100 + i) == (1, f"mensaje {i}")


def test_el_historial_no_crece_sin_freno(tmp_path):
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "Ana", join_ts=time.time())
    for i in range(40):
        db.update_last_message(CHAT, 1, 200 + i, f"m{i}")
    with db._cur() as c:
        n = c.execute("SELECT COUNT(*) n FROM mensajes_recientes WHERE user_id=1").fetchone()["n"]
    assert n == db.MAX_RECIENTES_POR_USUARIO
    # Se conservan los ÚLTIMOS, que son los que se van a borrar.
    assert db.mensaje_reciente(CHAT, 239) is not None
    assert db.mensaje_reciente(CHAT, 200) is None


def test_lo_viejo_se_purga(tmp_path):
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "Ana", join_ts=time.time())
    db.update_last_message(CHAT, 1, 300, "antiguo")
    with db._cur() as c:
        c.execute("UPDATE mensajes_recientes SET ts=? WHERE msg_id=300",
                  (time.time() - (db.RECIENTES_DIAS + 1) * 86400,))
    assert db.purgar_mensajes_recientes() == 1
    assert db.mensaje_reciente(CHAT, 300) is None


@pytest.mark.asyncio
async def test_ahora_el_lote_sale_completo(tmp_path):
    """El caso reportado, de punta a punta: se borran cuatro mensajes de la misma
    persona y el aviso los enseña los cuatro, no solo el último."""
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "Ana", join_ts=time.time())
    for i, txt in enumerate(["uno", "dos", "tres", "cuatro"]):
        db.update_last_message(CHAT, 1, 400 + i, txt)
    bot = _Bot()
    ids = [400, 401, 402, 403]
    await tb._notificar_borrados(_Cliente(ids=ids), bot, db, CHAT, ids)
    aviso = bot.enviados[0]
    for txt in ("uno", "dos", "tres", "cuatro"):
        assert txt in aviso, f"falta «{txt}»: el aviso vuelve a salir incompleto"
    assert "sin contenido guardado" not in aviso


def test_el_respaldo_cubre_lo_escrito_antes_del_cambio(tmp_path):
    """Quien actualice el bot no pierde el contenido de lo que ya había: si no
    está en el historial corto, se sigue mirando `seen_users`."""
    db = _db(tmp_path)
    db.record_join(CHAT, 1, "Ana", join_ts=time.time())
    db.update_last_message(CHAT, 1, 500, "de antes")
    with db._cur() as c:                      # se simula que no existía la tabla
        c.execute("DELETE FROM mensajes_recientes")
    datos = tb._contenido_de(db, CHAT, 500)
    assert datos and datos[2] == "de antes"
