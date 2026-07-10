#!/usr/bin/env python3
"""Asistente interactivo de configuración: genera el archivo `.env` preguntando
paso a paso (token del bot, tu user_id, grupos a moderar, modo).

Se ejecuta en el HOST, ANTES de levantar Docker, y NO necesita dependencias
(solo la librería estándar de Python):

    python3 scripts/setup.py

Toma `.env.example` como plantilla (con todos los comentarios y defaults) y solo
rellena los valores que respondas. El resto queda con sus valores por defecto.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
ENV = ROOT / ".env"

# Colores ANSI (se desactivan solos si la terminal no los soporta)
_C = sys.stdout.isatty()
BOLD = "\033[1m" if _C else ""
DIM = "\033[2m" if _C else ""
GREEN = "\033[32m" if _C else ""
YELLOW = "\033[33m" if _C else ""
CYAN = "\033[36m" if _C else ""
RESET = "\033[0m" if _C else ""


def _print_help(text: str) -> None:
    for line in text.strip("\n").splitlines():
        print(f"   {DIM}{line}{RESET}")


def ask(
    label: str,
    help_text: str = "",
    default: str | None = None,
    validate=None,
    required: bool = False,
    secret: bool = False,
) -> str:
    """Pregunta un valor con ayuda, default y validación. Repite si es inválido."""
    print()
    print(f"{BOLD}{CYAN}▸ {label}{RESET}")
    if help_text:
        _print_help(help_text)
    suffix = f" {DIM}[{default}]{RESET}" if default not in (None, "") else ""
    while True:
        try:
            raw = input(f"   {GREEN}➜{RESET} {label}{suffix}: ").strip()
        except EOFError:
            raw = ""
        if not raw and default is not None:
            raw = default
        if not raw and required:
            print(f"   {YELLOW}Este valor es obligatorio, no puede quedar vacío.{RESET}")
            continue
        if raw and validate is not None:
            ok, msg = validate(raw)
            if not ok:
                print(f"   {YELLOW}{msg}{RESET}")
                again = input("   ¿Usarlo igualmente? (s/N): ").strip().lower()
                if again not in ("s", "si", "sí", "y", "yes"):
                    continue
        if secret and raw:
            shown = raw[:6] + "…" + raw[-4:] if len(raw) > 12 else "…"
            print(f"   {DIM}guardado: {shown}{RESET}")
        return raw


def _valid_token(v: str) -> tuple[bool, str]:
    if re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{30,}", v):
        return True, ""
    return False, "No parece un token válido (formato <números>:<letras/números>)."


def _valid_userid(v: str) -> tuple[bool, str]:
    if v.isdigit():
        return True, ""
    return False, "Debe ser un número (tu user_id de Telegram, sin @)."


def _valid_chatids(v: str) -> tuple[bool, str]:
    parts = [p.strip() for p in v.split(",") if p.strip()]
    if all(p.lstrip("-").isdigit() for p in parts):
        return True, ""
    return False, "Deben ser chat_id numéricos separados por comas (empiezan por -100)."


def set_var(text: str, key: str, value: str) -> str:
    """Sustituye `KEY=...` (línea completa) por `KEY=value` conservando el resto.

    Usa una FUNCIÓN de reemplazo (no un string): así el valor se inserta literal
    y re.sub no interpreta escapes como `\\1` o `\\g<0>` si aparecen en el valor.
    """
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(lambda _m: f"{key}={value}", text, count=1)
    # Si por lo que sea no está en la plantilla, lo añadimos al final.
    return text.rstrip() + f"\n{key}={value}\n"


def _read_var(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main() -> int:
    force = "--force" in sys.argv[1:] or "-f" in sys.argv[1:]
    print(f"\n{BOLD}🛡️  Asistente de configuración — Bot Antispam Telegram{RESET}")
    print(f"{DIM}Genera tu archivo .env respondiendo unas preguntas. Ctrl+C para salir.{RESET}")

    if not EXAMPLE.is_file():
        print(f"\n{YELLOW}No encuentro .env.example en {EXAMPLE}. ¿Estás en la raíz del repo?{RESET}")
        return 1

    if ENV.is_file():
        cur = ENV.read_text()
        ya_token = bool(_read_var(cur, "TELEGRAM_BOT_TOKEN"))
        ya_admin = bool(_read_var(cur, "ADMIN_USER_ID"))
        if ya_token and ya_admin and not force:
            # Ya configurado: no molestamos. Editar a mano o --force para rehacerlo.
            print(f"\n{GREEN}✅ Ya está configurado.{RESET} Tu .env tiene el token y el admin puestos.")
            print(f"   {DIM}Para cambiar algo, edita el archivo .env directamente,{RESET}")
            print(f"   {DIM}o fuerza el asistente de nuevo:  python3 scripts/setup.py --force{RESET}\n")
            return 0
        print(f"\n{YELLOW}Ya existe un .env.{RESET} Actualizaré token, user_id, grupos y modo;")
        print(f"   {DIM}el RESTO de tu configuración (Telethon, umbrales, etc.) se conserva.{RESET}")
        if input("   ¿Continuar? (s/N): ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
            print("   Cancelado. No se ha tocado tu .env.")
            return 0

    # Si ya hay un .env, partimos de ÉL (conserva toda la config extra) y solo
    # actualizamos las 4 variables preguntadas. Si no, partimos de la plantilla.
    text = ENV.read_text() if ENV.is_file() else EXAMPLE.read_text()

    token = ask(
        "Token del bot (TELEGRAM_BOT_TOKEN)",
        help_text=(
            "Cómo crearlo (30 segundos):\n"
            " 1. En Telegram abre @BotFather y escribe /newbot\n"
            " 2. Ponle un nombre y un @usuario que termine en 'bot'\n"
            " 3. Te devuelve un token tipo  8123456789:AAF-xxxxxxxxxxxxxxxxxxxx\n"
            " 4. Pégalo aquí"
        ),
        validate=_valid_token,
        required=True,
        secret=True,
    )

    admin = ask(
        "Tu user_id de Telegram (ADMIN_USER_ID)",
        help_text=(
            "Serás el ÚNICO admin del bot (banear, aprender, configurar).\n"
            "Para saber tu id: escribe a @userinfobot y te dirá tu número.\n"
            "Ejemplo: 123456789"
        ),
        validate=_valid_userid,
        required=True,
    )

    chats = ask(
        "Grupos a moderar (MODERATED_CHAT_IDS)",
        help_text=(
            "Deja VACÍO (pulsa Enter) para que modere TODOS los grupos donde lo\n"
            "hagas admin (recomendado). O pega los chat_id separados por comas.\n"
            "El chat_id lo da @getidsbot o @RawDataBot dentro del grupo (empieza por -100).\n"
            "Ejemplo: -1001234567890,-1009876543210"
        ),
        default="",
        validate=_valid_chatids,
    )

    notify = ask(
        "¿Dónde recibir los avisos del bot? (ADMIN_NOTIFY_CHAT_ID)",
        help_text=(
            "Pulsa Enter (VACÍO) = te llegan a tu DM privado con el bot (recomendado).\n"
            "  IMPORTANTE: para recibir DMs, abre tu bot en Telegram y pulsa START una vez.\n"
            "O pega el chat_id de un GRUPO de moderación (empieza por -100); el bot debe\n"
            "estar en ese grupo. Ejemplo: -1001234567890"
        ),
        default="",
        validate=_valid_chatids,
    )

    mode = ask(
        "Modo de arranque (MODE)",
        help_text=(
            "shadow = solo REGISTRA lo que haría, no banea (para probar unos días).\n"
            "active = ejecuta acciones reales (ban/kick/delete).\n"
            "Recomendado empezar en shadow y pasar a active cuando confíes."
        ),
        default="shadow",
        validate=lambda v: (v in ("shadow", "active"), "Escribe 'shadow' o 'active'."),
    )

    text = set_var(text, "TELEGRAM_BOT_TOKEN", token)
    text = set_var(text, "ADMIN_USER_ID", admin)
    text = set_var(text, "MODERATED_CHAT_IDS", chats)
    text = set_var(text, "ADMIN_NOTIFY_CHAT_ID", notify)
    text = set_var(text, "MODE", mode)
    ENV.write_text(text)

    print(f"\n{GREEN}{BOLD}✅ .env guardado en {ENV}{RESET}")
    print(f"\n{BOLD}Siguientes pasos:{RESET}")
    print(f"  1. Añade tu bot como {BOLD}administrador{RESET} en cada grupo a moderar,")
    print(f"     con permisos de {BOLD}borrar mensajes{RESET} y {BOLD}expulsar/banear usuarios{RESET}.")
    print("  2. En @BotFather desactiva el modo privacidad para que vea todos los")
    print(f"     mensajes:  /setprivacy  →  tu bot  →  {BOLD}Disable{RESET}.")
    print("  3. Levanta el bot:")
    print(f"       {CYAN}docker compose up -d --build{RESET}")
    print("  4. Comprueba que arrancó:")
    print(f"       {CYAN}docker compose logs -f{RESET}   {DIM}(verás \"Bot @... listo\"){RESET}")
    if not notify:
        print(f"  5. {BOLD}Abre tu bot en Telegram y pulsa START/INICIAR una vez{RESET} — si no,")
        print("     Telegram no le deja mandarte los avisos por DM (no puede escribirte primero).")
    if mode == "shadow":
        print(f"\n  {DIM}Estás en modo shadow: cuando confíes, cambia MODE=active en .env y{RESET}")
        print(f"  {DIM}reinicia con  docker compose up -d.{RESET}")
    print()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        raise SystemExit(130)
