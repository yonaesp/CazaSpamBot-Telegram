"""Compartir una historia recién entrado: la defensa que NO necesita Telethon.

El contenido de una historia solo se lee por MTProto. Quien instale el bot sin
cuenta secundaria se quedaría sin ninguna defensa ante este vector, así que este
detector trabaja solo con la estructura: quién comparte, de quién es la historia y
cuánto lleva en el grupo.

La señal no es «tiene una historia» (eso sería un falso positivo asegurado), es
compartir la de OTRO chat nada más entrar.
"""
import types

from src.detectors import story_share as det


def _msg(story_chat_id=-100123, titulo="Fotografía de Montaña"):
    return types.SimpleNamespace(story=types.SimpleNamespace(
        id=7, chat=types.SimpleNamespace(id=story_chat_id, title=titulo, username=None)))


# --------------------------------------------------------------- positivos

def test_primer_mensaje_con_canal_neutro_no_actua_solo():
    """Compartir una historia al entrar es raro, pero NO es delito: puede ser el
    canal enlazado del propio grupo. Por debajo de MUTE_SCORE (40) a propósito."""
    from src.scoring import decide
    h = det.check(_msg(), user_id=555, is_first_msg=True, bot_saw_join=True, msg_count=1)
    assert h, "debería al menos anotar la estructura"
    assert h.score < 40, f"actuaría con la estructura sola: {h.score}"
    assert decide([h], 100, 70, 40, "ban", False).action == "noop"


def test_el_caso_real_que_se_colo_si_banea():
    """Recién llegado + canal «Insider Group Signal»: estructura + nombre = ban."""
    from src.scoring import decide
    h = det.check(_msg(titulo="Insider Group Signal"), user_id=555,
                  is_first_msg=True, bot_saw_join=True, msg_count=1)
    assert h and h.score >= 100, f"no llega a ban: {h.score if h else 0}"
    assert decide([h], 100, 70, 40, "ban", False).action == "ban"


def test_el_score_no_se_invierte():
    """Regresión: al retornar en la primera rama, el recién llegado con un canal de
    spam puntuaba 40 y el veterano con el MISMO canal, 100. Justo al revés."""
    recien = det.check(_msg(titulo="Crypto Signals VIP"), user_id=5, is_first_msg=True,
                       bot_saw_join=True, msg_count=1)
    veterano = det.check(_msg(titulo="Crypto Signals VIP"), user_id=5, is_first_msg=False,
                         bot_saw_join=False, msg_count=2)
    assert recien.score >= veterano.score, (
        f"el recién llegado ({recien.score}) puntúa menos que el veterano ({veterano.score})")


def test_recien_entrado_pero_ya_hablo_no_actua_solo():
    """La estructura sola nunca actúa: queda por debajo de MUTE_SCORE (40). Si además
    se pudo leer el contenido y este dispara, los scores se suman y ahí sí se actúa.

    Antes valía 40 exactos, que NO es «revisión» como decía el comentario: con
    MUTE_SCORE=40 eso son 24 h de mute automático y sin que nadie lo revise."""
    from src.scoring import decide
    h = det.check(_msg(), user_id=555, is_first_msg=False, bot_saw_join=True,
                  seconds_since_join=60, msg_count=2)
    assert h, "no marcó nada a un recién llegado"
    assert decide([h], 100, 70, 40, "ban", False).action == "noop", (
        f"actuaría con la estructura sola ({h.score} puntos)")


def test_estructura_mas_contenido_leido_si_actua():
    """Y sumada a una regla de contenido del texto recuperado, sí llega a ban."""
    from src.scoring import combine
    import types as _t
    estructura = det.check(_msg(), user_id=555, is_first_msg=True, bot_saw_join=True,
                           msg_count=1)
    contenido = _t.SimpleNamespace(rule="external_mention", score=100, reason="x",
                                   payload={}, __bool__=lambda s: True)
    total, _ = combine([estructura, contenido])
    assert total >= 100, f"estructura + contenido no llegan a ban: {total}"


