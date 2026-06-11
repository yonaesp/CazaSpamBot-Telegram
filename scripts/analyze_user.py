"""Analiza un usuario concreto en todos los grupos del bot.

Uso: python -m scripts.analyze_user @username
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DB  # noqa: E402

load_dotenv()


async def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python -m scripts.analyze_user @username|user_id")
        return 1
    target = sys.argv[1]
    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    if not api_id or not api_hash:
        print("Faltan TG_API_ID/TG_API_HASH")
        return 1
    db = DB(os.getenv("DB_PATH", "/app/data/antispam.db"))

    client = TelegramClient("/app/data/telethon.session", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("Telethon no autenticado")
        return 1

    # Resolver entidad del target
    try:
        ent = await client.get_entity(target)
    except (UsernameInvalidError, UsernameNotOccupiedError, ValueError) as exc:
        print(f"No se pudo resolver {target}: {exc}")
        return 1

    print(f"=== USUARIO ===")
    print(f"id={ent.id}  @{ent.username}  first={ent.first_name}  last={ent.last_name}")
    print(f"is_bot={ent.bot}  premium={getattr(ent,'premium',False)}  has_photo={ent.photo is not None}")
    try:
        photos = await client.get_profile_photos(ent, limit=10)
        if photos:
            dates = sorted([p.date for p in photos if hasattr(p, "date") and p.date])
            print(f"photo_count={len(photos)}  oldest={dates[0]}  newest={dates[-1]}")
            age_days = (_dt.datetime.now(tz=dates[0].tzinfo) - dates[0]).days
            print(f"account_age_days≈{age_days}")
    except Exception as e:
        print(f"profile_photos error: {e}")
    print()

    chats = [(c["chat_id"], c["title"]) for c in db.all_chats() if c["am_admin"]]
    chats_with_user: list[tuple[int, str]] = []
    all_messages = []

    for chat_id, title in chats:
        try:
            chat = await client.get_entity(chat_id)
        except Exception as e:
            print(f"skip {chat_id}: {e}")
            continue
        # ¿Está en el chat?
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            await client(GetParticipantRequest(chat, ent))
            chats_with_user.append((chat_id, title))
            present = True
        except Exception:
            present = False
        # Obtener sus mensajes (límite 200 para no abrumar)
        msgs = []
        try:
            async for m in client.iter_messages(chat, from_user=ent, limit=200):
                msgs.append(m)
        except Exception as e:
            print(f"iter_messages {title}: {e}")
        all_messages.append((title, present, msgs))

    # Resumen
    print("=== ESTADO EN LOS 3 GRUPOS ===")
    for title, present, msgs in all_messages:
        join_info = ""
        # Intentar sacar fecha de join via Telethon
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            cid = next(c for c, t in chats if t == title)
            chat = await client.get_entity(cid)
            res = await client(GetParticipantRequest(chat, ent))
            p = res.participant
            if hasattr(p, "date") and p.date:
                join_info = f"  (joined {p.date.strftime('%Y-%m-%d')})"
        except Exception:
            pass
        print(f"• {title}: {'✅ MIEMBRO' if present else '❌ NO MIEMBRO'}  msgs={len(msgs)}{join_info}")

    # Análisis de mensajes
    print()
    print("=== MENSAJES (más antiguo → más reciente) ===")
    flat = []
    for title, present, msgs in all_messages:
        for m in msgs:
            flat.append((m.date, title, m))
    flat.sort(key=lambda x: x[0])
    if not flat:
        print("(sin mensajes encontrados)")
    for date, title, m in flat[:80]:
        txt = (m.text or "(media/no-text)")[:200]
        rep = " [REPLY]" if m.reply_to_msg_id else ""
        print(f"[{date.strftime('%Y-%m-%d %H:%M')}] {title}{rep}: {txt}")

    if len(flat) > 80:
        print(f"... ({len(flat) - 80} mensajes más antiguos omitidos)")

    print()
    print("=== ANÁLISIS ESTADÍSTICO ===")
    if flat:
        total = len(flat)
        avg_len = sum(len((m.text or "")) for _, _, m in flat) / total
        only_emoji = sum(1 for _, _, m in flat if m.text and all(not c.isalnum() for c in m.text.strip()))
        replies = sum(1 for _, _, m in flat if m.reply_to_msg_id)
        short = sum(1 for _, _, m in flat if m.text and len(m.text) < 10)
        media_only = sum(1 for _, _, m in flat if not m.text)
        first_date = flat[0][0]
        last_date = flat[-1][0]
        days_active = max(1, (last_date - first_date).days)
        msgs_per_day = total / days_active
        print(f"Total mensajes (en estos 3 chats): {total}")
        print(f"Período: {first_date.strftime('%Y-%m-%d')} → {last_date.strftime('%Y-%m-%d')} ({days_active} días)")
        print(f"Frecuencia: {msgs_per_day:.1f} msgs/día")
        print(f"Longitud media: {avg_len:.0f} chars")
        print(f"Solo emojis/símbolos: {only_emoji} ({only_emoji*100//total}%)")
        print(f"Cortos (<10 chars): {short} ({short*100//total}%)")
        print(f"Solo media (sin texto): {media_only}")
        print(f"Replies (respuestas): {replies} ({replies*100//total}%)")

    await client.disconnect()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
