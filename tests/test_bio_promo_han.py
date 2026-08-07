"""Bio con enlace de invitación: ni salvoconducto ni «decide tú».

Caso real (7-ago-2026): entró una cuenta con nombre en ideogramas chinos, **1218
días de antigüedad y 8 fotos**, o sea con todas las señales de persona real. El
salvoconducto de «cuenta asentada» la libró del ban y quedó a decisión del admin.

Pero su bio era un anuncio de blanqueo con enlace de invitación privado:
«【新币公群】白资收U·代付大小额·押金18万U: https://t.me/+…». No había nada que decidir.

Dos arreglos, y el segundo es el general:
  1. El salvoconducto NO se aplica si la bio lleva un enlace de invitación. Una
     persona real con cuenta de tres años no anuncia un canal privado en su bio.
  2. `bio_spam` no puntuaba nada de esa bio salvo el enlace (40 de 60): sus otras
     señales (emojis, CTA, cifras) están pensadas para texto latino. Ahora una bio
     escrita mayoritariamente en otro alfabeto CON enlace de invitación suma.
"""
from types import SimpleNamespace

from src import verification as v
from src.detectors import bio_spam

BIO_SPAM = ("【新币公群】白资收U·代付大小额·押金18万U: https://t.me/+wtLPvEtoCq5kYzZl "
            "全网最高汇率 资金均来自实体")


def _cuenta(bio, fotos=8, dias=1218):
    return SimpleNamespace(photo_count=fotos, account_age_days=dias, bio=bio)


# ------------------------------------------------- el salvoconducto

def test_la_bio_publicitaria_anula_el_salvoconducto():
    """El caso real: cuenta de 3 años con 8 fotos, pero su bio es el anuncio."""
    baneado, _ = v._is_obvious_spam_profile(_cuenta(BIO_SPAM), "y38rnrst59302q92x9",
                                            "凎吙爪窝", None)
    assert baneado is True, "sigue librándose por tener cuenta antigua y fotos"


def test_una_bio_normal_conserva_el_salvoconducto():
    """Contrapeso: el salvoconducto existe para proteger a personas reales y tiene
    que seguir haciéndolo."""
    baneado, _ = v._is_obvious_spam_profile(_cuenta("Ingeniero. Vivo en Madrid."),
                                            "pepe", "凎吙爪窝", None)
    assert baneado is False


def test_no_se_pide_decision_de_algo_que_ya_se_banea():
    """Si se banea, pedir decisión solo genera un aviso que hay que descartar."""
    assert v.han_requiere_decision(_cuenta(BIO_SPAM), "x", "凎吙爪窝", None) is False
    assert v.han_requiere_decision(_cuenta("Fotógrafo"), "x", "凎吙爪窝", None) is True


# ------------------------------------------------- el detector de bios

def test_la_bio_del_caso_real_ahora_puntua():
    """Antes se quedaba en los 40 del enlace, por debajo del umbral de 60."""
    h = bio_spam.check(BIO_SPAM)
    assert h, "la bio de blanqueo seguía pasando como inocente"
    assert h.score >= 60


def test_un_canal_publico_no_cuenta_como_señal():
    """Quien tiene canal propio lo enlaza por su @nombre público, en cualquier
    idioma. Marcar eso sería banear al entrar a gente legítima."""
    assert not bio_spam.check("Мой канал про фотографию: https://t.me/mi_canal_ruso")
    assert not bio_spam.check("摄影师，我的频道: https://t.me/mi_canal")


def test_otro_alfabeto_sin_enlace_no_cuenta():
    """Una bio en cirílico o árabe es de lo más normal: el alfabeto solo pesa
    acompañado del enlace privado."""
    assert not bio_spam.check("Привет! Люблю фотографию и путешествия по миру")
    assert not bio_spam.check("مرحبا، أنا مهندس برمجيات وأحب القراءة")


def test_la_U_de_usdt_no_hace_pasar_la_bio_por_latina():
    """El fallo que tuve al implementarlo: comprobar «¿hay alguna letra latina?»
    era inútil porque el spam de USDT escribe «收U» y «18万U»."""
    assert bio_spam.check("押金18万U 收U: https://t.me/+abcdef123"), (
        "una sola U latina vuelve a colar la bio entera")
