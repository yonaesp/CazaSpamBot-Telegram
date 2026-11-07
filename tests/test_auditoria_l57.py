"""Lo que encontró la auditoría del 7-nov-2026 (L57), cada fallo con su test.

Los meta-tests (ast) vigilan la clase entera de cada fallo en todo `src/`.
"""
from __future__ import annotations

import ast
import datetime as dt
import logging
import time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import MessageEntity
from telegram.error import BadRequest

from src import handlers, link_reader, main, user_signals
from src.db import DB

FUENTES = sorted(Path("src").rglob("*.py"))
CHAT = -1001190184646


def _arbol(f: Path) -> ast.AST:
    return ast.parse(f.read_text(encoding="utf-8"))


# ------------------------------------------------------------ 1. el atajo del @admin

def _msg(texto, entidades=(), **kw):
    return NS(text=texto, caption=None, entities=list(entidades), caption_entities=[],
              forward_origin=None, reply_markup=None, via_bot=None, chat_id=CHAT, **kw)


def _cfg():
    return NS(allowed_scripts=["latin"])


@pytest.fixture
def db(tmp_path):
    return DB(str(tmp_path / "t.db"))


def test_un_aviso_admin_de_verdad_es_limpio(db):
    m = _msg("@admin hay un spam arriba", [MessageEntity("mention", 0, 6)])
    assert handlers._aviso_admin_limpio(db, _cfg(), m)


@pytest.mark.parametrize("texto,entidades", [
    ("@admin 🔥 packs t.me/+XXXX", [MessageEntity("mention", 0, 6)]),
    ("@admin mira https://x.y", [MessageEntity("mention", 0, 6), MessageEntity("url", 12, 11)]),
    ("@admin @amsoslbot", [MessageEntity("mention", 0, 6), MessageEntity("mention", 7, 10)]),
    ("@admins 过机假钞视频看货专业团队", [MessageEntity("mention", 0, 7)]),
    ("@admin " + "x" * 500, [MessageEntity("mention", 0, 6)]),
])
def test_un_admin_con_algo_mas_se_juzga_entero(db, texto, entidades):
    assert not handlers._aviso_admin_limpio(db, _cfg(), _msg(texto, entidades))


def test_un_admin_reenviado_o_con_botones_se_juzga(db):
    m = _msg("@admin", [MessageEntity("mention", 0, 6)])
    m.forward_origin = object()
    assert not handlers._aviso_admin_limpio(db, _cfg(), m)


