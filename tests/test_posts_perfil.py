"""Los «Posts» del perfil (historias fijadas) como escaparate de spam.

Caso real (1-nov-2026, Windows 10): «𝐙𝐄𝐑𝐎» (@zerotrace505) entró, se verificó en
6 s y lo baneó a mano otro admin dos minutos después. Bio vacía, sin canal: para
el bot estaba limpio. Sus posts eran un catálogo de la estafa de «recuperación» y
de espionaje de WhatsApp. Los textos de abajo son los leídos de verdad (pie y OCR)
con la cuenta secundaria, sin contar como visualización.

Foco en los ANTI falsos positivos: tener posts es lo normal, y en grupos de
informática salen capturas con «hacker» y negocios que dicen «contáctanos».
"""
from __future__ import annotations

import ast
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import i18n, posts_reader
from src import recien_llegados as rl
from src.db import DB
from src.detectors import posts_perfil as pp

RAIZ = Path(__file__).resolve().parent.parent

# Pie de cada post de ZERO, tal cual.
ZERO_PIES = [
    "La recuperación del dinero aquí está asegurada",
    "Activo para tu servicio",
    "Mira todo en tu WhatsApp personal",
    "Vincula WhatsApp a tu dispositivo y espía",
    "Snap 👀",
    "La recuperación de dinero es segura",
    "Espionaje🎭",
    "😷",
]
# Lo que leyó el OCR dentro de sus fotos (el ruido incluido).
ZERO_OCR = [
    "0 e e ¿Has sido estafado en línea tú o alguien que conoces? O Formo parte de un "
    "equipo dedicado a crear conciencia sobre las estafas en línea y el uso indebido de "
    "la identidad. ¿Has perdido dinero o activos a manos de estafadores? La recuperación "
    "podría ser posible: actúa rápido para mejorar tus posibilidades. Responde",
    "il O WhatsApp OTP Sc SS a E . a —_—_- 2 e ed LOS E E. =e",
    "Verifica +34 Usa el otro teléfono para confirmar la transferencia de WhatsApp a "
    "este. Ingresa el código de 6 dígitos que enviamos por WhatsApp a tu otro teléfono.",
    "NUESTRO SERVICIO Y) Recuperación de estafas de criptomonedas Y) Recuperación de "
    "billeteras perdidas Y) Recuperación de estafas románticas Y) Recuperación de "
    "inversiones falsas",
    "QUIERES SABER SI TU PAREJA TE ENGAÑA COMUNICATE CON NOSOTROS",
]


@pytest.fixture(autouse=True)
def _es():
    previo = i18n.current_lang()
    i18n.set_lang("es")
    yield
    i18n.set_lang(previo)


@pytest.fixture(autouse=True)
def _sin_caches():
    posts_reader._cache.clear()
    posts_reader._ocr_hecho.clear()
    yield
    posts_reader._cache.clear()
    posts_reader._ocr_hecho.clear()


# ------------------------------------------------------------------ el caso real

def test_zero_entero_cae():
    hit = pp.check(ZERO_PIES + ZERO_OCR)
    assert hit and hit.rule == "posts_spam"
    assert hit.score >= pp.MIN_SCORE
    assert hit.payload["posts_ilegales"] >= 2
    assert hit.payload["garantia"] and hit.payload["oferta"]


def test_zero_cae_solo_con_los_pies():
    """Sin Tesseract instalado se pierde el OCR, no la detección de ZERO."""
    assert pp.check(ZERO_PIES)


def test_zero_cae_solo_con_lo_que_dicen_las_imagenes():
    """Al revés: un catálogo que no pone nada en el pie también cae."""
    assert pp.check(ZERO_OCR)


def test_con_los_detectores_de_mensajes_no_puntuaba():
    """Por qué hace falta un juicio del CONJUNTO: post a post, ninguno de los
    detectores de contenido de mensajes daba nada con los textos de ZERO."""
    from src.detectors import commercial_ad, investment_scam
    for texto in ZERO_PIES:
        msg = SimpleNamespace(text=texto, caption=None, entities=[], caption_entities=[])
        assert not commercial_ad.check(msg, is_first_msg=True)
        assert not investment_scam.check(msg, is_first_msg=True)


