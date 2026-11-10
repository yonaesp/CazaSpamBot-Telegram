"""Auditoría de estabilidad del 10-nov-2026 (L61).

Lo que se encontró mirando producción y no el código: cada `docker compose restart`
mataba al bot con SIGKILL; un bucle colgado no lo reiniciaba nadie; los borrados
programados vivían solo en memoria (8 avisos de hasta seis meses en los grupos); y
Telethon, si se rendía reconectando, se quedaba caído hasta el siguiente reinicio.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.error import BadRequest, NetworkError

from src import borrado_diferido as bd
from src import main, permissions, reporter, vigia_cuelgue


# ------------------------------------------------------------ vigía de cuelgues

def test_el_contador_no_salta_mientras_el_bucle_late():
    c = vigia_cuelgue.Contador(limite=3)
    latidos = 0
    for _ in range(50):
        latidos += 1                      # un latido entre comprobación y comprobación
        assert c.comprobar(latidos) is False
    # El latido es cada 30 s y la comprobación cada 15: una de cada dos no ve latido nuevo.
    for i in range(50):
        assert c.comprobar(latidos + i // 2) is False


def test_el_contador_salta_tras_n_comprobaciones_seguidas_sin_latido():
    c = vigia_cuelgue.Contador(limite=3)
    assert [c.comprobar(7) for _ in range(4)] == [False, False, False, True]


def test_un_latido_a_tiempo_pone_el_contador_a_cero():
    c = vigia_cuelgue.Contador(limite=3)
    assert [c.comprobar(1), c.comprobar(1), c.comprobar(1)] == [False, False, False]
    assert c.comprobar(2) is False
    assert [c.comprobar(2), c.comprobar(2)] == [False, False]


def test_el_vigia_sale_y_deja_la_marca(tmp_path, monkeypatch):
    marca = tmp_path / "cuelgue.txt"
    salidas, vueltas = [], []
    monkeypatch.setattr(vigia_cuelgue, "_latidos", 5)
    vigia_cuelgue._vigilar(marca, cada=0, limite=3, salir=salidas.append, dormir=vueltas.append)
    assert salidas == [vigia_cuelgue.CODIGO_SALIDA] and vigia_cuelgue.CODIGO_SALIDA != 0
    assert len(vueltas) == 4              # la primera comprobación solo toma la referencia
    cuando = vigia_cuelgue.cuelgue_anterior(marca)
    assert cuando and not marca.exists()  # se cuenta una vez
    assert vigia_cuelgue.cuelgue_anterior(marca) is None


def _fn(path: str, nombre: str):
    return next(n for n in ast.walk(ast.parse(Path(path).read_text(encoding="utf-8")))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre)


def test_el_latido_y_el_vigia_estan_enganchados():
    assert "vigia_cuelgue.latido()" in ast.unparse(_fn("src/main.py", "_heartbeat_job"))
    arranque = ast.unparse(_fn("src/main.py", "_post_init"))
    assert "vigia_cuelgue.arrancar()" in arranque
    assert "_una_sola_parada()" in arranque
    assert "faulthandler.enable()" in ast.unparse(_fn("src/main.py", "main"))


@pytest.mark.asyncio
async def test_tras_un_cuelgue_se_le_cuenta_al_admin(tmp_path, tmp_db, monkeypatch):
    marca = tmp_path / "cuelgue.txt"
    marca.write_text("1794200000.0")
    monkeypatch.setattr(vigia_cuelgue, "MARCA", marca)
    monkeypatch.setattr(vigia_cuelgue.cuelgue_anterior, "__defaults__", (marca,))
    bot = NS(send_message=AsyncMock())
    ctx = NS(bot=bot, bot_data={"cfg": NS(admin_notify_chat_id=7), "db": tmp_db})
    await main._informar_cuelgue_job(ctx)
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.kwargs["disable_notification"] is False   # suena
    await main._informar_cuelgue_job(ctx)                                        # ya contado
    assert bot.send_message.await_count == 1


# ------------------------------------------------------------- parada ordenada

def test_la_segunda_señal_de_parada_se_ignora():
    parar = main._parada_unica()
    with pytest.raises(SystemExit):
        parar()
    parar()        # antes relanzaba SystemExit y abortaba el apagado a medias
    parar()


def test_el_compose_da_tiempo_a_apagar():
    assert "stop_grace_period: 45s" in Path("docker-compose.yml").read_text(encoding="utf-8")


# ---------------------------------------------- borrados que sobreviven a un reinicio

class _Cola:
    def __init__(self):
        self.jobs = []

    def get_jobs_by_name(self, nombre):
        return []

    def run_once(self, fn, when, data=None, name=None):
        self.jobs.append((fn, when, data, name))


def _ctx(db, bot=None, job=None):
    return NS(bot=bot or NS(delete_message=AsyncMock()), bot_data={"db": db},
              application=NS(job_queue=_Cola()), job=job)


def test_programar_deja_el_borrado_en_la_base(tmp_db):
    ctx = _ctx(tmp_db)
    assert bd.programar(ctx, -100, 55, 3600) == "del_-100_55"
    assert len(ctx.application.job_queue.jobs) == 1
    fila = tmp_db.borrados_vencidos(1e12)[0]
    assert (fila["chat_id"], fila["message_id"]) == (-100, 55)
    assert tmp_db.borrados_vencidos(0) == []            # aún no vence


def test_cero_sigue_siendo_no_borrar(tmp_db):
    ctx = _ctx(tmp_db)
    assert bd.programar(ctx, -100, 55, 0) is None
    bd.apuntar(ctx, -100, 55, 0)
    assert tmp_db.borrados_vencidos(1e12) == []


@pytest.mark.asyncio
async def test_el_job_que_borra_a_su_hora_olvida_la_fila(tmp_db):
    ctx = _ctx(tmp_db, job=NS(data={"chat_id": -100, "message_id": 55}))
    bd.programar(ctx, -100, 55, 3600)
    await bd.borrar_mensaje_job(ctx)
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=-100, message_id=55)
    assert tmp_db.borrados_vencidos(1e12) == []


@pytest.mark.asyncio
async def test_el_barrido_borra_lo_que_un_reinicio_dejo_sin_job(tmp_db):
    """El caso real: se programa, el bot se reinicia (la cola en memoria se pierde)
    y el mensaje vence. Antes se quedaba en el grupo para siempre."""
    tmp_db.apuntar_borrado(-100, 55, 1000.0)             # vencido hace mucho
    tmp_db.apuntar_borrado(-100, 56, 1e12)               # aún no toca
    ctx = _ctx(tmp_db)                                   # cola nueva, vacía
    await bd.barrido_job(ctx)
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=-100, message_id=55)
    quedan = [(f["chat_id"], f["message_id"]) for f in tmp_db.borrados_vencidos(1e13)]
    assert quedan == [(-100, 56)]


@pytest.mark.asyncio
async def test_el_barrido_no_se_adelanta_al_job_en_memoria(tmp_db):
    import time
    tmp_db.apuntar_borrado(-100, 55, time.time() - 10)   # vencido hace 10 s: el job está al caer
    ctx = _ctx(tmp_db)
    await bd.barrido_job(ctx)
    ctx.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_el_barrido_reintenta_si_falla_la_red_y_olvida_lo_que_ya_no_existe(tmp_db):
    import time
    hace_un_rato = time.time() - 600
    tmp_db.apuntar_borrado(-100, 1, hace_un_rato)
    tmp_db.apuntar_borrado(-100, 2, hace_un_rato)

    async def borrar(chat_id, message_id):
        raise NetworkError("Bad Gateway") if message_id == 1 else BadRequest("Message to delete not found")

    ctx = _ctx(tmp_db, bot=NS(delete_message=AsyncMock(side_effect=borrar)))
    await bd.barrido_job(ctx)
    assert [f["message_id"] for f in tmp_db.borrados_vencidos(1e12)] == [1]
    # Pero no eternamente: pasado un día de más, se da por perdida.
    tmp_db.apuntar_borrado(-100, 1, time.time() - bd.ABANDONO_S - 600)
    await bd.barrido_job(ctx)
    assert tmp_db.borrados_vencidos(1e12) == []


def test_ningun_borrado_se_programa_por_fuera():
    """Un `run_once(borrar_mensaje_job, …)` a pelo no queda en la base."""
    fuera = []
    for f in sorted(Path("src").rglob("*.py")):
        if f.name == "borrado_diferido.py":
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "run_once"
                    and n.args and "borrar_mensaje_job" in ast.unparse(n.args[0])):
                fuera.append(f"{f}:{n.lineno}")
    assert not fuera, f"usa borrado_diferido.programar: {fuera}"


def test_los_jobs_de_borrado_propios_tambien_se_apuntan():
    """Los tres que borran con su propio job (bienvenidas y aviso suave) llevan `apuntar`."""
    for ruta, nombre in (("src/verification.py", "del_friendly_welcome_"),
                         ("src/verification.py", "del_verified_welcome_"),
                         ("src/gentle_warning.py", "del_gentle_")):
        src = Path(ruta).read_text(encoding="utf-8")
        tras = src[src.index(nombre):][:400]
        assert "borrado_diferido.apuntar(" in tras, (ruta, nombre)


def test_el_barrido_esta_programado():
    assert "borrado_diferido.barrido_job" in ast.unparse(_fn("src/main.py", "_post_init"))


# ------------------------------------------------------------------- Telethon

class _Cliente:
    def __init__(self, conectado=False, conecta=True, autorizado=True):
        self._c, self._conecta, self._aut = conectado, conecta, autorizado
        self.intentos = 0

    def is_connected(self):
        return self._c

    async def connect(self):
        self.intentos += 1
        if not self._conecta:
            raise ConnectionError("sin red")
        self._c = True

    async def is_user_authorized(self):
        return self._aut


def _reporter(cliente):
    r = reporter.SpamReporter(telethon_enabled=True, reporting_enabled=True)
    r._client = cliente
    return r


@pytest.mark.asyncio
async def test_conectado_no_toca_nada():
    c = _Cliente(conectado=True)
    assert await _reporter(c).asegurar_conexion() is True and c.intentos == 0


@pytest.mark.asyncio
async def test_desconectado_reconecta():
    c = _Cliente(conectado=False)
    assert await _reporter(c).asegurar_conexion() is True and c.intentos == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cliente", [_Cliente(conecta=False), _Cliente(autorizado=False)])
async def test_si_no_vuelve_lo_dice_sin_lanzar(cliente):
    assert await _reporter(cliente).asegurar_conexion() is False


@pytest.mark.asyncio
async def test_un_reporte_que_no_vuelve_no_para_la_cola(monkeypatch):
    monkeypatch.setattr(reporter, "_TOPE_REPORTE_S", 0.05)
    r = _reporter(_Cliente(conectado=True))
    hechos = []

    async def enviar(task):
        if task.user_id == 1:
            await asyncio.sleep(30)       # la llamada que no vuelve
        hechos.append(task.user_id)

    r._enviar = enviar
    trabajador = asyncio.create_task(r._worker())
    r.enqueue(-100, 1, 10, "spam", "x")
    r.enqueue(-100, 2, 11, "spam", "x")
    await asyncio.wait_for(r._queue.join(), 3)
    trabajador.cancel()
    assert hechos == [2]


@pytest.mark.asyncio
async def test_avisa_a_la_tercera_caida_y_cuando_vuelve(tmp_db):
    rep = NS(get_client=lambda: object(),
             asegurar_conexion=AsyncMock(side_effect=[False, False, False, False, True, True]))
    bot = NS(send_message=AsyncMock())
    ctx = NS(bot=bot, bot_data={"cfg": NS(admin_notify_chat_id=7), "db": tmp_db, "reporter": rep})
    for _ in range(2):
        await main._telethon_vivo_job(ctx)
    assert bot.send_message.await_count == 0             # dos fallos: aún puede ser un corte breve
    await main._telethon_vivo_job(ctx)
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.kwargs["disable_notification"] is False   # suena
    await main._telethon_vivo_job(ctx)
    assert bot.send_message.await_count == 1             # no se repite en cada pasada
    await main._telethon_vivo_job(ctx)                   # vuelve
    assert bot.send_message.await_count == 2
    assert bot.send_message.await_args.kwargs["disable_notification"] is True    # en silencio
    await main._telethon_vivo_job(ctx)
    assert bot.send_message.await_count == 2


@pytest.mark.parametrize("ruta,funcion,llamada", [
    ("src/cuenta_secundaria.py", "vigilar_job", "asyncio.wait_for(_vigilar(context)"),
    ("src/barrido_bios.py", "barrido_job", "asyncio.wait_for(barrer("),
    ("src/telethon_bridge.py", "_quien_borro", "asyncio.wait_for(_leer_quien_borro("),
    ("src/reporter.py", "_worker", "asyncio.wait_for(self._enviar(task)"),
])
def test_los_trabajos_de_fondo_con_telethon_tienen_tope(ruta, funcion, llamada):
    """Una llamada que no vuelve dejaba el trabajo parado hasta el siguiente reinicio."""
    assert llamada in ast.unparse(_fn(ruta, funcion))


# --------------------------------------------------------------------- memoria

@pytest.mark.asyncio
async def test_el_cache_de_admins_tiene_tope(tmp_db, monkeypatch):
    monkeypatch.setattr(permissions, "_CACHE_MAX", 50)
    ctx = NS(bot=NS(get_chat_member=AsyncMock()), bot_data={"db": tmp_db})
    for uid in range(1, 400):
        await permissions.is_chat_admin_any(ctx, uid)
    assert len(ctx.bot_data["_admin_any_cache"]) <= 50


def test_magicmock_no_se_usa_como_base():
    """El doble de la cola imita a la de verdad: `get_jobs_by_name` devuelve una lista."""
    assert _Cola().get_jobs_by_name("x") == [] and not isinstance(_Cola(), MagicMock)
