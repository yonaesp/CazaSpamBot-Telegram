"""Tests para naive_bayes_spam_prob + check_against_samples combinado."""
from __future__ import annotations


from src import learning


SPAM_SAMPLES = [
    "compra criptomonedas gana dinero",
    "trabajo desde casa 5000 euros",
    "haz click aquí y multiplica",
    "inversión segura 200% rentabilidad",
    "join my channel for crypto signals",
    "earn money easy daily payout",
    "click bit ly trabajo online",
    "envío fotos privadas premium",
    "casino bonus gratis hoy",
    "préstamo rápido sin avales",
    "venta de likes y seguidores",
    "compra seguidores instagram garantizado",
]

HAM_SAMPLES = [
    "alguien sabe cómo configurar la rutina de Alexa",
    "no me funciona el HDMI con Windows 11",
    "buenas, ¿cómo va el grupo?",
    "tengo problema con Windows update",
    "compré una luz Yeelight y va genial",
    "Alexa no entiende cuando le hablo en gallego",
    "actualicé a Win11 y va más lento",
    "alguien tiene un router compatible con Home Assistant",
    "compré una bombilla Tapo y muy bien",
    "se puede hacer rutina con el Echo Dot",
    "windows me da pantallazo azul al cargar",
    "instalé linux dual boot y funciona",
]


def test_below_min_samples_returns_none():
    """Sin samples suficientes, Bayes no actúa."""
    out = learning.naive_bayes_spam_prob("trabajo crypto", ["a"], ["b"])
    assert out is None


