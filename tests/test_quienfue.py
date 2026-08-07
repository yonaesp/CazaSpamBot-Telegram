"""/quienfue: quién tocó a este usuario y qué le hizo.

Nace del caso del 3-ago: un baneado apareció dentro del grupo día y medio después
y averiguar quién deshizo el ban exigió consultar a mano el registro de acciones
de Telegram por MTProto. Esto lo pone a un comando.
"""
import datetime as dt
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import quienfue_cmd as q


# El código mira el NOMBRE de la clase (como hace MTProto), así que los dobles
# tienen que ser clases de verdad con esos nombres, no SimpleNamespace.
class ChannelParticipantBanned:
    def __init__(self, user_id, view_messages):
        self.user_id = user_id
        self.banned_rights = types.SimpleNamespace(view_messages=view_messages)


class ChannelParticipant:
    def __init__(self, user_id):
        self.user_id = user_id


def _participante(tipo, uid=777):
    if tipo == "expulsado":
        return ChannelParticipantBanned(uid, True)
    if tipo == "silenciado":
        return ChannelParticipantBanned(uid, False)
    return ChannelParticipant(uid)


def test_distingue_expulsado_de_silenciado():
    """Es LA distinción que importa: `view_messages` marca si sigue dentro. Un
    baneado que pasa a «silenciado» está de vuelta en el grupo, y eso fue justo lo
    que costó día y medio detectar."""
    exp = _participante("expulsado")
    sil = _participante("silenciado")
    assert q._estado(exp) != q._estado(sil)
    assert "expulsado" in q._estado(exp)
    assert "dentro" in q._estado(sil), "no deja claro que el silenciado SIGUE en el grupo"


def test_sin_estado_previo_no_revienta():
    assert q._estado(None)


@pytest.mark.asyncio
async def test_sin_telethon_lo_dice_en_vez_de_decir_que_no_paso_nada():
    """Responder «sin eventos» sugeriría que no hubo movimientos, que es lo
    contrario de lo que sabemos."""
    ctx = MagicMock()
    ctx.bot_data = {"reporter": None}
    assert await q._consultar(ctx, -100, 777) is None


@pytest.mark.asyncio
async def test_filtra_solo_los_eventos_de_ese_usuario():
    cliente = MagicMock()
    cliente.get_input_entity = AsyncMock(return_value="peer")

    otro = ChannelParticipant(999)

    def _ev(uid_objetivo, actor, cuando):
        p = _participante("expulsado") if uid_objetivo == 777 else otro
        return types.SimpleNamespace(
            date=cuando, user_id=actor,
            action=types.SimpleNamespace(prev_participant=None, new_participant=p))

    res = types.SimpleNamespace(
        users=[types.SimpleNamespace(id=1, username="yona", first_name="Y")],
        events=[_ev(777, 1, dt.datetime(2026, 8, 2, 1, 22)),
                _ev(999, 1, dt.datetime(2026, 8, 2, 1, 30))],
    )

    async def _llamada(_req):
        return res
    cliente.side_effect = _llamada

    reporter = MagicMock()
    reporter.get_client.return_value = cliente
    ctx = MagicMock()
    ctx.bot_data = {"reporter": reporter}

    lineas = await q._consultar(ctx, -100, 777)
    assert len(lineas) == 1, f"no filtró por usuario: {lineas}"
    assert "@yona" in lineas[0], "no dice quién fue"


def test_el_comando_esta_registrado_y_no_actua():
    from pathlib import Path
    main = Path("src/main.py").read_text()
    assert 'CommandHandler("quienfue"' in main
    fuente = Path("src/quienfue_cmd.py").read_text()
    for peligro in ("ban_chat_member", "restrict_chat_member", "delete_message("):
        assert peligro not in fuente, f"/quienfue no debería tocar nada, y usa {peligro}"
