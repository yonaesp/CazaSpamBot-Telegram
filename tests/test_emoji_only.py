"""Tests para emoji_only_first_msg detector."""
from types import SimpleNamespace
from src.detectors import emoji_only as det


def _msg(text):
    return SimpleNamespace(text=text, caption=None)


def test_emoji_only_dispara():
    hit = det.check(_msg("🍭🍄 🌟🎨 🌃🌃"), is_first_msg=True)
    assert hit is not None and hit.score >= 45


def test_no_primer_msg_no_dispara():
    hit = det.check(_msg("🍭🍄🌟🎨🌃"), is_first_msg=False)
    assert hit is None or hit.score == 0


def test_texto_real_con_emojis_no_dispara():
    # "jajaja" + emojis = texto real, legítimo
    hit = det.check(_msg("jajaja qué bueno 😂😂😂"), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_saludo_con_emoji_no_dispara():
    hit = det.check(_msg("hola buenas 👋"), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_pocos_emojis_no_dispara():
    hit = det.check(_msg("👍"), is_first_msg=True)
    assert hit is None or hit.score == 0
