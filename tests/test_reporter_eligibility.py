"""Tests para la whitelist + threshold de elegibilidad del reporter."""
from __future__ import annotations

from types import SimpleNamespace

from src.handlers import _is_reportable


def _dec(rule: str, score: int, action: str = "ban"):
    return SimpleNamespace(rule=rule, score=score, action=action)


def test_cas_match_always_reportable():
    assert _is_reportable(_dec("cas_match", 100)) is True


def test_lols_match_always_reportable():
    assert _is_reportable(_dec("lols_match", 100)) is True


def test_federation_known_ban_always_reportable():
    assert _is_reportable(_dec("federation_known_ban", 999)) is True


def test_url_blocklist_alone_NOT_reportable():
    """url_blocklist puede ser FP (un user pega un link legítimo extranjero)."""
    assert _is_reportable(_dec("url_blocklist", 100)) is False


def test_external_mention_alone_NOT_reportable():
    assert _is_reportable(_dec("external_mention_or_link", 130)) is False


def test_non_allowed_script_alone_NOT_reportable():
    """User bilingüe puede escribir en script no-latín legítimamente."""
    assert _is_reportable(_dec("non_allowed_script", 100)) is False


def test_first_msg_media_sola_NO_reportable_aunque_el_score_llegue():
    """Una regla de pura FORMA no basta para reportar a Telegram.

    Un reporte oficial quema la reputación de la cuenta secundaria. «Lleva foto»
    no dice nada de lo que el mensaje diga: hace falta al menos una regla que haya
    mirado el contenido o el perfil. Con una de contenido al lado, sí se reporta.
    """
    assert _is_reportable(_dec("first_msg_media", 150)) is False
    assert _is_reportable(_dec("first_msg_media", 300)) is False
    assert _is_reportable(_dec("commercial_ad+first_msg_media", 150)) is True


def test_first_msg_media_low_score_NOT_reportable():
    """Foto en primer msg con score bajo (sin suspicious) NO se reporta."""
    assert _is_reportable(_dec("first_msg_media", 100)) is False


def test_combined_rules_meet_threshold():
    """Combinación reglas + score >= 150 = reportable si una de ellas está en whitelist."""
    assert _is_reportable(_dec("external_mention_or_link+first_msg_media", 200)) is True


def test_combined_rules_below_threshold_NOT_reportable():
    assert _is_reportable(_dec("external_mention_or_link+first_msg_media", 120)) is False


def test_combined_rules_none_in_whitelist():
    """Aunque score alto, si ninguna regla está en whitelist, no reportar."""
    assert _is_reportable(_dec("external_mention_or_link+url_blocklist", 300)) is False


def test_forward_first_msg_solo_NO_reportable():
    assert _is_reportable(_dec("forward_first_msg", 100)) is False  # solo 100, < 150
    assert _is_reportable(_dec("forward_first_msg", 150)) is False  # pura forma
    # Caso real (7-sep-2026): «Kleo» sumó forward(80)+media(70) = 150 exactos y se
    # le reportó DOS VECES a Telegram por una pregunta sobre licencias de Windows.
    assert _is_reportable(_dec("forward_first_msg+first_msg_media", 150)) is False
    # Con una señal de contenido al lado vuelve a ser reportable.
    assert _is_reportable(_dec("non_allowed_script+forward_first_msg", 150)) is True


def test_reaction_farming_in_whitelist():
    assert _is_reportable(_dec("reaction_farming", 150)) is True
