"""Tests de la capa DB."""
from __future__ import annotations


def test_upsert_bot_chat_idempotent(tmp_db):
    tmp_db.upsert_bot_chat(-100123, "Grupo Test", "supergroup", True, True, True)
    tmp_db.upsert_bot_chat(-100123, "Grupo Test", "supergroup", True, True, True)
    assert tmp_db.admin_chats() == [-100123]


def test_record_message_increments(tmp_db):
    assert tmp_db.record_message(-100, 42, "alice") == 1
    assert tmp_db.record_message(-100, 42, "alice") == 2
    assert tmp_db.record_message(-100, 42, "alice") == 3


def test_record_join_creates_seen(tmp_db):
    tmp_db.record_join(-100, 42, "alice")
    row = tmp_db.get_seen(-100, 42)
    assert row is not None
    assert row["join_ts"] is not None
    assert row["msg_count"] == 0


def test_record_join_honra_hora_real_del_evento(tmp_db):
    """join_ts debe ser la hora REAL del evento (cmu.date), no la de proceso.

    Evita el falso positivo de jfm_delta: si el bot procesa el join tarde y se
    usara time.time(), el delta join→primer mensaje saldría falsamente corto.
    """
    real_join = 1_000_000.0  # hora del evento, muy anterior al "ahora"
    tmp_db.record_join(-100, 77, "bob", join_ts=real_join)
    row = tmp_db.get_seen(-100, 77)
    assert row["join_ts"] == real_join
    assert row["first_seen_ts"] == real_join


def test_ban_and_unban(tmp_db):
    tmp_db.add_ban(user_id=42, reason="spam", rule="cas_match", banned_in_chat=-100)
    assert tmp_db.is_banned(42)
    tmp_db.revoke_ban(42, revoked_by=999)
    assert not tmp_db.is_banned(42)


def test_username_map(tmp_db):
    tmp_db.remember_username("Alice", 42)
    assert tmp_db.resolve_username("@alice") == 42
    assert tmp_db.resolve_username("alice") == 42
    assert tmp_db.resolve_username("@BOB") is None


def test_suppression(tmp_db):
    tmp_db.suppress(42, "non_allowed_script", seconds=60)
    assert tmp_db.is_suppressed(42, "non_allowed_script")
    assert not tmp_db.is_suppressed(42, "url_blocklist")


def test_log_action_and_recent(tmp_db):
    aid = tmp_db.log_action(
        chat_id=-100, user_id=42, username="alice", message_id=1,
        rule="test", action="ban", score=100, mode="shadow",
        payload={"x": 1},
    )
    assert aid > 0
    row = tmp_db.get_action(aid)
    assert row is not None
    assert row["action"] == "ban"
    assert tmp_db.recent_actions(10)[0]["id"] == aid


def test_known_user_in_chat(tmp_db):
    assert not tmp_db.known_user_in_chat(-100, 42)
    tmp_db.record_message(-100, 42, None)
    assert tmp_db.known_user_in_chat(-100, 42)


def test_reactions_window(tmp_db):
    import time
    tmp_db.record_reaction(-100, 42, 1, ["👍"])
    tmp_db.record_reaction(-100, 42, 2, ["🔥"])
    tmp_db.record_reaction(-100, 42, 3, ["❤️"])
    # Ventana 60s atrás
    assert tmp_db.reactions_in_window(42, time.time() - 60) == 3
    # Ventana en el futuro
    assert tmp_db.reactions_in_window(42, time.time() + 60) == 0


def test_whitelist(tmp_db):
    assert not tmp_db.is_whitelisted(-100, 42)
    tmp_db.whitelist(-100, 42)
    assert tmp_db.is_whitelisted(-100, 42)


def test_cas_cache(tmp_db):
    assert tmp_db.cas_lookup(42, ttl=3600) is None
    tmp_db.cas_store(42, 3)
    assert tmp_db.cas_lookup(42, ttl=3600) == 3
    # TTL=0 expira inmediatamente
    assert tmp_db.cas_lookup(42, ttl=0) is None


