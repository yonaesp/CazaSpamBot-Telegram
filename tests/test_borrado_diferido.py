"""Un solo job para borrar mensajes a los N segundos.

Había SEIS copias idénticas repartidas por el código, y una de ellas
(`admin_report`) leía `data["msg_id"]` mientras las otras cinco leían
`data["message_id"]`. Copiar el patrón del vecino equivocado daba un `KeyError`
dentro de la cola de trabajos, que además falla en silencio.
"""
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import borrado_diferido as bd


def _ctx(data):
    ctx = MagicMock()
    ctx.bot.delete_message = AsyncMock()
    ctx.job = types.SimpleNamespace(data=data)
    return ctx


@pytest.mark.asyncio
async def test_borra_con_la_clave_normal():
    ctx = _ctx({"chat_id": -100, "message_id": 42})
    await bd.borrar_mensaje_job(ctx)
    assert ctx.bot.delete_message.await_args.kwargs == {"chat_id": -100, "message_id": 42}


@pytest.mark.asyncio
async def test_tambien_acepta_la_clave_antigua():
    """`admin_report` usaba `msg_id`. Aceptarla evita romper cualquier llamada
    que quedara suelta, en vez de fallar dentro de un job donde no se ve."""
    ctx = _ctx({"chat_id": -100, "msg_id": 42})
    await bd.borrar_mensaje_job(ctx)
    assert ctx.bot.delete_message.await_args.kwargs["message_id"] == 42


@pytest.mark.asyncio
async def test_sin_datos_no_revienta():
    ctx = _ctx({})
    await bd.borrar_mensaje_job(ctx)
    assert ctx.bot.delete_message.await_count == 0


@pytest.mark.asyncio
async def test_un_mensaje_ya_borrado_no_propaga():
    from telegram.error import TelegramError
    ctx = _ctx({"chat_id": -100, "message_id": 42})
    ctx.bot.delete_message = AsyncMock(side_effect=TelegramError("no existe"))
    await bd.borrar_mensaje_job(ctx)   # no debe lanzar


def test_cero_segundos_significa_no_borrar():
    """Mismo convenio que el resto del proyecto: 0 = permanente, no «borrar ya»."""
    ctx = MagicMock()
    assert bd.programar(ctx, -100, 42, 0) is None
    assert bd.programar(ctx, -100, 42, -5) is None
    assert ctx.application.job_queue.run_once.call_count == 0


def test_programar_cancela_el_anterior_del_mismo_mensaje():
    """Refrescar un TTL no puede dejar dos borrados encolados sobre el mismo
    mensaje: el primero en vencer se lo llevaría antes de tiempo."""
    ctx = MagicMock()
    previo = MagicMock()
    ctx.application.job_queue.get_jobs_by_name.return_value = [previo]
    bd.programar(ctx, -100, 42, 60, nombre="x")
    assert previo.schedule_removal.call_count == 1
    assert ctx.application.job_queue.run_once.call_count == 1


def test_ya_no_quedan_copias_del_job():
    """Si alguien vuelve a crear una copia local, este test lo caza."""
    from pathlib import Path
    copias = []
    for ruta in ("src/admin_report.py", "src/handlers.py", "src/warns_mod.py",
                 "src/ban_announce.py"):
        txt = Path(ruta).read_text()
        for linea in txt.splitlines():
            if linea.startswith("async def _delete") and "job" in linea:
                copias.append(f"{ruta}: {linea.strip()}")
    assert not copias, f"vuelven a existir copias del job de borrado: {copias}"
