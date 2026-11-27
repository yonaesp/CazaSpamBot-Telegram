"""La foto de una pantalla y el bono de casino con código (L68).

Caso real (27-nov-2026, Windows 11): una cuenta mandó una foto hecha con el móvil a
una pantalla en modo oscuro, torcida 5°, con un post falso de un famoso: «lanzo mi
casino de criptomonedas; regalo $3,200 a quien se registre con el código
promocional; el bono se retira al momento». El OCR sacó 562 caracteres, pero del
párrafo clave solo leyó «on A amped een on Srthdrave the bonus immediately». Y con
el texto leído entero tampoco saltaba nada: no es un testimonio ni dice «crypto
giveaway». Cayó por las señales de forma (prisa + adjunto), no por lo que decía.

Medido sobre la imagen: de 9 frases clave, el OCR leía 3; enderezada e invertida, 9.
Los modelos precisos de Tesseract (`tessdata_best`) no ganaban nada.
"""
from __future__ import annotations

import asyncio
import io
import sys
from types import SimpleNamespace as NS

import pytest

from src import handlers, ocr
from src.detectors import investment_scam as inv

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageDraw  # noqa: E402

TIMO = (
    "I am pleased to announce the launch of my own cryptocurrency casino. To celebrate, "
    "I am giving away $3,200 to everyone who registers, and you can withdraw the bonus "
    "immediately. How to claim your reward: 1. Go to weazex.com 2. Enter the special promo "
    "code: FAST 3. Receive your $3,200 bonus - play or withdraw. This post will be deleted "
    "one hour after publication, so only the fastest will get the bonus. Don't miss your chance!"
)
# Lo que leyó el OCR de verdad, sin preparar la imagen.
LEIDO_MAL = (
    "Posts Replies subs Highlights Media A Pinned on @mrBeast- 47 minutes ago on A amped "
    "een on Srthdrave the bonus immediately How to claim your reward: 4. Goto weazex.com "
    "+ Gory e special promo code: FAST 2 our 52200 Domus ply or wa a Tis pots"
)


def _check(texto: str):
    return inv.check(NS(text=texto, caption=None), is_first_msg=True)


# ------------------------------------------------------------------ el ancla nueva

def test_el_timo_del_casino_salta():
    hit = _check(TIMO)
    assert hit.rule == "investment_scam"
    assert hit.payload["casino_bonus"] is True
    assert hit.score >= 70


def test_tambien_en_espanol():
    hit = _check("Nuevo casino online: regístrate con el código promocional VIP y recibe "
                 "un bono de 500€ que puedes retirar al instante")
    assert hit.rule == "investment_scam"


def test_lo_mal_leido_no_basta():
    """Sin la segunda lectura, el texto del caso no dice lo bastante: por eso hace falta."""
    assert not _check(LEIDO_MAL)


@pytest.mark.parametrize("frase", [
    # Una oferta de una tienda: código y bono, pero ni casino ni cripto ni retirada.
    "Oferta: usa el código promocional ALEXA10 y te dan un bono de 10€ en tu cuenta de Amazon",
    # Microsoft Rewards, sus códigos de regalo y retirar un pendrive: Windows de cada día.
    "He canjeado el código de regalo de Microsoft Rewards, 5€ de premio en la tienda. "
    "Para retirar el pendrive hay que expulsarlo antes",
    "Con Microsoft Rewards canjeas puntos por un código de regalo: 10€ de bono para la Xbox Store",
    # Quien avisa del timo no dice «bono».
    "Cuidado con las capturas falsas de MrBeast regalando $3,200 con un promo code en un "
    "casino cripto, es un timo",
    # «24K» son los «me gusta» de una captura, no dinero.
    "24K likes 5.3K shares. Promo code inside, casino bonus for everyone",
])
def test_lo_normal_no_salta(frase):
    assert not _check(frase)


# ------------------------------------------------------------------ enderezar la imagen

