"""SQLite schema + CRUD para auditoría, federación, reputación y reacciones.

Concurrencia: WAL + un solo writer (el handler async corre en un thread).
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS bot_chats (
    chat_id        INTEGER PRIMARY KEY,
    title          TEXT,
    username       TEXT,
    type           TEXT,
    am_admin       INTEGER NOT NULL DEFAULT 0,
    can_restrict   INTEGER NOT NULL DEFAULT 0,
    can_delete     INTEGER NOT NULL DEFAULT 0,
    added_at       REAL NOT NULL,
    updated_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_users (
    chat_id        INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    username       TEXT,
    first_seen_ts  REAL NOT NULL,
    join_ts        REAL,
    first_msg_ts   REAL,
    msg_count      INTEGER NOT NULL DEFAULT 0,
    reaction_count INTEGER NOT NULL DEFAULT 0,
    reputation     INTEGER NOT NULL DEFAULT 0,
    whitelisted    INTEGER NOT NULL DEFAULT 0,
    last_msg_id    INTEGER,
    last_msg_text  TEXT,
    last_msg_ts    REAL,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id        INTEGER PRIMARY KEY,
    reason         TEXT NOT NULL,
    rule           TEXT NOT NULL,
    banned_at      REAL NOT NULL,
    banned_in_chat INTEGER NOT NULL,
    federated      INTEGER NOT NULL DEFAULT 1,
    revoked_at     REAL,
    revoked_by     INTEGER
);

CREATE TABLE IF NOT EXISTS moderation_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL NOT NULL,
    chat_id        INTEGER NOT NULL,
    user_id        INTEGER,
    username       TEXT,
    message_id     INTEGER,
    rule           TEXT NOT NULL,
    action         TEXT NOT NULL,
    score          INTEGER NOT NULL DEFAULT 0,
    mode           TEXT NOT NULL,
    payload_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_modlog_ts      ON moderation_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_modlog_user    ON moderation_log(user_id);
CREATE INDEX IF NOT EXISTS idx_modlog_chat    ON moderation_log(chat_id, ts DESC);

CREATE TABLE IF NOT EXISTS reaction_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL NOT NULL,
    chat_id        INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    message_id     INTEGER NOT NULL,
    new_emojis     TEXT
);
CREATE INDEX IF NOT EXISTS idx_react_userts ON reaction_events(user_id, ts DESC);

CREATE TABLE IF NOT EXISTS cas_cache (
    user_id        INTEGER PRIMARY KEY,
    offenses       INTEGER NOT NULL DEFAULT 0,
    checked_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS username_map (
    username_lower TEXT PRIMARY KEY,
    user_id        INTEGER NOT NULL,
    updated_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS suppressions (
    user_id        INTEGER NOT NULL,
    rule           TEXT NOT NULL,
    suppressed_until REAL NOT NULL,
    PRIMARY KEY (user_id, rule)
);

CREATE TABLE IF NOT EXISTS learning_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_norm     TEXT NOT NULL,
    text_hash     TEXT NOT NULL,
    label         TEXT NOT NULL CHECK (label IN ('spam','ham')),
    added_by      INTEGER NOT NULL,
    chat_id       INTEGER,
    source_user   INTEGER,
    ts            REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_samples_hash_label ON learning_samples(text_hash, label);
CREATE INDEX IF NOT EXISTS idx_samples_label_ts ON learning_samples(label, ts DESC);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id                       INTEGER PRIMARY KEY,
    welcome_text                  TEXT,
    welcome_enabled               INTEGER NOT NULL DEFAULT 1,
    welcome_button_text           TEXT,
    welcome_button_url            TEXT,
    welcome_delete_after_s        INTEGER NOT NULL DEFAULT 900,
    rules_text                    TEXT,
    warns_limit                   INTEGER NOT NULL DEFAULT 3,
    warns_action                  TEXT NOT NULL DEFAULT 'ban',
    verification_enabled          INTEGER NOT NULL DEFAULT 1,
    verification_suspicious_kick_h INTEGER NOT NULL DEFAULT 12,
    verification_suspicious_kick_minutes INTEGER NOT NULL DEFAULT 30,
    verification_reminder_hours   INTEGER NOT NULL DEFAULT 3,
    verification_kick_after_reminder_hours INTEGER NOT NULL DEFAULT 6,
    cleanservice                  INTEGER NOT NULL DEFAULT 1,
    updated_at                    REAL NOT NULL DEFAULT 0
);
-- Migración blanda para bases ya creadas


CREATE TABLE IF NOT EXISTS pending_verifications (
    chat_id          INTEGER NOT NULL,
    user_id          INTEGER NOT NULL,
    welcome_msg_id   INTEGER,
    joined_at        REAL NOT NULL,
    is_suspicious    INTEGER NOT NULL DEFAULT 0,
    reminder_sent_at REAL,
    verified_at      REAL,
    PRIMARY KEY (chat_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_pendver_joined ON pending_verifications(joined_at) WHERE verified_at IS NULL;

CREATE TABLE IF NOT EXISTS user_warns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    chat_id      INTEGER NOT NULL,
    by_admin     INTEGER NOT NULL,
    reason       TEXT,
    ts           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warns_user_chat ON user_warns(user_id, chat_id);

CREATE TABLE IF NOT EXISTS welcome_buttons (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id      INTEGER NOT NULL,
    position     INTEGER NOT NULL DEFAULT 0,
    text         TEXT NOT NULL,
    url          TEXT NOT NULL,
    same_row     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wb_chat_pos ON welcome_buttons(chat_id, position);

CREATE TABLE IF NOT EXISTS gentle_warnings (
    chat_id      INTEGER NOT NULL,
    user_msg_id  INTEGER NOT NULL,
    bot_msg_id   INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    ts           REAL NOT NULL,
    PRIMARY KEY (chat_id, user_msg_id)
);
CREATE INDEX IF NOT EXISTS idx_gw_botmsg ON gentle_warnings(chat_id, bot_msg_id);

CREATE TABLE IF NOT EXISTS weekly_msg_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    ts          REAL NOT NULL,
    length      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wml_chat_ts ON weekly_msg_log(chat_id, ts);
CREATE INDEX IF NOT EXISTS idx_wml_user ON weekly_msg_log(user_id);

CREATE TABLE IF NOT EXISTS friendly_greeters (
    user_id        INTEGER PRIMARY KEY,
    username       TEXT,
    reactions_json TEXT NOT NULL,
    added_by       INTEGER NOT NULL,
    ts             REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_reports (
    chat_id              INTEGER NOT NULL,
    reporter_msg_id      INTEGER NOT NULL,
    reporter_user_id     INTEGER NOT NULL,
    reporter_username    TEXT,
    reported_msg_id      INTEGER,
    reported_user_id     INTEGER,
    bot_confirm_msg_id   INTEGER,
    action_taken         TEXT,
    ts                   REAL NOT NULL,
    resolved_at          REAL,
    PRIMARY KEY (chat_id, reporter_msg_id)
);
CREATE INDEX IF NOT EXISTS idx_ar_reported ON admin_reports(chat_id, reported_msg_id) WHERE resolved_at IS NULL;
CREATE TABLE IF NOT EXISTS flood_state (
    chat_id          INTEGER NOT NULL,
    user_id          INTEGER NOT NULL,
    human_confirmed  INTEGER NOT NULL DEFAULT 0,  -- un admin pulsó "no es bot"
    mute_count       INTEGER NOT NULL DEFAULT 0,  -- nº de mutes por flood acumulados
    last_mute_ts     REAL,
    review_sent      INTEGER NOT NULL DEFAULT 0,  -- ya se preguntó al admin (es/no bot)
    PRIMARY KEY (chat_id, user_id)
);
"""


