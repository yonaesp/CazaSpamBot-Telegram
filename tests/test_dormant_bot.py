"""Tests dormant_bot_mention."""
import time
from types import SimpleNamespace
from src.detectors import dormant_bot_mention as det


def _msg(text, reply=None):
    return SimpleNamespace(text=text, caption=None, entities=[], caption_entities=[], reply_to_message=reply)


def test_dormida_menciona_bot_spam_dispara():
    hit = det.check(_msg("@aunimwfcbot mirad"), last_msg_ts=time.time()-400*86400)
    assert hit is not None and hit.score >= 100


def test_dormida_menciona_bot_LEGITIMO_no_dispara():
    hit = det.check(_msg("@GroupHelpBot ayuda por favor"), last_msg_ts=time.time()-400*86400)
    assert hit is None or hit.score == 0


def test_usuario_activo_no_dispara():
    hit = det.check(_msg("@xbot hola"), last_msg_ts=time.time()-86400)
    assert hit is None or hit.score == 0


def test_respuesta_no_dispara():
    hit = det.check(_msg("@spambot", reply=SimpleNamespace(message_id=1)), last_msg_ts=time.time()-400*86400)
    assert hit is None or hit.score == 0


def test_sin_historial_no_dispara():
    hit = det.check(_msg("@spambot"), last_msg_ts=None)
    assert hit is None or hit.score == 0
