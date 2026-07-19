"""Monedas de otras regiones y patrones editables de `commercial_ad`.

Los importes, la periodicidad, la urgencia y el scam de trabajo doméstico ya no
están cableados en el código: salen de `config/blacklist/`, así que un admin
argentino, brasileño o polaco puede meter SU moneda sin tocar Python.

El grueso de este archivo es anti falso positivo. Varios nombres de moneda son
palabras corrientes (peso, real, sol, libra, corona) y varios códigos ISO son
palabras inglesas (TRY, CUP, COP, PEN): si se cuelan sueltos, el bot empieza a
banear a gente que habla de recetas, del tiempo o del peso de un paquete.
"""
import re

import pytest

from src import wordlists
from src.detectors import bio_spam
from src.detectors import commercial_ad as ca
from src.i18n import set_lang


def _msg(text: str):
    from types import SimpleNamespace as NS
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _limpia_cache():
    """Las listas se cachean por idioma y directorio; que no se contaminen."""
    wordlists.clear_cache()
    ca._PERIODIC_CACHE.clear()
    yield
    wordlists.clear_cache()
    ca._PERIODIC_CACHE.clear()
    set_lang("es")


# ---------- importes de cada región ----------

@pytest.mark.parametrize("texto", [
    # Latinoamérica: símbolo delante (lo normal allí) y código ISO detrás
    "$5000 ARS", "20000 ARS", "1500 MXN", "$1.500 MXN", "2000000 COP",
    "850000 CLP", "45000 UYU", "1500 PEN", "S/ 1500", "S/1.500",
    "R$ 2.000", "R$2000", "1500 BRL", "500 reais", "2000 reales",
    "3000 soles", "500 bolívares", "1500000 guaraníes", "800 quetzales",
    "12000 lempiras", "9000 córdobas", "50000 colones", "15000 pesos",
    # Europa
    "250 £", "£250", "1500 CHF", "1'500 CHF", "2000 zł", "35000 Kč",
    "15000 SEK", "12000 NOK", "9000 DKK", "450000 HUF", "8000 RON",
    "50000 RUB", "₽50000", "30000 UAH", "2000 francos suizos",
    "800 libras esterlinas", "15000 coronas suecas",
    # Otras
    "50000 INR", "₹50000", "300000 JPY", "¥300000", "5000 CNY", "20000 ZAR",
    # Cripto usada como moneda en el spam
    "5000 USDT", "2000 USDC",
])
def test_importes_regionales_reconocidos(texto):
    assert ca.money_re().search(texto), f"no reconoce el importe {texto!r}"


@pytest.mark.parametrize("texto", [
    # Bug latente que había: un importe de 4+ cifras SIN separador de miles y
    # con el símbolo detrás no casaba con ninguna alternativa.
    "5000€", "5000 €", "2000€", "12500 €",
])
def test_importes_de_cuatro_cifras_sin_separador(texto):
    assert ca.money_re().search(texto), f"no reconoce el importe {texto!r}"


@pytest.mark.parametrize("texto", [
    "20000 ARS al mes", "1500 MXN mensuales", "R$ 2.000 por mês",
    "S/ 1500 mensuales", "3000 soles al mes", "2000 zł semanales",
    "50000 RUB semanal", "15000 pesos diarios", "500 reais por semana",
])
def test_periodicidad_con_monedas_regionales(texto):
    assert ca._periodic_money_re().search(texto), f"no reconoce {texto!r}"


# ---------- anti falso positivo (lo importante) ----------

# Palabras de moneda usadas en su sentido normal. NINGUNA debe casar.
FRASES_LEGITIMAS = [
    # nombres de moneda que son palabras corrientes
    "el peso del paquete es de 20 kilos, así que no lo puedo subir yo solo",
    "mi hermano pesa 80 kilos y mide 1,90, es un armario ropero",
    "los 2 pesos pesados del sector se han fusionado esta semana",
    "hace un sol increíble hoy, 30 grados a la sombra y sin una nube",
    "necesito media libra de harina para la receta de galletas de mi abuela",
    "me pusieron la corona del diente ayer y todavía me duele bastante",
    "esto es real, lo he visto con mis propios ojos esta misma mañana",
    "he visto 20 casos reales de este fallo en el foro oficial de soporte",
    "en 2020 lei un libro buenísimo sobre la historia de la informática",
    "el franco suizo y el euro llevan meses moviéndose casi igual",
    # códigos ISO que en minúscula son palabras inglesas normales
    "add 2 cup of flour and 3 tablespoons of sugar, then mix it well",
    "there were 20 cop cars outside the stadium after the match ended",
    "the shelf is 20 ft long and 3 ft wide, it should fit in the corner",
    "level 10 try again, the boss fight is way harder than the previous one",
    "I bought 3 pen drives and 2 usb hubs for the new office setup",
    "my bob build has 40 ron of resistance, whatever that means in this game",
    # cifras sin moneda ninguna
    "el partido acabó 3 a 2 y fueron 90 minutos de sufrimiento absoluto",
    "la actualización pesa 4 gb y tarda unos 20 minutos en instalarse",
]


