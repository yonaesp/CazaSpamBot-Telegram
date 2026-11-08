"""La cuenta secundaria no entra en grupos ajenos (L59, 8-nov-2026).

Medido: tenía «¿Quién puede añadirme a grupos?» en «Todos». El admin: «evita que
otros puedan añadir esa cuenta a otros grupos».
"""
from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from telethon.tl.types import (
    InputPeerUser,
    InputPrivacyValueAllowContacts,
    InputPrivacyValueAllowUsers,
    PrivacyValueAllowAll,
    PrivacyValueAllowContacts,
    PrivacyValueDisallowAll,
    PrivacyValueDisallowUsers,
)

from src import cuenta_secundaria as cs
from src import handlers, telethon_bridge

YO, ADMIN, CONTACTO, EXTRAÑO = 8714716537, 14573395, 555, 999
NUESTRO = -1001156069668


class Cliente:
    """Imita lo que devuelve Telegram a cada petición, por su nombre."""

    def __init__(self, reglas=(), dialogos=(), participantes=None, contactos=(CONTACTO,),
                 falla=()):
        self.reglas, self.dialogos = list(reglas), list(dialogos)
        self.part, self.contactos, self.falla = participantes or {}, list(contactos), set(falla)
        self.puestas, self.salidas = [], []

    async def __call__(self, req):
        nombre = type(req).__name__
        if nombre in self.falla:
            raise RuntimeError(nombre)
        if nombre == "GetPrivacyRequest":
            return NS(rules=self.reglas)
        if nombre == "SetPrivacyRequest":
            self.puestas.append(req.rules)
            return NS(rules=[])
        if nombre == "GetContactIDsRequest":
            return self.contactos
        if nombre == "GetParticipantRequest":
            return NS(participant=self.part[req.channel.id])  # KeyError = no se sabe
        if nombre == "GetFullChatRequest":
            return NS(full_chat=NS(participants=NS(participants=[self.part[req.chat_id]])))
        raise AssertionError(f"petición inesperada: {nombre}")

    async def get_input_entity(self, uid):
        return InputPeerUser(user_id=uid, access_hash=1)

    async def get_me(self, input_peer=False):
        return InputPeerUser(user_id=YO, access_hash=1) if input_peer else NS(id=YO)

    async def get_entity(self, uid):
        return NS(first_name="Spammer", last_name=None, username=None)

    async def iter_dialogs(self):
        for d in self.dialogos:
            yield d

    async def delete_dialog(self, entidad):
        self.salidas.append(entidad.id)


def _grupo(cid, titulo="Grupo", canal=True, **flags):
    ent = NS(id=cid, title=titulo, participants_count=40, left=False, creator=False,
             deactivated=False)
    for k, v in flags.items():
        setattr(ent, k, v)
    return NS(id=cid, is_user=False, is_channel=canal, entity=ent)


# --------------------------------------------------------------- privacidad

@pytest.mark.asyncio
async def test_si_cualquiera_puede_meterla_se_cierra():
    cli = Cliente(reglas=[PrivacyValueAllowAll()])
    assert await cs.cerrar_privacidad(cli, ADMIN) == cs.CERRADA
    (reglas,) = cli.puestas
    assert isinstance(reglas[0], InputPrivacyValueAllowContacts)
    assert isinstance(reglas[1], InputPrivacyValueAllowUsers)
    assert reglas[1].users[0].user_id == ADMIN


@pytest.mark.asyncio
async def test_todos_menos_alguien_sigue_abierto():
    cli = Cliente(reglas=[PrivacyValueDisallowUsers(users=[5]), PrivacyValueAllowAll()])
    assert await cs.cerrar_privacidad(cli, ADMIN) == cs.CERRADA


@pytest.mark.parametrize("reglas", [
    [PrivacyValueAllowContacts()],
    [PrivacyValueDisallowAll()],
    [],
])
@pytest.mark.asyncio
async def test_lo_que_eligio_alguien_se_respeta(reglas):
    cli = Cliente(reglas=reglas)
    assert await cs.cerrar_privacidad(cli, ADMIN) == cs.YA_CERRADA
    assert not cli.puestas


@pytest.mark.asyncio
async def test_si_no_puede_leerla_lo_dice():
    cli = Cliente(reglas=[PrivacyValueAllowAll()], falla={"GetPrivacyRequest"})
    assert await cs.cerrar_privacidad(cli, ADMIN) == cs.ERROR
    assert not cli.puestas


# ------------------------------------------------------------------ grupos

