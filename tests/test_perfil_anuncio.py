"""El perfil que es un anuncio: dos cosas lo dicen a la vez (L66).

Caso real (19-nov-2026, Domótica): «BEST IPTV RESELLING PANEL 🎁», Premium, con
la bio y nueve posts vendiendo IPTV, y una infracción en CAS. El bot solo
preguntó: cada cosa por separado no llegaba a nada. Decisión del admin: «si ya
tiene un cas y todos esos posts debería ser motivo de ban porque suma dos cosas».
Y después: «no es solo por revender IPTV sino por tener posts + el cas, eso
debería ser ban directo, la gente normal no suele usar posts».

Los textos de abajo son los reales, recortados.
"""
from __future__ import annotations

import ast
import time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import pytest

from src import handlers, posts_reader, user_signals
from src import recien_llegados as rl
from src.db import DB
from src.detectors import bio_spam
from src.detectors import perfil_anuncio as pa
from src.detectors.posts_perfil import _ilegal_en

NOMBRE = pa.nombre_de("BEST IPTV RESELLING PANEL", "🎁")
BIO = "🚀 Need a reliable IPTV service or reseller panel available"
POSTS = [
    "",
    "IM MF? TO DISCOVER. AE, ot) ae o ele Ce ew ae",
    "📲 WhatsApp:\nhttps://wa.me/000000000000\n\n Telegram:\n@unacuenta",
    "✨ BEST IPTV SUB, RESELLER PANEL ✨\n🔥 PREMIUM IPTV SERVICES AVAILABLE\n"
    "✅ VIP IPTV Subscriptions\n✅ IPTV Reseller Panels\n✅ Restream Connections",
]
UID, CHAT = 8600000900, -100


# ------------------------------------------------------------------ el detector

def test_el_caso_real_cae_ya_en_el_join_por_el_nombre_y_la_bio():
    hit = pa.check(NOMBRE, bio=BIO)
    assert hit and hit.rule == "perfil_anuncio" and hit.score == 100
    assert hit.payload["escaparates"] == ["nombre", "bio"]


def test_cas_y_los_posts_suman_aunque_el_nombre_este_limpio():
    """La frase del admin: «tiene un cas y todos esos posts»."""
    hit = pa.check("Daniel Ruiz", posts=POSTS, cas=1)
    assert hit and hit.payload == {
        "escaparates": ["posts"], "cas": 1, "con_posts": True, "ejemplos": {"posts": "IPTV SUB"}}


@pytest.mark.parametrize("kw", [
    {"tiene_posts": True},                                   # lo dice GetFullUser, sin leerlos
    {"posts": ["Domingo de playa", "Mi setup nuevo 🖥️"]},    # leídos, y no anuncian nada
    {"posts": ["", ""]},                                     # vídeos sin pie
])
def test_tener_posts_y_estar_en_cas_es_ban_digan_lo_que_digan(kw):
    """«No es solo por revender IPTV sino por tener posts + el cas» (admin, 19-nov)."""
    hit = pa.check("Jorge Salas", cas=1, **kw)
    assert hit and hit.rule == "perfil_anuncio" and hit.score == 100
    assert hit.payload["escaparates"] == [] and hit.payload["con_posts"] is True
    assert "posts" in hit.reason and "CAS" in hit.reason
    assert not pa.check("Jorge Salas", cas=0, **kw)          # los mismos posts sin CAS: nada


def test_cas_y_la_bio_suman():
    assert pa.check("Daniel Ruiz", bio=BIO, cas=1)


@pytest.mark.parametrize("kw", [
    {"nombre": NOMBRE},
    {"nombre": "Daniel Ruiz", "bio": BIO},
    {"nombre": "Daniel Ruiz", "posts": POSTS},
    {"nombre": "Daniel Ruiz", "canal": "IPTV reseller panel"},
    {"nombre": "Daniel Ruiz", "cas": 1},
    {"nombre": "Daniel Ruiz", "cas": 5},
    {"nombre": "Daniel Ruiz", "tiene_posts": True},
    {"nombre": "Daniel Ruiz", "posts": ["Domingo de playa"]},
    {"nombre": None},
])
def test_ninguna_cosa_decide_sola(kw):
    assert not pa.check(**kw)


def test_bio_y_posts_sin_el_nombre_ni_cas_no_banean():
    """Un técnico con esta bio y un post sobre un spyware es una persona normal.
    Eso lo siguen juzgando `bio_spam` y `posts_perfil` con sus umbrales."""
    assert not pa.check("Laura Méndez", bio="Experto en seguridad informática",
                        posts=["Nuevo spyware en extensiones de Chrome, hilo"])
    assert not pa.check("Daniel Ruiz", bio=BIO, posts=POSTS)


