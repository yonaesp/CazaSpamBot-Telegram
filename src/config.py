"""Carga de configuración desde .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    admin_user_id: int
    admin_notify_chat_id: int

    mode: str
    moderated_chat_ids: list[int]
    federation_enabled: bool

    first_msg_window: int
    allowed_scripts: list[str]
    non_latin_ratio_threshold: float
    first_msg_attack_action: str

    detect_external_mentions: bool
    detect_external_tg_links: bool

    url_blocklist: list[str]

    reaction_farming_enabled: bool
    reaction_threshold_count: int
    reaction_threshold_seconds: int

    cas_enabled: bool
    cas_cache_ttl_seconds: int
    cas_autoban_min: int
    lols_enabled: bool
    rescan_edited_messages: bool
    report_before_ban: bool
    # Master switch de Telethon (MTProto). False = bot solo con Bot API:
    # se desactivan bio_spam, photos_batch, señales de perfil, reportes oficiales,
    # bridge MessageDeleted y resolución get_participants. Útil para deploys
    # públicos sin la cuenta secundaria. Los detectores Bot-API siguen activos.
    telethon_enabled: bool

    llm_enabled: bool
    llm_provider: str
    llm_model: str
    anthropic_api_key: str

    ban_score: int
    kick_score: int
    mute_score: int

    notify_via_casa_yona: bool
    casa_yona_env_path: str
    casa_yona_token: str = ""
    casa_yona_chat_yona: str = ""

    public_quip_enabled: bool = True
    public_quip_delete_after_s: int = 3600
    # Híbrido: quip público SOLO en bans manuales del admin. Los bans automáticos
    # de detectores (chino/bots/bio/etc.) son silenciosos (95% del volumen, no
    # aportan al usuario verlos). True = también quip en auto-bans.
    quip_on_auto_ban: bool = False
    public_quip_batch_delete_after_s: int = 0

    # Rate limits del SpamReporter (Telethon → channels.reportSpam).
    # Bajar si Telegram empieza a flagear la cuenta la cuenta Telethon.
    reporter_rate_per_hour: int = 20
    reporter_rate_per_day: int = 100

    db_path: str = "/app/data/antispam.db"
    log_level: str = "INFO"

    moderated_chat_ids_set: frozenset[int] = field(default_factory=frozenset)

    def is_moderated(self, chat_id: int) -> bool:
        if not self.moderated_chat_ids_set:
            return True  # auto-discovery: modera todos donde sea admin
        return chat_id in self.moderated_chat_ids_set

    @property
    def shadow(self) -> bool:
        return self.mode != "active"


def _load_casa_yona(path: str) -> tuple[str, str]:
    p = Path(path)
    if not p.exists():
        return "", ""
    token, chat = "", ""
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("TG_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TG_CHAT_YONA="):
            chat = line.split("=", 1)[1].strip().strip('"').strip("'")
    return token, chat


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")
    admin = _int("ADMIN_USER_ID", 0)
    notify_chat_raw = os.getenv("ADMIN_NOTIFY_CHAT_ID", "").strip()
    notify_chat = int(notify_chat_raw) if notify_chat_raw else admin

    moderated_raw = _csv("MODERATED_CHAT_IDS")
    moderated = [int(x) for x in moderated_raw if x.lstrip("-").isdigit()]

    casa_path = os.getenv("CASA_YONA_ENV_PATH", "")
    casa_token, casa_chat = _load_casa_yona(casa_path)

    return Config(
        telegram_bot_token=token,
        admin_user_id=admin,
        admin_notify_chat_id=notify_chat,
        mode=os.getenv("MODE", "shadow").strip().lower(),
        moderated_chat_ids=moderated,
        moderated_chat_ids_set=frozenset(moderated),
        federation_enabled=_bool("FEDERATION_ENABLED", True),
        first_msg_window=_int("FIRST_MSG_WINDOW", 3),
        allowed_scripts=[s.lower() for s in _csv("ALLOWED_SCRIPTS", "latin")],
        non_latin_ratio_threshold=_float("NON_LATIN_RATIO_THRESHOLD", 0.30),
        first_msg_attack_action=os.getenv("FIRST_MSG_ATTACK_ACTION", "ban").strip().lower(),
        detect_external_mentions=_bool("DETECT_EXTERNAL_MENTIONS", True),
        detect_external_tg_links=_bool("DETECT_EXTERNAL_TG_LINKS", True),
        url_blocklist=[s.lower() for s in _csv(
            "URL_BLOCKLIST",
            "bit.ly,tinyurl.com,goo.gl,t.co,ow.ly,is.gd,buff.ly,rebrand.ly,cutt.ly,shorturl.at",
        )],
        reaction_farming_enabled=_bool("REACTION_FARMING_ENABLED", True),
        reaction_threshold_count=_int("REACTION_THRESHOLD_COUNT", 5),
        reaction_threshold_seconds=_int("REACTION_THRESHOLD_SECONDS", 60),
        cas_enabled=_bool("CAS_ENABLED", True),
        cas_cache_ttl_seconds=_int("CAS_CACHE_TTL_SECONDS", 86400),
        cas_autoban_min=_int("CAS_AUTOBAN_MIN", 2),
        lols_enabled=_bool("LOLS_ENABLED", True),
        rescan_edited_messages=_bool("RESCAN_EDITED_MESSAGES", True),
        report_before_ban=_bool("REPORT_BEFORE_BAN", True),
        telethon_enabled=_bool("TELETHON_ENABLED", True),
        llm_enabled=_bool("LLM_ENABLED", False),
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        ban_score=_int("BAN_SCORE", 100),
        kick_score=_int("KICK_SCORE", 70),
        mute_score=_int("MUTE_SCORE", 40),
        notify_via_casa_yona=_bool("NOTIFY_VIA_CASA_YONA", True),
        casa_yona_env_path=casa_path,
        casa_yona_token=casa_token,
        casa_yona_chat_yona=casa_chat,
        public_quip_enabled=_bool("PUBLIC_QUIP_ENABLED", True),
        public_quip_delete_after_s=_int("PUBLIC_QUIP_DELETE_AFTER_S", 3600),
        quip_on_auto_ban=_bool("QUIP_ON_AUTO_BAN", False),
        public_quip_batch_delete_after_s=_int("PUBLIC_QUIP_BATCH_DELETE_AFTER_S", 0),
        reporter_rate_per_hour=_int("REPORTER_RATE_PER_HOUR", 20),
        reporter_rate_per_day=_int("REPORTER_RATE_PER_DAY", 100),
        db_path=os.getenv("DB_PATH", "/app/data/antispam.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
