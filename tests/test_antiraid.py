"""Entradas en avalancha: mirar el grupo, no a cada uno por separado.

Todo lo demás en el bot razona persona a persona. Contra una raid eso no vale: el
ataque no está en ninguna cuenta, está en el conjunto. Quince cuentas que por
separado parecen del montón entrando en dos minutos pasan el filtro una a una.

Lo que más se cuida aquí es lo que NO hace: no cierra el grupo, no silencia a nadie
por entrar y no toca a quien ya estaba dentro. En una avalancha siempre hay gente
normal que pasaba por ahí, y convertir un ataque en una caída del grupo es
exactamente lo que busca quien lo lanza.
"""
import time
from types import SimpleNamespace

import pytest

from src import antiraid


def _ctx():
    return SimpleNamespace(bot_data={}, bot=None)


def _cfg():
    return SimpleNamespace(ban_score=100, kick_score=70, mute_score=40,
                           admin_notify_chat_id=None)


# ------------------------------------------------------------ cuándo salta

def test_las_entradas_normales_no_disparan_nada():
    ctx = _ctx()
    for i in range(antiraid.UMBRAL_ENTRADAS - 1):
        assert antiraid.registrar_entrada(ctx, -100, cuando=1000.0 + i) is False
    assert not antiraid.en_alerta(ctx, -100, ahora=1000.0)


def test_la_avalancha_dispara_al_cruzar_el_umbral():
    ctx = _ctx()
    saltos = [antiraid.registrar_entrada(ctx, -100, cuando=1000.0 + i)
              for i in range(antiraid.UMBRAL_ENTRADAS)]
    assert saltos[-1] is True
    assert saltos.count(True) == 1, "avisaría en cada entrada de la avalancha"


def test_las_entradas_repartidas_en_el_tiempo_no_son_una_avalancha():
    """Lo que distingue una raid no es el volumen, es la CONCENTRACIÓN. Un grupo
    que crece de verdad recibe muchas entradas, pero espaciadas."""
    ctx = _ctx()
    t0 = 1000.0
    for i in range(antiraid.UMBRAL_ENTRADAS * 3):
        salto = antiraid.registrar_entrada(ctx, -100, cuando=t0 + i * (antiraid.VENTANA_S / 2))
        assert salto is False, f"falso positivo en la entrada {i}"


def test_cada_chat_va_por_su_cuenta():
    ctx = _ctx()
    for i in range(antiraid.UMBRAL_ENTRADAS):
        antiraid.registrar_entrada(ctx, -100, cuando=1000.0 + i)
    assert antiraid.en_alerta(ctx, -100, ahora=1000.0)
    assert not antiraid.en_alerta(ctx, -200, ahora=1000.0)


def test_la_alerta_caduca_sola():
    ctx = _ctx()
    for i in range(antiraid.UMBRAL_ENTRADAS):
        antiraid.registrar_entrada(ctx, -100, cuando=1000.0 + i)
    assert antiraid.en_alerta(ctx, -100, ahora=1000.0)
    assert not antiraid.en_alerta(ctx, -100, ahora=1000.0 + antiraid.ALERTA_S + 60)


# --------------------------------------------------------- qué cambia y a quién

def _en_alerta(ctx, chat_id=-100):
    ahora = time.time()
    for i in range(antiraid.UMBRAL_ENTRADAS):
        antiraid.registrar_entrada(ctx, chat_id, cuando=ahora - i)
    return ahora


def test_fuera_de_alerta_los_umbrales_son_los_de_siempre():
    ctx, cfg = _ctx(), _cfg()
    assert antiraid.umbrales(ctx, cfg, -100, time.time()) == (100, 70, 40)


def test_en_alerta_baja_la_vara_a_quien_acaba_de_llegar():
    ctx, cfg = _ctx(), _cfg()
    ahora = _en_alerta(ctx)
    ban, kick, mute = antiraid.umbrales(ctx, cfg, -100, ahora)
    assert (ban, kick, mute) == (80, 55, 35)


def test_al_que_ya_estaba_en_el_grupo_no_se_le_toca():
    """Es la línea que separa «endurecer» de «castigar a los presentes»: en una raid
    también hay gente normal hablando, y no se les puede cambiar la vara de medir
    por algo que han hecho otros."""
    ctx, cfg = _ctx(), _cfg()
    _en_alerta(ctx)
    veterano = time.time() - 400 * 86400
    assert antiraid.umbrales(ctx, cfg, -100, veterano) == (100, 70, 40)


def test_sin_fecha_de_entrada_no_se_endurece_nada():
    """`join_ts` es NULL para quien ya estaba antes de que llegara el bot. Ante la
    duda, la vara de siempre."""
    ctx, cfg = _ctx(), _cfg()
    _en_alerta(ctx)
    assert antiraid.umbrales(ctx, cfg, -100, None) == (100, 70, 40)


def test_los_umbrales_nunca_bajan_de_uno():
    ctx = _ctx()
    ahora = _en_alerta(ctx)
    cfg = SimpleNamespace(ban_score=10, kick_score=5, mute_score=2, admin_notify_chat_id=None)
    ban, kick, mute = antiraid.umbrales(ctx, cfg, -100, ahora)
    assert ban >= 1 and kick >= 1 and mute >= 1


def test_un_recien_llegado_callado_sigue_puntuando_cero():
    """Bajar umbrales no crea señales: si no hay hits, no hay acción por muchos
    peldaños que se bajen."""
    from src.scoring import decide
    ctx, cfg = _ctx(), _cfg()
    ahora = _en_alerta(ctx)
    ban, kick, mute = antiraid.umbrales(ctx, cfg, -100, ahora)
    assert decide([], ban, kick, mute, "ban", is_first_msg_attack=False).action == "noop"


# ------------------------------------------------------------------ el aviso

@pytest.mark.asyncio
async def test_solo_se_avisa_una_vez_por_episodio():
    enviados = []

    class Bot:
        async def send_message(self, **kw):
            enviados.append(kw)
    ctx = SimpleNamespace(bot_data={}, bot=Bot())
    cfg = SimpleNamespace(ban_score=100, kick_score=70, mute_score=40,
                          admin_notify_chat_id=999)
    _en_alerta(ctx)
    await antiraid.avisar(ctx, cfg, -100, "Grupo")
    await antiraid.avisar(ctx, cfg, -100, "Grupo")
    assert len(enviados) == 1


@pytest.mark.asyncio
async def test_el_aviso_no_sale_en_el_grupo():
    """En público le confirmaría a quien ataca que ha funcionado, y alarmaría a los
    miembros por algo que el bot ya está tratando."""
    enviados = []

    class Bot:
        async def send_message(self, **kw):
            enviados.append(kw)
    ctx = SimpleNamespace(bot_data={}, bot=Bot())
    cfg = SimpleNamespace(ban_score=100, kick_score=70, mute_score=40,
                          admin_notify_chat_id=999)
    _en_alerta(ctx)
    await antiraid.avisar(ctx, cfg, -100, "Grupo")
    assert enviados and enviados[0]["chat_id"] == 999


@pytest.mark.asyncio
async def test_sin_privado_configurado_no_revienta():
    ctx, cfg = _ctx(), _cfg()
    _en_alerta(ctx)
    await antiraid.avisar(ctx, cfg, -100, "Grupo")   # no debe lanzar
