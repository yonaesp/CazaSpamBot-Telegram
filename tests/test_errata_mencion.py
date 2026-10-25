"""«¿Quizás te referías a @x?» (`errata_mencion` + `external_mention.posible_errata`).

Caso real (25-oct-2026, Domótica): «Juan M.» (124 mensajes, confianza 9/10)
escribió «Era porque @Moliko tenía varios Spot…» queriendo decir @Molkio, miembro
con 382 mensajes. Salió como mención a un externo: aviso suave en el grupo y
«Algo raro de alguien de confianza» por privado. Ahora no puntúa y el bot sugiere
el @ bueno; si el autor lo corrige editando, la sugerencia se borra.
"""
from __future__ import annotations

import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import MessageEntity

from src import errata_mencion, handlers
from src.detectors import external_mention as em

CHAT = -1001156069668
JUAN = 1047674290
MOLKIO = 186421917
TEXTO = ("Era porque @Moliko tenía varios Spot y sin hacer nada, de repente el volumen "
         "de los avisos, recordatorios y notificaciones se bajaba al mínimo")


def _msg(texto=TEXTO, msg_id=451443, uid=JUAN):
    ents = []
    i = 0
    while (i := texto.find("@", i)) != -1:
        fin = i + 1
        while fin < len(texto) and (texto[fin].isalnum() or texto[fin] == "_"):
            fin += 1
        ents.append(MessageEntity(type=MessageEntity.MENTION, offset=i, length=fin - i))
        i = fin
    return NS(text=texto, caption=None, entities=ents, caption_entities=None,
              chat_id=CHAT, chat=NS(id=CHAT, title="Domótica"), message_id=msg_id,
              from_user=NS(id=uid, username="JuanM"))


# --- A qué se parece lo mal escrito ------------------------------------------

def test_el_caso_real():
    assert em.posible_errata("Moliko", ["Molkio", "JuanM", "otra_persona"]) == "Molkio"


@pytest.mark.parametrize("escrito", ["Molkoi", "Molkioo", "Molio", "Molkia", "molkio_"])
def test_una_tecla(escrito):
    assert em.posible_errata(escrito, ["Molkio"]) == "Molkio"


def test_nombre_largo_admite_dos():
    assert em.posible_errata("DomoticaJonatn", ["DomoticaJonatan"]) == "DomoticaJonatan"
    assert em.posible_errata("DomotikaJonatn", ["DomoticaJonatan"]) == "DomoticaJonatan"
    # Corto con dos errores: ya no es una errata, es otro nombre
    assert em.posible_errata("Mlkoi", ["Molkio"]) is None


def test_ambiguo_no_adivina():
    """Dos miembros igual de cerca: una sugerencia equivocada señala a otra persona."""
    assert em.posible_errata("Molkia", ["Molkio", "Molkis"]) is None
    # Pero si uno está más cerca, gana ese
    assert em.posible_errata("Molkio_", ["Molkio", "Molkis"]) == "Molkio"


def test_demasiado_corto_o_lejos():
    assert em.posible_errata("Juan", ["Juana"]) is None      # < 5 letras
    assert em.posible_errata("xoaq2bot", ["Molkio"]) is None


def test_bots_de_spam_reales_no_se_parecen_a_nadie():
    miembros = ["Molkio", "JuanM", "Alexa_fan", "domotico2020"]
    for h in ["caig018", "dl88o", "xiao1xbot", "wfsvx1025bot", "pg888pg_bot", "stakeofficialtg_bot"]:
        assert em.posible_errata(h, miembros) is None


def test_un_desconocido_conocido_no_es_errata():
    """Si el @ resuelve a alguien, aunque no esté en el grupo, es otra persona."""
    m = _msg("Pregúntale a @Molkia")
    assert em.erratas_de_mencion(m, lambda h: None, ["Molkio"]) == [("Molkia", "Molkio")]
    assert em.erratas_de_mencion(m, lambda h: 555, ["Molkio"]) == []


# --- El detector ya no lo cuenta como externo ---------------------------------