@pytest.mark.parametrize("nombre,bio,posts", [
    ("Marta | Fire TV", "Tengo IPTV en el Fire TV y Alexa en toda la casa", ["Mi lista IPTV ya no carga"]),
    ("IPTV Fan", "Fan del IPTV y de la domótica", ["¿Qué app de IPTV recomendáis?"]),
    ("Paneles Solares Sevilla", "Vendo paneles solares e inversores", ["Instalación terminada"]),
    ("Hacker Mx", "hacking ético, CTF y café", ["Cuando el hacker de la peli entra en el Pentágono"]),
    ("Pedro", "Reseller de hosting y dominios", ["Panel de control nuevo en Home Assistant"]),
])
def test_el_tema_no_es_un_anuncio_ni_con_cas(nombre, bio, posts):
    """«IPTV» o «hacker» a secas son temas de conversación: no cuentan como anuncio.
    Con CAS y sin posts, nada; con posts y sin CAS, nada."""
    assert not pa.check(nombre, bio=bio, cas=1)
    assert not pa.check(nombre, bio=bio, posts=posts)
    assert pa.escaparates(nombre, bio, posts) == {}


def test_las_letras_de_adorno_cuentan_igual():
    assert pa.check("𝐁𝐄𝐒𝐓 𝐈𝐏𝐓𝐕 𝐑𝐄𝐒𝐄𝐋𝐋𝐄𝐑", bio="ＩＰＴＶ subscriptions, cheap")


def test_cada_cosa_de_mas_suma_y_hay_tope():
    assert pa.check(NOMBRE, bio=BIO).score == 100
    assert pa.check(NOMBRE, bio=BIO, posts=POSTS).score == 130
    assert pa.check(NOMBRE, bio=BIO, posts=POSTS, cas=1).score == 160
    assert pa.check(NOMBRE, bio=BIO, tiene_posts=True, cas=1).score == 160   # los posts, una sola vez
    assert pa.check(NOMBRE, bio=BIO, tiene_posts=True).score == 100          # sin CAS no cuentan
    assert pa.check(NOMBRE, bio=BIO, posts=POSTS, canal="IPTV reseller", cas=1).score == 190
    assert pa.SCORE_BASE + 4 * pa.SCORE_EXTRA <= 220 and pa.check(NOMBRE, bio=BIO).score <= 200


def test_el_motivo_dice_donde_y_si_estaba_en_cas():
    sin = pa.check(NOMBRE, bio=BIO).reason
    con = pa.check(NOMBRE, bio=BIO, cas=1).reason
    assert "IPTV RESELLING" in sin and "CAS" not in sin
    assert "CAS" in con


# ------------------------------------------------------------- el vocabulario

@pytest.mark.parametrize("texto", [
    "BEST IPTV RESELLING PANEL 🎁", BIO, "✨ BEST IPTV SUB, RESELLER PANEL ✨",
    "✅ VIP IPTV Subscriptions", "✅ IPTV Reseller Panels", "✅ Restream Connections",
    "🔥 PREMIUM IPTV SERVICES AVAILABLE", "Vendo suscripciones de IPTV",
    "Panel IPTV para revendedores", "Revendedor IPTV", "iptv_reseller",
])
def test_la_reventa_de_iptv_es_un_servicio(texto):
    assert _ilegal_en(texto)


@pytest.mark.parametrize("texto", [
    "Tengo IPTV en el Fire TV", "¿Qué app de IPTV recomendáis?", "Mi lista IPTV no carga en Alexa",
    "IPTV Smarters va lento", "IPTV subtitles no salen", "IPTV", "Fan del IPTV",
    "Vendo paneles solares", "selling panels and inverters", "Panel de control de Home Assistant",
    "mi suscripción de Netflix", "restream de Twitch a YouTube", "reseller de hosting",
])
def test_hablar_de_iptv_no_es_venderlo(texto):
    assert _ilegal_en(texto) is None


def test_la_bio_real_sola_no_basta_y_con_enlace_privado_si():
    """El vocabulario nuevo también lo ven los detectores de siempre."""
    assert not bio_spam.check(BIO)
    assert bio_spam.check("IPTV reseller panel 👉 t.me/+AbCdEfGh1234")


# ------------------------------------------------------------------ el enganche

def _fn(path: str, nombre: str) -> str:
    arbol = ast.parse(Path(path).read_text(encoding="utf-8"))
    return ast.unparse(next(n for n in ast.walk(arbol)
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre))


