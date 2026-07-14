"""Tests del detector external_reply: promoción de canal externo vía cita a otro chat."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import external_reply


def _msg(chat_type="channel", username="Forexrading120", title="FX GREEN PIPS", chat_id=-100999):
    er = SimpleNamespace(chat=SimpleNamespace(type=chat_type, username=username,
                                              title=title, id=chat_id))
    return SimpleNamespace(external_reply=er)


def test_cita_canal_externo_primer_mensaje_dispara():
    """El caso real: primer mensaje que cita @Forexrading120 (canal externo público)."""
    hit = external_reply.check(_msg(), is_first_msg=True)
    assert hit
    assert hit.rule == "external_quote_channel"
    assert hit.score == 80
    assert hit.payload["channel"] == "Forexrading120"


def test_sin_external_reply_no_dispara():
    assert not external_reply.check(SimpleNamespace(external_reply=None), is_first_msg=True)


def test_canal_privado_sin_username_no_dispara():
    """Cita a un canal privado (sin @) no es 'unible por el enlace': señal débil."""
    assert not external_reply.check(_msg(username=None), is_first_msg=True)


def test_cita_a_chat_moderado_no_dispara():
    """Si citamos uno de NUESTROS grupos, no es promoción externa."""
    hit = external_reply.check(_msg(chat_id=-100123), is_first_msg=True,
                               is_moderated_chat=lambda cid: cid == -100123)
    assert not hit


def test_no_primer_mensaje_baja_score():
    hit = external_reply.check(_msg(), is_first_msg=False)
    assert hit and hit.score == 35


def test_cita_a_usuario_no_canal_no_dispara():
    assert not external_reply.check(_msg(chat_type="private"), is_first_msg=True)
