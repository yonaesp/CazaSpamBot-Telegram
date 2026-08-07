"""Deshacer los disfraces del texto ANTES de pasarlo por los detectores.

Las listas negras comparan letras. Cambia una letra por otra que se ve igual y la
lista deja de casar, aunque el mensaje siga diciendo exactamente lo mismo. Medido
en este bot antes de escribir esto, con una frase que ya cazaba:

    «Gana 500 euros al dia trabajando desde casa»          commercial_ad = 75
    «Gana 500 eurоs al dia trabajando desde casa»          commercial_ad =  0

La única diferencia es la `о` de «euros», que es CIRÍLICA. Una letra. Y tampoco
saltaba `unicode_script`, porque mide la PROPORCIÓN de caracteres ajenos sobre el
total y una letra de cuarenta y siete no llega ni de lejos al umbral. O sea: el
mensaje se volvía invisible entero.

Lo mismo con el espaciado: «G a n a  5 0 0  e u r o s» no casa con ningún patrón.

Aquí no se decide nada ni se puntúa: se **devuelve el texto sin el disfraz** para
que lo juzguen las reglas de siempre, con sus umbrales de siempre. Es deliberado y
es lo que lo hace seguro: si el mensaje desenmascarado no dice nada punible, no
pasa nada. Quitar el disfraz no puede crear un falso positivo que las reglas no
tuvieran ya.

Dos decisiones que conviene entender antes de tocarlo:

- **Solo se tocan las palabras MEZCLADAS.** Una palabra escrita entera en cirílico,
  griego o árabe es una palabra de ese idioma y se deja intacta; si la
  «tradujéramos» a letras latinas, un grupo ruso vería su conversación convertida
  en galimatías latino que podría casar con cualquier patrón por casualidad. Lo
  que delata al disfraz es la MEZCLA dentro de una misma palabra, que es algo que
  nadie escribe queriendo.
- **La sustitución conserva la longitud** (una letra por una letra). Los
  desplazamientos de las entidades de Telegram se cuentan sobre el texto, así que
  cambiarla rompería los enlaces y las menciones. El desespaciado sí acorta, y por
  eso su texto solo se le da a los detectores que no miran entidades.
"""
from __future__ import annotations

import functools
import logging
import re

log = logging.getLogger(__name__)

try:  # la librería ya es dependencia del proyecto (se usa para los nombres)
    from confusable_homoglyphs import confusables as _confusables  # type: ignore
except Exception:  # noqa: BLE001 - sin ella el módulo simplemente no hace nada
    _confusables = None  # type: ignore

# Trozos de texto que se analizan como «palabra»: letras y dígitos seguidos.
_PALABRA_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Mínimos para dar por bueno que un texto viene con las letras separadas. Altos a
# propósito: escribir «H O L A» para dar énfasis es corriente, y con estos números
# no cuenta. Además, aunque contara, lo único que pasaría es que el mensaje se
# juzgaría por su contenido real.
_MIN_TROZOS_ESPACIADOS = 6
_PROPORCION_SUELTAS = 0.7


