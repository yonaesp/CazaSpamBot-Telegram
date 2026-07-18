"""Regresión CRÍTICA (auditoría 2026-07-18): una bienvenida con llaves que no sean
{name}/{chat} dejaba al recién llegado MUTEADO PARA SIEMPRE.

Secuencia del bug en verification.on_join (verificación ON):
  1. se aplica el mute,
  2. `welcome_text.format(name=..., chat=...)` lanzaba (KeyError/IndexError/ValueError),
  3. la excepción escapaba de on_join → NUNCA se llamaba a add_pending_verification.
Sin fila pendiente, cleanup_job (que se apoya en esa tabla para los 3 tiers) no veía
al usuario: quedaba silenciado e invisible para toda vía de recuperación. Y con /sync
ON, un /setwelcome malo escribía el texto a todos los grupos a la vez.

El texto lo escribe el admin con /setwelcome o el editor de /config, sin validación
de llaves, así que el disparador está al alcance normal del usuario.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src import verification as v

CHAT = -100321
USER = 77


def _ctx(tmp_db):
    cfg = SimpleNamespace(shadow=False, admin_notify_chat_id=555, admin_user_id=999)
    # send_message debe devolver un mensaje con message_id ENTERO: es lo que se
    # persiste en pending_verifications (un AsyncMock pelado no es bindeable en SQLite).
    bot = SimpleNamespace(
        restrict_chat_member=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=4321)),
    )
    return SimpleNamespace(
        bot=bot, bot_data={"cfg": cfg, "db": tmp_db},
        application=SimpleNamespace(job_queue=None),
    )


@pytest.mark.parametrize("welcome", [
    "Escribe {algo} para empezar",       # KeyError
    "Hola {user}!",                      # KeyError
    "usa {} para citar",                 # IndexError
    "Bienvenido {name} :-{",             # ValueError
])
@pytest.mark.asyncio
async def test_bienvenida_con_llaves_raras_no_deja_muteado(tmp_db, welcome):
    tmp_db.ensure_chat_settings(CHAT)
    tmp_db.update_chat_setting(CHAT, "verification_enabled", 1)
    tmp_db.update_chat_setting(CHAT, "verification_review_suspicious", 0)
    tmp_db.update_chat_setting(CHAT, "welcome_text", welcome)
    ctx = _ctx(tmp_db)
    chat = SimpleNamespace(id=CHAT, title="G")
    user = SimpleNamespace(id=USER, username="pepe", first_name="Pepe",
                           last_name=None, is_premium=False)

    await v.on_join(update=None, context=ctx, chat=chat, user=user)   # no debe lanzar

    # Lo esencial: el usuario queda registrado como pendiente, así que cleanup_job
    # puede recuperarlo (recordatorio/kick). Sin esta fila quedaba muteado y perdido.
    with tmp_db._cur() as c:
        row = c.execute(
            "SELECT user_id FROM pending_verifications WHERE chat_id=? AND user_id=?",
            (CHAT, USER),
        ).fetchone()
    assert row is not None, "sin fila pendiente: el usuario quedaría muteado e invisible"
    ctx.bot.send_message.assert_awaited()   # y se le manda la bienvenida igualmente