# Tres cuentas ya baneadas por otras vías (lols, anuncio) con posts de la misma
# familia, medidas el 2-nov-2026. Con el vocabulario de partida se quedaban en 45-70.
FAMILIA = {
    "recuperar dinero y espiar a la pareja": [
        "Contáctame para recuperar tu dinero y para todos los servicios de piratería "
        "informática.\na E AS _ RECOVER LOST",
        "¿ESTÁ SU PAREJA 44M MINTIÉNDOLE? dé eS | oe zs",
    ],
    "recuperar cuentas con garantía": [
        "Recuperar Facebook",
        "La recuperación del dinero aquí está asegurada, amigos",
        "WhatsApp HACKEADO Para completar el trabajo tendrás que elegir cualquier minuto "
        "de tu elección LOADING 1Horas = 60 2 horas = 70 5 minutos = 50",
        "rs [ru] ira o Help facebooi Help You've unlocked your account",
    ],
    "catálogo de hackeo en imágenes": [
        "RY IAL MEDIA ACCOUNT HACKING De y Email Hacking Facebook Hacking (9) Twitter "
        "Hacking Instagram Hacking 5",
        "(©) Pirater Facebook =a El AN © Pirater Twitter == +5 7) ES f © Pirater WhatsApp",
        "AESDY: Hack Recovery Message me now for Y) all social media [+] j hacking/Recovery",
        "DOWN! iP Many users are reporting issues with _ and Instagram.",
    ],
}


@pytest.mark.parametrize("caso", list(FAMILIA))
def test_la_misma_familia_tambien_cae(caso):
    hit = pp.check(FAMILIA[caso])
    assert hit and hit.score >= pp.MIN_SCORE, caso


# ------------------------------------------------------------------ el contrato

def test_ninguna_senal_suelta_llega_a_banear():
    for peso in (pp.SCORE_CATALOGO, pp.SCORE_ILEGAL_UNO, pp.SCORE_OFERTA, pp.SCORE_GARANTIA):
        assert peso < pp.MIN_SCORE


def test_el_trozo_del_ancla_no_cuenta_ademas_como_servicio_ilegal():
    """«La recuperación de dinero es segura» es la garantía, no además un servicio
    ilegal: sumaría dos veces la misma frase."""
    hit = pp.check(["La recuperación de dinero es segura", "Mis vacaciones en Cádiz"])
    assert not hit
    con_otro = pp.check(["La recuperación de dinero es segura",
                         "Espionaje de WhatsApp", "Clonación de WhatsApp"])
    assert con_otro and con_otro.payload["posts_ilegales"] == 2


def test_sin_posts_o_vacios_no_hay_nada():
    assert not pp.check(None)
    assert not pp.check([])
    assert not pp.check(["", "  ", "😷"])


# ------------------------------------------------------------------ anti falsos positivos

def test_capturas_con_hacker_y_un_contactame_no_banean():
    """Memes y capturas de un grupo de informática. «hacker» a secas es el tema,
    no un servicio a terceros."""
    assert not pp.check([
        "Cuando el hacker de la peli escribe 3 líneas y entra en el Pentágono",
        "Curso de hacking ético, módulo 2 terminado",
        "Hackeo del Wi-Fi del vecino: mito o realidad",
        "Si te interesa el curso, contáctame",
    ])


def test_un_negocio_normal_que_se_anuncia_no_cae():
    """Ofrecerse no es delito: un taller que dice «nuestros servicios» y
    «contáctanos» sin nada ilegal se queda en la oferta sola."""
    assert not pp.check([
        "Nuestros servicios: reparación de ordenadores y móviles",
        "Contáctanos por privado para presupuesto",
        "Servicio a tu disposición",
    ])