def _check(m, erratas, is_first=False):
    return em.check(m, CHAT, is_first, True, True,
                    is_user_in_chat=lambda c, u: u == MOLKIO,
                    resolve_username=lambda h: MOLKIO if h.lstrip("@").lower() == "molkio" else None,
                    erratas=erratas)


def test_la_errata_no_puntua():
    assert _check(_msg(), None).score == 40          # lo que pasaba
    assert not _check(_msg(), [("Moliko", "Molkio")])


def test_otra_mencion_externa_sigue_contando():
    m = _msg("@Moliko y @canal_de_spam")
    hit = _check(m, [("Moliko", "Molkio")])
    assert hit.score == 40
    assert [e["username"] for e in hit.payload["external_mentions"]] == ["@canal_de_spam"]


# --- Cuándo se busca ----------------------------------------------------------

_CFG = NS(detect_external_mentions=True, shadow=False)


def _db_con_miembros(tmp_db):
    tmp_db.record_message(CHAT, MOLKIO, "Molkio")
    tmp_db.remember_username("Molkio", MOLKIO)
    tmp_db.record_message(CHAT, JUAN, "JuanM")
    return tmp_db


def test_buscar_caso_real(tmp_db):
    db = _db_con_miembros(tmp_db)
    user = NS(id=JUAN, username="JuanM")
    assert errata_mencion.buscar(db, _CFG, _msg(), user, is_first=False) == [("Moliko", "Molkio")]


def test_nunca_en_primeros_mensajes(tmp_db):
    """Un recién llegado a una tecla del @ de un admin es la forma de suplantarlo."""
    db = _db_con_miembros(tmp_db)
    assert errata_mencion.buscar(db, _CFG, _msg(), NS(id=JUAN, username="JuanM"), is_first=True) == []


def test_ni_baneados_ni_uno_mismo(tmp_db):
    db = _db_con_miembros(tmp_db)
    db.add_ban(MOLKIO, "x", "manual_admin_ban", CHAT)
    assert errata_mencion.buscar(db, _CFG, _msg(), NS(id=JUAN, username="JuanM"), False) == []
    m = _msg("Soy @JuanN")
    assert errata_mencion.buscar(_db_con_miembros(tmp_db), _CFG, m,
                                 NS(id=JUAN, username="JuanM"), False) == []


def test_sin_menciones_no_toca_la_base():
    db = MagicMock()
    assert errata_mencion.buscar(db, _CFG, _msg("Hola a todos"), NS(id=1, username=None), False) == []
    db.usernames_del_chat.assert_not_called()


# --- Publicar, corregir, caducar ---------------------------------------------

def _ctx(db):
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=NS(message_id=9001))
    ctx.bot.delete_message = AsyncMock()
    ctx.bot_data = {"db": db, "cfg": _CFG}
    return ctx


@pytest.mark.asyncio
async def test_sugiere_sin_avisar_a_nadie(tmp_db):
    ctx = _ctx(tmp_db)
    await errata_mencion.sugerir(ctx, tmp_db, _CFG, _msg(), [("Moliko", "Molkio")])
    kw = ctx.bot.send_message.await_args.kwargs
    rp = kw["reply_parameters"]
    # Cita justo lo mal escrito, en su sitio (posición en UTF-16, como pide Telegram)
    assert (rp.message_id, rp.quote, rp.quote_position) == (451443, "@Moliko", TEXTO.index("@"))
    assert rp.allow_sending_without_reply is False
    # En <code>: ni Molkio ni el dueño de @Moliko reciben una mención del bot
    assert "<code>@Molkio</code>" in kw["text"] and "<code>@Moliko</code>" in kw["text"]
    assert kw["text"].replace("<code>@Molkio</code>", "").replace("<code>@Moliko</code>", "").count("@") == 0
    assert "No encuentro" in kw["text"]
    assert tmp_db.errata_pendiente(CHAT, 451443) == (9001, [["Moliko", "Molkio"]])


def test_la_cita_cuenta_en_utf16():
    """Con un emoji delante, la posición de Python y la de Telegram difieren."""
    m = _msg("🔊🔊 Era porque @Moliko tenía")
    m.entities[0] = MessageEntity(type=MessageEntity.MENTION, offset=16, length=7)
    assert errata_mencion._cita(m, "moliko") == ("@Moliko", 16)


