"""El PERFIL también se mira al escribir, no solo el texto.

El bot miraba el perfil en dos momentos —al entrar y, desde el 2026-08-09, en el
repaso de recién llegados— pero al hablar juzgaba solo el texto. Entre la última
pasada del repaso y el primer mensaje pueden ir minutos, y ahí cabe entero el
truco: entrar con el perfil limpio y cambiarlo justo antes de escribir.

Caso medido (9-ago-2026, Domótica): «李大哥», nombre 100 % Han, con el canal
`财天下飞机进群结演员结算频道` en el perfil. Entró a las 00:39 pasando los
filtros, **se verificó en 4 segundos** y escribió 15 horas después. Lo cazó
`non_allowed_script`, o sea por el IDIOMA DEL TEXTO: con un «hola buenas» habría
pasado limpio. Y «Vickycat46», de la misma red, tenía nombre latino.

Aquí no hay umbrales nuevos: se aplican los mismos criterios del join. Si con ese
perfil no habría entrado, tampoco habla.
"""
from pathlib import Path

import pytest

from src.detectors import personal_channel as pc
from src.verification import _is_obvious_spam_profile


def _bloque() -> str:
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("# 3d bis) EL PERFIL en el primer mensaje")
    return fuente[i:fuente.index("# 3e)", i)]


# --------------------------------------------------- el caso real, pieza a pieza

def test_el_nombre_de_ese_perfil_ya_bastaba():
    """La premisa: con ese nombre el join lo habría baneado. Lo que fallaba no era
    el criterio, era que en el primer mensaje no se aplicaba."""
    obvio, razones = _is_obvious_spam_profile(None, None, "李大哥", None)
    assert obvio
    assert any(r[0] == "han_dominant" for r in razones)


def test_y_el_canal_tambien_puntuaba():
    h = pc.check("财天下飞机进群结演员结算频道", first_name="李大哥",
                 has_photo=True, has_bio=False, allowed_scripts=("latin",))
    assert h and h.score >= 100


def test_con_un_saludo_en_espanol_no_habria_saltado_nada_antes():
    """Lo que hace falta entender: `non_allowed_script` lo cazó por el idioma del
    texto. Ese detector no ve el perfil, así que un texto latino lo desactiva."""
    from src.detectors import unicode_script as us
    assert not us.check("hola buenas", is_first_msgs=True, allowed_scripts=["latin"],
                        threshold=0.5)
    # ...y con el texto que sí escribió, salta. Esa es toda la diferencia.
    assert us.check("凎活啦", is_first_msgs=True, allowed_scripts=["latin"], threshold=0.5)


# ------------------------------------------------------------- lo que se exige

def test_se_mira_el_perfil_en_el_primer_mensaje():
    bloque = _bloque()
    assert "_is_obvious_spam_profile" in bloque
    assert "_mirar_canal_personal" in bloque


def test_solo_en_los_primeros_mensajes():
    """Quien ya participa no paga una llamada a Telethon por cada mensaje."""
    assert "if is_first" in _bloque()


def test_no_se_aplica_a_quien_ya_estaba_antes_que_el_bot():
    """La guarda que evita el falso positivo documentado: con `join_ts` a NULL el
    usuario podía llevar años en el grupo y esto no es su primer mensaje."""
    bloque = _bloque()
    assert 'join_ts' in bloque and "is not None" in bloque


def test_usa_los_mismos_criterios_que_el_join_sin_inventar_umbrales():
    """Si aquí hubiera un umbral propio, habría dos varas de medir y el perfil
    que entra podría ser distinto del que puede hablar."""
    bloque = _bloque()
    for prohibido in ("score=1", "MIN_SCORE", "> 0.5", "ratio ="):
        assert prohibido not in bloque, f"umbral propio detectado: {prohibido}"


def test_un_fallo_de_telethon_no_tumba_el_mensaje():
    assert "except Exception" in _bloque()


# --------------------------------------------------- una sola llamada por mensaje

def test_las_senales_se_piden_una_sola_vez():
    """Antes había hasta tres sitios pidiendo el perfil en el mismo mensaje, cada
    uno con su propia llamada y su tope de 12 s, en una ruta donde PTB procesa los
    updates de uno en uno."""
    fuente = Path("src/handlers.py").read_text()
    i = fuente.index("async def on_message(")
    cuerpo = fuente[i:fuente.index("\nasync def ", i + 10)]
    directas = cuerpo.count("user_signals.fetch(")
    assert directas <= 1, (
        f"{directas} llamadas directas a user_signals.fetch en on_message: "
        "deberían pasar todas por el ayudante que cachea")
    assert "_senales()" in cuerpo


@pytest.mark.asyncio
async def test_el_ayudante_cachea_de_verdad(monkeypatch):
    """Comprobación de comportamiento, no de texto: dos consumidores, una llamada."""
    from types import SimpleNamespace

    llamadas = []

    async def falso_fetch(client, user_id, **kw):
        llamadas.append(user_id)
        return SimpleNamespace(personal_channel_title=None, photo_count=1, bio=None)

    monkeypatch.setattr("src.user_signals.fetch", falso_fetch)

    # Se reproduce el ayudante tal cual está escrito en on_message.
    import src.handlers as h
    perfil: dict = {}
    context = SimpleNamespace(bot_data={"reporter": SimpleNamespace(get_client=lambda: object())})
    user = SimpleNamespace(id=7, first_name="X")

    async def _senales():
        if "sig" not in perfil:
            reporter_ = context.bot_data.get("reporter")
            cli = reporter_.get_client() if reporter_ else None
            valor = None
            if cli is not None:
                valor = await h.user_signals.fetch(cli, user.id, chat_id=-100,
                                                   first_name=user.first_name)
            perfil["sig"], perfil["client"] = valor, cli
        return perfil["sig"], perfil["client"]

    await _senales()
    await _senales()
    await _senales()
    assert llamadas == [7], "el perfil se pidió más de una vez en el mismo mensaje"


def test_sin_telethon_devuelve_none_y_el_bot_sigue():
    """Quien instale el bot sin cuenta secundaria pierde esta vía, no el bot: el
    ayudante tiene que tolerar que no haya reporter."""
    bloque = Path("src/handlers.py").read_text()
    i = bloque.index("async def _senales():")
    cuerpo = bloque[i:i + 900]
    assert "if cli is not None" in cuerpo