def _lineas(oscura: bool, giro: float) -> bytes:
    """Una «pantalla» con renglones de texto, torcida `giro` grados."""
    fondo, tinta = (20, 20, 20) if oscura else (250, 250, 250), (230, 230, 230) if oscura else (10, 10, 10)
    im = Image.new("RGB", (900, 700), fondo)
    d = ImageDraw.Draw(im)
    for y in range(60, 660, 40):
        d.rectangle((60, y, 840, y + 14), fill=tinta)
    if giro:
        im = im.rotate(giro, resample=Image.BICUBIC, expand=True, fillcolor=fondo)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def _gris(datos: bytes):
    return Image.open(io.BytesIO(datos)).convert("L")


def test_encuentra_la_inclinacion_y_la_deshace():
    gris = _gris(_lineas(oscura=False, giro=5))
    angulo = ocr._inclinacion(gris)
    assert abs(abs(angulo) - 5) <= 1
    recta = gris.rotate(angulo, resample=Image.BICUBIC, expand=True, fillcolor=255)
    assert abs(ocr._inclinacion(recta)) < ocr.GIRO_MIN


def test_una_imagen_recta_y_clara_no_se_toca():
    """Sin inversión ni giro no hay segunda lectura: costaría un segundo para nada."""
    assert ocr._preparar_sincrono(_lineas(oscura=False, giro=0)) is None


def test_la_oscura_se_invierte():
    sale = ocr._preparar_sincrono(_lineas(oscura=True, giro=0))
    assert sale is not None
    from PIL import ImageStat
    assert ImageStat.Stat(_gris(sale)).mean[0] > 128


def test_la_torcida_se_endereza():
    sale = ocr._preparar_sincrono(_lineas(oscura=True, giro=5))
    assert sale is not None
    assert abs(ocr._inclinacion(_gris(sale))) < ocr.GIRO_MIN


def test_sin_pillow_no_se_prepara_nada(monkeypatch):
    datos = _lineas(oscura=True, giro=5)
    monkeypatch.setitem(sys.modules, "PIL", None)
    assert ocr._preparar_sincrono(datos) is None


def test_una_imagen_rota_no_tumba_nada():
    assert ocr._preparar_sincrono(b"esto no es una imagen") is None


# ------------------------------------------------------------------ la segunda lectura

class _Bot:
    async def get_file(self, file_id):
        async def bajar():
            return bytearray(b"img")
        return NS(download_as_bytearray=bajar)


def _preparar_lectura(monkeypatch, primera: str, segunda: str) -> list:
    llamadas = []

    async def leer(datos, *, preparar=False):
        llamadas.append(preparar)
        return segunda if preparar else primera
    monkeypatch.setattr(ocr, "_disponible", True)
    monkeypatch.setattr(ocr, "leer", leer)
    monkeypatch.setattr(handlers, "_ocr_activo", lambda db, chat: True)
    monkeypatch.setattr(handlers, "_chat_money_guard", lambda db, chat: "normal")
    monkeypatch.setattr(handlers.destinos, "fichados", lambda db: set())
    handlers._IMAGENES_LEIDAS.clear()
    return llamadas


def _leer_imagen(msg_id: int = 1):
    msg = NS(photo=[NS(file_id="f", file_size=100)], document=None, chat_id=-100,
             message_id=msg_id, chat=NS(id=-100, title="W11"))
    cfg = NS(url_blocklist=[], mute_score=40)
    return asyncio.run(handlers._hits_de_la_imagen(
        NS(bot=_Bot()), None, cfg, msg, NS(id=5), avisar=False))


def test_si_la_primera_no_dice_nada_se_lee_enderezada(monkeypatch):
    llamadas = _preparar_lectura(monkeypatch, LEIDO_MAL, TIMO)
    reales = [h for h in _leer_imagen() if h]
    assert llamadas == [False, True]
    assert [h.rule for h in reales] == ["investment_scam"]


def test_si_la_primera_ya_dispara_no_se_lee_otra_vez(monkeypatch):
    llamadas = _preparar_lectura(monkeypatch, TIMO, "")
    assert any(_leer_imagen())
    assert llamadas == [False]


def test_la_regla_y_el_perdon_no_leen_dos_veces_la_misma_foto(monkeypatch):
    llamadas = _preparar_lectura(monkeypatch, LEIDO_MAL, TIMO)
    primera = _leer_imagen(msg_id=7)
    segunda = _leer_imagen(msg_id=7)
    assert [h.rule for h in primera if h] == [h.rule for h in segunda if h]
    assert llamadas == [False, True]