def test_clear_spam_text():
    """Texto típicamente spam → probabilidad alta."""
    p = learning.naive_bayes_spam_prob(
        "gana dinero compra criptomonedas premium",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert p is not None
    assert p > 0.7, f"esperaba >0.7, got {p}"


def test_clear_ham_text():
    """Texto legítimo → nunca puntúa como spam.

    Ojo con el margen: tras quitar las palabras funcionales y el vocabulario
    temático (`alexa`, `rutina`), de esta frase solo sobrevive un token,
    "problema". Con una única palabra el clasificador no puede (ni debe) estar
    muy seguro de nada; lo que importa es que no acuse, y no acusa: el score
    combinado es 0. Para el caso con contenido real, ver el test siguiente.
    """
    p = learning.naive_bayes_spam_prob(
        "alguien tiene problema con Alexa y rutina",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert p is not None
    assert p < 0.5, f"esperaba <0.5, got {p}"
    score, _ = learning.check_against_samples(
        "alguien tiene problema con Alexa y rutina", SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert score <= 0


def test_clear_ham_text_con_contenido():
    """Un ham con vocabulario propio sí baja con claridad."""
    p = learning.naive_bayes_spam_prob(
        "instalé linux dual boot y me da pantallazo azul al cargar",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert p is not None
    assert p < 0.3, f"esperaba <0.3, got {p}"


def test_check_against_samples_combines():
    """check_against_samples integra Bayes + Cosine."""
    score, match = learning.check_against_samples(
        "alguien sabe cómo configurar Alexa rutina",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    # debería ser negativo (penalización) por Bayes ham low o cosine ham match
    assert score <= 0


def test_check_against_samples_spam_clear():
    score, match = learning.check_against_samples(
        "gana dinero trabajo crypto desde casa fácil",
        SPAM_SAMPLES, HAM_SAMPLES,
    )
    assert score >= 50  # Bayes >0.85 o cosine alto


def test_check_against_samples_no_samples():
    """Sin samples, no actúa."""
    score, match = learning.check_against_samples("texto random", [], [])
    assert score == 0
    assert match is None


def test_tokenize_unicode():
    """Tokenizer maneja español + chars unicode, excluyendo stop-words."""
    tokens = learning._tokenize("comprar criptomonedas baratas ahora")
    # palabras con señal se mantienen
    assert "comprar" in tokens
    assert "criptomonedas" in tokens
    assert "baratas" in tokens


def test_tokenize_excluye_stopwords_y_tematicas():
    """Stop-words y vocabulario temático (alexa/windows) se eliminan."""
    tokens = learning._tokenize("hola que tal con alexa y windows")
    assert "hola" not in tokens   # stop-word
    assert "alexa" not in tokens  # temático
    assert "windows" not in tokens


def test_bayes_with_very_short_text():
    """Texto sin tokens → None."""
    p = learning.naive_bayes_spam_prob("a", SPAM_SAMPLES, HAM_SAMPLES)
    assert p is None  # menos de min token len


# --------- Salvaguardas: el vocabulario del grupo no puede volverse spam ---------

# Grupo de FOTOGRAFÍA. Los spammers venden cámaras, así que "camara" acaba en
# todas las muestras de spam. No puede convertirse por eso en señal de spam:
# es la palabra que más va a escribir la gente legítima del grupo.
_FOTO_SPAM = [
    "vendo camara barata escribeme al privado",
    "vendo camara reflex nueva contactame por dm",
    "tengo camara canon barata interesados privado",
    "camara nikon en oferta escribeme ya",
    "liquido camara sony precio increible dm",
    "camara profesional barata solo hoy privado",
    "vendo lente y camara escribeme",
    "camara usada como nueva contactame",
    "oferta camara digital privado interesados",
    "camara barata envio gratis escribeme",
]
_FOTO_HAM = [
    "buenos dias a todos como va el finde",
    "alguien sabe editar en lightroom",
    "que tal la exposicion larga de noche",
    "me encanta esa foto del atardecer",
    "voy a salir a hacer fotos manana",
    "el revelado digital me cuesta mucho",
    "gracias por el consejo lo probare",
    "hoy hay buena luz para retratos",
    "cual es vuestro objetivo favorito",
    "acabo de volver del viaje con mil fotos",
]


def test_token_tematico_del_grupo_no_castiga_al_legitimo():
    """La palabra del tema del grupo, sola, no basta para actuar."""
    for texto in (
        "mi camara nueva hace unas fotos increibles",
        "que camara me recomendais para empezar",
        "he comprado una camara de segunda mano",
        "estoy pensando en vender mi camara vieja",
    ):
        score, _ = learning.check_against_samples(texto, _FOTO_SPAM, _FOTO_HAM)
        assert score <= 0, f"{texto!r} puntuó {score}: castigaría a un legítimo"


def test_spam_real_del_mismo_grupo_sigue_detectandose():
    """Las salvaguardas no pueden dejar ciego al detector: varias señales juntas
    (vender + barato + contacto privado) siguen puntuando."""
    score, _ = learning.check_against_samples(
        "vendo camara olympus barata interesados al privado", _FOTO_SPAM, _FOTO_HAM,
    )
    assert score >= 50, f"esperaba detectar el anuncio, got {score}"


def test_un_token_solo_nunca_supera_el_umbral_de_bayes():
    """Ni la palabra más quemada del corpus decide sola: hay tope por token."""
    spam = [f"gratis chollo{i} camara" for i in range(20)]
    ham = [f"buenos dias grupo mensaje numero {i} de hoy" for i in range(20)]
    p = learning.naive_bayes_spam_prob("camara", spam, ham)
    assert p is not None
    assert p < 0.85, f"un token suelto llegó a {p}: decidiría él solo"


def test_token_en_ambas_clases_pesa_menos():
    """Un token que sale en spam Y en ham no separa nada: debe pesar la mitad."""
    solo_spam = [f"oferta chollo palabra{i}" for i in range(12)]
    ham_base = [f"buenos dias grupo mensaje {i}" for i in range(12)]
    p_solo_spam = learning.naive_bayes_spam_prob("chollo", solo_spam, ham_base)
    # Mismo corpus pero "chollo" aparece también en ham.
    ham_compartido = [f"buenos dias grupo chollo mensaje {i}" for i in range(12)]
    p_compartido = learning.naive_bayes_spam_prob("chollo", solo_spam, ham_compartido)
    assert p_solo_spam is not None and p_compartido is not None
    assert p_compartido < p_solo_spam, (
        f"compartido {p_compartido} debería pesar menos que exclusivo {p_solo_spam}"
    )


def test_token_visto_una_sola_vez_pesa_poco():
    """Un hapax (una única aparición) es ruido, no evidencia."""
    base_spam = [f"oferta chollo palabra{i}" for i in range(12)]
    base_ham = [f"buenos dias grupo mensaje {i}" for i in range(12)]
    # "bicicleta" se cuela UNA vez en una muestra de spam.
    spam_con_hapax = [*base_spam[:-1], "oferta chollo bicicleta"]
    p_hapax = learning.naive_bayes_spam_prob("bicicleta", spam_con_hapax, base_ham)
    p_frecuente = learning.naive_bayes_spam_prob("chollo", spam_con_hapax, base_ham)
    assert p_hapax is not None and p_frecuente is not None
    assert p_hapax < p_frecuente
    assert p_hapax < 0.75, f"un hapax llegó a {p_hapax}"


def test_evidencia_que_exculpa_no_esta_topada():
    """El tope es asimétrico: acusar cuesta, absolver no.

    Regla número uno del proyecto (mejor un falso negativo que un falso
    positivo): una palabra claramente del vocabulario legítimo debe poder
    tirar la probabilidad hacia abajo sin límite.
    """
    spam = [f"oferta chollo palabra{i}" for i in range(12)]
    ham = [f"revelado analogico en el laboratorio numero {i}" for i in range(12)]
    p = learning.naive_bayes_spam_prob("revelado analogico", spam, ham)
    assert p is not None
    assert p < 0.15, f"la evidencia a favor del usuario quedó topada: {p}"


def test_cosine_texto_corto_exige_similitud_alta():
    """En textos cortos el coseno se infla: ahí exigimos casi calcar el mensaje."""
    muestra = ["hola busco gente para trabajar desde casa escribeme"]
    # Parecido de forma pero inocente y corto → no debe puntuar.
    score, _ = learning.check_against_samples(
        "hola busco gente para jugar escribeme", muestra, [],
    )
    assert score == 0, f"mensaje corto inocente puntuó {score}"
    # Calcado → sigue cazándose aunque sea corto.
    score_calcado, _ = learning.check_against_samples(
        "hola busco gente para trabajar desde casa escribidme", muestra, [],
    )
    assert score_calcado >= 80


def test_defaults_sin_vocabulario_tematico_ajeno():
    """El default en código son palabras funcionales, no el vocabulario de los
    grupos de nadie: quien instale el bot en un grupo de cocina no hereda
    exclusiones de domótica."""
    assert learning._DEFAULT_THEMATIC_TOKENS == []
    assert "que" in learning._STOPWORDS_ES
    assert "the" in learning._STOPWORDS_EN
