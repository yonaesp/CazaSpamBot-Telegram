#!/usr/bin/env python3
"""Simulación realista: conversaciones enteras por el código del bot, sin tocar nada real.

Pasa escenas completas (entrar, saludar, esperar, soltar el enlace) por
`on_chat_member`, `on_message` y `on_manual_ban_callback`, con updates en el
formato exacto de la Bot API y el reloj avanzando de verdad entre mensajes. Cada
escena dice qué acción espera; si alguna no sale, el script termina con código 1.

La primera pasada (29-oct-2026) destapó dos fallos que los tests unitarios no
veían: `calentamiento` expulsaba a una persona normal y una red de reclutamiento
no daba nada (docs/lecciones.md, L48). Pásalo antes de dar por bueno un detector
nuevo y añade aquí su escena, con un caso de spam y otro de persona normal.

Uso:
    .venv/bin/python scripts/simular.py --vacia          # base vacía (lo que corre el test)
    .venv/bin/python scripts/simular.py --base COPIA.db  # con muestras y ajustes reales
    ... -v                                               # además, cada llamada a Telegram

`--base` es una COPIA de la base; la copia nocturna vale (data/backups/ es del
usuario del contenedor, así que con sudo y a una carpeta tuya, en 600: lleva datos
personales). El script trabaja sobre otra copia temporal y la borra al terminar.

Aislamiento: Telegram es un doble que apunta cada llamada; CAS y lols contestan
«no fichado»; Telethon y el veto de IA, apagados; el `.env` real no se carga y
cualquier conexión de red falla. Los ids de chat salen de la copia (o son
inventados con `--vacia`): ningún identificador real vive en este fichero.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import socket
import sqlite3
import sys
import tempfile
import time
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _sin_red(*a, **k):
    raise OSError("simulación: red bloqueada")


socket.socket.connect = _sin_red
socket.create_connection = _sin_red
import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False  # el .env real no entra

ADMIN = 111000111       # dueño del bot (inventado)
OTRO_ADMIN = 222000222  # admin de un grupo (inventado)
BOT_ID = 999000999      # el propio bot (inventado)
CHATS_VACIA = {-1000000000001 - i: (f"Grupo de prueba {i + 1}", f"grupo_prueba_{i + 1}") for i in range(4)}

RELOJ = [time.time()]


def avanza(minutos: float) -> None:
    RELOJ[0] += minutos * 60


# --- Telegram de mentira ---------------------------------------------------------------
LLAMADAS: list[tuple[str, dict]] = []
_mid = [900000]
_ADMIN_RIGHTS = {k: True for k in (
    "can_be_edited", "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
    "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users",
    "can_post_stories", "can_edit_stories", "can_delete_stories", "can_pin_messages")}


def _msg_res(data):
    _mid[0] += 1
    chat = data.get("chat_id", ADMIN)
    return {"message_id": _mid[0], "date": int(RELOJ[0]),
            "chat": {"id": chat, "type": "supergroup" if int(chat) < 0 else "private"},
            "text": data.get("text") or data.get("caption") or ""}


def _bot_falso():
    from telegram import Bot
    from telegram.error import BadRequest

    class BotFalso(Bot):
        async def _do_post(self, endpoint, data, **kw):
            LLAMADAS.append((endpoint, dict(data)))
            if endpoint == "getMe":
                return {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "BotSimulado"}
            if endpoint in ("sendMessage", "sendPhoto", "editMessageText", "editMessageReplyMarkup",
                            "sendAnimation", "forwardMessage", "copyMessage"):
                return _msg_res(data)
            if endpoint == "getChatMember":
                uid = int(data["user_id"])
                u = {"id": uid, "is_bot": uid == BOT_ID, "first_name": "x"}
                if uid in (BOT_ID, OTRO_ADMIN, ADMIN):
                    return {"status": "administrator", "user": u, "is_anonymous": False, **_ADMIN_RIGHTS}
                return {"status": "member", "user": u}
            if endpoint == "getChatAdministrators":
                return [{"status": "administrator", "is_anonymous": False, **_ADMIN_RIGHTS,
                         "user": {"id": i, "is_bot": i == BOT_ID, "first_name": "adm"}}
                        for i in (BOT_ID, OTRO_ADMIN)]
            if endpoint == "getUserProfilePhotos":
                return {"total_count": 1, "photos": [[{"file_id": "F", "file_unique_id": "U",
                                                       "width": 160, "height": 160}]]}
            if endpoint == "getChatMemberCount":
                return 5000
            if endpoint == "getChat":
                raise BadRequest("simulación: getChat no imitado")
            return True

    return BotFalso


class _Resp:
    status = 200

    def __init__(self, data):
        self._d = data

    async def json(self, **k):
        return self._d

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class SesionHttp:
    """CAS y lols contestan «no fichado», como para casi todo el que entra."""

    def get(self, url, **k):
        return _Resp({"ok": False, "description": "Record not found."} if "cas" in url
                     else {"ok": True, "banned": False, "offenses": 0})


class JobQueueFalsa:
    def run_once(self, *a, **k):
        pass

    def run_repeating(self, *a, **k):
        pass

    def get_jobs_by_name(self, *a):
        return []


class ReporterFalso:
    def get_client(self):
        return None

    def is_ready(self):
        return False

    def __getattr__(self, n):
        async def _f(*a, **k):
            return None
        return _f


# --- updates con el formato de la Bot API --------------------------------------------
_upd = [1]


def _utf16(s):
    return len(s.encode("utf-16-le")) // 2


def _entidades(texto):
    ents = [{"type": "mention", "offset": _utf16(texto[:m.start()]), "length": _utf16(m.group())}
            for m in re.finditer(r"@[A-Za-z0-9_]{4,}", texto)]
    ents += [{"type": "url", "offset": _utf16(texto[:m.start()]), "length": _utf16(m.group())}
             for m in re.finditer(r"(?:https?://)?t\.me/\S+", texto)]
    return ents


def _usuario(u):
    d = {"id": u["id"], "is_bot": False, "first_name": u["nombre"], "language_code": "es"}
    if u.get("username"):
        d["username"] = u["username"]
    return d


class Sim:
    def __init__(self, app, chats):
        self.app, self.chats = app, chats
        self.db = app.bot_data["db"]
        self.fallos: list[str] = []

    def _chat(self, cid):
        titulo, un = self.chats[cid]
        return {"id": cid, "type": "supergroup", "title": titulo, "username": un}

    async def _despacha(self, handler, upd):
        from telegram import Update
        _upd[0] += 1
        antes = len(LLAMADAS)
        await handler(Update.de_json({"update_id": _upd[0], **upd}, self.app.bot), self.app)
        return LLAMADAS[antes:]

    async def entra(self, cid, u):
        from src import handlers
        await self._despacha(handlers.on_chat_member, {"chat_member": {
            "chat": self._chat(cid), "from": _usuario(u), "date": int(RELOJ[0]),
            "old_chat_member": {"status": "left", "user": _usuario(u)},
            "new_chat_member": {"status": "member", "user": _usuario(u)}}})
        self.db.mark_verified(cid, u["id"])  # pulsa el botón si el grupo verifica

    async def escribe(self, cid, u, texto):
        from src import handlers
        _mid[0] += 1
        m = {"message_id": _mid[0], "date": int(RELOJ[0]), "chat": self._chat(cid),
             "from": _usuario(u), "text": texto}
        if ents := _entidades(texto):
            m["entities"] = ents
        return await self._despacha(handlers.on_message, {"message": m})

    def accion(self, cid, uid, desde):
        """Última acción registrada (None si nada o noop) y la regla."""
        with self.db._cur() as c:
            f = c.execute("SELECT rule, action, score FROM moderation_log WHERE user_id=? AND chat_id=? "
                          "AND ts>=? ORDER BY id DESC LIMIT 1", (uid, cid, desde)).fetchone()
        if not f or f["action"] == "noop":
            return None, (f"{f['rule']} {f['score']:.0f} (noop)" if f else "")
        return f["action"], f"{f['rule']} {f['score']:.0f}"

    async def escena(self, nombre, cid, u, pasos, espera):
        """pasos: [(minutos, texto)]; `espera`: acción del ÚLTIMO mensaje (None = ninguna).
        Los anteriores no deben provocar ninguna."""
        print(f"\n== {nombre} ==")
        t0 = RELOJ[0]
        await self.entra(cid, u)
        for i, (mins, texto) in enumerate(pasos):
            avanza(mins)
            ll = await self.escribe(cid, u, texto)
            accion, detalle = self.accion(cid, u["id"], RELOJ[0])
            esperada = espera if i == len(pasos) - 1 else None
            ok = accion == esperada
            corto = texto if len(texto) < 70 else texto[:67] + "..."
            print(f"  {'✓' if ok else '✗'} +{(RELOJ[0] - t0) / 60:3.0f} min «{corto}» → "
                  f"{accion or 'nada'}{f' [{detalle}]' if detalle else ''}"
                  + ("" if ok else f"  (se esperaba {esperada or 'nada'})"))
            if not ok:
                self.fallos.append(f"{nombre}: «{corto}» → {accion}, se esperaba {esperada}")
            _detalle_llamadas(ll)


VERBOSO = [False]


def _detalle_llamadas(ll):
    if not VERBOSO[0]:
        return
    for ep, d in ll:
        if ep.startswith("get"):
            continue
        txt = " ".join(str(d.get("text") or d.get("caption") or "").split())[:110]
        rm = d.get("reply_markup")
        bot = (" [" + " | ".join(b.text for f in rm.inline_keyboard for b in f) + "]"
               if rm is not None and hasattr(rm, "inline_keyboard") else "")
        print(f"        telegram: {ep}({d.get('chat_id', '')}) {txt}{bot}".rstrip())


def _nuevo(i, nombre, username=None):
    return {"id": 8_600_000_000 + i, "nombre": nombre, "username": username}


async def escenas(s: Sim) -> None:
    c1, c2, c3, c4 = list(s.chats)[:4]

    # Calentamiento (L47, L48): solo una invitación privada tras el relleno.
    await s.escena("Calienta y suelta un @ de fuera", c1, _nuevo(1, "Lucía Romero"), [
        (6, "hola"), (3, "buenas a todos"), (4, "👍"),
        (35, "Para soporte de Windows escribid a @SoporteWinOficial24")], "mute")
    await s.escena("Calienta y suelta una invitación privada", c1, _nuevo(2, "Marta Gil"), [
        (5, "hola"), (2, "ok"), (6, "jaja"), (40, "Unios aquí, regalamos licencias: t.me/+Ab3dEfGhIjk")], "kick")
    await s.escena("Control: conversa de verdad y luego la misma invitación", c1, _nuevo(3, "Pablo Ruiz"), [
        (5, "hola, tengo una duda con la barra de tareas"), (4, "se me queda congelada al arrancar el equipo"),
        (6, "ya probé reiniciar el explorador y nada"),
        (40, "Unios aquí, regalamos licencias: t.me/+Ab3dEfGhIjk")], "mute")
    await s.escena("Persona normal: saluda corto y recomienda un canal", c4, _nuevo(4, "Andrés Molina", "andresmol"), [
        (3, "hola!"), (2, "gracias"), (8, "vale lo miro"), (30, "en @xataka sacaron un artículo sobre eso")], "mute")
    await s.escena("Persona normal: saluda corto y pasa un grupo público", c4, _nuevo(5, "Rosa Navarro", "rosanav"), [
        (3, "buenas"), (2, "gracias!!"), (8, "ok"),
        (30, "yo lo pregunté en t.me/WindowsAyuda y me ayudaron")], "mute")

    # Oleadas (L47) y reclutamiento (L48).
    oferta = [
        "Hola a todos, busco 5 personas serias para un proyecto online, se gana entre 200 y 300 euros al día "
        "desde el móvil, interesados escribidme por privado",
        "Hola a todos 👋 busco 5 personas serias para un proyecto online, se gana entre 200 y 300 euros al dia "
        "desde el movil, interesados escribidme por privado",
        "HOLA A TODOS, busco 5 personas serias para un proyecto online, se gana entre 200 y 300 euros al día "
        "desde el móvil. Interesados escribidme por privado 💰",
    ]
    for i, (cid, txt, esp) in enumerate(zip((c2, c1, c3), oferta, ("kick", "ban", "ban"))):
        await s.escena(f"Red que recluta, cuenta {i + 1}/3", cid, _nuevo(10 + i, f"Cuenta{i + 1}"), [(12, txt)], esp)
    sigilo = [
        "Buenas gente, acabo de encontrar una herramienta gratuita que arregla todos los errores de Windows en "
        "dos minutos, la tengo en mi perfil por si a alguien le sirve",
        "Buenas gente!! acabo de encontrar una herramienta gratuita que arregla todos los errores de windows en "
        "dos minutos, la tengo en mi perfil por si a alguien le sirve",
        "buenas gente, acabo de encontrar una herramienta gratuita que arregla todos los errores de Windows en "
        "dos minutos. La tengo en mi perfil por si a alguien le sirve 🙂",
    ]
    for i, (cid, txt) in enumerate(zip((c4, c1, c2), sigilo)):
        await s.escena(f"Red sin palabras de spam, cuenta {i + 1}/3 (oleada solo suma)", cid,
                       _nuevo(20 + i, f"Sigilo{i + 1}"), [(9, txt)], None)
    error = ("Me sale el error 0x800f0922 al instalar la actualización acumulativa de octubre de Windows 11, "
             "alguien sabe cómo arreglarlo?")
    await s.escena("Dos personas pegan el mismo error (1/2)", c1, _nuevo(30, "Jorge Peña", "jorgep"), [(15, error)], None)
    await s.escena("Dos personas pegan el mismo error (2/2)", c4, _nuevo(31, "Elena Sanz", "elenasanz"), [(20, error)], None)

    # Ban manual de otro admin y los botones del aviso (L47).
    from src import handlers
    print("\n== Otro admin banea a mano y pulsas «Banear en todos» ==")
    u = _nuevo(40, "Charlotte")
    await s.entra(c4, u)
    avanza(5)
    ll = await s._despacha(handlers.on_chat_member, {"chat_member": {
        "chat": s._chat(c4), "from": {"id": OTRO_ADMIN, "is_bot": False, "first_name": "Admin"},
        "date": int(RELOJ[0]), "old_chat_member": {"status": "member", "user": _usuario(u)},
        "new_chat_member": {"status": "kicked", "user": _usuario(u), "until_date": 0}}})
    _detalle_llamadas(ll)
    botones = [b.callback_data for ep, d in ll if ep == "sendMessage" and hasattr(d.get("reply_markup"), "inline_keyboard")
               for f in d["reply_markup"].inline_keyboard for b in f]
    cb = next((b for b in botones if b and b.startswith("mban:all:")), None)
    _comprueba(s, "el aviso trae «Banear en todos»", cb is not None)
    if cb:
        def _pulsa():
            return s._despacha(handlers.on_manual_ban_callback, {"callback_query": {
                "id": "1", "chat_instance": "ci", "data": cb,
                "from": {"id": ADMIN, "is_bot": False, "first_name": "Dueño"},
                "message": {"message_id": 1, "date": int(RELOJ[0]),
                            "chat": {"id": ADMIN, "type": "private"}, "text": "aviso"}}})
        ll = await _pulsa()
        _detalle_llamadas(ll)
        baneados = {d["chat_id"] for ep, d in ll if ep == "banChatMember"}
        _comprueba(s, f"baneado en {len(baneados)} de {len(s.chats)} grupos", baneados == set(s.chats))
        ll = await _pulsa()
        _comprueba(s, "la segunda pulsación no repite el ban",
                   not any(ep == "banChatMember" for ep, _ in ll))


def _comprueba(s: Sim, que: str, ok: bool) -> None:
    print(f"  {'✓' if ok else '✗'} {que}")
    if not ok:
        s.fallos.append(que)


def _chats_de(base: str) -> dict[int, tuple[str, str]]:
    c = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    filas = c.execute("SELECT chat_id, title, username FROM bot_chats WHERE type='supergroup' "
                      "AND am_admin=1 AND can_restrict=1 ORDER BY chat_id LIMIT 4").fetchall()
    c.close()
    return {cid: (t or "grupo", un or "") for cid, t, un in filas}


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--base", help="copia de antispam.db (no la viva)")
    g.add_argument("--vacia", action="store_true", help="base nueva, sin datos reales")
    ap.add_argument("-v", action="store_true", help="enseña cada llamada a Telegram")
    a = ap.parse_args()
    VERBOSO[0] = a.v

    with tempfile.TemporaryDirectory(prefix="simulacion-") as tmp:
        db_path = os.path.join(tmp, "sim.db")
        if a.base:
            if Path(a.base).resolve() == (_ROOT / "data" / "antispam.db").resolve():
                sys.exit("--base tiene que ser una COPIA, no la base viva")
            shutil.copy(a.base, db_path)
            chats = _chats_de(db_path)
            if len(chats) < 4:
                sys.exit(f"la copia tiene {len(chats)} grupos donde el bot puede moderar; hacen falta 4")
        else:
            chats = CHATS_VACIA
        os.environ.update({
            "TELEGRAM_BOT_TOKEN": "123:SIMULACION", "ADMIN_USER_ID": str(ADMIN), "MODE": "active",
            "MODERATED_CHAT_IDS": ",".join(str(c) for c in chats), "TELETHON_ENABLED": "false",
            "TG_API_ID": "", "TG_API_HASH": "", "ANTHROPIC_API_KEY": "", "LLM_VETO": "false",
            "EXTERNAL_NOTIFY_ENV_PATH": "", "DB_PATH": db_path,
        })
        time.time = lambda: RELOJ[0]

        from src.config import load_config
        from src.db import DB
        cfg = load_config()
        db = DB(cfg.db_path)
        bot = _bot_falso()(cfg.telegram_bot_token)
        await bot.initialize()
        app = types.SimpleNamespace(
            bot=bot, args=[], user_data={}, job=None, error=None,
            bot_data={"cfg": cfg, "db": db, "http": SesionHttp(), "reporter": ReporterFalso(),
                      "notifier": types.SimpleNamespace(is_configured=lambda: False)})
        app.application = types.SimpleNamespace(
            job_queue=JobQueueFalsa(), bot_data=app.bot_data,
            create_task=lambda c, *x, **k: asyncio.ensure_future(c))
        s = Sim(app, chats)
        await escenas(s)

    if s.fallos:
        print(f"\n✗ {len(s.fallos)} escena(s) no dieron lo esperado:")
        for f in s.fallos:
            print(f"  - {f}")
        return 1
    print("\n✓ Todas las escenas dieron lo esperado.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
