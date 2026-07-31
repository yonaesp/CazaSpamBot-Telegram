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

def test_primer_mensaje_es_historia_ajena_banea():
    """El caso que se coló en el grupo."""
    h = det.check(_msg(), user_id=555, is_first_msg=True, bot_saw_join=True)
    assert h, "no detectó el patrón que se coló"
    assert h.score >= 100, f"no llega a ban: {h.score}"
    assert "Fotografía" in h.reason, "el motivo no dice de dónde viene la historia"


def test_recien_entrado_pero_ya_hablo_no_banea_solo():
    """40 puntos: sospecha, va a revisión, pero no banea por sí solo. Si además se
    pudo leer el contenido y este dispara, los scores se suman y ahí sí se actúa."""
    h = det.check(_msg(), user_id=555, is_first_msg=False, bot_saw_join=True,
                  seconds_since_join=60)
    assert h, "no marcó nada a un recién llegado"
    assert h.score < 100, f"banearía sin haber leído el contenido: {h.score}"
    assert h.score >= 40


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
    h = det.check(_msg(titulo="Insider Group Signal"), user_id=555,
                  is_first_msg=False, bot_saw_join=False, msg_count=2)
    assert h, "no detectó al usuario callado que comparte un canal de señales"
    assert h.score >= 100, f"no llega a ban: {h.score}"
    assert "2" in h.reason, "el motivo no dice que apenas escribe"


def test_el_que_si_participa_no_se_banea_solo_por_el_nombre():
    """Un usuario activo compartiendo un canal con nombre feo NO se banea por eso.
    Suma, y deciden el resto de señales y el trust."""
    h = det.check(_msg(titulo="Crypto News"), user_id=555, is_first_msg=False,
                  bot_saw_join=True, msg_count=250)
    assert h, "debería al menos sumar"
    assert h.score < 100, f"banearía a un participante activo por el nombre: {h.score}"


def test_canal_con_nombre_normal_no_dispara_aunque_escriba_poco():
    """Sin nombre sospechoso no hay señal: compartir historias es normal."""
    assert not det.check(_msg(titulo="Recetas de la Abuela"), user_id=555,
                         is_first_msg=False, bot_saw_join=False, msg_count=1)


def test_el_nombre_tambien_se_mira_en_el_username():
    m = types.SimpleNamespace(story=types.SimpleNamespace(
        id=7, chat=types.SimpleNamespace(id=-100123, title="Grupo", username="btc_signals_vip")))
    h = det.check(m, user_id=555, is_first_msg=False, bot_saw_join=False, msg_count=1)
    assert h and h.score >= 100


def test_palabras_corrientes_no_estan_en_la_lista():
    """Guarda de falsos positivos: si alguien mete «ofertas» o «noticias» en la
    lista, canales legítimos empezarían a caer."""
    from src.detectors.story_share import _fuente_sospechosa
    for legitimo in ("Ofertas Informática", "Noticias Tech", "Grupo de Fotografía",
                     "Ayuda Windows 11", "Domótica España"):
        assert not _fuente_sospechosa(legitimo, None), f"falso positivo con {legitimo!r}"