@pytest.mark.asyncio
async def test_si_telegram_rechaza_la_cita_responde_sin_ella(tmp_db):
    from telegram.error import BadRequest
    ctx = _ctx(tmp_db)
    ctx.bot.send_message.side_effect = [BadRequest("Quote_text_invalid"), NS(message_id=9001)]
    await errata_mencion.sugerir(ctx, tmp_db, _CFG, _msg(), [("Moliko", "Molkio")])
    citas = [c.kwargs["reply_parameters"].quote for c in ctx.bot.send_message.await_args_list]
    assert citas == ["@Moliko", None]
    assert tmp_db.errata_pendiente(CHAT, 451443) == (9001, [["Moliko", "Molkio"]])


@pytest.mark.asyncio
async def test_una_sola_sugerencia_por_mensaje(tmp_db):
    ctx = _ctx(tmp_db)
    await errata_mencion.sugerir(ctx, tmp_db, _CFG, _msg(), [("Moliko", "Molkio")])
    await errata_mencion.sugerir(ctx, tmp_db, _CFG, _msg(), [("Moliko", "Molkio")])
    assert ctx.bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_en_shadow_no_publica(tmp_db):
    ctx = _ctx(tmp_db)
    await errata_mencion.sugerir(ctx, tmp_db, NS(shadow=True), _msg(), [("Moliko", "Molkio")])
    ctx.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_al_corregir_editando_se_borra(tmp_db):
    ctx = _ctx(tmp_db)
    await errata_mencion.sugerir(ctx, tmp_db, _CFG, _msg(), [("Moliko", "Molkio")])
    # Edita pero sigue mal: la sugerencia se queda
    await errata_mencion.al_editar(ctx, tmp_db, _msg(TEXTO + " (editado)"))
    ctx.bot.delete_message.assert_not_awaited()
    # Lo corrige
    await errata_mencion.al_editar(ctx, tmp_db, _msg(TEXTO.replace("Moliko", "Molkio")))
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=CHAT, message_id=9001)
    assert tmp_db.errata_pendiente(CHAT, 451443) is None


@pytest.mark.asyncio
async def test_editar_otro_mensaje_no_toca_nada(tmp_db):
    ctx = _ctx(tmp_db)
    tmp_db.add_gentle_warning(CHAT, 451443, 9001, JUAN)    # un aviso suave normal, sin errata
    await errata_mencion.al_editar(ctx, tmp_db, _msg("ya sin mención"))
    ctx.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_edited_message_corrige_aunque_no_reescanee(tmp_db, monkeypatch):
    ctx = _ctx(tmp_db)
    ctx.bot_data["cfg"] = NS(rescan_edited_messages=False)
    tmp_db.add_gentle_warning(CHAT, 451443, 9001, JUAN, errata=[["Moliko", "Molkio"]])
    upd = NS(edited_message=_msg(TEXTO.replace("Moliko", "Molkio")))
    await handlers.on_edited_message(upd, ctx)
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=CHAT, message_id=9001)


@pytest.mark.asyncio
async def test_barrido_tras_reinicio(tmp_db):
    ctx = _ctx(tmp_db)
    tmp_db.add_gentle_warning(CHAT, 451443, 9001, JUAN, errata=[["Moliko", "Molkio"]])
    tmp_db.add_gentle_warning(CHAT, 451444, 9002, JUAN)    # aviso normal: no es suyo
    with tmp_db._cur() as c:
        c.execute("UPDATE gentle_warnings SET ts=?", (time.time() - 3600,))
    await errata_mencion.barrido_job(ctx)
    ctx.bot.delete_message.assert_awaited_once_with(chat_id=CHAT, message_id=9001)
    assert tmp_db.pop_gentle_warning_by_user_msg(CHAT, 451444) == 9002


def test_on_message_lo_usa():
    """Las tres salidas sin acción sugieren, y el detector recibe las erratas."""
    import inspect
    src = inspect.getsource(handlers.on_message)
    assert src.count("await errata_mencion.sugerir(") == 3
    assert "erratas=_erratas," in src