def test_se_mira_en_los_tres_momentos():
    """Join (perfil y rama de CAS), primer mensaje y repaso (perfil y posts)."""
    join = _fn("src/handlers.py", "on_chat_member")
    assert join.count("perfil_anuncio_det.check(") == 2
    assert "cas=offenses, tiene_posts=" in join
    assert _fn("src/handlers.py", "on_message").count("perfil_anuncio_det.check(") == 1
    assert _fn("src/recien_llegados.py", "_revisar_perfil").count("perfil_anuncio.check(") == 1
    assert _fn("src/recien_llegados.py", "_revisar_posts").count("perfil_anuncio.check(") == 1
    for ruta, fn in (("src/handlers.py", "on_message"), ("src/recien_llegados.py", "_revisar_perfil"),
                     ("src/recien_llegados.py", "_revisar_posts")):
        assert "tiene_posts=" in _fn(ruta, fn), fn


def test_la_suma_con_cas_va_antes_de_preguntar():
    """En la rama de CAS con una infracción, primero se suma el perfil; si no hay
    nada que sumar, se pregunta como siempre."""
    join = _fn("src/handlers.py", "on_chat_member")
    assert join.index("cas=offenses") < join.index("rule='cas_low_offense'")


def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(CHAT, "Domótica", "supergroup", True, True, True)
    return db


def _cfg(cas=False):
    return NS(
        lols_enabled=False, cas_enabled=cas, cas_autoban_min=2, cas_cache_ttl_seconds=3600,
        ban_score=100, kick_score=70, mute_score=40, first_msg_attack_action="ban",
        shadow=False, mode="active", admin_user_id=1, admin_notify_chat_id=None,
        public_quip_enabled=False, moderated_chat_ids=[], allowed_scripts=["latin"],
    )


def _sig(bio=None, tiene_posts=False):
    return NS(personal_channel_title=None, personal_channel_id=None, personal_channel_entity=None,
              photo_count=3, bio=bio, tiene_posts=tiene_posts, entidad=object(),
              oldest_photo=None, is_premium=True, account_age_days=68)


def _ctx(db, cfg, nombre="BEST IPTV RESELLING PANEL"):
    class _Bot:
        async def get_chat_member(self, chat_id, user_id):
            return NS(user=NS(id=user_id, is_bot=False, first_name=nombre, last_name=None,
                              username="unacuenta"))
    return NS(bot=_Bot(), application=NS(job_queue=None),
              bot_data={"db": db, "cfg": cfg, "http": None,
                        "reporter": NS(get_client=lambda: object())})


def _captura(monkeypatch) -> dict:
    aplicado: dict = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)
    return aplicado


@pytest.mark.asyncio
async def test_el_repaso_caza_el_nombre_y_la_bio(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(CHAT, UID, "unacuenta", join_ts=time.time() - 600)
    sig = _sig(bio=BIO)

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)
    aplicado = _captura(monkeypatch)

    await rl.revisar_job(_ctx(db, _cfg()))
    assert aplicado.get("user_id") == UID
    assert aplicado["decision"].rule == "perfil_anuncio" and aplicado["decision"].action == "ban"
    assert aplicado["decision"].payload["via"] == "recien_llegados"


@pytest.mark.asyncio
async def test_el_repaso_no_toca_a_quien_solo_habla_de_iptv(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(CHAT, UID, "marta", join_ts=time.time() - 600)
    db.cas_store(UID, 1)
    sig = _sig(bio="Tengo IPTV en el Fire TV y Alexa en toda la casa")

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)
    aplicado = _captura(monkeypatch)

    await rl.revisar_job(_ctx(db, _cfg(cas=True), nombre="Marta | Fire TV"))
    assert not aplicado


@pytest.mark.asyncio
async def test_el_repaso_banea_a_quien_tiene_posts_y_esta_en_cas_sin_leerlos(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(CHAT, UID, "jorge", join_ts=time.time() - 600)
    db.cas_store(UID, 1)
    sig = _sig(tiene_posts=True)

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)
    leidos = []

    async def falsos_posts(*a):
        leidos.append(1)
        return []
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    aplicado = _captura(monkeypatch)

    await rl.revisar_job(_ctx(db, _cfg(cas=True), nombre="Jorge Salas"))
    assert aplicado["decision"].rule == "perfil_anuncio" and aplicado["decision"].action == "ban"
    assert aplicado["decision"].payload["con_posts"] is True and not leidos


