"""El bot mira A DÓNDE lleva el enlace antes de decidir si es spam.

Caso real que lo originó (24/07/2026, grupo de domótica): una cuenta con dos años
y 34 mensajes publicó `https://t.me/EromeVideosPacks`. El bot lo detectó
(`external_mention_or_link`, 50 puntos) pero, al ser su autor un veterano, aplicó
el aviso suave: recordatorio que se autoborra y el enlace INTACTO en el grupo. Una
hora después otro miembro escribía «este se le ha escapado al bot».

El destino, en cambio, se presenta solo: se titulaba «Mujeres / Packs / Caseros /
Videos / Videos Caseros / Erome / Jovencitas / Colegialas» y se describía como
«Mejor grupo de packs y videos exclusivos». Con esa evidencia el enlace deja de ser
una señal débil, y el trust ya no puede taparlo.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import link_reader
from src.detectors import link_target as det


# El destino real del caso, tal cual lo devolvió Telegram.
EROME = link_reader.Destino(
    titulo="Mujeres / Packs / Caseros / Videos / Videos Caseros / Erome / Jovencitas / Colegialas /",
    descripcion="Mejor grupo de packs y videos exclusivos",
    url="https://t.me/EromeVideosPacks",
)


# ---------------------------------------------------------------- el detector

def test_el_caso_real_dispara():
    hit = det.check(EROME)
    assert hit, "el canal que se escapó seguiría escapándose"
    assert hit.rule == "link_target_spam"
    assert hit.score >= 100


def test_con_el_enlace_ya_puntuado_se_pasa_de_ban_score():
    """No decide solo: se suma a los 50 del enlace externo y cruza BAN_SCORE=100."""
    assert det.check(EROME).score + 50 >= 100


@pytest.mark.parametrize("titulo,descripcion", [
    ("Domótica España", "Grupo sobre Home Assistant, Zigbee y Alexa"),
    ("Windows 11 en Español", "Ayuda y soporte para Windows"),
    ("Ofertas y chollos", "Los mejores packs de viaje y videos de nuestros destinos"),
    ("Fotografía casera", "Comparte tus fotos y videos, exclusivos de miembros"),
    ("Grupo de compraventa", "Vendo y compro material de segunda mano"),
    ("Real Madrid", "Videos de los partidos"),
])
def test_canales_legitimos_no_disparan(titulo, descripcion):
    """FP > FN: el precio de equivocarse aquí es expulsar a un veterano."""
    destino = link_reader.Destino(titulo=titulo, descripcion=descripcion, url="https://t.me/x")
    assert not det.check(destino), f"falso positivo con {titulo!r} / {descripcion!r}"


def test_sin_destino_no_dispara():
    assert not det.check(None)
    assert not det.check(link_reader.Destino(titulo="", descripcion="", url="u"))


def test_hereda_el_vocabulario_del_canal_personal():
    """La lista de `personal_channel` describe lo mismo (blanqueo, apuestas, docs
    falsos); reutilizarla evita mantener dos copias que se desincronizan."""
    destino = link_reader.Destino(titulo="恒泰集团洗钱车队", descripcion="", url="u")
    assert det.check(destino)


# ------------------------------------------------------- lectura del destino

def test_reconoce_las_formas_de_enlace():
    c = link_reader._clave
    assert c("https://t.me/EromeVideosPacks") == "user:eromevideospacks"
    assert c("t.me/Canal/123") == "user:canal"           # enlace a un post
    assert c("https://t.me/+AbCdEf123") == "invite:AbCdEf123"
    assert c("https://t.me/joinchat/AbCdEf123") == "invite:AbCdEf123"
    assert c("https://telegram.me/Canal") == "user:canal"


def test_ignora_lo_que_no_es_un_chat():
    c = link_reader._clave
    assert c("https://example.com/canal") is None       # otro dominio
    assert c("https://t.me/") is None                   # sin destino
    assert c("https://t.me/addstickers/pack") is None   # segmento reservado
    assert c("https://t.me/s/canal") is None            # vista web
    assert c("https://t.me/ab") is None                 # demasiado corto


class _ClienteFalso:
    """Telethon de mentira: cuenta las llamadas para poder medir la caché."""

    def __init__(self, titulo="Packs Caseros", about="Vendo packs"):
        self.titulo, self.about, self.llamadas = titulo, about, 0

    async def get_entity(self, ref):
        self.llamadas += 1
        return SimpleNamespace(id=999, title=self.titulo, megagroup=True, broadcast=False)

    async def __call__(self, request):
        return SimpleNamespace(full_chat=SimpleNamespace(about=self.about))


def _contexto(cliente):
    return SimpleNamespace(
        bot_data={"reporter": SimpleNamespace(get_client=lambda: cliente)})


@pytest.mark.asyncio
async def test_lee_titulo_y_descripcion():
    link_reader.limpiar_cache()
    cliente = _ClienteFalso()
    destino = await link_reader.leer(_contexto(cliente), ["https://t.me/canalspam"])
    assert destino is not None
    assert destino.titulo == "Packs Caseros"
    assert destino.descripcion == "Vendo packs"
    assert det.check(destino), "leído el destino, el detector debe verlo"


@pytest.mark.asyncio
async def test_el_segundo_enlace_igual_no_vuelve_a_preguntar():
    """Resolver un @username dispara `contacts.ResolveUsername`, de lo más propenso
    a FloodWait, y un canal de spam se publica muchas veces seguidas."""
    link_reader.limpiar_cache()
    cliente = _ClienteFalso()
    ctx = _contexto(cliente)
    await link_reader.leer(ctx, ["https://t.me/canalspam"])
    await link_reader.leer(ctx, ["https://t.me/canalspam/42"])
    assert cliente.llamadas == 1, "la caché no está evitando la segunda resolución"


@pytest.mark.asyncio
async def test_sin_telethon_el_bot_sigue_como_antes():
    link_reader.limpiar_cache()
    ctx = SimpleNamespace(bot_data={})
    assert await link_reader.leer(ctx, ["https://t.me/canalspam"]) is None


@pytest.mark.asyncio
async def test_un_error_de_telegram_no_rompe_la_moderacion():
    link_reader.limpiar_cache()

    class Rota:
        async def get_entity(self, ref):
            raise RuntimeError("FLOOD_WAIT_420")

    assert await link_reader.leer(_contexto(Rota()), ["https://t.me/x1234"]) is None


@pytest.mark.asyncio
async def test_no_se_juzgan_los_enlaces_a_nuestros_propios_grupos():
    link_reader.limpiar_cache()
    cliente = _ClienteFalso()
    destino = await link_reader.leer(
        _contexto(cliente), ["https://t.me/canalspam"], es_moderado=lambda cid: True)
    assert destino is None


@pytest.mark.asyncio
async def test_no_se_consultan_veinte_enlaces_de_un_mensaje():
    """Los updates se procesan de uno en uno: cada espera congela el bot entero."""
    link_reader.limpiar_cache()

    class Vacio(_ClienteFalso):
        async def get_entity(self, ref):
            self.llamadas += 1
            raise RuntimeError("no existe")

    cliente = Vacio()
    urls = [f"https://t.me/canal{n:03d}" for n in range(20)]
    await link_reader.leer(_contexto(cliente), urls)
    assert cliente.llamadas <= link_reader._MAX_ENLACES


# --------------------------------------------------------------- el enganche

def _fuente() -> str:
    return Path("src/handlers.py").read_text()


def test_solo_se_mira_el_destino_de_enlaces_ya_sospechosos():
    """Ir a Telegram por cada t.me de cada mensaje sería caro y delataría la cuenta.
    Las URLs salen del payload del hit que ya saltó."""
    fuente = _fuente()
    i = fuente.index("def _enlaces_tg_de(")
    cuerpo = fuente[i:fuente.index("\ndef ", i + 10)]
    assert "external_tg_links" in cuerpo


def test_el_trust_no_puede_anular_el_destino_confeso():
    """Es justo lo que falló: el autor era veterano y el enlace se quedó."""
    from src.handlers import HARD_RULES_BAN
    assert "link_target_spam" in HARD_RULES_BAN


def test_el_aviso_suave_ya_no_es_un_silencio():
    """El aviso suave se autoborra a los 5 min y el mensaje se queda: sin avisar al
    admin, el bot ve spam, decide no tocarlo y no se entera nadie."""
    fuente = _fuente()
    i = fuente.index("action=\"gentle_warn\"")
    assert "_send_trust_notice" in fuente[i:i + 1200]