def test_un_aviso_contra_la_estafa_de_recuperacion_no_cae():
    """Quien avisa de la estafa usa las mismas palabras, pero no se ofrece ni
    garantiza nada."""
    assert not pp.check([
        "Cuidado: las estafas de recuperación de fondos se ceban con quien ya perdió dinero",
        "Nadie puede garantizar que recuperes tu dinero. Denuncia en la policía.",
    ])


def test_recuperarse_de_una_lesion_no_es_una_garantia():
    assert not pp.check([
        "Tres meses de fisio: la recuperación de la rodilla es segura si no fuerzas",
        "Nuestro servicio de fisioterapia a tu disposición",
    ])


def test_fotos_personales_no_dicen_nada():
    assert not pp.check(["Feliz cumpleaños, mamá ❤️", "Domingo de playa", "Mi gato"])


# ------------------------------------------------------------------ el lector

class MessageMediaPhoto:  # el lector distingue por el nombre del tipo, como Telethon
    pass


class MessageMediaDocument:
    pass


class _Cliente:
    def __init__(self, stories, count=None, roto=False):
        self.stories, self.count, self.roto = stories, count, roto
        self.peticiones = 0
        self.descargas = 0

    async def __call__(self, req):
        self.peticiones += 1
        if self.roto:
            raise RuntimeError("PEER_ID_INVALID")
        assert type(req).__name__ == "GetPinnedStoriesRequest"
        return SimpleNamespace(stories=self.stories, count=self.count or len(self.stories))

    async def download_media(self, media, file=None):
        self.descargas += 1
        return b"jpeg"


def _story(i, pie="", media=None, areas=None):
    return SimpleNamespace(id=i, caption=pie, media=media, media_areas=areas)


@pytest.fixture
def _ocr_falso(monkeypatch):
    async def leer(datos):
        return "NUESTRO SERVICIO Recuperación de estafas de criptomonedas"
    monkeypatch.setattr("src.ocr.leer", leer)
    monkeypatch.setattr("src.ocr.disponible", lambda: True)


@pytest.mark.asyncio
async def test_el_lector_junta_pie_y_ocr_de_las_fotos(_ocr_falso):
    cli = _Cliente([
        _story(15, "La recuperación de dinero es segura", MessageMediaPhoto()),
        _story(13, "😷", MessageMediaDocument()),
        _story(9, "", None, [SimpleNamespace(url="https://t.me/+abcdef123")]),
    ])
    posts = await posts_reader.leer(cli, object(), 5540199905)
    assert [p.id for p in posts] == [15, 13, 9]
    assert "NUESTRO SERVICIO" in posts[0].texto and "segura" in posts[0].texto
    assert posts[1].imagen == ""            # de un vídeo solo cuenta el pie
    assert "t.me/+abcdef123" in posts[2].texto
    assert cli.descargas == 1


@pytest.mark.asyncio
async def test_el_ocr_de_cada_post_se_hace_una_vez(_ocr_falso):
    cli = _Cliente([_story(15, "", MessageMediaPhoto())])
    await posts_reader.leer(cli, object(), 1)
    posts_reader._cache.clear()               # como si hubiera pasado la hora
    await posts_reader.leer(cli, object(), 1)
    assert cli.peticiones == 2 and cli.descargas == 1


@pytest.mark.asyncio
async def test_la_lectura_entera_se_recuerda_un_rato(_ocr_falso):
    cli = _Cliente([_story(15, "hola", None)])
    await posts_reader.leer(cli, object(), 2)
    await posts_reader.leer(cli, object(), 2)
    assert cli.peticiones == 1


@pytest.mark.asyncio
async def test_un_fallo_de_telegram_es_no_lo_se_y_no_revienta():
    assert await posts_reader.leer(_Cliente([], roto=True), object(), 3) is None
    assert await posts_reader.leer(None, object(), 3) is None
    assert await posts_reader.leer(_Cliente([]), None, 3) is None


@pytest.mark.asyncio
async def test_una_telegram_colgada_no_cuelga_la_lectura(monkeypatch):
    class Colgada(_Cliente):
        async def __call__(self, req):
            await asyncio.sleep(3600)
    monkeypatch.setattr(posts_reader, "_TIMEOUT_S", 0.05)
    t0 = time.monotonic()
    assert await posts_reader.leer(Colgada([]), object(), 4) is None
    assert time.monotonic() - t0 < 2


