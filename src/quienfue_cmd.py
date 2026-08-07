"""/quienfue — quién tocó a este usuario, y qué le hizo.

Nace de un caso real: un usuario baneado aparecía dentro del grupo día y medio
después, y averiguar quién había deshecho el ban exigió consultar a mano el
registro de acciones de Telegram por MTProto. Esto lo pone a un comando.

Telegram guarda un historial de acciones de administrador por grupo
(`channels.getAdminLog`) que la Bot API **no expone**: hace falta la cuenta
Telethon. Ahí consta quién baneó, quién expulsó, quién levantó un ban y quién
cambió permisos, con fecha y autor.

Tres cosas que conviene saber al leerlo:

- **No es eterno.** Telegram conserva una ventana limitada de eventos; lo que se
  salga de ella ya no se puede consultar, y el comando lo dice en vez de fingir
  que no hubo nada.
- **`ToggleBan` es un interruptor.** El mismo evento sirve para banear y para
  dejar de banear, así que lo importante no es el nombre sino el ANTES y el
  DESPUÉS, que es lo que se muestra. Un caso real se explicó justo así: alguien
  pasó de «expulsado» a «silenciado dentro», que es readmitir sin pretenderlo.
- **Sin Telethon no hay nada que consultar.** Se dice claramente, en vez de
  responder «no hay eventos», que sugeriría que no pasó nada.
"""
from __future__ import annotations

import html as _h

from telegram import Update
from telegram.ext import ContextTypes

from .config import Config
from .db import DB
from .i18n import t

# Cuántos eventos se piden a Telegram. Suficiente para cubrir su ventana sin
# pedir de más: el filtrado por usuario se hace después, en local.
_LIMITE = 200


def _estado(p) -> str:
    """Traduce un «participante» de MTProto a algo legible."""
    if p is None:
        return t("quienfue.st_ninguno")
    nombre = type(p).__name__
    if "Banned" in nombre:
        derechos = getattr(p, "banned_rights", None)
        # `view_messages=True` significa «no puede ni ver el chat» = expulsado.
        # Sin él, sigue DENTRO del grupo pero con restricciones.
        if derechos is not None and getattr(derechos, "view_messages", False):
            return t("quienfue.st_expulsado")
        return t("quienfue.st_silenciado")
    if "Creator" in nombre:
        return t("quienfue.st_creador")
    if "Admin" in nombre:
        return t("quienfue.st_admin")
    if "Left" in nombre:
        return t("quienfue.st_fuera")
    return t("quienfue.st_miembro")


async def _consultar(context, chat_id: int, user_id: int) -> list[str] | None:
    """Líneas del historial para ese usuario, o None si no se puede consultar."""
    reporter = context.bot_data.get("reporter")
    client = reporter.get_client() if reporter else None
    if client is None:
        return None
    try:
        from telethon.tl.functions.channels import GetAdminLogRequest
    except Exception:  # noqa: BLE001
        return None

    try:
        canal = await client.get_input_entity(chat_id)
        res = await client(GetAdminLogRequest(channel=canal, q="", max_id=0,
                                              min_id=0, limit=_LIMITE))
    except Exception as exc:  # noqa: BLE001
        from .story_reader import log as _log
        _log.info("quienfue: no se pudo leer el registro de %s: %s", chat_id, exc)
        return None

    actores = {}
    for u in res.users:
        actores[u.id] = ("@" + u.username) if u.username else (u.first_name or str(u.id))

    lineas: list[str] = []
    for ev in sorted(res.events, key=lambda e: e.date, reverse=True):
        accion = ev.action
        antes = getattr(accion, "prev_participant", None)
        despues = getattr(accion, "new_participant", None)
        objetivo = None
        for p in (antes, despues):
            if p is not None:
                objetivo = (getattr(p, "user_id", None)
                            or getattr(getattr(p, "peer", None), "user_id", None))
                if objetivo:
                    break
        if objetivo != user_id:
            continue
        lineas.append(t(
            "quienfue.linea",
            fecha=ev.date.strftime("%d/%m %H:%M"),
            actor=_h.escape(str(actores.get(ev.user_id, ev.user_id))),
            antes=_estado(antes), despues=_estado(despues),
        ))
    return lineas


async def cmd_quienfue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.bot_data["cfg"]
    db: DB = context.bot_data["db"]
    msg = update.effective_message
    chat_id = msg.chat_id if msg else 0

    from .admin import _resolve_target_user
    user_id, _resto, err = await _resolve_target_user(update, context, db)
    if user_id is None:
        await msg.reply_text(t("quienfue.usage") + (f"\n⚠️ {err}" if err else ""),
                             parse_mode="HTML")
        return

    lineas = await _consultar(context, chat_id, user_id)
    if lineas is None:
        cuerpo = t("quienfue.sin_telethon")
    elif not lineas:
        cuerpo = t("quienfue.sin_eventos")
    else:
        cuerpo = "\n".join(lineas)

    texto = t("quienfue.header", uid=user_id) + "\n\n" + cuerpo + t("quienfue.footer")

    # Igual que /scan y /scanuser: en grupo se borra el comando y se responde al
    # privado. Quién moderó a quién no es información para el grupo.
    from .scan_cmd import _entregar
    await _entregar(context, msg, texto, cfg)