@pytest.mark.asyncio
async def test_el_repaso_no_toca_a_quien_tiene_posts_y_no_esta_en_cas(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(CHAT, UID, "jorge", join_ts=time.time() - 600)
    sig = _sig(tiene_posts=True)

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)

    async def falsos_posts(client, entidad, user_id):
        return [posts_reader.Post(id=1, pie="Domingo de playa"), posts_reader.Post(id=2, pie="Mi setup")]
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    aplicado = _captura(monkeypatch)

    await rl.revisar_job(_ctx(db, _cfg(cas=True), nombre="Jorge Salas"))
    assert not aplicado


@pytest.mark.asyncio
async def test_la_tarea_del_join_suma_cas_y_los_posts(tmp_path, monkeypatch):
    """Nombre limpio y bio vacía: los posts solos no llegan, pero CAS ya lo tenía."""
    db = _db(tmp_path)
    db.cas_store(UID, 1)
    monkeypatch.setattr(rl, "_ESPERA_JOIN_S", 0)

    async def falsos_posts(client, entidad, user_id):
        return [posts_reader.Post(id=i, pie=x) for i, x in enumerate(POSTS)]
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    aplicado = _captura(monkeypatch)

    chat = NS(id=CHAT, title="Domótica")
    user = NS(id=UID, username="unacuenta", first_name="Daniel", last_name="Ruiz")
    sig = _sig(tiene_posts=True)
    assert await rl.revisar_posts_aparte(_ctx(db, _cfg(cas=True)), chat, user, sig, object())
    assert aplicado["decision"].rule == "perfil_anuncio"
    assert aplicado["decision"].payload["cas"] == 1 and aplicado["decision"].payload["via"] == "join"


@pytest.mark.asyncio
async def test_sin_cas_los_mismos_posts_no_banean(tmp_path, monkeypatch):
    db = _db(tmp_path)
    monkeypatch.setattr(rl, "_ESPERA_JOIN_S", 0)

    async def falsos_posts(client, entidad, user_id):
        return [posts_reader.Post(id=i, pie=x) for i, x in enumerate(POSTS)]
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    aplicado = _captura(monkeypatch)

    chat = NS(id=CHAT, title="Domótica")
    user = NS(id=UID, username="unacuenta", first_name="Daniel", last_name="Ruiz")
    for cfg in (_cfg(cas=True), _cfg(cas=False)):
        assert not await rl.revisar_posts_aparte(_ctx(db, cfg), chat, user, _sig(tiene_posts=True), object())
    assert not aplicado


def test_cas_apagado_o_viejo_no_suma(tmp_path):
    db = _db(tmp_path)
    db.cas_store(UID, 1)
    assert handlers._cas_conocido(db, _cfg(cas=True), UID) == 1
    assert handlers._cas_conocido(db, _cfg(cas=False), UID) == 0
    assert handlers._cas_conocido(db, _cfg(cas=True), UID + 1) == 0
    with db._cur() as c:
        c.execute("UPDATE cas_cache SET checked_at=? WHERE user_id=?",
                  (time.time() - handlers.CAS_SUMA_S - 60, UID))
    assert handlers._cas_conocido(db, _cfg(cas=True), UID) == 0


# ------------------------------------------- la revisión enseña lo que ya se leyó

@pytest.mark.asyncio
async def test_la_revision_de_cas_trae_el_nombre_y_la_bio(tmp_path, monkeypatch):
    """Llegó con el @ a secas, sin nombre ni bio: hubo que abrir el perfil."""
    from src import notify_prefs
    monkeypatch.setattr(notify_prefs, "sin_sonido", lambda db, importante: False)
    db = _db(tmp_path)
    ctx = MagicMock()
    ctx.bot.send_message = AsyncMock(return_value=NS(message_id=1))
    sig = user_signals.UserSignals(user_id=UID, photo_count=3, bio=BIO, is_premium=True)
    await handlers._revision_humana(
        ctx, db, NS(admin_notify_chat_id=345), NS(id=CHAT, title="Domótica"),
        NS(id=UID, username="unacuenta", first_name="BEST IPTV RESELLING PANEL", last_name="🎁"),
        [("cas_low_offense", {})], sig=sig)
    texto = ctx.bot.send_message.await_args.kwargs["text"]
    assert "BEST IPTV RESELLING PANEL 🎁 · @unacuenta" in texto
    assert "reseller panel available" in texto


def test_las_revisiones_del_join_pasan_el_perfil_leido():
    join = _fn("src/handlers.py", "on_chat_member")
    assert join.count("_revision_humana(") == join.count(", sig=sig_pre)") == 3