def test_on_message_solo_toma_el_atajo_con_un_aviso_limpio():
    fn = next(n for n in ast.walk(_arbol(Path("src/handlers.py")))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message")
    ifs = [n for n in ast.walk(fn) if isinstance(n, ast.If)
           and "contains_admin_mention" in ast.unparse(n.test)]
    assert ifs and all("_aviso_admin_limpio" in ast.unparse(n.test) for n in ifs)


# ------------------------------------------------- 2. reaction_farming y el mensaje ajeno

def test_el_ban_por_reacciones_no_lleva_el_mensaje_de_otro():
    fn = next(n for n in ast.walk(_arbol(Path("src/handlers.py")))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message_reaction")
    for c in [n for n in ast.walk(fn) if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "_apply_action"]:
        mid = next(k.value for k in c.keywords if k.arg == "message_id")
        assert isinstance(mid, ast.Constant) and mid.value is None, ast.unparse(mid)


# ----------------------------------------------- 3. is_moderated como callback y link_reader

def test_nadie_pasa_cfg_is_moderated_como_funcion():
    """Sin lista explícita dice que sí a CUALQUIER chat: como filtro de «grupo propio»
    descartaba todo destino. Se llama (`cfg.is_moderated(x)`) o se usa `_se_modera`."""
    malos = []
    for f in FUENTES:
        arbol = _arbol(f)
        llamados = {id(n.func) for n in ast.walk(arbol) if isinstance(n, ast.Call)}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Attribute) and n.attr == "is_moderated" and id(n) not in llamados:
                malos.append(f"{f}:{n.lineno}")
    assert not malos, f"cfg.is_moderated pasado sin llamar: {malos}"


def test_link_reader_convierte_el_id_de_telethon():
    from telethon.tl.types import Channel
    c = Channel(id=1190184646, title="x", photo=None, date=None, access_hash=1, megagroup=True)
    assert link_reader._id_bot_api(c) == CHAT


@pytest.mark.asyncio
async def test_lo_cacheado_tambien_pasa_el_filtro_de_grupo_propio():
    link_reader.limpiar_cache()
    propio = link_reader.Destino(titulo="Windows 11", descripcion="", url="t.me/Windows11ESP", chat_id=CHAT)
    link_reader._cache[link_reader._clave("https://t.me/Windows11ESP")] = (time.time(), propio)
    ctx = NS(bot_data={"reporter": None})
    assert await link_reader._leer(ctx, ["https://t.me/Windows11ESP"], lambda c: c == CHAT) is None
    assert await link_reader._leer(ctx, ["https://t.me/Windows11ESP"], lambda c: False) is propio
    link_reader.limpiar_cache()


# ----------------------------------------------------- 4. revisión: el mensaje revisado

def test_los_botones_de_revision_no_aprenden_del_ultimo_mensaje():
    fn = next(n for n in ast.walk(_arbol(Path("src/handlers.py")))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_pending_review_callback")
    assert "last_msg_text" not in ast.unparse(fn)
    assert "mensaje_reciente" in ast.unparse(fn)


# ------------------------------------------------------- 5. ban local por warns

def test_un_ban_de_un_solo_grupo_no_cuenta_como_federado(db):
    db.add_ban(user_id=1, reason="warns", rule="warns_limit", banned_in_chat=CHAT, federated=False)
    db.add_ban(user_id=2, reason="spam", rule="bio_spam", banned_in_chat=CHAT, federated=True)
    assert not db.is_banned(1) and db.is_banned(2)


# ---------------------------------------------------------- 7. auditar antes de borrar

def test_quien_banea_audita():
    """Toda función que banea deja su fila en `moderation_log` (o pasa por
    `_apply_action`, que la deja) antes de borrar el mensaje."""
    exentas = {"federate_ban", "_ban_one", "unfederate_ban", "_reconcile_banned_users",
               "_banear_bot_en_los_demas"}
    malos = []
    for f in FUENTES:
        for fn in [n for n in ast.walk(_arbol(f)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            if fn.name in exentas:
                continue
            llamadas = [(n.lineno, n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", ""))
                        for n in ast.walk(fn) if isinstance(n, ast.Call)]
            nombres = {x for _, x in llamadas}
            if not nombres & {"federate_ban", "ban_chat_member", "ban_chat_sender_chat"}:
                continue
            if nombres & {"log_action", "_apply_action"}:
                audita = min(n for n, x in llamadas if x in ("log_action", "_apply_action"))
                borra = [n for n, x in llamadas if x == "delete_message"]
                if borra and min(borra) < audita and "_apply_action" not in nombres:
                    malos.append(f"{f}:{fn.name} borra antes de auditar")
                continue
            malos.append(f"{f}:{fn.name} banea sin auditar")
    assert not malos, malos


# --------------------------------------------------------- 8. BadRequest no es la red

@pytest.mark.asyncio
async def test_un_badrequest_no_se_toma_por_un_fallo_de_red(caplog):
    ctx = MagicMock()
    ctx.error = BadRequest("Can't parse entities: unclosed start tag")
    ctx.bot_data = {"cfg": NS(admin_notify_chat_id=345), "db": None}
    ctx.bot.send_message = AsyncMock()
    with caplog.at_level(logging.WARNING, logger="antispam"):
        await main._on_error(None, ctx)
    assert not any("Red transitoria" in r.message for r in caplog.records)
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ------------------------------------------------------------ 9. desbanear olvida

def test_solo_federation_y_maintenance_quitan_bans():
    """Un desbaneo a mano (`revoke_ban`) no olvida lo aprendido: todo pasa por
    `unfederate_ban`."""
    malos = [f"{f}:{n.lineno}" for f in FUENTES if f.name not in ("federation.py", "maintenance.py", "db.py")
             for n in ast.walk(_arbol(f)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "revoke_ban"]
    assert not malos, malos


# ------------------------------------------------------------ 11. la bio en el aviso

def test_la_bio_sale_siempre_aunque_haya_premium_y_fotos():
    d = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
    sig = user_signals.UserSignals(user_id=1, photo_count=3, oldest_photo=d,
                                   newest_photo=d + dt.timedelta(days=400), bio="canal t.me/x", is_premium=True)
    assert "canal t.me/x" in user_signals.render_markup(sig)


# ----------------------------------------- 6. revisiones de CAS/lols que no llegaban

@pytest.mark.asyncio
async def test_la_revision_de_cas_llega_al_privado_con_botones(db, monkeypatch):
    from src import notify_prefs
    monkeypatch.setattr(notify_prefs, "sin_sonido", lambda db, importante: False)
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=NS(message_id=1))
    cfg = NS(admin_notify_chat_id=345)
    await handlers._revision_humana(ctx, db, cfg, NS(id=CHAT, title="Windows 11"),
                                    NS(id=7, username=None, first_name="Ana"), [("cas_low_offense", {})])
    kw = ctx.bot.send_message.await_args.kwargs
    assert kw["chat_id"] == 345 and kw["reply_markup"] is not None
    assert "CAS" in kw["text"]


def test_toda_revision_de_lista_externa_avisa():
    """Cada rama que deja una revisión de CAS/lols manda también el aviso."""
    def cuenta(f, fn_name):
        fn = next(n for n in ast.walk(_arbol(Path(f)))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name)
        src = ast.unparse(fn)
        return src.count("_trusted_review") + src.count("rule='cas_low_offense'"), src.count("_revision_humana(")
    revisiones, avisos = cuenta("src/handlers.py", "on_chat_member")
    assert revisiones == avisos == 3
    revisiones, avisos = cuenta("src/recien_llegados.py", "_actuar")
    assert revisiones == avisos == 1
