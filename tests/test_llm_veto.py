"""Segunda opinión de un modelo, y SOLO para tumbar acciones.

La idea viene de `tg-spam`, que puede usar un modelo en dos modos. Solo se ha
portado el de VETO, porque es el único que encaja con la primera regla del
proyecto: un veto solo puede reducir castigos, así que en el peor de los casos
deja pasar un spam (el error barato) y nunca castiga a alguien legítimo (el caro).

Lo que estos tests protegen es justo eso: que no pueda crear acciones, que no se
consulte donde no hay duda que resolver, y que **cualquier** problema — timeout,
error de red, respuesta rara, paquete ausente — mantenga lo que decidieron las
reglas. El silencio no perdona a nadie.
"""
from types import SimpleNamespace

import pytest

from src import llm_veto
from src.handlers import HARD_RULES_BAN


def _cfg(**extra):
    base = dict(llm_veto=True, llm_veto_model="claude-opus-5")
    base.update(extra)
    return SimpleNamespace(**base)


# ------------------------------------------------------- cuándo ni se pregunta

def test_apagado_por_defecto():
    assert llm_veto.activo(SimpleNamespace()) is False
    assert llm_veto.activo(SimpleNamespace(llm_veto=False)) is False


def test_sin_clave_no_se_activa(monkeypatch):
    """Encenderlo sin credenciales no puede dejar el bot llamando al vacío."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_veto.activo(_cfg()) is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm_veto.activo(_cfg()) is True


def test_no_se_pregunta_por_las_reglas_duras():
    """CAS, lols, ban federado, destino confeso: ahí no hay duda que resolver, y
    preguntar solo añadiría una vía para equivocarse."""
    for regla in HARD_RULES_BAN:
        assert not llm_veto.procede_preguntar("ban", 120, [regla], HARD_RULES_BAN)


def test_no_se_pregunta_por_lo_evidente():
    """Un spam de 230 puntos no necesita una segunda opinión."""
    assert not llm_veto.procede_preguntar("ban", 230, ["commercial_ad"], HARD_RULES_BAN)


def test_no_se_pregunta_por_acciones_leves():
    for accion in ("mute", "delete", "noop", "gentle_warn"):
        assert not llm_veto.procede_preguntar(accion, 100, ["commercial_ad"], HARD_RULES_BAN)


def test_se_pregunta_en_la_zona_gris():
    assert llm_veto.procede_preguntar("ban", 100, ["commercial_ad"], HARD_RULES_BAN)
    assert llm_veto.procede_preguntar("kick", 80, ["learned_similarity"], HARD_RULES_BAN)


# --------------------------------------------- qué pasa con cada respuesta

def _cliente(texto, stop_reason=None):
    class Respuesta:
        content = [SimpleNamespace(type="text", text=texto)]
    Respuesta.stop_reason = stop_reason

    class Mensajes:
        async def create(self, **kw):
            return Respuesta()

    class Cliente:
        messages = Mensajes()
    return Cliente


def _parchear(monkeypatch, cliente):
    import sys
    import types
    modulo = types.ModuleType("anthropic")
    modulo.AsyncAnthropic = lambda *a, **k: cliente()
    monkeypatch.setitem(sys.modules, "anthropic", modulo)


@pytest.mark.asyncio
async def test_un_si_rotundo_perdona(monkeypatch):
    _parchear(monkeypatch, _cliente("legitimo\npregunta normal sobre Windows"))
    vetar, motivo = await llm_veto.veta(_cfg(), "Hola, tengo un problema", ["commercial_ad"])
    assert vetar is True
    assert "Windows" in motivo


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta", [
    "spam\nanuncio de trabajo",
    "no estoy seguro",                 # la duda no perdona
    "Creo que podría ser legitimo",    # tiene que ser la primera palabra
    "",                                # respuesta vacía
    "\n\n",
])
async def test_cualquier_cosa_que_no_sea_un_si_mantiene_la_decision(monkeypatch, respuesta):
    _parchear(monkeypatch, _cliente(respuesta))
    vetar, _ = await llm_veto.veta(_cfg(), "Gana 500 euros al dia", ["commercial_ad"])
    assert vetar is False


@pytest.mark.asyncio
async def test_si_el_modelo_declina_no_se_veta(monkeypatch):
    """Una negativa por seguridad no es un veredicto: sin respuesta útil se hace
    lo que decían las reglas."""
    _parchear(monkeypatch, _cliente("legitimo\nda igual", stop_reason="refusal"))
    vetar, _ = await llm_veto.veta(_cfg(), "texto", ["commercial_ad"])
    assert vetar is False


@pytest.mark.asyncio
async def test_un_error_de_red_mantiene_la_decision(monkeypatch):
    class Rota:
        class messages:
            @staticmethod
            async def create(**kw):
                raise RuntimeError("429 rate limited")
    _parchear(monkeypatch, lambda: Rota())
    assert (await llm_veto.veta(_cfg(), "texto", ["commercial_ad"]))[0] is False


@pytest.mark.asyncio
async def test_una_espera_larga_no_congela_el_bot(monkeypatch):
    """Los updates se procesan de uno en uno: sin este tope, una API lenta
    congelaría la moderación entera."""
    import asyncio

    class Lenta:
        class messages:
            @staticmethod
            async def create(**kw):
                await asyncio.sleep(30)
    _parchear(monkeypatch, lambda: Lenta())
    monkeypatch.setattr(llm_veto, "TIMEOUT_S", 0.05)
    assert (await llm_veto.veta(_cfg(), "texto", ["commercial_ad"]))[0] is False


@pytest.mark.asyncio
async def test_sin_el_paquete_el_bot_sigue_igual(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)
    assert (await llm_veto.veta(_cfg(), "texto", ["commercial_ad"]))[0] is False


@pytest.mark.asyncio
async def test_sin_texto_no_se_pregunta(monkeypatch):
    llamadas = []

    class Espia:
        class messages:
            @staticmethod
            async def create(**kw):
                llamadas.append(kw)
                return SimpleNamespace(content=[], stop_reason=None)
    _parchear(monkeypatch, lambda: Espia())
    await llm_veto.veta(_cfg(), "", ["commercial_ad"])
    await llm_veto.veta(_cfg(), "   ", ["commercial_ad"])
    assert not llamadas


# ------------------------------------------------------------- el enganche

def test_solo_puede_tumbar_acciones_nunca_crearlas():
    """El invariante de todo el módulo. Si alguien engancha esto en una rama que
    pueda subir la acción, este test debería impedirlo."""
    from pathlib import Path
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("llm_veto.activo(cfg)")
    bloque = fuente[i:i + 1400]
    assert "if vetar:" in bloque
    assert 'action="noop_llm_veto"' in bloque, "un veto tiene que quedar registrado"
    for prohibido in ('action="ban"', 'action="kick"', "decide("):
        assert prohibido not in bloque, f"el veto no puede crear acciones ({prohibido})"


@pytest.mark.asyncio
async def test_no_se_le_manda_nada_de_la_base_de_datos(monkeypatch):
    """Solo el texto que ya iba a ser castigado y los nombres de las reglas."""
    capturado = {}

    class Espia:
        class messages:
            @staticmethod
            async def create(**kw):
                capturado.update(kw)
                return SimpleNamespace(content=[], stop_reason=None)
    _parchear(monkeypatch, lambda: Espia())
    await llm_veto.veta(_cfg(), "el mensaje", ["commercial_ad"], chat_titulo="Domótica")
    enviado = str(capturado.get("messages"))
    assert "el mensaje" in enviado and "commercial_ad" in enviado
    for filtrado in ("user_id", "trust", "join_ts", "msg_count"):
        assert filtrado not in enviado