# --------------------------------------------------------------- anti falso positivo

def test_su_propia_historia_no_cuenta():
    """Compartir la historia de uno mismo es de lo más normal."""
    assert not det.check(_msg(story_chat_id=555), user_id=555,
                         is_first_msg=True, bot_saw_join=True)


def test_sin_join_presenciado_no_se_toca():
    """Usuario anterior al bot: no sabemos si es su primer mensaje, podría llevar
    años. Es el falso positivo conocido de first_msg_media."""
    assert not det.check(_msg(), user_id=555, is_first_msg=True, bot_saw_join=False)


def test_un_veterano_compartiendo_una_historia_no_dispara():
    """Lleva tiempo en el grupo y comparte una historia normal: eso es usar Telegram."""
    assert not det.check(_msg(), user_id=555, is_first_msg=False, bot_saw_join=True,
                         seconds_since_join=45 * 86400, msg_count=300)


def test_sin_historia_no_hace_nada():
    assert not det.check(types.SimpleNamespace(story=None), user_id=555,
                         is_first_msg=True, bot_saw_join=True)


def test_recien_entrado_sin_dato_de_antiguedad_no_dispara():
    """Sin saber cuánto lleva, no se inventa: ante la duda, no se marca."""
    assert not det.check(_msg(), user_id=555, is_first_msg=False, bot_saw_join=True,
                         seconds_since_join=None)


# --------------------------------------------------------------- integración

def test_estructura_mas_contenido_suman_hasta_ban():
    """El reparto de puntos tiene sentido: 40 de estructura + una regla de contenido
    del texto recuperado pasan de sobra el umbral de ban."""
    from src.scoring import combine
    estructura = det.check(_msg(), user_id=555, is_first_msg=False, bot_saw_join=True,
                           seconds_since_join=60)
    contenido = types.SimpleNamespace(rule="external_mention", score=100, reason="x",
                                      payload={}, __bool__=lambda s: True)
    total, _ = combine([estructura, contenido])
    assert total >= 100, f"estructura + contenido no llegan a ban: {total}"


def test_la_regla_esta_en_el_inventario():
    """Sin esto el admin vería el id técnico en vez de una explicación."""
    from src.rule_explain import KNOWN_RULES
    assert "story_share" in KNOWN_RULES


# ------------------------------------- el canal de origen tiene nombre de spam
# Esta señal NO exige join presenciado: la evidencia es el nombre del canal, no
# cuándo entró. Cubre justo al que lleva tiempo en el grupo y apenas escribe.

def test_apenas_escribe_y_comparte_canal_con_nombre_de_spam():
    """El caso pedido: lleva tiempo, casi no habla, y de repente planta esto."""
    from src.scoring import decide
    h = det.check(_msg(titulo="Insider Group Signal"), user_id=555,
                  is_first_msg=False, bot_saw_join=False, msg_count=2)
    assert h, "no detectó al usuario callado que comparte un canal de señales"
    assert decide([h], 100, 70, 40, "ban", False).action in ("ban", "kick")
    assert "2" in h.reason, "el motivo no dice que apenas escribe"


def test_el_que_si_participa_no_se_banea_solo_por_el_nombre():
    """Un usuario activo compartiendo un canal con nombre feo NO se banea por eso.
    Suma, y deciden el resto de señales y el trust."""
    h = det.check(_msg(titulo="Crypto Signals VIP"), user_id=555, is_first_msg=False,
                  bot_saw_join=True, msg_count=250)
    assert h, "debería al menos sumar"
    assert h.score < 70, f"actuaría contra un participante activo por el nombre: {h.score}"


def test_canal_con_nombre_normal_no_dispara_aunque_escriba_poco():
    """Sin nombre sospechoso no hay señal: compartir historias es normal."""
    assert not det.check(_msg(titulo="Recetas de la Abuela"), user_id=555,
                         is_first_msg=False, bot_saw_join=False, msg_count=1)


