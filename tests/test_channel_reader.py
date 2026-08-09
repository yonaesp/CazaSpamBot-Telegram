"""Leer lo que PUBLICA el canal del perfil, no solo cómo se titula.

El caso que lo motivó (2026-08-08, Windows 11): «Vickycat46», nombre latino y
foto de perfil normal, con un canal titulado `恒泰招聘车队高速结算`. El título
sumaba 85 de los 100 puntos necesarios y se libraba **por tener foto**. El primer
post del canal era esto:

    洗米来有码就要 无风险 日3-8k ... 担保公群 https://t.me/+...

Fíjese en `洗米` («lavar arroz») donde la lista esperaba `洗钱` («lavar dinero»):
jerga hecha para esquivar filtros de palabras. Persiguiendo títulos siempre se va
por detrás; leyendo lo que publican se mira la prueba.

Lo que estos tests fijan es el coste, que es la parte peligrosa: esto corre en la
ruta del join, PTB procesa los updates de uno en uno y Telethon duerme sola hasta
60 s ante un FloodWait sin lanzar nada.
"""
import asyncio
import time

import pytest

from src import channel_reader


class _Canal:
    id = 4412923989
    title = "恒泰招聘车队高速结算"


class _Post:
    def __init__(self, texto):
        self.message = texto


def _cliente(posts, about="", tarda=0.0, revienta=False):
    class Cli:
        async def __call__(self, req):           # GetFullChannelRequest
            if revienta:
                raise RuntimeError("canal privado")
            await asyncio.sleep(tarda)

            class Full:
                class full_chat:
                    pass
            Full.full_chat.about = about
            return Full()

        async def get_messages(self, entidad, limit=5):
            if revienta:
                raise RuntimeError("canal privado")
            await asyncio.sleep(tarda)
            return [_Post(p) for p in posts]
    return Cli()


@pytest.fixture(autouse=True)
def _limpia_cache():
    channel_reader._cache.clear()
    yield
    channel_reader._cache.clear()


# ------------------------------------------------------------------ lo que lee

@pytest.mark.asyncio
async def test_lee_los_posts_del_canal():
    texto = await channel_reader.leer(_cliente(["洗米来有码就要 无风险 日3-8k"]), _Canal(), _Canal.id)
    assert "洗米" in texto and "日3-8k" in texto


@pytest.mark.asyncio
async def test_lee_tambien_la_descripcion():
    """La descripción va aparte del título y suele ser más explícita."""
    texto = await channel_reader.leer(
        _cliente(["hola"], about="担保公群 24h"), _Canal(), _Canal.id)
    assert "担保公群" in texto and "hola" in texto


@pytest.mark.asyncio
async def test_los_posts_sin_texto_no_estorban():
    texto = await channel_reader.leer(_cliente(["", None, "el bueno"]), _Canal(), _Canal.id)
    assert texto == "el bueno"


@pytest.mark.asyncio
async def test_se_recorta_para_no_crecer_sin_freno():
    texto = await channel_reader.leer(_cliente(["x" * 5000]), _Canal(), _Canal.id)
    assert len(texto) <= channel_reader._MAX_CHARS


# ------------------------------------------------ cuando no se puede, no pasa nada

@pytest.mark.asyncio
async def test_sin_cliente_ni_entidad_no_revienta():
    assert await channel_reader.leer(None, _Canal(), 1) is None
    assert await channel_reader.leer(_cliente([]), None, 1) is None
    assert await channel_reader.leer(_cliente([]), _Canal(), 0) is None


@pytest.mark.asyncio
async def test_un_canal_privado_devuelve_none_y_el_bot_sigue():
    """Un canal al que no se puede entrar no es motivo para dejar de moderar: se
    sigue juzgando por el título, exactamente como antes."""
    assert await channel_reader.leer(_cliente([], revienta=True), _Canal(), _Canal.id) is None


@pytest.mark.asyncio
async def test_un_canal_lento_no_congela_el_bot(monkeypatch):
    """Sin tope, un FloodWait aquí para la moderación entera: los updates se
    procesan de uno en uno."""
    monkeypatch.setattr(channel_reader, "_TIMEOUT_TOTAL_S", 0.1)
    monkeypatch.setattr(channel_reader, "_TIMEOUT_S", 0.05)
    t0 = time.perf_counter()
    assert await channel_reader.leer(_cliente(["x"], tarda=30), _Canal(), _Canal.id) is None
    assert time.perf_counter() - t0 < 1.0


# ------------------------------------------------------------------------ caché

@pytest.mark.asyncio
async def test_el_mismo_canal_solo_se_lee_una_vez():
    """Una red enlaza el MISMO canal desde decenas de cuentas: medido, 6 cuentas
    y 2 canales. Sin caché se pagaría la llamada en cada entrada."""
    llamadas = []

    class Contador:
        async def __call__(self, req):
            llamadas.append(1)

            class Full:
                class full_chat:
                    about = ""
            return Full()

        async def get_messages(self, entidad, limit=5):
            llamadas.append(1)
            return [_Post("洗米")]

    cli = Contador()
    for _ in range(5):
        await channel_reader.leer(cli, _Canal(), _Canal.id)
    assert len(llamadas) == 2, "solo la primera vez debería llamar a Telegram"


@pytest.mark.asyncio
async def test_tambien_se_cachea_el_fallo():
    """Un canal ilegible lo seguirá siendo dentro de un minuto, y reintentar
    cuesta tiempo del bot."""
    llamadas = []

    class Rota:
        async def __call__(self, req):
            llamadas.append(1)
            raise RuntimeError("no")

        async def get_messages(self, *a, **k):
            llamadas.append(1)
            raise RuntimeError("no")

    cli = Rota()
    await channel_reader.leer(cli, _Canal(), _Canal.id)
    antes = len(llamadas)
    await channel_reader.leer(cli, _Canal(), _Canal.id)
    assert len(llamadas) == antes


@pytest.mark.asyncio
async def test_la_cache_no_crece_sin_freno(monkeypatch):
    monkeypatch.setattr(channel_reader, "_CACHE_MAX", 5)
    for i in range(1, 40):
        await channel_reader.leer(_cliente([f"post {i}"]), _Canal(), i)
    assert len(channel_reader._cache) <= 5


@pytest.mark.asyncio
async def test_la_cache_caduca(monkeypatch):
    await channel_reader.leer(_cliente(["viejo"]), _Canal(), 77)
    channel_reader._cache[77] = (time.time() - channel_reader._TTL_S - 1, "viejo")
    assert await channel_reader.leer(_cliente(["nuevo"]), _Canal(), 77) == "nuevo"


def test_nunca_se_une_al_canal():
    """Leer un canal público no requiere suscribirse, y suscribirse dejaría a la
    cuenta secundaria en la lista de miembros de un canal de blanqueo."""
    from pathlib import Path
    fuente = Path("src/channel_reader.py").read_text()
    # Se buscan los nombres tal y como aparecerían EN CÓDIGO (con el sufijo
    # `Request` que usa Telethon), no como se mencionan en la prosa de arriba.
    for prohibido in ("JoinChannelRequest", "ImportChatInviteRequest",
                      "IncrementStoryViewsRequest", "GetMessagesViewsRequest"):
        assert prohibido not in fuente
