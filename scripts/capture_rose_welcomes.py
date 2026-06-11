"""Captura el welcome y rules de Rose en cada grupo y los guarda en chat_settings.

Uso (dentro del contenedor):
    python -m scripts.capture_rose_welcomes
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.db import DB  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("capture_rose")


async def _capture(client: TelegramClient, chat, rose_user, cmd: str, timeout_s: int = 6) -> tuple[int, list, str]:
    sent = await client.send_message(chat, cmd)
    deadline = asyncio.get_event_loop().time() + timeout_s
    rose_msgs = []
    last_id = sent.id
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(1)
        async for m in client.iter_messages(chat, min_id=last_id, limit=10, reverse=True):
            if m.id <= last_id:
                continue
            last_id = m.id
            s = await m.get_sender()
            if s and getattr(s, "username", None) and s.username.lower() == rose_user.username.lower():
                rose_msgs.append(m)
        if rose_msgs:
            await asyncio.sleep(1.5)
            async for m in client.iter_messages(chat, min_id=last_id, limit=10, reverse=True):
                if m.id <= last_id:
                    continue
                last_id = m.id
                s = await m.get_sender()
                if s and getattr(s, "username", None) and s.username.lower() == rose_user.username.lower():
                    rose_msgs.append(m)
            break
    text = "\n\n".join(m.text or "" for m in rose_msgs if m.text)
    return sent.id, rose_msgs, text


async def main() -> int:
    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    db = DB(os.getenv("DB_PATH", "/app/data/antispam.db"))
    client = TelegramClient("/app/data/telethon.session", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        log.error("Telethon no autenticado")
        return 1
    rose = await client.get_entity("MissRose_bot")

    for chat_id in db.admin_chats():
        try:
            chat = await client.get_entity(chat_id)
        except Exception as exc:
            log.warning("skip %s: %s", chat_id, exc)
            continue
        log.info("==== %s ====", chat.title)
        db.ensure_chat_settings(chat_id)

        # /welcome noformat
        cmd_id, rose_msgs, welcome_raw = await _capture(client, chat, rose, "/welcome noformat")
        if welcome_raw:
            # Quitar todo lo anterior a "Los usuarios son bienvenidos con el siguiente mensaje:"
            m = re.search(r"Los usuarios son bienvenidos con el siguiente mensaje:\s*\n+(.+)", welcome_raw, re.DOTALL)
            if m:
                welcome_clean = m.group(1).strip()
            else:
                welcome_clean = re.sub(r"^.*?:\n", "", welcome_raw, count=1).strip()
            # Extraer TODOS los botones del welcome
            BUTTON_RE = re.compile(r"\[([^\]]+)\]\(buttonurl://([^\s\)]+?)(:same)?\)", re.I)
            buttons = []
            for bm in BUTTON_RE.finditer(welcome_clean):
                buttons.append({
                    "text": bm.group(1).strip(),
                    "url": bm.group(2).strip(),
                    "same": bool(bm.group(3)),
                })
            welcome_clean_no_btn = BUTTON_RE.sub("", welcome_clean).strip()
            # Reemplazar placeholders Rose
            welcome_clean_no_btn = (welcome_clean_no_btn
                .replace("{first}", "{name}")
                .replace("{fullname}", "{name}")
                .replace("{mention}", "{name}")
                .replace("{username}", "{name}")
                .replace("{chatname}", "{chat}"))
            # Markdown → HTML básico
            welcome_clean_no_btn = re.sub(r"\*([^\*\n]+)\*", r"<b>\1</b>", welcome_clean_no_btn)
            welcome_clean_no_btn = re.sub(r"_([^_\n]+)_", r"<i>\1</i>", welcome_clean_no_btn)
            db.update_chat_setting(chat_id, "welcome_text", welcome_clean_no_btn)
            # Migrar botones a welcome_buttons
            if buttons:
                db.clear_welcome_buttons(chat_id)
                for b in buttons:
                    db.add_welcome_button(chat_id, b["text"], b["url"], same_row=b["same"])
                # Legacy: dejar el primer botón también en welcome_button_text/url por compat
                db.update_chat_setting(chat_id, "welcome_button_text", buttons[0]["text"])
                db.update_chat_setting(chat_id, "welcome_button_url", buttons[0]["url"])
            log.info(
                "  ✓ welcome guardado (%d chars) con %d botón(es): %s",
                len(welcome_clean_no_btn), len(buttons),
                ", ".join(b['text'] for b in buttons) if buttons else "(ninguno)",
            )
        # Borrar comando + respuesta
        try:
            ids = [cmd_id] + [m.id for m in rose_msgs]
            await client.delete_messages(chat, ids[:3])
        except Exception:
            pass
        await asyncio.sleep(2)

        # /rules
        cmd_id, rose_msgs, rules_raw = await _capture(client, chat, rose, "/rules")
        if rules_raw and "rules for" in rules_raw.lower() or "reglas" in (rules_raw or "").lower():
            # Quitar header tipo "The rules for [grupo] are:"
            rules_clean = re.sub(r"^[^:]*:\s*", "", rules_raw, count=1).strip()
            if rules_clean and len(rules_clean) > 10 and "haven't been set" not in rules_clean.lower():
                db.update_chat_setting(chat_id, "rules_text", rules_clean)
                log.info("  ✓ rules guardadas (%d chars)", len(rules_clean))
            else:
                log.info("  – rules vacías o no configuradas")
        try:
            ids = [cmd_id] + [m.id for m in rose_msgs]
            await client.delete_messages(chat, ids[:3])
        except Exception:
            pass
        await asyncio.sleep(2)

    await client.disconnect()
    db.close()
    log.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
