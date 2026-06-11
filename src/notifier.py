"""Notificaciones al admin vía Casa_Yona (bot separado).

Incluye botones inline "Era spam / No era spam / Whitelist" que el handler
de callbacks revierte si el admin lo decide.
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass

import aiohttp

from . import trust as _trust

log = logging.getLogger(__name__)


@dataclass
class Notifier:
    casa_yona_token: str
    notify_chat_id: int | str
    enabled: bool

    def is_configured(self) -> bool:
        return self.enabled and bool(self.casa_yona_token) and bool(self.notify_chat_id)

    async def send_text(self, text: str, parse_mode: str = "HTML") -> bool:
        """Envío simple sin botones (acks técnicos de comandos admin)."""
        if not self.is_configured():
            return False
        url = f"https://api.telegram.org/bot{self.casa_yona_token}/sendMessage"
        payload = {
            "chat_id": self.notify_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        log.warning("Casa_Yona send_text falló: %s", data)
                        return False
                    return True
        except Exception as exc:
            log.warning("Notifier send_text error: %s", exc)
            return False

    async def send_action_alert(
        self,
        session: aiohttp.ClientSession,
        action_id: int,
        chat_title: str | None,
        chat_id: int,
        user_id: int | None,
        username: str | None,
        action: str,
        rule: str,
        reason: str,
        score: int,
        original_text: str | None,
        mode: str,
        federation_results: dict[int, str] | None,
        user_signals_markup: str = "",
    ) -> bool:
        if not self.is_configured():
            return False

        chat_title = chat_title or str(chat_id)
        username_disp = f"@{username}" if username else "(sin username)"
        text_preview = (original_text or "")[:300]

        fed_summary = ""
        if federation_results:
            ok = sum(1 for v in federation_results.values() if v == "ok")
            shadow = sum(1 for v in federation_results.values() if v == "shadow")
            err = sum(1 for v in federation_results.values() if v.startswith("error"))
            fed_summary = f"\n🌐 <b>Federación:</b> {ok} ok · {shadow} shadow · {err} err ({len(federation_results)} chats)"

        emoji = {"ban": "🔨", "kick": "👢", "mute": "🤐", "delete": "🗑️", "noop": "👁️"}.get(action, "ℹ️")
        mode_tag = "🌒 SHADOW" if mode == "shadow" else "🔴 ACTIVE"

        # tg://user?id=X permite abrir perfil del user directamente en el cliente
        user_link = f"<a href=\"tg://user?id={user_id}\">{html.escape(username_disp)}</a>" if user_id else html.escape(username_disp)

        msg = (
            f"{emoji} <b>{action.upper()}</b> · {mode_tag}\n"
            f"📍 <b>Chat:</b> {html.escape(chat_title)} (<code>{chat_id}</code>)\n"
            f"👤 <b>User:</b> {user_link} (<code>{user_id or '?'}</code>)\n"
            f"📏 <b>Nivel de spam:</b> {_trust.render_spam(score)} <i>(score interno {score})</i>\n"
            f"🚨 <b>Regla:</b> <code>{html.escape(rule)}</code>\n"
            f"💬 <b>Razón:</b> {html.escape(reason)}"
            f"{user_signals_markup}"
            f"{fed_summary}\n"
            f"\n📝 <b>Mensaje:</b>\n<pre>{html.escape(text_preview)}</pre>"
        )

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "❌ No era spam", "callback_data": f"notspam:{action_id}"},
                    {"text": "✅ Confirmar", "callback_data": f"confirm:{action_id}"},
                ],
                [
                    {"text": "🛡️ Whitelist user", "callback_data": f"wl:{action_id}"},
                ],
            ]
        }

        url = f"https://api.telegram.org/bot{self.casa_yona_token}/sendMessage"
        payload = {
            "chat_id": self.notify_chat_id,
            "text": msg,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
            "disable_web_page_preview": True,
        }
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    log.error("Casa_Yona sendMessage falló: %s", data)
                    return False
                return True
        except Exception as exc:
            log.warning("Notifier error: %s", exc)
            return False