def _escenario():
    dialogos = [
        NS(id=ADMIN, is_user=True, is_channel=False, entity=NS(id=ADMIN)),
        _grupo(NUESTRO, "Alexa"),
        _grupo(-1001, "Creado por ella", creator=True),
        _grupo(-1002, "Entró con un enlace"),
        _grupo(-1003, "La metió el admin"),
        _grupo(-1004, "La metió un contacto"),
        _grupo(-1005, "Por solicitud"),
        _grupo(-1006, "No se sabe"),
        _grupo(-1007, "Ya se fue", left=True),
        _grupo(-1008, "公群 blanqueo"),
        _grupo(-1009, "Grupo básico de spam", canal=False),
    ]
    part = {
        -1002: NS(inviter_id=YO), -1003: NS(inviter_id=ADMIN),
        -1004: NS(inviter_id=CONTACTO), -1005: NS(inviter_id=EXTRAÑO, via_request=True),
        -1008: NS(inviter_id=EXTRAÑO), -1009: NS(user_id=YO, inviter_id=EXTRAÑO),
    }
    return Cliente(reglas=[PrivacyValueAllowContacts()], dialogos=dialogos, participantes=part)


@pytest.mark.asyncio
async def test_solo_cuentan_los_grupos_donde_la_metio_un_extraño():
    cli = _escenario()
    ajenos = await cs.grupos_ajenos(cli, YO, {ADMIN, CONTACTO}, lambda cid: cid == NUESTRO)
    assert [g.chat_id for g in ajenos] == [-1008, -1009]
    assert all(g.invito == EXTRAÑO for g in ajenos)


@pytest.fixture
def contexto(tmp_db, monkeypatch):
    monkeypatch.setattr(handlers, "_se_modera", lambda db, cfg, cid: cid == NUESTRO)

    def hacer(cli, shadow=False):
        cfg = NS(shadow=shadow, admin_user_id=ADMIN, admin_notify_chat_id=ADMIN)
        return NS(bot=NS(send_message=AsyncMock()),
                  bot_data={"reporter": NS(get_client=lambda: cli), "cfg": cfg, "db": tmp_db})
    return hacer


@pytest.mark.asyncio
async def test_el_job_cierra_sale_y_avisa_en_silencio(contexto):
    cli = _escenario()
    cli.reglas = [PrivacyValueAllowAll()]
    ctx = contexto(cli)
    await cs.vigilar_job(ctx)
    assert cli.salidas == [-1008, -1009]
    assert len(cli.puestas) == 1
    kw = ctx.bot.send_message.await_args.kwargs
    assert "公群 blanqueo" in kw["text"] and "Grupo básico de spam" in kw["text"]
    assert "🔒" in kw["text"] and "{" not in kw["text"]
    assert kw["disable_notification"] is True     # ya está resuelto: no suena


@pytest.mark.asyncio
async def test_sin_nada_que_hacer_no_avisa(contexto):
    cli = Cliente(reglas=[PrivacyValueAllowContacts()], dialogos=[_grupo(NUESTRO)])
    ctx = contexto(cli)
    await cs.vigilar_job(ctx)
    ctx.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sin_contactos_no_sale_de_nada(contexto):
    cli = _escenario()
    cli.falla = {"GetContactIDsRequest"}
    await cs.vigilar_job(contexto(cli))
    assert cli.salidas == []


@pytest.mark.asyncio
async def test_en_shadow_no_toca_nada(contexto):
    cli = _escenario()
    cli.reglas = [PrivacyValueAllowAll()]
    ctx = contexto(cli, shadow=True)
    await cs.vigilar_job(ctx)
    assert cli.salidas == [] and cli.puestas == []
    ctx.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_nunca_sale_de_un_grupo_donde_esta_el_bot(contexto, tmp_db):
    """Aunque el bot haya perdido el permiso de restringir, sigue siendo nuestro."""
    tmp_db.upsert_bot_chat(-1008, "x", "supergroup", am_admin=False, can_restrict=False,
                           can_delete=False)
    cli = _escenario()
    await cs.vigilar_job(contexto(cli))
    assert cli.salidas == [-1009]


# ------------------------------------------------- el alta, en el momento

@pytest.mark.parametrize("añadidos,revisa", [([YO], True), ([EXTRAÑO], False)])
@pytest.mark.asyncio
async def test_si_la_meten_en_un_grupo_se_mira_ya(monkeypatch, añadidos, revisa):
    vigilar = AsyncMock()
    monkeypatch.setattr(cs, "vigilar_job", vigilar)
    capturado = {}

    class Cli(Cliente):
        def on(self, builder):
            def deco(fn):
                capturado["fn"], capturado["builder"] = fn, builder
                return fn
            return deco

    eventos = NS(ChatAction=lambda func: ("ChatAction", func))
    telethon_bridge._attach_cuenta_en_grupo(Cli(), eventos, NS())
    _, filtro = capturado["builder"]
    evento = NS(user_added=True, user_ids=añadidos, chat_id=-1008)
    assert filtro(evento)
    await capturado["fn"](evento)
    assert vigilar.await_count == (1 if revisa else 0)