def test_el_nombre_tambien_se_mira_en_el_username():
    m = types.SimpleNamespace(story=types.SimpleNamespace(
        id=7, chat=types.SimpleNamespace(id=-100123, title="Grupo", username="crypto_signals_vip")))
    h = det.check(m, user_id=555, is_first_msg=False, bot_saw_join=False, msg_count=1)
    assert h and h.score >= 70


def test_palabras_corrientes_no_estan_en_la_lista():
    """Guarda de falsos positivos: si alguien mete «ofertas» o «noticias» en la
    lista, canales legítimos empezarían a caer."""
    from src.detectors.story_share import _fuente_sospechosa
    for legitimo in ("Ofertas Informática", "Noticias Tech", "Grupo de Fotografía",
                     "Ayuda Windows 11", "Domótica España"):
        assert not _fuente_sospechosa(legitimo, None), f"falso positivo con {legitimo!r}"


def test_los_limites_de_palabra_evitan_banear_canales_legitimos():
    """Regresión: sin \\b, «rich» casaba dentro de «Zürich» y «pump» dentro de
    «Pumpkin». Un usuario con 4 mensajes compartiendo una historia de un canal de
    noticias suizo se comía un ban federado."""
    from src.detectors.story_share import _fuente_sospechosa
    for legitimo in ("Zürich Nachrichten", "Heinrich Böll Stiftung", "Pumpkin Recipes",
                     "Enrichment Center", "Ostrich Fans", "Learn English",
                     "Richard Fotografía", "Casinos de Historia"):
        assert not _fuente_sospechosa(legitimo, None), f"falso positivo con {legitimo!r}"


def test_los_guiones_bajos_del_username_no_esconden_el_termino():
    """En `btc_signals_vip` el guion bajo es carácter de palabra, así que `\\bsignals\\b`
    no casaría. Y los @username de Telegram van llenos de guiones bajos."""
    from src.detectors.story_share import _fuente_sospechosa
    for uname in ("crypto_signals_vip", "vip_forex_signals", "free_signals_club"):
        assert _fuente_sospechosa("", uname), f"se escapó {uname!r}"


def test_bateria_de_canales_legitimos_de_la_auditoria():
    """Los 16 canales REALES que una versión anterior de la lista habría baneado.

    Los peores estaban justo en los grupos moderados: «Windows Insider Program» en
    los de Windows y «Heat Pump UK» (aerotermia) en el de domótica. Por eso la lista
    es de PAREJAS: el tema lo nombra mucha gente legítima, la combinación no.
    """
    from src.detectors.story_share import _fuente_sospechosa
    legitimos = [
        "Windows Insider Program", "Business Insider España", "Signal Messenger",
        "Digital Signal Processing", "SignalRGB", "Heat Pump UK", "Pumpkin Recipes",
        "Cryptography Weekly", "Apple AirDrop Tips", "Ford Escort Club",
        "Casino Royale", "Whale Watching Tarifa", "XXX Aniversario del Club",
        "Rich Text Editor", "Zürich Nachrichten", "Nonprofit Tech News",
    ]
    fallos = [n for n in legitimos if _fuente_sospechosa(n, None)]
    assert not fallos, f"banearía canales legítimos: {fallos}"


def test_el_spam_de_verdad_sigue_cayendo():
    """Contrapeso del anterior: afinar la lista no puede dejarla inútil."""
    from src.detectors.story_share import _fuente_sospechosa
    spam = ["Insider Group Signal", "Crypto Signals VIP", "Bitcoin Pump Club",
            "Free Airdrop Daily", "Online Casino Bonus", "OnlyFans Leaks",
            "Private Signals", "Forex Signals Premium"]
    escapados = [n for n in spam if not _fuente_sospechosa(n, None)]
    assert not escapados, f"se escapa spam evidente: {escapados}"
