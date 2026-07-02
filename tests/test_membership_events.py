"""Tests de clasificación de eventos de membresía (ban/kick vs self-leave).

Regresión del bug 2026-07-02: el bot notificaba "ban manual de admin" cuando un
usuario se iba por su cuenta (self-leave). El evento ChatMemberUpdated con
new_status=LEFT no separa self-leave (actor == afectado) de kick (actor != afectado).
"""
from __future__ import annotations

from telegram.constants import ChatMemberStatus as S

from src.handlers import _is_admin_ban_or_kick, _is_join

BOT = 1000
ADMIN = 2000
USER = 3000


# --- _is_join: detección de entrada al grupo ---

def test_join_normal():
    assert _is_join(S.LEFT, S.MEMBER, None) is True
    assert _is_join(None, S.MEMBER, None) is True
    assert _is_join(S.BANNED, S.MEMBER, None) is True  # reentra tras desban


def test_join_directo_a_restricted_es_join():
    """Otro bot mutea en el instante del join: →RESTRICTED con is_member=True.
    Antes se saltaba TODO el pipeline de entrada (bug 1.1 del audit)."""
    assert _is_join(S.LEFT, S.RESTRICTED, True) is True
    assert _is_join(None, S.RESTRICTED, True) is True


def test_restricted_fuera_no_es_join():
    """RESTRICTED con is_member=False = restringido y fuera, no es entrada."""
    assert _is_join(S.LEFT, S.RESTRICTED, False) is False


def test_unmute_no_es_join():
    """RESTRICTED→MEMBER (unmute) NO es un join (no re-welcome)."""
    assert _is_join(S.RESTRICTED, S.MEMBER, None) is False


def test_member_a_restricted_no_es_join():
    """MEMBER→RESTRICTED (mute de un ya-miembro) no es entrada."""
    assert _is_join(S.MEMBER, S.RESTRICTED, True) is False


def test_leave_no_es_join():
    assert _is_join(S.MEMBER, S.LEFT, None) is False


def test_self_leave_no_notifica():
    """Usuario se va solo (actor == afectado, →LEFT) → NO es ban/kick de admin."""
    assert _is_admin_ban_or_kick(S.MEMBER, S.LEFT, actor_id=USER, target_id=USER, bot_id=BOT) is False


def test_kick_por_admin_si_notifica():
    """Admin expulsa (actor != afectado, →LEFT) → sí."""
    assert _is_admin_ban_or_kick(S.MEMBER, S.LEFT, actor_id=ADMIN, target_id=USER, bot_id=BOT) is True


def test_ban_directo_por_admin_si_notifica():
    assert _is_admin_ban_or_kick(S.MEMBER, S.BANNED, actor_id=ADMIN, target_id=USER, bot_id=BOT) is True


def test_ban_por_el_bot_no_notifica():
    """Si el actor es el propio bot, no se notifica (es su propia acción)."""
    assert _is_admin_ban_or_kick(S.MEMBER, S.BANNED, actor_id=BOT, target_id=USER, bot_id=BOT) is False


def test_ban_desde_restricted_si_notifica():
    """Un usuario muteado (RESTRICTED) que un admin banea → sí."""
    assert _is_admin_ban_or_kick(S.RESTRICTED, S.BANNED, actor_id=ADMIN, target_id=USER, bot_id=BOT) is True


def test_self_leave_desde_restricted_no_notifica():
    """Usuario muteado que se va solo → self-leave, no notifica."""
    assert _is_admin_ban_or_kick(S.RESTRICTED, S.LEFT, actor_id=USER, target_id=USER, bot_id=BOT) is False


def test_actor_desconocido_no_notifica():
    """Sin actor conocido (from_user None) → no se asume ban."""
    assert _is_admin_ban_or_kick(S.MEMBER, S.LEFT, actor_id=None, target_id=USER, bot_id=BOT) is False
    assert _is_admin_ban_or_kick(S.MEMBER, S.BANNED, actor_id=None, target_id=USER, bot_id=BOT) is False


def test_join_no_es_ban():
    """Entrar (→MEMBER) no es ban/kick."""
    assert _is_admin_ban_or_kick(S.LEFT, S.MEMBER, actor_id=USER, target_id=USER, bot_id=BOT) is False


def test_unmute_no_es_ban():
    """RESTRICTED→MEMBER (unmute) no es ban/kick."""
    assert _is_admin_ban_or_kick(S.RESTRICTED, S.MEMBER, actor_id=ADMIN, target_id=USER, bot_id=BOT) is False


def test_unban_no_es_ban():
    """BANNED→LEFT (desbaneo: el estado pasa de banned a left) no debe notificar."""
    assert _is_admin_ban_or_kick(S.BANNED, S.LEFT, actor_id=ADMIN, target_id=USER, bot_id=BOT) is False