@pytest.mark.parametrize("texto", FRASES_LEGITIMAS)
def test_palabras_comunes_no_son_importes(texto):
    match = ca.money_re().search(texto)
    assert match is None, f"falso positivo: {texto!r} casa con {match.group()!r}"


@pytest.mark.parametrize("texto", FRASES_LEGITIMAS)
def test_frases_legitimas_no_disparan_el_detector(texto):
    for lang in ("es", "en"):
        set_lang(lang)
        wordlists.clear_cache()
        assert ca.check(_msg(texto)).score == 0, f"falso positivo en {lang}: {texto!r}"


def test_urgencia_no_dispara_sola():
    """La urgencia suma 10: por sí sola nunca llega al umbral de 60."""
    assert ca.check(_msg("Necesito ayuda URGENTE con el portátil, no arranca")).score == 0


# ---------- las listas son editables de verdad ----------

def _dir_listas(monkeypatch, tmp_path):
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    wordlists.clear_cache()
    ca._PERIODIC_CACHE.clear()
    return tmp_path


def test_admin_puede_anadir_su_moneda(monkeypatch, tmp_path):
    """Una moneda inventada por el admin funciona sin tocar código."""
    d = _dir_listas(monkeypatch, tmp_path)
    assert not ca.money_re().search("300 dracmas")
    (d / "commercial_money.txt").write_text(r"\b\d+\s*dracmas\b" + "\n", encoding="utf-8")
    wordlists.clear_cache()
    ca._PERIODIC_CACHE.clear()
    assert ca.money_re().search("300 dracmas")
    # y la periodicidad se compone sola con la lista nueva, sin repetir la moneda
    assert ca._periodic_money_re().search("300 dracmas al mes")


def test_admin_puede_anadir_urgencia_y_domestico(monkeypatch, tmp_path):
    d = _dir_listas(monkeypatch, tmp_path)
    (d / "commercial_urgency.txt").write_text("corre\\s+que\\s+vuela\n", encoding="utf-8")
    (d / "commercial_domestic.txt").write_text("plancha[rn]?\\s+camisas\n", encoding="utf-8")
    wordlists.clear_cache()
    assert ca._urgency_re().search("corre que vuela, que se acaba")
    assert ca._domestic_re().search("busco a alguien para planchar camisas")


def test_lista_vacia_cae_a_los_defaults(monkeypatch, tmp_path):
    """Sin config/, el bot sigue protegido con los defaults del código."""
    _dir_listas(monkeypatch, tmp_path)
    assert ca.money_re().search("2.000 €")
    assert ca._periodic_money_re().search("$500/day")
    assert ca._urgency_re().search("es URGENTE")
    assert ca._domestic_re().search("busco persona responsable para el puesto")


def test_patron_de_moneda_invalido_no_tumba_el_bot(monkeypatch, tmp_path):
    d = _dir_listas(monkeypatch, tmp_path)
    (d / "commercial_money.txt").write_text("(roto\n\\b\\d+\\s*dracmas\\b\n", encoding="utf-8")
    wordlists.clear_cache()
    assert ca.money_re().search("300 dracmas")


def test_bio_spam_usa_la_misma_lista_de_monedas(monkeypatch, tmp_path):
    """Añadir la moneda una vez vale para los dos detectores."""
    d = _dir_listas(monkeypatch, tmp_path)
    (d / "commercial_money.txt").write_text(r"\b\d+\s*dracmas\b" + "\n", encoding="utf-8")
    wordlists.clear_cache()
    assert bio_spam._money_re().search("gano 300 dracmas")


# ---------- las listas del repo son sanas ----------

def test_listas_sin_boundaries_compilan_juntas():
    """Los patrones de importe/periodicidad se concatenan: deben compilar."""
    for rx in (ca.money_re(), ca._periodic_terms_re(), ca._periodic_money_re()):
        assert isinstance(rx, re.Pattern)
    assert ca._periodic_money_re().groups == 0, "no puede haber grupos capturantes"


def test_spam_latinoamericano_completo_se_detecta():
    """Anuncio con la estructura de siempre pero en pesos: debe caer igual."""
    hit = ca.check(_msg(
        "🚀 ¡TRABAJO DESDE CASA URGENTE!\n"
        "💰 Ganás 150000 ARS por semana\n"
        "📲 Contáctame ahora https://t.me/joinchat/xyz"
    ))
    assert hit.score >= 60, f"spam evidente en pesos no detectado (score={hit.score})"
