"""El vocabulario de investment_scam es editable desde config/blacklist/.

Las tres listas de vocabulario (praise, cta, vocab) se cargan con
`load_and_compile`, igual que las de commercial_ad. Aquí se fija que:

- sin los archivos, los defaults en código reproducen el comportamiento actual
  (la estafa se sigue cazando idéntico, incluida la variante en inglés);
- un patrón añadido a un archivo se recoge en caliente;
- un regex inválido en un archivo se ignora sin tumbar la carga ni el detector.

NO se toca el ancla numérica («di X, me devolvieron Y»): esa es lógica del
núcleo, no vocabulario, y no debe ser editable.
"""
from types import SimpleNamespace as NS

import pytest

from src import wordlists
from src.detectors import investment_scam as inv
from src.i18n import set_lang

# Caso real en inglés: el testimonio que originó el detector.
_CASO_REAL_EN = (
    "Mrs RafaelMarrero7 has been so good to me. I gave her 25,000 Rs, and after "
    "12 hours, she gave me 318,000Rs."
)


def _msg(text: str):
    return NS(text=text, caption=None, entities=[], caption_entities=[])


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    """Idioma español fijo y caché de patrones limpia entre tests.

    El _BLACKLIST_DIR apunta por defecto a un tmp VACÍO: así cada test parte de
    los defaults del código y decide qué archivos poner. Sin limpiar la caché,
    los patrones compilados de un test contaminarían al siguiente.
    """
    set_lang("es")
    monkeypatch.setattr(wordlists, "_BLACKLIST_DIR", tmp_path)
    wordlists.clear_cache()
    yield
    wordlists.clear_cache()
    set_lang("es")


# ---------- sin archivos: los defaults reproducen el comportamiento ----------

def test_sin_archivos_usa_defaults_y_caza_la_estafa():
    """Con el directorio vacío (defaults en código) la estafa en inglés cae igual."""
    assert inv.check(_msg(_CASO_REAL_EN), is_first_msg=True).score >= 60


def test_sin_archivos_no_hay_falso_positivo():
    """Y una conversación normal sobre dinero sigue sin disparar."""
    normal = "I paid $500 for my GPU last year and it was worth every cent honestly"
    assert inv.check(_msg(normal), is_first_msg=True).score == 0


def test_defaults_cubren_los_tres_grupos_de_vocabulario():
    """praise, cta y vocab funcionan solo con los defaults (sin config/)."""
    assert inv._praise_re().search("she has been so good to me")
    assert inv._cta_re().search("DM her now")
    assert inv._cta_re().search("mira 👇")  # el emoji va fuera del \b
    assert inv._vocab_re().search("guaranteed profit")


# ---------- un patrón añadido a un archivo se recoge ----------

def test_patron_praise_anadido_se_recoge(tmp_path):
    """Un elogio nuevo escrito en el archivo hace saltar un testimonio que sin él
    solo tendría el ancla (1 señal) y no llegaría al umbral."""
    texto = "Le di 1000 y me devolvió 9000, mi socio mágico"
    # Sin el archivo: solo ancla, no basta.
    assert inv.check(_msg(texto), is_first_msg=True).score == 0
    # Con el elogio nuevo en el archivo: ancla + praise -> cae.
    (tmp_path / "investment_praise.txt").write_text(
        "mi\\s+socio\\s+m[aá]gico\n", encoding="utf-8",
    )
    wordlists.clear_cache()
    assert inv.check(_msg(texto), is_first_msg=True).score >= 60


def test_patron_vocab_anadido_se_recoge(tmp_path):
    """Igual con el vocabulario de reclutamiento."""
    texto = "Deposité 500 y gané 8000 con este esquema ponzi premium"
    assert inv.check(_msg(texto), is_first_msg=True).score == 0
    (tmp_path / "investment_vocab.txt").write_text(
        "esquema\\s+ponzi\\s+premium\n", encoding="utf-8",
    )
    wordlists.clear_cache()
    assert inv.check(_msg(texto), is_first_msg=True).score >= 60


# ---------- un regex inválido no rompe la carga ----------

def test_regex_invalido_en_archivo_no_rompe_la_carga(tmp_path):
    """Un paréntesis sin cerrar se descarta; los patrones válidos siguen activos
    y el detector no se cae."""
    (tmp_path / "investment_vocab.txt").write_text(
        "(sin cerrar\nesquema\\s+ponzi\\s+premium\n", encoding="utf-8",
    )
    wordlists.clear_cache()
    rx = inv._vocab_re()  # no debe lanzar
    assert rx.search("esquema ponzi premium")
    texto = "Deposité 500 y gané 8000 con este esquema ponzi premium"
    assert inv.check(_msg(texto), is_first_msg=True).score >= 60
