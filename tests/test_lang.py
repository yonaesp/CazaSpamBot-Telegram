"""Tests heurística español."""
from src.lang import likely_spanish


def test_short_text_returns_false():
    assert not likely_spanish("")
    assert not likely_spanish("hi")
    assert not likely_spanish(None)


def test_with_accents_or_n():
    assert likely_spanish("Hola compañero")
    assert likely_spanish("¿Qué tal estás?")
    assert likely_spanish("España es un país increíble")


def test_with_stopwords():
    assert likely_spanish("hola que tal alguien sabe esto")
    assert likely_spanish("muy bien gracias")


def test_english_returns_false():
    assert not likely_spanish("hello bro check this out cool stuff")
    assert not likely_spanish("come and join this awesome group right now")


def test_random_letters_returns_false():
    assert not likely_spanish("xkcd abcdef ghijkl")


def test_mixed_with_one_spanish_stopword():
    """Con al menos 1 stopword debería ser español."""
    assert likely_spanish("hello que pasa amigo")  # 'que' es stopword