def test_pending_welcomes_past_ttl_respeta_verified_at(tmp_db):
    """El barrido NO debe borrar el welcome de un usuario verificado recientemente
    aunque su join sea viejo (bug #1 del audit: anulaba VERIFIED_WELCOME_DELETE)."""
    import time as _t
    now = _t.time()
    tmp_db.add_pending_verification(-100, 1, welcome_msg_id=11, is_suspicious=False)  # sin verificar
    tmp_db.add_pending_verification(-100, 2, welcome_msg_id=22, is_suspicious=False)  # verificado reciente
    tmp_db.add_pending_verification(-100, 3, welcome_msg_id=33, is_suspicious=False)  # verificado viejo
    with tmp_db._cur() as c:
        c.execute("UPDATE pending_verifications SET joined_at=? WHERE chat_id=-100 AND user_id=1", (now - 2000,))
        c.execute("UPDATE pending_verifications SET joined_at=?, verified_at=? WHERE chat_id=-100 AND user_id=2", (now - 2000, now - 100))
        c.execute("UPDATE pending_verifications SET joined_at=?, verified_at=? WHERE chat_id=-100 AND user_id=3", (now - 3000, now - 2000))
    ids = {r["user_id"] for r in tmp_db.pending_welcomes_past_ttl(prompt_ttl_seconds=900, verified_ttl_seconds=1200)
           if r["chat_id"] == -100}
    assert 1 in ids        # sin verificar y join viejo → se barre
    assert 3 in ids        # verificado hace mucho → se barre
    assert 2 not in ids    # verificado hace 100s (< 1200) → NO se barre todavía


def test_admin_ban_abuse_counting(tmp_db):
    """Cuenta baneos por admin en ventana; dedup por target; no mezcla admins."""
    import time as _t
    now = _t.time()
    chat, admin = -100, 500
    for i, tid in enumerate([1, 2, 3, 4, 5]):
        tmp_db.record_admin_ban(chat, admin, tid, now - i * 60)   # 5 en ventana
    tmp_db.record_admin_ban(chat, admin, 6, now - 6 * 3600)       # viejo, fuera de 5h
    tmp_db.record_admin_ban(chat, admin, 1, now - 30)            # dup del target 1
    since = now - 5 * 3600
    bans = tmp_db.admin_bans_in_window(chat, admin, since)
    assert len(bans) == 5                                          # 5 únicos (dup no suma, viejo fuera)
    assert {r["target_id"] for r in bans} == {1, 2, 3, 4, 5}
    assert tmp_db.admin_bans_in_window(chat, 999, since) == []    # otro admin, nada


def test_bot_prefs_get_set(tmp_db):
    from src import notify_prefs
    assert tmp_db.get_pref("notify_manual_ban") is None       # sin fijar → None
    # sin pref, effective usa el default que le pasan
    assert notify_prefs.is_enabled(tmp_db, "manual_ban", True) is True
    assert notify_prefs.is_enabled(tmp_db, "manual_ban", False) is False
    # al fijar, la preferencia manda sobre el default
    tmp_db.set_pref("notify_manual_ban", False)
    assert tmp_db.get_pref("notify_manual_ban") is False
    assert notify_prefs.is_enabled(tmp_db, "manual_ban", True) is False
    tmp_db.set_pref("notify_manual_ban", True)
    assert notify_prefs.is_enabled(tmp_db, "manual_ban", False) is True


def test_pending_normal_past_hours(tmp_db):
    """Kick sin recordatorio: solo normales (no suspicious) sin verificar y viejos."""
    import time as _t
    now = _t.time()
    tmp_db.add_pending_verification(-100, 1, welcome_msg_id=None, is_suspicious=False)  # normal viejo
    tmp_db.add_pending_verification(-100, 2, welcome_msg_id=None, is_suspicious=True)   # suspicious → excluido
    tmp_db.add_pending_verification(-100, 3, welcome_msg_id=None, is_suspicious=False)  # normal reciente
    with tmp_db._cur() as c:
        c.execute("UPDATE pending_verifications SET joined_at=? WHERE chat_id=-100 AND user_id=1", (now - 10 * 3600,))
        c.execute("UPDATE pending_verifications SET joined_at=? WHERE chat_id=-100 AND user_id=2", (now - 10 * 3600,))
        c.execute("UPDATE pending_verifications SET joined_at=? WHERE chat_id=-100 AND user_id=3", (now - 1 * 3600,))
    ids = {r["user_id"] for r in tmp_db.pending_normal_past_hours(9)}
    assert ids == {1}
