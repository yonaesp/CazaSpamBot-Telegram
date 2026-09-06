"""Tests para detector forward_first_msg."""
from __future__ import annotations

from types import SimpleNamespace

from src.detectors import forward_first_msg as det


def _msg(forward_from_chat=None, forward_from=None, forward_sender_name=None, forward_origin=None):
    return SimpleNamespace(
        forward_from_chat=forward_from_chat,
        forward_from=forward_from,
        forward_sender_name=forward_sender_name,
        forward_origin=forward_origin,
    )


def test_no_forward_returns_none():
    hit = det.check(_msg(), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_not_first_msg_outside_window_returns_none():
    fwd_chat = SimpleNamespace(type="channel", username="spamchan", title="Spam")
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=False, seconds_since_first_seen=600)
    assert hit is None or hit.score == 0


def test_forward_from_channel_first_msg_bans():
    fwd_chat = SimpleNamespace(type="channel", username="飞哥收款赚几千", title="飞哥收款赚几千")
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=True)
    assert hit is not None
    assert hit.rule == "forward_first_msg"
    assert hit.score == 100
    assert "CANAL" in hit.reason
    assert hit.payload["origin_type"] == "channel"


def test_forward_from_bot_first_msg_bans():
    fwd_user = SimpleNamespace(is_bot=True, username="spambot", first_name="SpamBot")
    hit = det.check(_msg(forward_from=fwd_user), is_first_msg=True)
    assert hit is not None
    assert hit.score == 95
    assert hit.payload["origin_type"] == "bot"


def test_forward_from_user_first_msg_kicks():
    fwd_user = SimpleNamespace(is_bot=False, username="someone", first_name="Someone")
    hit = det.check(_msg(forward_from=fwd_user), is_first_msg=True)
    assert hit is not None
    assert hit.score == 80


def test_forward_in_early_window_after_first_msg():
    fwd_chat = SimpleNamespace(type="channel", username="x", title="x")
    # is_first_msg=False pero dentro de 3 min
    hit = det.check(_msg(forward_from_chat=fwd_chat), is_first_msg=False, seconds_since_first_seen=100)
    assert hit is not None
    assert hit.score >= 70


def test_forward_hidden_user():
    hit = det.check(_msg(forward_sender_name="Anonimo"), is_first_msg=True)
    assert hit is not None
    assert hit.payload["origin_type"] == "hidden_user"
    assert hit.score == 80


def test_forward_origin_ptb21_channel():
    """PTB ≥21 usa forward_origin con type='channel'."""
    chat = SimpleNamespace(username="evilch", title="EvilChan")
    origin = SimpleNamespace(type="channel", chat=chat)
    hit = det.check(_msg(forward_origin=origin), is_first_msg=True)
    assert hit is not None
    assert hit.score == 100
    assert hit.payload["origin_type"] == "channel"
    assert hit.payload["origin_name"] == "evilch"


# --- Reenviarse un mensaje PROPIO no es traer contenido de fuera ---------------
#
# Caso real (7-sep-2026, Windows 11): «Kleo» entró, se verificó y reenvió un
# mensaje SUYO con la captura de una compra y 165 caracteres preguntando si la
# licencia era retail. Sumó 80 aquí + 70 en `first_msg_media` = 150 → ban federado
# en los cuatro grupos y reporte a Telegram, sin una sola regla de contenido.
# Medido en los 15 casos del histórico: este detector solo ha acertado con origen
# CANAL (7 de 7); con origen usuario no ha cazado nunca nada.

def _msg_de(autor_id: int, nombre: str = "Kleo", **kw):
    m = _msg(**kw)
    m.from_user = SimpleNamespace(id=autor_id, first_name=nombre, last_name=None)
    return m


def test_reenvio_de_uno_mismo_no_puntua_legacy():
    yo = SimpleNamespace(is_bot=False, id=8409186137, username="kakermalicioso",
                         first_name="Kleo")
    hit = det.check(_msg_de(8409186137, forward_from=yo), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_reenvio_de_uno_mismo_no_puntua_forward_origin():
    yo = SimpleNamespace(is_bot=False, id=8409186137, username="kakermalicioso",
                         first_name="Kleo")
    origen = SimpleNamespace(type="user", sender_user=yo)
    hit = det.check(_msg_de(8409186137, forward_origin=origen), is_first_msg=True)
    assert hit is None or hit.score == 0


def test_reenvio_de_OTRO_usuario_sigue_puntuando():
    otro = SimpleNamespace(is_bot=False, id=999, username="otro", first_name="Otro")
    hit = det.check(_msg_de(8409186137, forward_from=otro), is_first_msg=True)
    assert hit is not None and hit.score == 80


def test_la_exencion_no_alcanza_a_los_canales():
    """Aunque el canal se llame como él: el patrón fuerte es el canal, y sigue."""
    canal = SimpleNamespace(type="channel", username="Kleo", title="Kleo")
    hit = det.check(_msg_de(8409186137, forward_from_chat=canal), is_first_msg=True)
    assert hit is not None and hit.score == 100


def test_reenvio_propio_con_privacidad_activada_no_puntua():
    """Sin id que comparar, Telegram solo deja el nombre visible."""
    hit = det.check(_msg_de(8409186137, "Kleo", forward_sender_name="Kleo"),
                    is_first_msg=True)
    assert hit is None or hit.score == 0


def test_usuario_oculto_con_OTRO_nombre_sigue_puntuando():
    hit = det.check(_msg_de(8409186137, "Kleo", forward_sender_name="Otra Persona"),
                    is_first_msg=True)
    assert hit is not None and hit.score == 80
