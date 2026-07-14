"""Tests del detector contact_spam: contactos compartidos con reclamo de spam."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import contact_spam

ALLOWED = ["latin"]
THRESHOLD = 0.30


def _msg(contact):
    return SimpleNamespace(contact=contact)


def _contact(first="", last="", phone="+34600000000", vcard=""):
    return SimpleNamespace(first_name=first, last_name=last, phone_number=phone, vcard=vcard)


def test_nombre_chino_dispara():
    """El caso real: contacto cuyo nombre es el anuncio en chino (apuestas)."""
    msg = _msg(_contact(first="赛车.六合彩.PC28", phone="+972529270792"))
    hit = contact_spam.check(msg, ALLOWED, THRESHOLD)
    assert hit
    assert hit.rule == "contact_spam"
    assert hit.score >= 80


def test_nombre_con_enlace_dispara():
    msg = _msg(_contact(first="Ofertas", last="t.me/canalspam"))
    hit = contact_spam.check(msg, ALLOWED, THRESHOLD)
    assert hit
    assert hit.score == 90


def test_vcard_con_handle_dispara():
    vcard = "BEGIN:VCARD\nFN:Promo\nTEL:+34600\nURL:https://wa.me/34600\nEND:VCARD"
    msg = _msg(_contact(first="Promo", vcard=vcard))
    assert contact_spam.check(msg, ALLOWED, THRESHOLD)


def test_contacto_latino_normal_no_dispara():
    """Anti-FP: compartir el contacto de un amigo con nombre normal no es spam."""
    msg = _msg(_contact(first="María", last="García López"))
    assert not contact_spam.check(msg, ALLOWED, THRESHOLD)


def test_mensaje_sin_contacto_no_dispara():
    msg = SimpleNamespace(contact=None)
    assert not contact_spam.check(msg, ALLOWED, THRESHOLD)


def test_arabe_permitido_no_dispara_si_esta_en_allowed():
    """Si el grupo permite árabe, un contacto árabe no debe dispararse."""
    msg = _msg(_contact(first="محمد", last="علي"))
    assert not contact_spam.check(msg, ["latin", "arabic"], THRESHOLD)
