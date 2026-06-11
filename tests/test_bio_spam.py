"""Tests para detector bio_spam."""
from __future__ import annotations

from src.detectors import bio_spam as det


CASE_REAL = "Hier geht's zu mir😈:https://t.me/+Th8CEkvfiWw0ODNk 🔥🥵"


def test_caso_real_aleman_invite_emojis_dispara():
    hit = det.check(CASE_REAL)
    assert hit is not None
    assert hit.rule == "bio_spam"
    assert hit.score >= 60


def test_bio_normal_no_dispara():
    assert det.check("Hola, soy Juan de Madrid. Me gusta la tecnología.") is None or det.check("Hola, soy Juan").score == 0


def test_bio_vacia_no_dispara():
    assert det.check(None) is None or det.check(None).score == 0
    assert det.check("").score == 0 if det.check("") else True


def test_bio_solo_link_no_invite():
    hit = det.check("Mira mi canal: https://t.me/elgrupobueno")
    # solo link t.me no invite + sin más señales = 25 pts no dispara
    assert hit is None or hit.score == 0


def test_bio_invite_solo_no_dispara():
    """Solo el invite link (35 pts) sin más señales no llega a 60."""
    hit = det.check("Únete: https://t.me/+abc123XYZ")
    assert hit is None or hit.score == 0


def test_onlyfans_keyword_dispara():
    """Keyword onlyfans + URL = ban."""
    hit = det.check("Subscribe to my OnlyFans https://onlyfans.com/mia 💋")
    assert hit is not None
    assert hit.score >= 60


def test_crypto_signal_dispara():
    hit = det.check("Crypto trading signals 100% win rate https://t.me/+xyz")
    assert hit is not None


def test_bio_money_cta_idioma_dispara():
    hit = det.check("Hier geht's zu mir, gana 5000€/mes, contáctame ya https://t.me/+xyz")
    assert hit is not None
    assert hit.score >= 60


def test_bio_legitima_con_url_propio_no_dispara():
    """Bio con URL propio (web personal) sin otras señales — score muy bajo."""
    hit = det.check("Soy Marta, mi web: https://martagomez.es")
    assert hit is None or hit.score == 0


def test_bio_corta_no_evalua():
    assert det.check("hi") is None or det.check("hi").score == 0


def test_caso_johanna_aleman_geil():
    """Bio alemán adulto con invite + emojis (caso Johanna 2026-06-03)."""
    hit = det.check("Mehr von der geilen Lea💦: https://t.me/+Th8CEkvfiWw0ODNk 😈")
    assert hit is not None
    assert hit.score >= 60


def test_caso_hacking_bio_web_externa():
    """Bio de servicios de hacking + web externa + CTA (caso CHRIST WHITE HACK 2026-06-07)."""
    bio = (
        "un experto en materia de piratería informática"
        "☆☆https://christwhite.websites.co.in/☆ Puedes consultar el sitio"
    )
    hit = det.check(bio)
    assert hit is not None
    assert hit.rule == "bio_spam"
    assert hit.score >= 60
    assert "hacking" in hit.reason


def test_bio_legit_con_web_no_dispara():
    """Bio normal con web/blog personal NO debe disparar (anti-FP)."""
    for legit in (
        "Me gusta la informática y Alexa. Visita mi blog https://miblog.com",
        "Desarrollador de software. https://github.com/usuario",
        "Aficionado a la ciberseguridad y al hardware",
    ):
        hit = det.check(legit)
        assert hit is None or hit.score < 60, legit