def test_las_caches_no_crecen_sin_fin():
    for i in range(posts_reader._CACHE_MAX + 50):
        posts_reader._guardar(i, [])
    assert len(posts_reader._cache) <= posts_reader._CACHE_MAX
    for i in range(posts_reader._OCR_MAX + 50):
        posts_reader._recordar_ocr((1, i), "")
    assert len(posts_reader._ocr_hecho) <= posts_reader._OCR_MAX


# ------------------------------------------------------------------ el enganche

def _db(tmp_path) -> DB:
    db = DB(str(tmp_path / "t.db"))
    db.upsert_bot_chat(-100, "Windows 10", "supergroup", True, True, True)
    return db


def _cfg():
    return SimpleNamespace(
        lols_enabled=False, cas_enabled=False, cas_autoban_min=2, cas_cache_ttl_seconds=3600,
        ban_score=100, kick_score=70, mute_score=40, first_msg_attack_action="ban",
        shadow=False, mode="active", admin_user_id=1, admin_notify_chat_id=None,
        public_quip_enabled=False, moderated_chat_ids=[], allowed_scripts=["latin"],
    )


class _Bot:
    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(user=SimpleNamespace(
            id=user_id, is_bot=False, first_name="ZERO", last_name=None,
            username="zerotrace505"))


def _sig(tiene_posts=True):
    return SimpleNamespace(
        personal_channel_title=None, personal_channel_id=None, personal_channel_entity=None,
        photo_count=1, bio=None, tiene_posts=tiene_posts, entidad=object(),
        oldest_photo=None, is_premium=False,
    )


def _ctx(db, sig):
    return SimpleNamespace(
        bot=_Bot(),
        bot_data={"db": db, "cfg": _cfg(), "http": object(),
                  "reporter": SimpleNamespace(get_client=lambda: object())},
        application=SimpleNamespace(job_queue=None),
    )


@pytest.mark.asyncio
async def test_el_repaso_caza_a_zero_sin_esperar_a_que_escriba(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(-100, 5540199905, "zerotrace505", join_ts=time.time() - 600)
    sig = _sig()

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)

    async def falsos_posts(client, entidad, user_id):
        return [posts_reader.Post(id=i, pie=x) for i, x in enumerate(ZERO_PIES)]
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)

    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    await rl.revisar_job(_ctx(db, sig))
    assert aplicado.get("user_id") == 5540199905
    assert aplicado["decision"].rule == "posts_spam"
    assert aplicado["decision"].action == "ban"
    assert aplicado["decision"].payload["via"] == "recien_llegados"


@pytest.mark.asyncio
async def test_sin_posts_no_se_gasta_ni_una_llamada(tmp_path, monkeypatch):
    db = _db(tmp_path)
    db.record_join(-100, 902, None, join_ts=time.time() - 600)
    sig = _sig(tiene_posts=False)

    async def falso_fetch(client, user_id, **kw):
        return sig
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)
    leidos = []

    async def falsos_posts(*a):
        leidos.append(1)
        return []
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    await rl.revisar_job(_ctx(db, sig))
    assert not leidos


@pytest.mark.asyncio
async def test_la_tarea_del_join_banea_por_su_cuenta(tmp_path, monkeypatch):
    db = _db(tmp_path)
    monkeypatch.setattr(rl, "_ESPERA_JOIN_S", 0)

    async def falsos_posts(client, entidad, user_id):
        return [posts_reader.Post(id=1, pie=x) for x in ZERO_PIES]
    monkeypatch.setattr("src.posts_reader.leer", falsos_posts)
    aplicado = {}

    async def falso_apply(context, db_, cfg_, **kw):
        aplicado.update(kw)
    monkeypatch.setattr("src.handlers._apply_action", falso_apply)

    chat = SimpleNamespace(id=-100, title="Windows 10")
    user = SimpleNamespace(id=5540199905, username="zerotrace505", first_name="ZERO")
    assert await rl.revisar_posts_aparte(_ctx(db, _sig()), chat, user, _sig(), object())
    assert aplicado["decision"].rule == "posts_spam"
    assert aplicado["decision"].payload["via"] == "join"
    assert aplicado["chat_id"] == -100


