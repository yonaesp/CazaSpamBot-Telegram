"""`user_signals.fetch` no puede congelar el bot, y su None significa «no lo sé».

Encontrado en un audit de estabilidad. `fetch()` se llama en la ruta caliente —cada
entrada al grupo, y en varios caminos de `on_message`— y PTB procesa los updates DE
UNO EN UNO: cada segundo ahí es un segundo en el que el bot no modera nada más.

No tenía ningún tope, y el peor caso era abierto por dos motivos que se suman:

1. `_resolve_entity` reintenta 3 veces con 1,5 s de espera. **Medido con un cliente
   que falla al instante: 4,3 s de reloj**, íntegros de `asyncio.sleep`, cada vez
   que una entidad no se resuelve.
2. Ante un FloodWait, Telethon **duerme sola hasta 60 s sin lanzar excepción** —lo
   mismo que ya obligó a poner topes en `story_reader` y `photos_batch`— y aquí hay
   hasta seis llamadas encadenadas.

No había reventado todavía: es un riesgo latente, no un incidente. Estos tests lo
dejan acotado.
"""
import asyncio
import time

import pytest

from src import user_signals


class _Colgada:
    """Un Telethon que no responde nunca. Es lo que hace un FloodWait."""

    async def get_participants(self, *a, **k):
        await asyncio.sleep(3600)

    async def get_entity(self, *a, **k):
        await asyncio.sleep(3600)

    async def get_profile_photos(self, *a, **k):
        await asyncio.sleep(3600)

    async def __call__(self, *a, **k):
        await asyncio.sleep(3600)


class _Muerta:
    """Un Telethon que falla al instante: mide solo el coste de los reintentos."""

    async def get_participants(self, *a, **k):
        raise ValueError("no encontrado")

    async def get_entity(self, *a, **k):
        raise ValueError("no encontrado")

    async def get_profile_photos(self, *a, **k):
        return []

    async def __call__(self, *a, **k):
        raise ValueError("no")


@pytest.mark.asyncio
async def test_una_llamada_colgada_no_congela_el_bot(monkeypatch):
    monkeypatch.setattr(user_signals, "_TIMEOUT_LLAMADA_S", 0.05)
    monkeypatch.setattr(user_signals, "_TIMEOUT_TOTAL_S", 0.3)
    t0 = time.perf_counter()
    sig = await user_signals.fetch(_Colgada(), 123, chat_id=-100, first_name="X")
    tardado = time.perf_counter() - t0
    assert sig is None, "sin señales debe devolver None, no colgarse"
    assert tardado < 1.0, f"tardó {tardado:.2f}s: el tope no está funcionando"


@pytest.mark.asyncio
async def test_el_tope_total_manda_sobre_los_reintentos(monkeypatch):
    """El tope total se eligió POR ENCIMA de los 4,3 s de los reintentos: recortarlo
    por debajo desactivaría en silencio la espera del race del join, que existe
    porque Telegram tarda 1-2 s en propagar una participación nueva."""
    assert user_signals._TIMEOUT_TOTAL_S > 4.3


@pytest.mark.asyncio
async def test_los_reintentos_del_race_del_join_siguen_ahi():
    """Si alguien "optimiza" quitando los reintentos, las cuentas recién llegadas
    dejan de resolverse y el bot se queda sin señales justo cuando más las necesita."""
    import inspect
    fuente = inspect.getsource(user_signals._resolve_entity)
    assert "retries" in fuente and "asyncio.sleep" in fuente


@pytest.mark.asyncio
async def test_sin_cliente_no_revienta():
    assert await user_signals.fetch(None, 123) is None


@pytest.mark.asyncio
async def test_una_entidad_irresoluble_devuelve_none_y_no_tarda_de_mas(monkeypatch):
    monkeypatch.setattr(user_signals, "_TIMEOUT_TOTAL_S", 1.0)
    t0 = time.perf_counter()
    assert await user_signals.fetch(_Muerta(), 123, chat_id=-100, first_name="X") is None
    assert time.perf_counter() - t0 < 1.5


def test_todas_las_llamadas_de_telethon_pasan_por_el_tope():
    """La red de seguridad: si alguien añade una llamada nueva sin `_con_tope`,
    el peor caso vuelve a ser abierto."""
    from pathlib import Path
    import re
    fuente = Path("src/user_signals.py").read_text()
    cuerpo = fuente[fuente.index("async def _resolve_once"):]
    sueltas = [ln.strip() for ln in cuerpo.splitlines()
               if re.search(r"await client[\(.]", ln) and "_con_tope" not in ln]
    assert not sueltas, f"llamadas Telethon sin tope: {sueltas}"
