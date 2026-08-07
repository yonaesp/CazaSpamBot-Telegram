"""Quitar el disfraz al texto antes de juzgarlo.

Medido en este bot ANTES de escribir el módulo, con una frase que ya cazaba:

    «Gana 500 euros al dia trabajando desde casa»   commercial_ad = 75
    «Gana 500 eurоs al dia trabajando desde casa»   commercial_ad =  0

La única diferencia es la `о` de «euros», que es CIRÍLICA. Una letra, y el mensaje
se volvía invisible: tampoco saltaba `unicode_script`, porque mide la PROPORCIÓN de
caracteres ajenos y una entre cuarenta y siete no llega al umbral.

La idea viene de `tg-spam` (umputun), que tiene comprobaciones específicas de
«palabras multi-alfabeto» y de espaciado anómalo. Aquí se resuelve al revés y sale
más barato: en vez de una regla nueva que puntúe el disfraz, se DESHACE el disfraz y
deciden las reglas de siempre. Si el texto desenmascarado no dice nada punible, no
pasa nada, así que no puede inventarse un falso positivo que no existiera ya.
"""
from types import SimpleNamespace

import pytest

from src import desofuscar
from src.detectors import commercial_ad as com


def _msg(t):
    return SimpleNamespace(text=t, caption=None, entities=None, caption_entities=None)


LIMPIA = "Gana 500 euros al dia trabajando desde casa, escribeme ahora"


# ------------------------------------------------------------- lo que arregla

@pytest.mark.parametrize("texto", [
    "Gana 500 eurоs al dia trabajando desde casa, escribeme ahora",     # 1 cirílica
    "Gаna 500 eurоs al dia trabajandо desde casa, escribeme ahora",     # 3 cirílicas
])
def test_una_letra_cambiada_ya_no_esconde_el_mensaje(texto):
    assert com.check(_msg(texto), is_first_msg=True).score == 0, "premisa: sin limpiar no casa"
    limpio, trucos = desofuscar.limpiar(texto)
    assert trucos == ["homoglifos"]
    assert com.check(_msg(limpio), is_first_msg=True).score == \
        com.check(_msg(LIMPIA), is_first_msg=True).score


def test_el_espaciado_letra_a_letra_tampoco():
    texto = ("G a n a  5 0 0  e u r o s  a l  d i a  t r a b a j a n d o  "
             "d e s d e  c a s a  e s c r i b e m e  a h o r a")
    assert com.check(_msg(texto), is_first_msg=True).score == 0
    limpio, trucos = desofuscar.limpiar(texto)
    assert trucos == ["espaciado"]
    assert limpio.startswith("Gana 500 euros al dia")
    assert com.check(_msg(limpio), is_first_msg=True).score > 0


def test_los_dos_disfraces_a_la_vez():
    limpio, trucos = desofuscar.limpiar("G а n а  5 0 0  e u r о s  a l  d i a")
    assert trucos == ["homoglifos", "espaciado"]
    assert limpio.startswith("Gana 500 euros")


def test_la_longitud_no_cambia_al_quitar_homoglifos():
    """Los desplazamientos de las entidades de Telegram se cuentan sobre el texto:
    si el esqueleto cambiara la longitud, los enlaces y menciones se descuadrarían."""
    texto = "Mira esto: Gаna dinerо en https://ejemplo.com ahora"
    assert len(desofuscar.esqueleto(texto)) == len(texto)


# --------------------------------------------------- lo que NO debe tocar nunca

@pytest.mark.parametrize("texto", [
    # Idiomas de verdad: la palabra entera está en su alfabeto, no hay mezcla.
    "Привет, у меня проблема con Windows y no se que hacer",
    "Καλημέρα, έχω πρόβλημα με τα Windows",
    "مرحبا، لدي مشكلة في ويندوز",
    "你好，我的电脑有问题",
    # Énfasis a mano: corriente en un chat, y son pocas piezas.
    "H O L A a todos",
    "Q U E fuerte lo que me ha pasado hoy con el ordenador",
    # Técnico: Ω y µ no son confundibles con ninguna letra latina.
    "La resistencia es de 10Ω y el condensador 20µF en el circuito",
    "El procesador va a 3.2GHz con 16GB de RAM",
    # Normal y corriente.
    LIMPIA,
    "Buenos dias, alguien sabe como activar Windows 11 Home?",
])
def test_el_texto_legitimo_sale_intacto(texto):
    limpio, trucos = desofuscar.limpiar(texto)
    assert limpio == texto and trucos == [], f"tocó texto legítimo: {texto!r} -> {limpio!r}"


def test_una_palabra_entera_en_otro_alfabeto_no_es_disfraz():
    """Si «tradujéramos» el ruso a letras latinas, un grupo ruso vería su
    conversación convertida en galimatías que podría casar con cualquier patrón."""
    assert desofuscar.palabras_mezcladas("Привет мир") == []
    assert desofuscar.palabras_mezcladas("euroс") == ["euroс"]


def test_hacen_falta_dos_letras_para_hablar_de_mezcla():
    """Un carácter suelto (una inicial, un símbolo) no prueba nada."""
    assert desofuscar.palabras_mezcladas("a б c") == []


# ------------------------------------------------------------- el envoltorio

def test_el_envoltorio_deja_pasar_todo_lo_demas():
    """El bot tiene que seguir borrando y respondiendo al mensaje REAL."""
    real = SimpleNamespace(text="Gаna dinerо", caption=None, message_id=42,
                           chat_id=-100, from_user="quien")
    envuelto, trucos = desofuscar.para_detectores(real)
    assert trucos == ["homoglifos"]
    assert envuelto.text == "Gana dinero"
    assert envuelto.message_id == 42 and envuelto.chat_id == -100
    assert envuelto.from_user == "quien"


def test_el_envoltorio_no_lleva_entidades():
    """El desespaciado acorta el texto, así que las entidades quedarían
    descuadradas. Solo lo ven los detectores de texto plano."""
    real = SimpleNamespace(text="Gаna dinerо", caption=None, entities=["falsa"])
    envuelto, _ = desofuscar.para_detectores(real)
    assert envuelto.entities == []


def test_sin_disfraz_se_devuelve_el_mismo_objeto():
    """Ni copias ni envoltorios cuando no hacen falta: esto corre en cada mensaje."""
    real = _msg(LIMPIA)
    assert desofuscar.para_detectores(real)[0] is real


def test_mensaje_vacio_no_revienta():
    assert desofuscar.limpiar("") == ("", [])
    assert desofuscar.limpiar(None) == (None, [])
    assert desofuscar.para_detectores(SimpleNamespace(text=None, caption=None))[1] == []


def test_el_caption_tambien_se_limpia():
    real = SimpleNamespace(text=None, caption="Gаna dinerо")
    envuelto, trucos = desofuscar.para_detectores(real)
    assert trucos and envuelto.caption == "Gana dinero" and envuelto.text is None