def _es_latina(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


@functools.lru_cache(maxsize=4096)
def _homoglifo_latino(ch: str) -> str | None:
    """Letra latina que imita `ch`, o None si no imita ninguna.

    Cacheado porque se pregunta carácter a carácter y el alfabeto útil es pequeño.
    Solo valen los reemplazos de UN carácter: cambiar la longitud del texto
    descuadraría los desplazamientos de las entidades de Telegram.
    """
    if _confusables is None:
        return None
    try:
        info = _confusables.is_confusable(ch, preferred_aliases=["latin"])
    except Exception:  # noqa: BLE001 - dato raro, se deja el carácter como está
        return None
    if not info:
        return None
    for hom in info[0].get("homoglyphs", []):
        cand = hom.get("c") or ""
        if len(cand) == 1 and _es_latina(cand):
            return cand
    return None


def palabras_mezcladas(texto: str) -> list[str]:
    """Palabras que mezclan letras latinas con letras de otro alfabeto.

    Es la firma del disfraz: nadie escribe «eurоs» con la o cirílica sin querer.
    Una palabra entera en otro alfabeto NO cuenta: eso es hablar otro idioma.
    """
    if not texto:
        return []
    fuera: list[str] = []
    for palabra in _PALABRA_RE.findall(texto):
        letras = [c for c in palabra if c.isalpha()]
        if len(letras) < 2:
            continue
        if any(_es_latina(c) for c in letras) and any(not _es_latina(c) for c in letras):
            fuera.append(palabra)
    return fuera


def esqueleto(texto: str) -> str:
    """El texto con los homoglifos devueltos a su letra latina.

    Solo dentro de palabras mezcladas, y conservando la longitud.
    """
    if not texto or _confusables is None:
        return texto
    mezcladas = set(palabras_mezcladas(texto))
    if not mezcladas:
        return texto

    def _arreglar(m: re.Match) -> str:
        palabra = m.group(0)
        if palabra not in mezcladas:
            return palabra
        return "".join(
            (_homoglifo_latino(c) or c) if (c.isalpha() and not _es_latina(c)) else c
            for c in palabra
        )

    return _PALABRA_RE.sub(_arreglar, texto)


def _parece_espaciado(texto: str) -> bool:
    trozos = texto.split()
    if len(trozos) < _MIN_TROZOS_ESPACIADOS:
        return False
    sueltas = sum(1 for t in trozos if len(t) == 1 and not t.isspace())
    return sueltas / len(trozos) >= _PROPORCION_SUELTAS


def desespaciar(texto: str) -> str:
    """«G a n a  5 0 0  e u r o s» → «Gana 500 euros».

    El disfraz usa un espacio entre letras y DOS entre palabras, así que se corta
    por los espacios dobles y se pega cada grupo cuyas piezas sean todas de un
    carácter. Un grupo con piezas largas se deja como está: ahí no hay disfraz que
    deshacer y unirlo solo destrozaría el texto.
    """
    if not texto or not _parece_espaciado(texto):
        return texto
    salida = []
    for grupo in re.split(r"\s{2,}|\n+", texto):
        piezas = grupo.split()
        if len(piezas) >= 2 and all(len(p) == 1 for p in piezas):
            salida.append("".join(piezas))
        else:
            salida.append(grupo)
    return " ".join(s for s in salida if s)


def limpiar(texto: str) -> tuple[str, list[str]]:
    """Texto sin disfraces y lista de los que se han encontrado.

    La lista se usa solo para poder contarlo en el log y en el motivo: quien
    decide sigue siendo la regla de contenido que case con el texto limpio.
    """
    if not texto:
        return texto, []
    trucos: list[str] = []
    limpio = esqueleto(texto)
    hubo_homoglifos = limpio != texto
    sin_espacios = desespaciar(limpio)
    if sin_espacios != limpio:
        trucos.append("espaciado")
        # Segunda pasada: con las letras separadas, cada «palabra» era un carácter
        # suelto y no había mezcla que ver, así que los homoglifos sobrevivían al
        # primer esqueleto. Al juntarlas ya se les ve. Combinar los dos disfraces
        # es justo lo que haría alguien que sabe que le estamos mirando.
        rejuntado = esqueleto(sin_espacios)
        hubo_homoglifos = hubo_homoglifos or rejuntado != sin_espacios
        sin_espacios = rejuntado
    if hubo_homoglifos:
        trucos.insert(0, "homoglifos")
    return sin_espacios, trucos


class MensajeDesofuscado:
    """El mensaje real, pero enseñando el texto ya sin disfraz.

    Mismo patrón que `story_reader.MensajeConTextoDeHistoria`: todo lo demás
    (message_id, chat, from_user...) se delega al mensaje de verdad, porque el bot
    tiene que seguir borrando y respondiendo al mensaje del grupo.

    **Sin entidades a propósito.** El desespaciado acorta el texto y dejaría los
    desplazamientos descuadrados; se lo damos solo a los detectores que miran texto
    plano. Los de enlaces y menciones siguen viendo el mensaje original, que es lo
    correcto: una URL no se puede disfrazar espaciándola, dejaría de ser clicable.
    """

    __slots__ = ("_real", "text", "caption", "entities", "caption_entities")

    def __init__(self, real, texto: str):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "text", texto if getattr(real, "text", None) else None)
        object.__setattr__(self, "caption", None if getattr(real, "text", None) else texto)
        object.__setattr__(self, "entities", [])
        object.__setattr__(self, "caption_entities", [])

    def __getattr__(self, nombre):
        if nombre == "_real":
            raise AttributeError(nombre)
        return getattr(self._real, nombre)


def para_detectores(msg):
    """Devuelve (mensaje_a_usar, trucos). Sin disfraz, devuelve el mismo mensaje."""
    texto = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
    if not texto:
        return msg, []
    limpio, trucos = limpiar(texto)
    if not trucos:
        return msg, []
    return MensajeDesofuscado(msg, limpio), trucos