class DB:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Migraciones blandas para DBs existentes (ALTER TABLE idempotente)."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(chat_settings)").fetchall()}
        if "welcome_delete_after_s" not in cols:
            self._conn.execute(
                "ALTER TABLE chat_settings ADD COLUMN welcome_delete_after_s INTEGER NOT NULL DEFAULT 900"
            )
        bot_chat_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(bot_chats)").fetchall()}
        if "username" not in bot_chat_cols:
            self._conn.execute("ALTER TABLE bot_chats ADD COLUMN username TEXT")
        pv_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(pending_verifications)").fetchall()}
        if "reminder_sent_at" not in pv_cols:
            self._conn.execute("ALTER TABLE pending_verifications ADD COLUMN reminder_sent_at REAL")
        cs_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(chat_settings)").fetchall()}
        if "verification_reminder_hours" not in cs_cols:
            self._conn.execute(
                "ALTER TABLE chat_settings ADD COLUMN verification_reminder_hours INTEGER NOT NULL DEFAULT 6"
            )
        if "verification_suspicious_kick_minutes" not in cs_cols:
            self._conn.execute(
                "ALTER TABLE chat_settings ADD COLUMN verification_suspicious_kick_minutes INTEGER NOT NULL DEFAULT 30"
            )
        if "verification_kick_after_reminder_hours" not in cs_cols:
            # Tras enviar reminder, esperar N horas antes de kickear (tier 'normal')
            self._conn.execute(
                "ALTER TABLE chat_settings ADD COLUMN verification_kick_after_reminder_hours INTEGER NOT NULL DEFAULT 6"
            )
            # Migración de valores antiguos (10min/6h) → nuevos (30min/3h+6h).
            # Solo actualiza filas con los defaults exactos previos para no pisar configs custom.
            self._conn.execute(
                "UPDATE chat_settings SET verification_suspicious_kick_minutes=30 "
                "WHERE verification_suspicious_kick_minutes=10"
            )
            self._conn.execute(
                "UPDATE chat_settings SET verification_reminder_hours=3 "
                "WHERE verification_reminder_hours=6"
            )
        if "topweekly_enabled" not in cs_cols:
            self._conn.execute(
                "ALTER TABLE chat_settings ADD COLUMN topweekly_enabled INTEGER NOT NULL DEFAULT 0"
            )
        su_cols2 = {r[1] for r in self._conn.execute("PRAGMA table_info(seen_users)").fetchall()}
        if "first_name" not in su_cols2:
            self._conn.execute("ALTER TABLE seen_users ADD COLUMN first_name TEXT")
        ar_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(admin_reports)").fetchall()}
        if ar_cols and "action_taken" not in ar_cols:
            self._conn.execute("ALTER TABLE admin_reports ADD COLUMN action_taken TEXT")
        su_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(seen_users)").fetchall()}
        if "last_msg_id" not in su_cols:
            self._conn.execute("ALTER TABLE seen_users ADD COLUMN last_msg_id INTEGER")
        if "last_msg_text" not in su_cols:
            self._conn.execute("ALTER TABLE seen_users ADD COLUMN last_msg_text TEXT")
        if "last_msg_ts" not in su_cols:
            self._conn.execute("ALTER TABLE seen_users ADD COLUMN last_msg_ts REAL")

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _cur(self):
        cur = self._conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    # ------------- bot_chats -------------

    def upsert_bot_chat(
        self,
        chat_id: int,
        title: str | None,
        chat_type: str | None,
        am_admin: bool,
        can_restrict: bool,
        can_delete: bool,
        username: str | None = None,
    ) -> None:
        now = time.time()
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO bot_chats (chat_id, title, username, type, am_admin, can_restrict, can_delete, added_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                  title=excluded.title, username=COALESCE(excluded.username, bot_chats.username),
                  type=excluded.type,
                  am_admin=excluded.am_admin, can_restrict=excluded.can_restrict,
                  can_delete=excluded.can_delete, updated_at=excluded.updated_at
                """,
                (chat_id, title, username, chat_type, int(am_admin), int(can_restrict), int(can_delete), now, now),
            )

    def chat_username(self, chat_id: int) -> str | None:
        with self._cur() as c:
            row = c.execute("SELECT username FROM bot_chats WHERE chat_id=?", (chat_id,)).fetchone()
        return row["username"] if row else None

    def admin_chats(self) -> list[int]:
        with self._cur() as c:
            rows = c.execute("SELECT chat_id FROM bot_chats WHERE am_admin=1").fetchall()
        return [r["chat_id"] for r in rows]

    def all_chats(self) -> list[sqlite3.Row]:
        with self._cur() as c:
            return c.execute("SELECT * FROM bot_chats ORDER BY title").fetchall()

    # ------------- seen_users -------------

    def get_seen(self, chat_id: int, user_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM seen_users WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()

    def record_join(self, chat_id: int, user_id: int, username: str | None) -> None:
        now = time.time()
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO seen_users (chat_id, user_id, username, first_seen_ts, join_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                  join_ts=COALESCE(seen_users.join_ts, excluded.join_ts),
                  username=COALESCE(excluded.username, seen_users.username)
                """,
                (chat_id, user_id, username, now, now),
            )

    def record_topweekly_msg(self, chat_id: int, user_id: int, length: int, cooldown_s: int = 10) -> None:
        """Inserta un mensaje en weekly_msg_log si el último del mismo user fue
        hace >cooldown_s segundos (anti-flood mínimo, 10s default)."""
        with self._cur() as c:
            row = c.execute(
                "SELECT ts FROM weekly_msg_log WHERE chat_id=? AND user_id=? "
                "ORDER BY ts DESC LIMIT 1",
                (chat_id, user_id),
            ).fetchone()
            now = time.time()
            if row and (now - row["ts"]) < cooldown_s:
                return
            c.execute(
                "INSERT INTO weekly_msg_log (chat_id, user_id, ts, length) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, now, length),
            )

    def top_weekly(self, chat_id: int, since_ts: float, limit: int = 5) -> list[sqlite3.Row]:
        """Top users por count de msgs en la ventana. Devuelve user_id, count, last_name."""
        with self._cur() as c:
            return c.execute(
                """
                SELECT w.user_id, COUNT(*) AS cnt,
                       (SELECT first_name FROM seen_users s WHERE s.user_id = w.user_id LIMIT 1) AS first_name,
                       (SELECT username FROM seen_users s WHERE s.user_id = w.user_id LIMIT 1) AS username
                FROM weekly_msg_log w
                WHERE w.chat_id = ? AND w.ts >= ?
                GROUP BY w.user_id
                ORDER BY cnt DESC, w.user_id ASC
                LIMIT ?
                """,
                (chat_id, since_ts, limit),
            ).fetchall()

    def update_seen_first_name(self, chat_id: int, user_id: int, first_name: str | None) -> None:
        if not first_name:
            return
        with self._cur() as c:
            c.execute(
                "UPDATE seen_users SET first_name=? WHERE chat_id=? AND user_id=? AND (first_name IS NULL OR first_name != ?)",
                (first_name[:60], chat_id, user_id, first_name[:60]),
            )

    def update_last_message(self, chat_id: int, user_id: int, msg_id: int, text: str | None) -> None:
        """Guarda el último mensaje del user (truncado a 500 chars) para revisar tras bans."""
        with self._cur() as c:
            c.execute(
                "UPDATE seen_users SET last_msg_id=?, last_msg_text=?, last_msg_ts=? "
                "WHERE chat_id=? AND user_id=?",
                (msg_id, (text or "")[:500], time.time(), chat_id, user_id),
            )

    def record_message(self, chat_id: int, user_id: int, username: str | None) -> int:
        """Registra mensaje y devuelve msg_count POSTERIOR al incremento."""
        now = time.time()
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO seen_users (chat_id, user_id, username, first_seen_ts, first_msg_ts, msg_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                  msg_count = seen_users.msg_count + 1,
                  first_msg_ts = COALESCE(seen_users.first_msg_ts, excluded.first_msg_ts),
                  username = COALESCE(excluded.username, seen_users.username)
                """,
                (chat_id, user_id, username, now, now),
            )
            row = c.execute(
                "SELECT msg_count FROM seen_users WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()
        return int(row["msg_count"]) if row else 1

    def record_reaction(self, chat_id: int, user_id: int, message_id: int, new_emojis: list[str]) -> None:
        with self._cur() as c:
            c.execute(
                "INSERT INTO reaction_events (ts, chat_id, user_id, message_id, new_emojis) VALUES (?, ?, ?, ?, ?)",
                (time.time(), chat_id, user_id, message_id, json.dumps(new_emojis, ensure_ascii=False)),
            )
            c.execute(
                """
                INSERT INTO seen_users (chat_id, user_id, first_seen_ts, reaction_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                  reaction_count = seen_users.reaction_count + 1
                """,
                (chat_id, user_id, time.time()),
            )

    def reactions_in_window(self, user_id: int, since_ts: float) -> int:
        with self._cur() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM reaction_events WHERE user_id=? AND ts>=?",
                (user_id, since_ts),
            ).fetchone()
        return int(row["n"]) if row else 0

    def total_msgs_user(self, user_id: int) -> int:
        with self._cur() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(msg_count),0) AS n FROM seen_users WHERE user_id=?",
                (user_id,),
            ).fetchone()
        return int(row["n"]) if row else 0

    def whitelist(self, chat_id: int, user_id: int) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO seen_users (chat_id, user_id, first_seen_ts, whitelisted)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET whitelisted=1
                """,
                (chat_id, user_id, time.time()),
            )

    def is_whitelisted(self, chat_id: int, user_id: int) -> bool:
        row = self.get_seen(chat_id, user_id)
        return bool(row and row["whitelisted"])

    # ------------- banned_users -------------

    def add_ban(
        self,
        user_id: int,
        reason: str,
        rule: str,
        banned_in_chat: int,
        federated: bool = True,
    ) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO banned_users (user_id, reason, rule, banned_at, banned_in_chat, federated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  reason=excluded.reason, rule=excluded.rule,
                  banned_at=excluded.banned_at, banned_in_chat=excluded.banned_in_chat,
                  federated=excluded.federated, revoked_at=NULL, revoked_by=NULL
                """,
                (user_id, reason, rule, time.time(), banned_in_chat, int(federated)),
            )

    def revoke_ban(self, user_id: int, revoked_by: int) -> None:
        with self._cur() as c:
            c.execute(
                "UPDATE banned_users SET revoked_at=?, revoked_by=? WHERE user_id=?",
                (time.time(), revoked_by, user_id),
            )

    def is_banned(self, user_id: int) -> bool:
        with self._cur() as c:
            row = c.execute(
                "SELECT 1 FROM banned_users WHERE user_id=? AND revoked_at IS NULL",
                (user_id,),
            ).fetchone()
        return bool(row)

    # ------------- moderation_log -------------

    def log_action(
        self,
        chat_id: int,
        user_id: int | None,
        username: str | None,
        message_id: int | None,
        rule: str,
        action: str,
        score: int,
        mode: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO moderation_log (ts, chat_id, user_id, username, message_id, rule, action, score, mode, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(), chat_id, user_id, username, message_id,
                    rule, action, score, mode,
                    json.dumps(payload, ensure_ascii=False) if payload else None,
                ),
            )
            row = c.execute("SELECT last_insert_rowid() AS id").fetchone()
        return int(row["id"])

    def stats(self) -> dict[str, int]:
        with self._cur() as c:
            return {
                "chats": c.execute("SELECT COUNT(*) AS n FROM bot_chats WHERE am_admin=1").fetchone()["n"],
                "seen_users": c.execute("SELECT COUNT(*) AS n FROM seen_users").fetchone()["n"],
                "banned": c.execute("SELECT COUNT(*) AS n FROM banned_users WHERE revoked_at IS NULL").fetchone()["n"],
                "actions_24h": c.execute(
                    "SELECT COUNT(*) AS n FROM moderation_log WHERE ts >= ?",
                    (time.time() - 86400,),
                ).fetchone()["n"],
            }

    # ------------- cas cache -------------

    def cas_lookup(self, user_id: int, ttl: int) -> int | None:
        with self._cur() as c:
            row = c.execute(
                "SELECT offenses, checked_at FROM cas_cache WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        if time.time() - row["checked_at"] > ttl:
            return None
        return int(row["offenses"])

    def cas_store(self, user_id: int, offenses: int) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO cas_cache (user_id, offenses, checked_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET offenses=excluded.offenses, checked_at=excluded.checked_at
                """,
                (user_id, offenses, time.time()),
            )

    # ------------- username_map -------------

    def remember_username(self, username: str | None, user_id: int) -> None:
        if not username:
            return
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO username_map (username_lower, user_id, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(username_lower) DO UPDATE SET user_id=excluded.user_id, updated_at=excluded.updated_at
                """,
                (username.lower().lstrip("@"), user_id, time.time()),
            )

    def resolve_username(self, username: str) -> int | None:
        with self._cur() as c:
            row = c.execute(
                "SELECT user_id FROM username_map WHERE username_lower=?",
                (username.lower().lstrip("@"),),
            ).fetchone()
        return int(row["user_id"]) if row else None

    def known_user_in_chat(self, chat_id: int, user_id: int) -> bool:
        return self.get_seen(chat_id, user_id) is not None

    # ------------- suppressions -------------

    def suppress(self, user_id: int, rule: str, seconds: int) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO suppressions (user_id, rule, suppressed_until) VALUES (?, ?, ?)
                ON CONFLICT(user_id, rule) DO UPDATE SET suppressed_until=excluded.suppressed_until
                """,
                (user_id, rule, time.time() + seconds),
            )

    def is_suppressed(self, user_id: int, rule: str) -> bool:
        with self._cur() as c:
            row = c.execute(
                "SELECT suppressed_until FROM suppressions WHERE user_id=? AND rule=?",
                (user_id, rule),
            ).fetchone()
        return bool(row and row["suppressed_until"] > time.time())

    # ------------- queries para comandos admin -------------

    def recent_actions(self, limit: int = 20) -> list[sqlite3.Row]:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM moderation_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def get_action(self, action_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM moderation_log WHERE id=?",
                (action_id,),
            ).fetchone()

    # ------------- learning_samples -------------

    def add_sample(
        self,
        text_norm: str,
        text_hash: str,
        label: str,
        added_by: int,
        chat_id: int | None,
        source_user: int | None,
    ) -> bool:
        """Devuelve True si se insertó, False si era duplicado (hash+label ya existían)."""
        if label not in ("spam", "ham"):
            raise ValueError("label debe ser spam o ham")
        with self._cur() as c:
            try:
                c.execute(
                    """
                    INSERT INTO learning_samples
                      (text_norm, text_hash, label, added_by, chat_id, source_user, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (text_norm, text_hash, label, added_by, chat_id, source_user, time.time()),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def list_samples(self, label: str, limit: int = 50, since_days: int | None = None) -> list[sqlite3.Row]:
        with self._cur() as c:
            sql = "SELECT * FROM learning_samples WHERE label=?"
            params: list = [label]
            if since_days:
                sql += " AND ts >= ?"
                params.append(time.time() - since_days * 86400)
            sql += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)
            return c.execute(sql, params).fetchall()

    def sample_count(self) -> dict[str, int]:
        with self._cur() as c:
            return {
                "spam": c.execute("SELECT COUNT(*) AS n FROM learning_samples WHERE label='spam'").fetchone()["n"],
                "ham": c.execute("SELECT COUNT(*) AS n FROM learning_samples WHERE label='ham'").fetchone()["n"],
            }

    def delete_sample(self, sample_id: int) -> bool:
        with self._cur() as c:
            cur = c.execute("DELETE FROM learning_samples WHERE id=?", (sample_id,))
            return cur.rowcount > 0

    def recent_sample_texts(self, label: str, limit: int = 200, since_days: int = 90) -> list[str]:
        with self._cur() as c:
            rows = c.execute(
                "SELECT text_norm FROM learning_samples WHERE label=? AND ts >= ? ORDER BY ts DESC LIMIT ?",
                (label, time.time() - since_days * 86400, limit),
            ).fetchall()
        return [r["text_norm"] for r in rows]

    # ------------- chat_settings -------------

    def get_chat_settings(self, chat_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute("SELECT * FROM chat_settings WHERE chat_id=?", (chat_id,)).fetchone()

    def ensure_chat_settings(self, chat_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "INSERT OR IGNORE INTO chat_settings (chat_id, updated_at) VALUES (?, ?)",
                (chat_id, time.time()),
            )

    def update_chat_setting(self, chat_id: int, field: str, value) -> None:
        ALLOWED = {
            "welcome_text", "welcome_enabled", "welcome_button_text", "welcome_button_url",
            "welcome_delete_after_s",
            "rules_text", "warns_limit", "warns_action",
            "verification_enabled", "verification_suspicious_kick_h",
            "verification_suspicious_kick_minutes",
            "verification_reminder_hours", "cleanservice",
            "topweekly_enabled",
        }
        if field not in ALLOWED:
            raise ValueError(f"campo no permitido: {field}")
        self.ensure_chat_settings(chat_id)
        with self._cur() as c:
            c.execute(
                f"UPDATE chat_settings SET {field}=?, updated_at=? WHERE chat_id=?",
                (value, time.time(), chat_id),
            )

    # ------------- pending_verifications -------------

    def add_pending_verification(
        self, chat_id: int, user_id: int, welcome_msg_id: int | None,
        is_suspicious: bool,
    ) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO pending_verifications (chat_id, user_id, welcome_msg_id, joined_at, is_suspicious)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                  welcome_msg_id=excluded.welcome_msg_id,
                  joined_at=excluded.joined_at,
                  is_suspicious=excluded.is_suspicious,
                  verified_at=NULL
                """,
                (chat_id, user_id, welcome_msg_id, time.time(), int(is_suspicious)),
            )

    def mark_verified(self, chat_id: int, user_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            row = c.execute(
                "SELECT * FROM pending_verifications WHERE chat_id=? AND user_id=? AND verified_at IS NULL",
                (chat_id, user_id),
            ).fetchone()
            if not row:
                return None
            c.execute(
                "UPDATE pending_verifications SET verified_at=? WHERE chat_id=? AND user_id=?",
                (time.time(), chat_id, user_id),
            )
            return row

    def get_pending(self, chat_id: int, user_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM pending_verifications WHERE chat_id=? AND user_id=? AND verified_at IS NULL",
                (chat_id, user_id),
            ).fetchone()

    def expired_suspicious_pending(self, hours: int) -> list[sqlite3.Row]:
        """Suspicious users que llevan >hours sin verificar."""
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM pending_verifications "
                "WHERE verified_at IS NULL AND is_suspicious=1 AND joined_at <= ?",
                (time.time() - hours * 3600,),
            ).fetchall()

    def expired_suspicious_pending_minutes(self, minutes: int) -> list[sqlite3.Row]:
        """Suspicious users que llevan >minutes sin verificar (granularidad fina)."""
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM pending_verifications "
                "WHERE verified_at IS NULL AND is_suspicious=1 AND joined_at <= ?",
                (time.time() - minutes * 60,),
            ).fetchall()

    def pending_needing_reminder(self, hours: int) -> list[sqlite3.Row]:
        """Pending users (cualquiera) que llevan >hours sin verificar y sin reminder enviado."""
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM pending_verifications "
                "WHERE verified_at IS NULL AND reminder_sent_at IS NULL AND joined_at <= ?",
                (time.time() - hours * 3600,),
            ).fetchall()

    def pending_kick_after_reminder(self, hours: int) -> list[sqlite3.Row]:
        """Pending normales (no suspicious) que recibieron reminder hace >hours y siguen sin verificar."""
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM pending_verifications "
                "WHERE verified_at IS NULL AND is_suspicious=0 "
                "  AND reminder_sent_at IS NOT NULL AND reminder_sent_at <= ?",
                (time.time() - hours * 3600,),
            ).fetchall()

    def mark_reminder_sent(self, chat_id: int, user_id: int, new_welcome_msg_id: int | None) -> None:
        with self._cur() as c:
            c.execute(
                "UPDATE pending_verifications SET reminder_sent_at=?, welcome_msg_id=? "
                "WHERE chat_id=? AND user_id=?",
                (time.time(), new_welcome_msg_id, chat_id, user_id),
            )

    def delete_pending(self, chat_id: int, user_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "DELETE FROM pending_verifications WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )

    def pending_welcomes_past_ttl(self, ttl_seconds: int) -> list[sqlite3.Row]:
        """Pendings con welcome_msg_id cuyo welcome ya superó el TTL.

        Robusto ante reinicios: el auto-delete por jq.run_once vive en memoria
        y se pierde al reiniciar; este barrido desde DB lo recupera.
        """
        with self._cur() as c:
            return c.execute(
                "SELECT chat_id, user_id, welcome_msg_id FROM pending_verifications "
                "WHERE welcome_msg_id IS NOT NULL AND joined_at <= ?",
                (time.time() - ttl_seconds,),
            ).fetchall()

    def clear_welcome_msg_id(self, chat_id: int, user_id: int) -> None:
        """Marca el welcome como ya borrado (no reintentar en el próximo barrido)."""
        with self._cur() as c:
            c.execute(
                "UPDATE pending_verifications SET welcome_msg_id=NULL "
                "WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )

    # ------------- user_warns -------------

    def add_warn(self, user_id: int, chat_id: int, by_admin: int, reason: str | None) -> int:
        with self._cur() as c:
            c.execute(
                "INSERT INTO user_warns (user_id, chat_id, by_admin, reason, ts) VALUES (?, ?, ?, ?, ?)",
                (user_id, chat_id, by_admin, reason, time.time()),
            )
        return self.count_warns(user_id, chat_id)

    def count_warns(self, user_id: int, chat_id: int) -> int:
        with self._cur() as c:
            return c.execute(
                "SELECT COUNT(*) AS n FROM user_warns WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ).fetchone()["n"]

    def list_warns(self, user_id: int, chat_id: int) -> list[sqlite3.Row]:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM user_warns WHERE user_id=? AND chat_id=? ORDER BY ts ASC",
                (user_id, chat_id),
            ).fetchall()

    # ------------- gentle_warnings -------------

    def add_gentle_warning(self, chat_id: int, user_msg_id: int, bot_msg_id: int, user_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "INSERT OR REPLACE INTO gentle_warnings (chat_id, user_msg_id, bot_msg_id, user_id, ts) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_msg_id, bot_msg_id, user_id, time.time()),
            )

    def pop_gentle_warning_by_user_msg(self, chat_id: int, user_msg_id: int) -> int | None:
        """Si existe, devuelve bot_msg_id y borra la fila. Para borrado en cascada."""
        with self._cur() as c:
            row = c.execute(
                "SELECT bot_msg_id FROM gentle_warnings WHERE chat_id=? AND user_msg_id=?",
                (chat_id, user_msg_id),
            ).fetchone()
            if not row:
                return None
            c.execute(
                "DELETE FROM gentle_warnings WHERE chat_id=? AND user_msg_id=?",
                (chat_id, user_msg_id),
            )
            return int(row["bot_msg_id"])

    # ------------- friendly_greeters -------------

    def upsert_friendly_greeter(
        self, user_id: int, username: str | None, reactions: list[str], added_by: int,
    ) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT INTO friendly_greeters (user_id, username, reactions_json, added_by, ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  username=excluded.username,
                  reactions_json=excluded.reactions_json,
                  added_by=excluded.added_by,
                  ts=excluded.ts
                """,
                (user_id, username, json.dumps(reactions, ensure_ascii=False), added_by, time.time()),
            )

    def remove_friendly_greeter(self, user_id: int) -> bool:
        with self._cur() as c:
            cur = c.execute("DELETE FROM friendly_greeters WHERE user_id=?", (user_id,))
            return cur.rowcount > 0

    def get_friendly_greeter(self, user_id: int) -> list[str] | None:
        """Devuelve la lista de reactions configurada para este user, o None si no es greeter."""
        with self._cur() as c:
            row = c.execute(
                "SELECT reactions_json FROM friendly_greeters WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["reactions_json"])
        except Exception:
            return []

    def list_friendly_greeters(self) -> list[sqlite3.Row]:
        with self._cur() as c:
            return c.execute(
                "SELECT user_id, username, reactions_json, ts FROM friendly_greeters ORDER BY ts DESC"
            ).fetchall()

    def delete_gentle_warning(self, chat_id: int, user_msg_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "DELETE FROM gentle_warnings WHERE chat_id=? AND user_msg_id=?",
                (chat_id, user_msg_id),
            )

    # ------------- admin_reports -------------

    def add_admin_report(
        self,
        chat_id: int,
        reporter_msg_id: int,
        reporter_user_id: int,
        reporter_username: str | None,
        reported_msg_id: int | None,
        reported_user_id: int | None,
        bot_confirm_msg_id: int | None,
    ) -> None:
        with self._cur() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO admin_reports
                  (chat_id, reporter_msg_id, reporter_user_id, reporter_username,
                   reported_msg_id, reported_user_id, bot_confirm_msg_id, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, reporter_msg_id, reporter_user_id, reporter_username,
                 reported_msg_id, reported_user_id, bot_confirm_msg_id, time.time()),
            )

    def find_admin_report_by_reported(self, chat_id: int, reported_msg_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM admin_reports WHERE chat_id=? AND reported_msg_id=? AND resolved_at IS NULL "
                "ORDER BY ts DESC LIMIT 1",
                (chat_id, reported_msg_id),
            ).fetchone()

    def resolve_admin_report(self, chat_id: int, reporter_msg_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "UPDATE admin_reports SET resolved_at=? WHERE chat_id=? AND reporter_msg_id=?",
                (time.time(), chat_id, reporter_msg_id),
            )

    def mark_admin_report_action(self, chat_id: int, reported_msg_id: int, action: str) -> None:
        """Marca el action_taken del admin_report cuyo reported_msg_id coincide.

        Usado por cmd_warn / cmd_ban etc. para que el cascade thanks elija
        el template adecuado (warn → "avisado"; ban → "expulsado").
        """
        with self._cur() as c:
            c.execute(
                "UPDATE admin_reports SET action_taken=? "
                "WHERE chat_id=? AND reported_msg_id=? AND resolved_at IS NULL",
                (action, chat_id, reported_msg_id),
            )

    def user_trust_metrics(self, chat_id: int, user_id: int) -> tuple[int, float | None]:
        """Devuelve (msg_count, days_in_chat). Si nunca visto, (0, None)."""
        with self._cur() as c:
            row = c.execute(
                "SELECT msg_count, first_seen_ts FROM seen_users WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()
        if not row:
            return 0, None
        days = (time.time() - row["first_seen_ts"]) / 86400 if row["first_seen_ts"] else None
        return int(row["msg_count"] or 0), days

    def user_trust_score(self, chat_id: int, user_id: int) -> int:
        """Score de confianza 0-100 del user en ese chat.

        Componentes:
          - Whitelisted explícito → 100
          - Por mensajes vistos: min(msg_count * 1.0, 40)
          - Por días en grupo: min(days * 1.5, 30)
          - Bot vio el join (join_ts NOT NULL) → +10 (sabemos trayectoria limpia)
          - Por antigüedad de first_seen (>=30 días) → +20
          - Penalty por warns activos: -10 por warn (cap -40)

        Total típico: 0 (nuevo) a 80 (veterano). 100 solo con whitelist.

        Reglas downstream:
          - score >= 70 → muy confiable, solo actuar con reglas de severidad máxima
          - score >= 40 → confiable, degradar acción (ban→mute, kick→noop)
          - score < 40  → trato normal
        """
        with self._cur() as c:
            row = c.execute(
                "SELECT msg_count, first_seen_ts, join_ts, whitelisted "
                "FROM seen_users WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()
        if not row:
            return 0
        if row["whitelisted"]:
            return 100
        score = 0.0
        score += min(int(row["msg_count"] or 0) * 1.0, 40)
        if row["first_seen_ts"]:
            days = (time.time() - row["first_seen_ts"]) / 86400
            score += min(days * 1.5, 30)
            if days >= 30:
                score += 20
        if row["join_ts"]:
            score += 10
        # Warns activos restan
        with self._cur() as c:
            n_warns = c.execute(
                "SELECT COUNT(*) AS n FROM user_warns WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            ).fetchone()["n"]
        score -= min(int(n_warns) * 10, 40)
        return max(0, min(100, int(round(score))))

    # ------------- flood_state (antiflood con revisión humana) -------------

    def flood_get(self, chat_id: int, user_id: int) -> sqlite3.Row | None:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM flood_state WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()

    def flood_is_human_confirmed(self, chat_id: int, user_id: int) -> bool:
        row = self.flood_get(chat_id, user_id)
        return bool(row and row["human_confirmed"])

    def flood_record_mute(self, chat_id: int, user_id: int, ts: float) -> tuple[int, bool, bool]:
        """Registra un mute por flood. Devuelve (mute_count, review_ya_enviado, human_confirmed)."""
        with self._cur() as c:
            c.execute(
                "INSERT INTO flood_state (chat_id, user_id, mute_count, last_mute_ts) "
                "VALUES (?, ?, 1, ?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET "
                "mute_count = mute_count + 1, last_mute_ts = excluded.last_mute_ts",
                (chat_id, user_id, ts),
            )
            row = c.execute(
                "SELECT mute_count, review_sent, human_confirmed FROM flood_state WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            ).fetchone()
        return int(row["mute_count"]), bool(row["review_sent"]), bool(row["human_confirmed"])

    def flood_mark_review_sent(self, chat_id: int, user_id: int) -> None:
        with self._cur() as c:
            c.execute(
                "UPDATE flood_state SET review_sent=1 WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )

    def flood_confirm_human(self, chat_id: int, user_id: int) -> None:
        """El admin marcó 'no es bot': más margen de flood en adelante."""
        with self._cur() as c:
            c.execute(
                "INSERT INTO flood_state (chat_id, user_id, human_confirmed, review_sent) "
                "VALUES (?, ?, 1, 1) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET human_confirmed=1, review_sent=1",
                (chat_id, user_id),
            )

    def remove_last_warn(self, user_id: int, chat_id: int) -> bool:
        with self._cur() as c:
            row = c.execute(
                "SELECT id FROM user_warns WHERE user_id=? AND chat_id=? ORDER BY ts DESC LIMIT 1",
                (user_id, chat_id),
            ).fetchone()
            if not row:
                return False
            c.execute("DELETE FROM user_warns WHERE id=?", (row["id"],))
            return True

    def reset_warns(self, user_id: int, chat_id: int) -> int:
        with self._cur() as c:
            cur = c.execute(
                "DELETE FROM user_warns WHERE user_id=? AND chat_id=?",
                (user_id, chat_id),
            )
            return cur.rowcount

    # ------------- welcome_buttons (múltiples botones por chat) -------------

    def list_welcome_buttons(self, chat_id: int) -> list[sqlite3.Row]:
        with self._cur() as c:
            return c.execute(
                "SELECT * FROM welcome_buttons WHERE chat_id=? ORDER BY position ASC, id ASC",
                (chat_id,),
            ).fetchall()

    def add_welcome_button(self, chat_id: int, text: str, url: str, same_row: bool = False) -> int:
        with self._cur() as c:
            row = c.execute(
                "SELECT COALESCE(MAX(position),-1)+1 AS p FROM welcome_buttons WHERE chat_id=?",
                (chat_id,),
            ).fetchone()
            pos = row["p"]
            c.execute(
                "INSERT INTO welcome_buttons (chat_id, position, text, url, same_row) VALUES (?, ?, ?, ?, ?)",
                (chat_id, pos, text, url, int(same_row)),
            )
            return c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    def delete_welcome_button(self, button_id: int) -> bool:
        with self._cur() as c:
            cur = c.execute("DELETE FROM welcome_buttons WHERE id=?", (button_id,))
            return cur.rowcount > 0

    def clear_welcome_buttons(self, chat_id: int) -> int:
        with self._cur() as c:
            cur = c.execute("DELETE FROM welcome_buttons WHERE chat_id=?", (chat_id,))
            return cur.rowcount

    def migrate_legacy_welcome_button(self, chat_id: int) -> None:
        """Si chat_settings tiene welcome_button_text+url y welcome_buttons está vacío, migra."""
        s = self.get_chat_settings(chat_id)
        if not s or not s["welcome_button_text"] or not s["welcome_button_url"]:
            return
        existing = self.list_welcome_buttons(chat_id)
        if existing:
            return
        self.add_welcome_button(chat_id, s["welcome_button_text"], s["welcome_button_url"], same_row=False)
