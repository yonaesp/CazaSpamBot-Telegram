"""Segunda opinión de un modelo, y SOLO para tumbar acciones. Nunca para crearlas.

La idea viene de `tg-spam` (umputun), que puede consultar a un modelo en dos modos.
El interesante es el segundo: en modo **veto** el modelo no acusa a nadie, solo se
le pregunta por lo que las reglas YA han marcado, y si dice que aquello no es spam
se anula la acción.

Por qué solo ese modo, y no el de acusar:

- Encaja con la primera regla del proyecto (falsos positivos > falsos negativos).
  Un veto solo puede **reducir** castigos, así que en el peor de los casos deja
  pasar un spam, que es el error barato. Si el modelo acusara, un fallo suyo se
  convertiría en un ban a alguien legítimo, que es el error caro.
- Deja el bot funcionando igual sin él. La decisión la siguen tomando las reglas
  deterministas de siempre; esto es una capa de seguridad encima, no un detector.

## Lo que hace que esto sea seguro de tener en producción

- **Apagado por defecto** y desactivable al instante (`LLM_VETO=false`). Sin clave
  de API tampoco se activa, aunque esté puesto a true.
- **Solo en la zona gris.** No se pregunta por las reglas duras (CAS, lols, ban
  federado, destino confeso del enlace): ahí no hay duda que resolver. Y solo si
  la puntuación está en la franja borderline, que es donde el bot puede
  equivocarse. Un spam de 230 puntos no se consulta.
- **A prueba de fallos hacia la decisión existente.** Si no hay respuesta, si
  tarda, si el JSON viene raro o si la API devuelve un error, NO se veta: se hace
  lo que decían las reglas. El silencio nunca perdona.
- **Tope de tiempo duro.** Los updates se procesan de uno en uno, así que una
  espera aquí congela el bot entero. Mismo criterio que `story_reader` y
  `link_reader`.
- **Se cuenta en el registro.** Un veto queda anotado en `moderation_log` con el
  motivo que dio el modelo, para que se pueda auditar si empieza a perdonar cosas
  que no debería.

Lo que NO se le manda: nada de la base de datos, ni el historial del usuario, ni
identificadores. Solo el texto del mensaje que ya iba a ser castigado y el nombre
de las reglas que saltaron.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

# Franja de puntuación en la que se pregunta. Por debajo la acción es leve y no
# merece la consulta; por encima la evidencia es abrumadora y preguntar solo
# añadiría una vía para equivocarse.
MIN_SCORE = 70
MAX_SCORE = 160

# Tope duro. Los updates se procesan de uno en uno: pasado esto, se sigue sin veto.
TIMEOUT_S = 8.0

# Cuánto texto del mensaje se manda. De sobra para juzgar y acotado para no
# depender de la longitud de lo que escriba un spammer.
MAX_CHARS = 1500

_SISTEMA = (
    "Eres el segundo par de ojos de un bot antispam de Telegram. El bot ya ha "
    "marcado este mensaje y va a castigar a quien lo escribió.\n\n"
    "Tu ÚNICO trabajo es evitar una injusticia: responde 'legitimo' solo si estás "
    "seguro de que quien escribió esto es una persona normal participando en el "
    "grupo, y de que castigarla sería un error claro.\n\n"
    "Ante cualquier duda responde 'spam'. No estás aquí para cazar spam (de eso ya "
    "se encargan las reglas), sino para frenar los errores evidentes.\n\n"
    "Responde SOLO con una de estas dos palabras en la primera línea: legitimo | spam\n"
    "En la segunda línea, máximo diez palabras explicando por qué."
)


def activo(cfg) -> bool:
    """¿Está configurado y encendido? Sin clave no se activa aunque esté a true."""
    return bool(getattr(cfg, "llm_veto", False)) and bool(os.getenv("ANTHROPIC_API_KEY"))


def procede_preguntar(accion: str, score: int, reglas, hard_rules) -> bool:
    """¿Es este uno de los casos dudosos en los que merece la pena preguntar?"""
    if accion not in ("ban", "kick"):
        return False                       # una acción leve no justifica la consulta
    if any(r in hard_rules for r in reglas):
        return False                       # evidencia externa: no hay duda que resolver
    return MIN_SCORE <= score <= MAX_SCORE


async def veta(cfg, texto: str, reglas, chat_titulo: str | None = None) -> tuple[bool, str]:
    """(vetar, motivo). `vetar=True` significa: NO castigues a esta persona.

    Cualquier problema devuelve (False, ...): el silencio nunca perdona.
    """
    if not texto or not texto.strip():
        return False, ""                   # sin texto no hay nada que juzgar
    try:
        return await asyncio.wait_for(_preguntar(cfg, texto, reglas, chat_titulo), TIMEOUT_S)
    except asyncio.TimeoutError:
        log.info("llm_veto: se agotó el tiempo; se mantiene la decisión de las reglas")
        return False, ""
    except Exception as exc:  # noqa: BLE001 — jamás puede tumbar la moderación
        log.info("llm_veto: fallo (%s); se mantiene la decisión de las reglas", exc)
        return False, ""


async def _preguntar(cfg, texto: str, reglas, chat_titulo: str | None) -> tuple[bool, str]:
    try:
        from anthropic import AsyncAnthropic
    except Exception:  # noqa: BLE001 — dependencia opcional
        log.info("llm_veto: falta el paquete `anthropic`; se sigue sin veto")
        return False, ""

    cliente = AsyncAnthropic()             # lee ANTHROPIC_API_KEY del entorno
    pregunta = (
        f"Grupo: {chat_titulo or 'un grupo de Telegram'}\n"
        f"Reglas que han saltado: {', '.join(reglas) or '?'}\n\n"
        f"Mensaje:\n---\n{texto[:MAX_CHARS]}\n---"
    )
    respuesta = await cliente.messages.create(
        model=getattr(cfg, "llm_veto_model", "claude-opus-5"),
        max_tokens=64,
        system=_SISTEMA,
        messages=[{"role": "user", "content": pregunta}],
    )
    # Una negativa del modelo por seguridad NO es un veto: sin respuesta útil, se
    # mantiene lo que decían las reglas.
    if getattr(respuesta, "stop_reason", None) == "refusal":
        log.info("llm_veto: el modelo declinó responder; se mantiene la decisión")
        return False, ""

    salida = "".join(b.text for b in respuesta.content if getattr(b, "type", None) == "text")
    lineas = [ln.strip() for ln in salida.strip().splitlines() if ln.strip()]
    if not lineas:
        return False, ""
    veredicto = lineas[0].lower()
    motivo = lineas[1][:120] if len(lineas) > 1 else ""
    # Se exige la palabra exacta. Cualquier otra cosa (un "no estoy seguro", una
    # frase larga) se trata como «no vetar»: solo un sí rotundo perdona.
    if veredicto.startswith("legitimo") or veredicto.startswith("legítimo"):
        return True, motivo
    return False, motivo
