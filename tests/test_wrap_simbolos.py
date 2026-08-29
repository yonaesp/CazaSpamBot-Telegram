"""El envoltorio `\\b(?:…)\\b` mataba todos los patrones con símbolos.

Encontrado el 2026-08-29 investigando por qué no se detectó «Have Passport or id
i pay you 500$». Al mirar las señales una por una salió algo mayor: **ningún
importe con símbolo de moneda casaba**. Ni `$500`, ni `500€`, ni `500$`.

La causa está en cómo se compilaban las listas:

    \\b(?:…|\\d+\\s*[€$]|[€$]\\s*\\d+|…)\\b

`\\b` exige una frontera de palabra pegada al símbolo, y ahí no puede haberla:
`$` no es carácter de palabra, así que junto a un espacio o al final de línea no
hay transición que valga. La señal de dinero de `commercial_ad` llevaba muerta en
silencio, y el `CLAUDE.md` afirmaba lo contrario («el importe se escribe distinto
por región: `500€` detrás y `$500` delante, ambas formas soportadas») porque los
tests usaban importes en palabra («500 euros», «500 USD»), que sí pasan el `\\b`.

El arreglo son lookarounds `(?<!\\w)…(?!\\w)`: para una palabra se comportan igual
que `\\b`, pero no exigen una transición imposible junto a un símbolo.
"""
import pytest

from src.wordlists import compile_alternation


@pytest.mark.parametrize("texto", ["500$", "$500", "500€", "€500", "500 €", "1.500€"])
def test_los_importes_con_simbolo_casan(texto):
    rx = compile_alternation([r"\d[\d.,]*\s*[€$]", r"[€$]\s*\d[\d.,]*"])
    assert rx.search(texto), f"{texto!r} no casa: vuelve el fallo del \\b"


def test_dentro_de_una_frase_tambien():
    rx = compile_alternation([r"\d[\d.,]*\s*[€$]"])
    assert rx.search("te pago 500€ por el trabajo")


def test_una_palabra_sigue_sin_casar_dentro_de_otra():
    """Lo que el `\\b` protegía y no se puede perder: `bet` no puede casar dentro
    de «Roberto» ni de «betún»."""
    rx = compile_alternation(["bet"])
    assert not rx.search("Roberto")
    assert not rx.search("betún")
    assert rx.search("una bet online")


def test_los_numeros_pegados_tampoco():
    rx = compile_alternation(["500"])
    assert not rx.search("2500")
    assert not rx.search("5001")
    assert rx.search("son 500 euros")


def test_sin_boundaries_se_comporta_igual_que_antes():
    """El chino y el japonés no separan palabras con espacios: esas listas se
    compilan sin envoltorio y no pueden cambiar."""
    rx = compile_alternation(["洗钱"], boundaries=False)
    assert rx.search("恒泰集团招洗钱车队")


def test_el_envoltorio_no_usa_b_pelado():
    """La costura: si alguien vuelve a `\\b(?:…)\\b`, los símbolos mueren otra vez."""
    from src.wordlists import _wrap
    envuelto = _wrap("x", boundaries=True)
    assert envuelto.startswith("(?<!"), envuelto
    assert not envuelto.startswith(r"\b"), "vuelve el fallo de los símbolos"


def test_el_caso_real_completo():
    """El mensaje que se coló, de punta a punta."""
    from types import SimpleNamespace as NS
    from src.detectors import commercial_ad
    texto = ("People from Europe, uk, usa,  come for work\n"
             "Have Passport or id i pay you 500$\n"
             "Only one person i need")
    msg = NS(text=texto, caption=None, entities=(), caption_entities=(),
             reply_to_message=None)
    hit = commercial_ad.check(msg, is_first_msg=True)
    assert hit and hit.score >= 100, f"puntúa {hit.score if hit else 0}, no llega a ban"


@pytest.mark.parametrize("texto", [
    "Alguien sabe si necesito el pasaporte para viajar a Londres o vale el DNI?",
    "Me han pedido el pasaporte y una foto para el registro del hotel, es normal?",
    "I have a passport question, do I need a visa for Spain as a UK citizen?",
    "Vengo a trabajar a Madrid el mes que viene, alguna recomendacion de barrio?",
    "People from Europe usually prefer this brand, at least in my experience",
])
def test_hablar_de_pasaportes_o_de_trabajo_no_es_spam(texto):
    """Anti-FP del vocabulario nuevo: lo inequívoco no es «passport», que es una
    palabra normal, sino pedirlo JUNTO A un pago. Todos los patrones nuevos son
    compuestos por eso."""
    from types import SimpleNamespace as NS
    from src.detectors import commercial_ad
    msg = NS(text=texto, caption=None, entities=(), caption_entities=(),
             reply_to_message=None)
    assert not commercial_ad.check(msg, is_first_msg=True)