@pytest.mark.asyncio
async def test_la_tarea_del_join_no_vuelve_a_banear_al_ya_baneado(tmp_path, monkeypatch):
    """Si otro admin (o otra regla) se adelantó, no se repite el ban ni el aviso."""
    db = _db(tmp_path)
    db.add_ban(user_id=5540199905, reason="manual", rule="manual_admin_ban", banned_in_chat=-100)
    monkeypatch.setattr(rl, "_ESPERA_JOIN_S", 0)
    llamado = []
    monkeypatch.setattr("src.handlers._apply_action", lambda *a, **k: llamado.append(1))
    chat = SimpleNamespace(id=-100, title="Windows 10")
    user = SimpleNamespace(id=5540199905, username="zerotrace505", first_name="ZERO")
    assert not await rl.revisar_posts_aparte(_ctx(db, _sig()), chat, user, _sig(), object())
    assert not llamado


@pytest.mark.asyncio
async def test_un_fallo_en_la_tarea_del_join_no_se_escapa(tmp_path, monkeypatch):
    monkeypatch.setattr(rl, "_ESPERA_JOIN_S", 0)
    ctx = SimpleNamespace(bot_data={})                 # sin db: KeyError dentro
    chat = SimpleNamespace(id=-100, title="x")
    user = SimpleNamespace(id=1, username=None, first_name="x")
    assert await rl.revisar_posts_aparte(ctx, chat, user, _sig(), object()) is False


def test_el_ocr_de_los_posts_nunca_corre_en_la_ruta_de_un_update():
    """PTB procesa los updates de uno en uno: diez fotos con OCR son segundos sin
    moderar. `posts_reader.leer` solo se llama desde `recien_llegados`, y el join
    y el primer mensaje lanzan su tarea con `create_task`, sin esperarla."""
    llamadores = []
    for f in (RAIZ / "src").rglob("*.py"):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "leer"
                    and isinstance(nodo.func.value, ast.Name)
                    and nodo.func.value.id == "posts_reader"):
                llamadores.append(f.name)
    assert llamadores and set(llamadores) == {"recien_llegados.py"}

    handlers = ast.parse((RAIZ / "src" / "handlers.py").read_text(encoding="utf-8"))
    esperadas = [n for n in ast.walk(handlers) if isinstance(n, ast.Await)
                 and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
                 and n.value.func.attr == "revisar_posts_aparte"]
    assert not esperadas
    lanzadas = [n for n in ast.walk(handlers) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "create_task"
                and any(isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute)
                        and a.func.attr == "revisar_posts_aparte" for a in n.args)]
    assert len(lanzadas) == 2           # join y primer mensaje


def test_user_signals_lee_si_hay_posts_de_getfulluser():
    fuente = (RAIZ / "src" / "user_signals.py").read_text(encoding="utf-8")
    assert "stories_pinned_available" in fuente
    assert "sig.entidad = entity" in fuente


@pytest.mark.asyncio
async def test_scan_dice_si_tiene_posts_sin_leerlos(tmp_path, monkeypatch):
    """`/scan` corre en la ruta de un update: dice que los hay, no los lee."""
    from tests.test_scanuser import _montar, _texto
    from src import scanuser_cmd, user_signals
    upd, ctx, _db, msg = _montar(tmp_path, con_telethon=True)

    async def falso_fetch(client, user_id, **kw):
        return user_signals.UserSignals(user_id=user_id, tiene_posts=True)
    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)
    leidos = []
    monkeypatch.setattr("src.posts_reader.leer", lambda *a: leidos.append(1))
    await scanuser_cmd.cmd_scanuser(upd, ctx)
    assert "Posts" in _texto(msg)
    assert not leidos
