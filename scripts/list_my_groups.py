"""Lista los grupos/canales donde la cuenta Telethon es miembro.

Útil para diagnosticar antes de lanzar analyze_members.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()


async def main() -> int:
    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    if not api_id or not api_hash:
        print("Faltan TG_API_ID/TG_API_HASH en .env", file=sys.stderr)
        return 1
    client = TelegramClient("/app/data/telethon.session", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("No autenticado. Corre primero scripts/telethon_login.py request/confirm.", file=sys.stderr)
        return 1

    me = await client.get_me()
    print(f"Cuenta: {me.first_name} (@{me.username}) id={me.id}\n")
    print(f"{'Type':<12} {'ID':>15} {'Title':<60}")
    print("-" * 90)

    groups = 0
    # Chats objetivo: se leen de MODERATED_CHAT_IDS (.env), CSV de chat_ids.
    target_ids = {
        int(x) for x in os.getenv("MODERATED_CHAT_IDS", "").replace(" ", "").split(",")
        if x.strip().lstrip("-").isdigit()
    }
    found_targets: set[int] = set()

    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            groups += 1
            kind = "channel" if dialog.is_channel and not dialog.is_group else "group"
            title = (dialog.title or "")[:58]
            print(f"{kind:<12} {dialog.id:>15} {title}")
            if dialog.id in target_ids:
                found_targets.add(dialog.id)

    print()
    print(f"Total grupos/canales: {groups}")
    print()
    if target_ids:
        print("=== Estado de los chats objetivo (MODERATED_CHAT_IDS) ===")
        for cid in sorted(target_ids):
            mark = "✅ MIEMBRO" if cid in found_targets else "❌ NO MIEMBRO"
            print(f"  {mark}  {cid}")

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
