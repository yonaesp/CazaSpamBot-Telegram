"""Análisis de miembros sospechosos de cada grupo via Telethon (MTProto).

Uso (desde dentro del contenedor):
    python -m scripts.analyze_members              # solo reporta
    python -m scripts.analyze_members --ban-cas    # banea automáticamente los CAS match
    python -m scripts.analyze_members --top 50     # top N sospechosos por chat
    python -m scripts.analyze_members --aggressive # itera más miembros (lento)

Requiere en .env:
    TG_API_ID=...      # de https://my.telegram.org
    TG_API_HASH=...
    TG_PHONE=+34...    # tu número (solo primera vez para autenticarse)

La session se guarda en /app/data/telethon.session (persistente en el volumen).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import (
    Channel,
    ChannelParticipantsAdmins,
    ChannelParticipantsRecent,
    ChannelParticipantsSearch,
    User,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

# Importes del bot — para reusar DB y CAS cache
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DB  # noqa: E402
from src import quips  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("analyze")


CAS_URL = "https://api.cas.chat/check"


# ============== Modelo ==============


@dataclass
class MemberFlags:
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    is_bot: bool = False
    is_premium: bool = False
    has_photo: bool = False
    no_username: bool = False
    no_first_name: bool = False
    name_all_digits: bool = False
    name_random_looking: bool = False
    status_offline_days: Optional[int] = None
    cas_offenses: int = 0
    is_admin: bool = False
    is_in_federation: bool = False
    score: int = 0
    reasons: list[str] = field(default_factory=list)


# ============== Heurísticas de perfil ==============


def _name_is_random_looking(name: str | None) -> bool:
    """Detecta nombres tipo 'a1b2c3', 'User12345', mucho mayúscula + número."""
    if not name:
        return False
    digits = sum(1 for c in name if c.isdigit())
    letters = sum(1 for c in name if c.isalpha())
    if digits >= 3 and digits >= letters:
        return True
    # Cadena tipo "Xj2K9aB" — alta entropía
    if letters >= 6 and digits >= 2 and not any(c == " " for c in name):
        upper = sum(1 for c in name if c.isupper())
        if upper >= len(name) * 0.4:
            return True
    return False


def _status_to_offline_days(status) -> int | None:
    now = time.time()
    if isinstance(status, UserStatusOffline):
        return int((now - status.was_online.timestamp()) / 86400)
    if isinstance(status, UserStatusOnline):
        return 0
    if isinstance(status, UserStatusRecently):
        return 0
    if isinstance(status, UserStatusLastWeek):
        return 7
    if isinstance(status, UserStatusLastMonth):
        return 30
    if isinstance(status, UserStatusEmpty):
        return None
    return None


def _score_member(f: MemberFlags) -> None:
    """Llena f.score y f.reasons según heurísticas."""
    if f.is_admin:
        f.score = 0
        f.reasons.append("admin")
        return

    if f.cas_offenses > 0:
        f.score += 100
        f.reasons.append(f"CAS offenses={f.cas_offenses}")

    if f.is_in_federation:
        f.score += 100
        f.reasons.append("ya en federación ban")

    if f.no_username:
        f.score += 15
        f.reasons.append("sin username")

    if f.no_first_name:
        f.score += 20
        f.reasons.append("sin first_name")

    if f.name_all_digits:
        f.score += 25
        f.reasons.append("nombre solo dígitos")

    if f.name_random_looking:
        f.score += 25
        f.reasons.append("nombre con aspecto aleatorio")

    if not f.has_photo:
        f.score += 10
        f.reasons.append("sin foto")

    if f.is_bot:
        # bots oficiales declarados (is_bot=True). Casi siempre legítimos pero
        # marcamos suavemente para revisión.
        f.score += 5
        f.reasons.append("bot declarado")


# ============== Telethon iteration ==============


async def _iter_members(
    client: TelegramClient,
    channel,
    aggressive: bool,
    limit: int,
):
    """Yield User objects from the channel.

    Estrategia: admins + recientes + (opcional) búsqueda por letras (aggressive).
    Deduplicado por user_id.
    """
    seen: set[int] = set()

    # 1) Admins
    try:
        async for u in client.iter_participants(channel, filter=ChannelParticipantsAdmins()):
            if u.id not in seen:
                seen.add(u.id)
                u._is_admin = True  # type: ignore[attr-defined]
                yield u
    except Exception as exc:
        log.warning("iter admins falló: %s", exc)

    # 2) Recientes (lo que Telegram permita; en grupos grandes ~10k)
    try:
        async for u in client.iter_participants(
            channel, filter=ChannelParticipantsRecent(), limit=limit, aggressive=aggressive,
        ):
            if u.id not in seen:
                seen.add(u.id)
                yield u
    except Exception as exc:
        log.warning("iter recent falló: %s", exc)


# ============== CAS lookup ==============


async def _cas_check(session: aiohttp.ClientSession, db: DB, user_id: int, ttl: int) -> int:
    cached = db.cas_lookup(user_id, ttl)
    if cached is not None:
        return cached
    try:
        async with session.get(CAS_URL, params={"user_id": user_id}, timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json(content_type=None)
        offenses = int(data.get("result", {}).get("offenses", 0)) if data.get("ok") else 0
    except Exception:
        offenses = 0
    db.cas_store(user_id, offenses)
    return offenses


# ============== Ban federado ==============


async def _bot_ban_federated(bot_token: str, user_id: int, chat_ids: list[int]) -> dict[int, str]:
    """Llama a banChatMember del bot por HTTP (sin levantar PTB)."""
    out: dict[int, str] = {}
    async with aiohttp.ClientSession() as s:
        for cid in chat_ids:
            url = f"https://api.telegram.org/bot{bot_token}/banChatMember"
            try:
                async with s.post(url, json={"chat_id": cid, "user_id": user_id}, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    d = await r.json()
                    out[cid] = "ok" if d.get("ok") else f"error: {d.get('description','?')}"
            except Exception as exc:
                out[cid] = f"error: {exc}"
    return out


async def _send_review_candidates(
    bot_token: str,
    notify_chat: str,
    candidates: list["MemberFlags"],
    client: "TelegramClient",
) -> None:
    """Envía a chat de admin la lista de candidatos CAS<umbral con info enriquecida.

    Por cada candidato consulta Telethon get_profile_photos para ver:
      - count de fotos
      - fecha foto más antigua (cuenta con foto antigua = probablemente real)
      - fecha foto más reciente
    Construye una recomendación heurística y la incluye en el mensaje.
    """
    import datetime as _dt
    import html as _html
    import json as _json

    blocks: list[str] = []
    blocks.append(
        f"👀 <b>Revisión humana CAS</b>\n"
        f"{len(candidates)} candidato(s) con CAS offenses=1.\n"
        f"<i>Para banear: /ban &lt;user_id&gt; razón — al bot @CazaSpamBot por DM.</i>\n"
        f"<i>Para descartar: /unban &lt;user_id&gt; (si ya estaba en federación).</i>\n"
    )

    for i, m in enumerate(candidates, 1):
        photo_count = 0
        oldest = None
        newest = None
        try:
            photos = await client.get_profile_photos(m.user_id, limit=20)
            photo_count = len(photos)
            if photos:
                dates = [p.date for p in photos if getattr(p, "date", None)]
                if dates:
                    oldest = min(dates)
                    newest = max(dates)
        except Exception as exc:
            log.debug("get_profile_photos %s falló: %s", m.user_id, exc)

        # Heurística de recomendación
        rec = "🟡 REVISAR"
        rec_reason = []
        if photo_count == 0:
            rec = "🔴 PROBABLE BOT"
            rec_reason.append("sin foto de perfil")
        else:
            now = _dt.datetime.now(tz=oldest.tzinfo) if oldest else _dt.datetime.utcnow()
            age_days = (now - oldest).days if oldest else 0
            if age_days > 365:
                rec = "🟢 PROBABLE REAL"
                rec_reason.append(f"foto de hace {age_days} días")
            elif age_days > 90:
                rec = "🟡 REVISAR"
                rec_reason.append(f"foto de hace {age_days} días")
            else:
                rec = "🟠 SOSPECHOSO"
                rec_reason.append(f"foto reciente ({age_days}d)")

        if m.no_username:
            rec_reason.append("sin username")
        if m.name_random_looking:
            rec_reason.append("nombre random")
        if m.name_all_digits:
            rec_reason.append("nombre solo dígitos")

        uname = ("@" + m.username) if m.username else "(sin user)"
        line = (
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>#{i}</b> {rec}\n"
            f"👤 <code>{m.user_id}</code> {_html.escape(uname)}\n"
            f"📛 nombre: {_html.escape(m.first_name or '(vacío)')} {_html.escape(m.last_name or '')}\n"
            f"📷 fotos: {photo_count}"
        )
        if oldest:
            line += f" · más antigua: {oldest.strftime('%Y-%m-%d')}"
        if newest and newest != oldest:
            line += f" · más reciente: {newest.strftime('%Y-%m-%d')}"
        line += f"\n💡 razones: {_html.escape(', '.join(rec_reason))}"
        blocks.append(line)

    # Enviar por chunks
    async with aiohttp.ClientSession() as s:
        buf = ""
        for b in blocks:
            if len(buf) + len(b) + 1 > 3800:
                await _send_msg(s, bot_token, notify_chat, buf)
                buf = ""
            buf += b + "\n"
        if buf.strip():
            await _send_msg(s, bot_token, notify_chat, buf)


async def _send_msg(session: "aiohttp.ClientSession", bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
            d = await r.json()
            if not d.get("ok"):
                log.warning("sendMessage falló: %s", d.get("description"))
    except Exception as exc:
        log.warning("sendMessage exc: %s", exc)


async def _post_batch_summary(
    bot_token: str,
    banned_by_chat: dict[int, list[dict]],
    category: str = "cas_match",
) -> None:
    """Publica un mensaje resumen permanente en cada chat con la lista de baneados."""
    async with aiohttp.ClientSession() as s:
        for chat_id, items in banned_by_chat.items():
            if not items:
                continue
            text = quips.batch_summary(items, category=category)
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            try:
                async with s.post(url, json={
                    "chat_id": chat_id, "text": text,
                    "parse_mode": "HTML", "disable_notification": True,
                    "disable_web_page_preview": True,
                }, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    d = await r.json()
                    if not d.get("ok"):
                        log.warning("batch summary chat=%s falló: %s", chat_id, d.get("description"))
                    else:
                        log.info("batch summary publicado en chat=%s", chat_id)
            except Exception as exc:
                log.warning("batch summary chat=%s exc: %s", chat_id, exc)


# ============== Main ==============


async def main() -> int:
    parser = argparse.ArgumentParser(description="Analiza miembros sospechosos de cada grupo")
    parser.add_argument("--top", type=int, default=30, help="Top N sospechosos por chat")
    parser.add_argument("--limit", type=int, default=5000, help="Máximo miembros a inspeccionar por chat")
    parser.add_argument("--aggressive", action="store_true", help="Iteración agresiva (lento pero exhaustivo)")
    parser.add_argument("--ban-cas", action="store_true", help="Banea automáticamente los CAS match (solo offenses >= --cas-autoban-min)")
    parser.add_argument("--cas-autoban-min", type=int, default=int(os.getenv("CAS_AUTOBAN_MIN", "2")),
                        help="Mínimo de offenses CAS para autoban automático. Los matches con menos van a revisión humana.")
    parser.add_argument("--ban-score", type=int, default=200, help="Score mínimo para sugerir ban (no automático salvo --ban-cas)")
    parser.add_argument("--cas-ttl", type=int, default=86400, help="TTL CAS cache (s)")
    parser.add_argument("--notify-chat", type=str, default=os.getenv("ADMIN_NOTIFY_CHAT_ID", ""),
                        help="chat_id donde enviar los candidatos a revisión humana (default: ADMIN_NOTIFY_CHAT_ID)")
    args = parser.parse_args()

    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    phone = os.getenv("TG_PHONE")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "/app/data/antispam.db")

    if not api_id or not api_hash or not phone:
        log.error("Faltan TG_API_ID, TG_API_HASH o TG_PHONE en .env")
        log.error("Sácalos de https://my.telegram.org → API development tools")
        return 1

    db = DB(db_path)
    chats = [int(r["chat_id"]) for r in db.all_chats() if r["am_admin"]]
    titles = {int(r["chat_id"]): (r["title"] or str(r["chat_id"])) for r in db.all_chats()}
    if not chats:
        log.error("No hay chats donde el bot sea admin. Asegúrate de que el bot ya esté operativo.")
        return 1
    log.info("Analizando %d chats: %s", len(chats), [titles[c] for c in chats])

    session_path = "/app/data/telethon.session"
    client = TelegramClient(session_path, int(api_id), api_hash)
    await client.start(phone=phone)
    log.info("Telethon autenticado.")

    http = aiohttp.ClientSession()
    suspicious_by_chat: dict[int, list[MemberFlags]] = {}

    for chat_id in chats:
        log.info("--- Chat %s (%s) ---", chat_id, titles[chat_id])
        try:
            entity = await client.get_entity(chat_id)
        except Exception as exc:
            log.warning("get_entity %s falló: %s", chat_id, exc)
            continue

        members: list[MemberFlags] = []
        async for u in _iter_members(client, entity, args.aggressive, args.limit):
            if not isinstance(u, User):
                continue
            f = MemberFlags(
                user_id=u.id,
                username=u.username,
                first_name=u.first_name,
                last_name=u.last_name,
                is_bot=bool(u.bot),
                is_premium=bool(getattr(u, "premium", False)),
                has_photo=u.photo is not None,
                no_username=not u.username,
                no_first_name=not u.first_name,
                name_all_digits=bool(u.first_name and u.first_name.strip().isdigit()),
                name_random_looking=_name_is_random_looking(u.first_name),
                status_offline_days=_status_to_offline_days(u.status),
                is_admin=getattr(u, "_is_admin", False),
                is_in_federation=db.is_banned(u.id),
            )
            f.cas_offenses = await _cas_check(http, db, u.id, args.cas_ttl)
            db.remember_username(u.username, u.id)
            _score_member(f)
            members.append(f)

        log.info("Chat %s: %d miembros inspeccionados", chat_id, len(members))
        suspicious = sorted(members, key=lambda m: m.score, reverse=True)
        suspicious_by_chat[chat_id] = suspicious

    await http.close()
    await client.disconnect()

    # ============== Reporte ==============
    print()
    print("=" * 72)
    print("  REPORTE DE MIEMBROS SOSPECHOSOS")
    print("=" * 72)

    total_to_ban: list[int] = []
    for chat_id, members in suspicious_by_chat.items():
        relevant = [m for m in members if m.score > 0 and not m.is_admin]
        print(f"\n📍 {titles[chat_id]} (chat_id={chat_id})")
        print(f"   Total inspeccionados: {len(members)} | Con alguna señal: {len(relevant)}")
        cas_hits = [m for m in members if m.cas_offenses > 0 and not m.is_admin]
        if cas_hits:
            print(f"   🛡️ CAS match: {len(cas_hits)}")
        print(f"\n   {'Score':>5} {'CAS':>4} {'UserID':>11} {'Username':<20} {'Razones'}")
        print(f"   {'-'*5} {'-'*4} {'-'*11} {'-'*20} {'-'*40}")
        for m in relevant[: args.top]:
            uname = ("@" + m.username) if m.username else "(none)"
            if len(uname) > 20:
                uname = uname[:19] + "…"
            print(f"   {m.score:>5} {m.cas_offenses:>4} {m.user_id:>11} {uname:<20} {', '.join(m.reasons)}")
            if args.ban_cas and m.cas_offenses > 0:
                total_to_ban.append(m.user_id)

    # ============== Separar CAS en autoban vs revisión manual ==============
    # autoban: offenses >= cas_autoban_min (default 2). review: 0 < offenses < min
    autoban_uids: set[int] = set()
    review_candidates: list[MemberFlags] = []
    seen_review_uids: set[int] = set()
    for cid, members in suspicious_by_chat.items():
        for m in members:
            if m.is_admin:
                continue
            if m.cas_offenses >= args.cas_autoban_min:
                autoban_uids.add(m.user_id)
            elif m.cas_offenses > 0 and m.user_id not in seen_review_uids:
                review_candidates.append(m)
                seen_review_uids.add(m.user_id)

    if args.ban_cas and autoban_uids:
        unique_ban = sorted(autoban_uids)
        print(f"\n🔨 Auto-baneando {len(unique_ban)} usuarios con CAS offenses >= {args.cas_autoban_min} (federado en {len(chats)} chats)...")

        banned_items_by_chat: dict[int, list[dict]] = {cid: [] for cid in chats}
        for cid, members in suspicious_by_chat.items():
            for m in members:
                if m.user_id in unique_ban:
                    banned_items_by_chat[cid].append({
                        "user_id": m.user_id, "username": m.username,
                        "cas_offenses": m.cas_offenses, "reasons": m.reasons,
                    })

        for uid in unique_ban:
            results = await _bot_ban_federated(bot_token, uid, chats)
            db.add_ban(user_id=uid, reason="Auto-ban CAS via analyze", rule="cas_match", banned_in_chat=chats[0])
            ok = sum(1 for v in results.values() if v == "ok")
            err = sum(1 for v in results.values() if v.startswith("error"))
            print(f"   user {uid}: {ok} ok · {err} err")

        await _post_batch_summary(bot_token, banned_items_by_chat, category="cas_match")
    elif args.ban_cas:
        print(f"\n✅ Sin CAS matches con offenses >= {args.cas_autoban_min} para autoban.")

    # ============== Candidatos a revisión humana (CAS=1) ==============
    if review_candidates and args.notify_chat:
        print(f"\n👀 {len(review_candidates)} candidatos CAS<{args.cas_autoban_min} para revisión humana → enviando a chat {args.notify_chat}...")
        # Re-conectar telethon brevemente para sacar fotos
        client = TelegramClient("/app/data/telethon.session", int(os.getenv("TG_API_ID")), os.getenv("TG_API_HASH"))
        await client.start(phone=os.getenv("TG_PHONE"))
        await _send_review_candidates(bot_token, args.notify_chat, review_candidates, client)
        await client.disconnect()

    print()
    print("=" * 72)
    print("Listo. Para banear manualmente: ./ctl.sh restart && envía /ban <user_id> al bot por DM")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
