"""Login Telethon en dos pasos para entornos no-interactivos (docker exec).

Uso:
    python -m scripts.telethon_login request         # Solicita código (lo enviará Telegram a la app de TG_PHONE)
    python -m scripts.telethon_login confirm 12345   # Completa login con el código recibido
    python -m scripts.telethon_login confirm 12345 mi2faPassword   # Si hay 2FA
    python -m scripts.telethon_login status          # Comprueba si la session ya existe y es válida
    python -m scripts.telethon_login logout          # Cierra sesión Telethon y borra .session
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

load_dotenv()

SESSION = "/app/data/telethon.session"
PENDING = Path("/app/data/.pending_login.json")


def _client() -> TelegramClient:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    if not api_id or not api_hash:
        print("ERROR: Faltan TG_API_ID / TG_API_HASH en .env", file=sys.stderr)
        sys.exit(1)
    return TelegramClient(SESSION, int(api_id), api_hash)


async def cmd_request() -> int:
    phone = os.getenv("TG_PHONE")
    if not phone:
        print("ERROR: Falta TG_PHONE en .env (con prefijo internacional, ej. +34...)", file=sys.stderr)
        return 1
    client = _client()
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"YA AUTENTICADO como {me.first_name} (@{me.username}) id={me.id}")
        await client.disconnect()
        return 0
    sent = await client.send_code_request(phone)
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps({"phone": phone, "hash": sent.phone_code_hash}))
    print(f"Código solicitado para {phone}. Mira en la app oficial de Telegram (chat 'Telegram').")
    print("Cuando lo tengas, ejecuta:")
    print("  python -m scripts.telethon_login confirm <CODIGO>")
    print("o si tienes 2FA:")
    print("  python -m scripts.telethon_login confirm <CODIGO> <PASSWORD_2FA>")
    await client.disconnect()
    return 0


async def cmd_confirm(code: str, password: str | None) -> int:
    if not PENDING.exists():
        print("ERROR: No hay login pendiente. Ejecuta primero 'request'.", file=sys.stderr)
        return 1
    data = json.loads(PENDING.read_text())
    client = _client()
    await client.connect()
    try:
        await client.sign_in(phone=data["phone"], code=code, phone_code_hash=data["hash"])
    except PhoneCodeInvalidError:
        print("ERROR: código incorrecto.", file=sys.stderr)
        return 2
    except PhoneCodeExpiredError:
        print("ERROR: código expirado. Ejecuta 'request' otra vez.", file=sys.stderr)
        PENDING.unlink(missing_ok=True)
        return 3
    except SessionPasswordNeededError:
        if not password:
            print("ERROR: la cuenta tiene 2FA. Vuelve a ejecutar:", file=sys.stderr)
            print("  python -m scripts.telethon_login confirm <CODIGO> <PASSWORD_2FA>", file=sys.stderr)
            return 4
        await client.sign_in(password=password)
    me = await client.get_me()
    print(f"✅ Login OK como {me.first_name} (@{me.username}) id={me.id}")
    print(f"Session persistida en {SESSION}")
    PENDING.unlink(missing_ok=True)
    await client.disconnect()
    return 0


async def cmd_status() -> int:
    client = _client()
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Autenticado como {me.first_name} (@{me.username}) id={me.id}")
        await client.disconnect()
        return 0
    print("❌ No autenticado. Ejecuta 'request'.")
    await client.disconnect()
    return 1


async def cmd_logout() -> int:
    client = _client()
    await client.connect()
    if await client.is_user_authorized():
        await client.log_out()
        print("✅ Sesión Telethon cerrada en Telegram.")
    p = Path(SESSION)
    if p.exists():
        p.unlink()
        print(f"✅ {SESSION} eliminado.")
    PENDING.unlink(missing_ok=True)
    return 0


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "request":
        return await cmd_request()
    if cmd == "confirm":
        if len(sys.argv) < 3:
            print("Uso: confirm <CODIGO> [PASSWORD_2FA]", file=sys.stderr)
            return 1
        code = sys.argv[2]
        password = sys.argv[3] if len(sys.argv) > 3 else None
        return await cmd_confirm(code, password)
    if cmd == "status":
        return await cmd_status()
    if cmd == "logout":
        return await cmd_logout()
    print(f"Comando desconocido: {cmd}\n{__doc__}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
