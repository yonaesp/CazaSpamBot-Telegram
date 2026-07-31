"""Los desplazamientos de las entidades vienen en UTF-16, no en caracteres.

Telegram cuenta los offsets en unidades UTF-16; Python indexa por carácter. Cada
emoji fuera del plano básico ocupa DOS unidades UTF-16 y UN carácter de Python, así
que cortar con `texto[offset:offset+length]` se desplaza uno por cada emoji que haya
ANTES de la entidad. Y el spam va cargado de emojis justo delante del enlace.

Efecto real: la URL salía como «ttps://t.me/+abc». Con la URL mutilada, las listas
negras no casan y `resolve_username` no encuentra al usuario. Detección perdida,
en silencio y sin ningún error.
"""
from telegram import MessageEntity

from src.detectors import trozo_entidad


def _entidad(texto, trozo, tipo="url"):
    """Construye la entidad como la manda Telegram: offset en unidades UTF-16."""
    off = len(texto[:texto.index(trozo)].encode("utf-16-le")) // 2
    ln = len(trozo.encode("utf-16-le")) // 2
    return MessageEntity(type=tipo, offset=off, length=ln)


def test_recorta_bien_con_emojis_delante():
    texto = "▶️▶️▶️▶️ 👀Mira esto https://t.me/+67gOPOowkDliODQy"
    url = "https://t.me/+67gOPOowkDliODQy"
    e = _entidad(texto, url)
    assert trozo_entidad(texto, e.offset, e.length) == url


def test_el_corte_ingenuo_fallaba():
    """Fija el porqué del helper: sin él, el corte pierde caracteres."""
    texto = "▶️▶️▶️▶️ 👀Mira esto https://t.me/+abc"
    url = "https://t.me/+abc"
    e = _entidad(texto, url)
    ingenuo = texto[e.offset:e.offset + e.length]
    assert ingenuo != url, "si esto empieza a coincidir, el helper ya no hace falta"
    assert trozo_entidad(texto, e.offset, e.length) == url


def test_sin_emojis_sigue_funcionando():
    texto = "mira esto https://ejemplo.com y dime"
    url = "https://ejemplo.com"
    e = _entidad(texto, url)
    assert trozo_entidad(texto, e.offset, e.length) == url


def test_una_mencion_tras_emojis_se_extrae_entera():
    """Con la mención cortada, resolve_username no encuentra a nadie."""
    texto = "‼️🪙 escríbele a @usuario_spam ya"
    men = "@usuario_spam"
    e = _entidad(texto, men, tipo="mention")
    assert trozo_entidad(texto, e.offset, e.length) == men


def test_la_mencion_mutilada_rompia_la_busqueda_del_usuario():
    """Este es el daño concreto, medido.

    En las URLs el desfase solía ser inofensivo porque `urlparse` seguía sacando el
    dominio de «ps://t.me/...». En las menciones no: el recorte se lleva un espacio
    por delante o por detrás, y `resolve_username(\'usuario_spam \')` no encuentra a
    nadie. La detección se pierde sin ningún error de por medio.
    """
    texto = "‼️🪙 escríbele a @usuario_spam ya"
    men = "@usuario_spam"
    e = _entidad(texto, men, tipo="mention")

    ingenuo = texto[e.offset:e.offset + e.length].lstrip("@")
    assert ingenuo != "usuario_spam", "si esto coincide, el helper ya no hace falta"

    bueno = trozo_entidad(texto, e.offset, e.length).lstrip("@")
    assert bueno == "usuario_spam", f"la mención sigue saliendo mal: {bueno!r}"


def test_con_muchos_emojis_la_url_pierde_hasta_el_esquema():
    """Con desfase suficiente, «https://» desaparece entero y ahí sí falla todo."""
    from urllib.parse import urlparse
    texto = "🔥" * 10 + " https://malo.example/x"
    url = "https://malo.example/x"
    e = _entidad(texto, url)
    ingenuo = texto[e.offset:e.offset + e.length]
    assert urlparse(ingenuo).netloc != "malo.example", "el desfase ya no rompe la URL"
    assert urlparse(trozo_entidad(texto, e.offset, e.length)).netloc == "malo.example"


def test_el_motivo_cita_el_trozo_exacto_que_salto():
    """El motivo es lo que el admin lee al revisar un ban meses después.

    Las etiquetas genéricas («llama a contactar a esa persona») dejaron de describir
    la realidad cuando las listas crecieron: en el caso real saltaba por «only 100
    spots left», que no pide contactar a nadie. Un motivo que cuenta algo que no
    pasó es peor que uno escueto.
    """
    import types
    from src.detectors import investment_scam as inv
    texto = ("Recently I came across a private group of a legendary whale. He shares "
             "valuable insights. only 100 spots left. Click to subscribe")
    h = inv.check(types.SimpleNamespace(text=texto, caption=None), is_first_msg=True)
    assert h, "no disparó"
    assert "only 100 spots left" in h.reason, (
        f"el motivo no cita lo que realmente saltó: {h.reason}"
    )


def test_la_cita_no_puede_romper_el_html_del_aviso():
    """El trozo sale del mensaje del spammer: si colara un `<b>`, Telegram
    rechazaría el aviso entero y el admin no se enteraría de nada."""
    import types
    from src.detectors import investment_scam as inv
    texto = ("<b>Recently I came across a private group of a legendary whale. He shares "
             "valuable insights. only 100 spots left. <i>Click to subscribe")
    h = inv.check(types.SimpleNamespace(text=texto, caption=None), is_first_msg=True)
    assert h
    assert "<" not in h.reason and ">" not in h.reason, f"HTML colado: {h.reason}"
