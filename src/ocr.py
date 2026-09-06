"""Leer el texto que va DENTRO de una imagen.

Un cartel publicitario es, para el bot, un mensaje vacío: ningún detector de
contenido tiene nada que mirar. Caso que lo motivó (6-sep-2026, Windows 11): una
imagen ofreciendo «INSTALACIÓN Y ACTIVACIÓN DE SOFTWARE — Windows, Office,
Photoshop, AutoCAD (todas las versiones) — ESCRÍBEME POR INTERNO», sin una sola
letra en el mensaje. Con el texto extraído puntúa 105 y cae; sin él, nada.

## Por qué Tesseract y no otra cosa

Medido sobre esa imagen (168 KB): **0,61 s** y sin GPU. EasyOCR y PaddleOCR son
más precisos con fotos difíciles, pero arrastran PyTorch u ONNX, cientos de megas
y mucha más RAM, y aquí el texto es grande y con contraste: el caso más fácil que
existe para un OCR.

El volumen tampoco lo justifica: en este despliegue hay **2 primeros mensajes al
día**, así que aunque todos llevaran foto serían **~1 segundo de CPU diario**.

## Lo que hace que sea seguro tenerlo en producción

- **No decide nada.** Solo aporta texto; los detectores de siempre lo juzgan con
  sus mismos umbrales. Una foto de un ordenador sin letras da texto vacío o ruido
  y puntúa 0, exactamente igual que antes.
- **Corre en un hilo aparte** (`run_in_executor`). PTB procesa los updates de uno
  en uno: 0,61 s bloqueando el bucle son 0,61 s sin moderar nada más.
- **Tope duro de tiempo.** Una imagen enorme o retorcida no puede colgar el bot.
- **Sin Tesseract instalado, el bot funciona igual**: se registra una vez y no se
  vuelve a intentar. Es una mejora opcional, no una dependencia dura.
- **Solo donde importa**: primeros mensajes con imagen, que es donde llega este
  spam. No se pasa OCR a cada foto del grupo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile

log = logging.getLogger(__name__)

# Tope por imagen. Medido: 0,61 s en el caso real; con 8 s cabe una imagen mucho
# mayor sin que un caso patológico llegue a notarse.
TIMEOUT_S = 8.0

# Imágenes más grandes que esto no se leen: una foto de móvil normal no llega, y
# descargar y procesar algo enorme en la ruta de moderación no compensa.
MAX_BYTES = 5 * 1024 * 1024

# Códigos de idioma de Tesseract, que NO son los de dos letras del bot.
_TESS = {
    "es": "spa", "en": "eng", "pt": "por", "fr": "fra", "de": "deu", "it": "ita",
    "ru": "rus", "uk": "ukr", "ar": "ara", "zh": "chi_sim", "ja": "jpn",
    "ko": "kor", "tr": "tur", "pl": "pol", "nl": "nld", "ro": "ron",
}


def idiomas() -> str:
    """Idiomas del OCR, derivados de los que ya usa el bot para sus listas.

    Se reutiliza `wordlists.active_langs()` (idioma activo + inglés, o lo que diga
    `BLACKLIST_LANGS`) en vez de tener una lista aparte: si alguien modera una
    comunidad en portugués y añade `pt` a sus listas negras, no tiene sentido que
    el OCR siga leyendo solo en español.

    Se filtran los que Tesseract no tenga instalados: pedirle un idioma que le
    falta hace que falle la llamada ENTERA y no lea nada, ni siquiera en los
    idiomas que sí tiene. `OCR_LANGS` lo sustituye por completo para quien quiera
    fijarlo a mano (formato de Tesseract: `spa+eng`).
    """
    fijado = (os.getenv("OCR_LANGS") or "").strip()
    if fijado:
        return fijado
    try:
        from .wordlists import active_langs
        quiere = [_TESS.get(c) for c in active_langs()]
    except Exception:  # noqa: BLE001
        quiere = ["spa", "eng"]
    hay = _instalados()
    usables = [c for c in quiere if c and (not hay or c in hay)]
    return "+".join(dict.fromkeys(usables)) or "eng"


def _instalados() -> set:
    """Idiomas que Tesseract tiene de verdad. Vacío si no se puede saber."""
    global _IDIOMAS_INSTALADOS
    if _IDIOMAS_INSTALADOS is None:
        try:
            r = subprocess.run(["tesseract", "--list-langs"],
                               capture_output=True, timeout=10, text=True)
            _IDIOMAS_INSTALADOS = {
                ln.strip() for ln in r.stdout.splitlines()[1:] if ln.strip()}
        except (OSError, subprocess.SubprocessError):
            _IDIOMAS_INSTALADOS = set()
    return _IDIOMAS_INSTALADOS


_IDIOMAS_INSTALADOS: set | None = None

# Menos de esto es ruido de bordes y logos, no un texto que juzgar.
MIN_CARACTERES = 12

_disponible: bool | None = None


def disponible() -> bool:
    """¿Está Tesseract en el sistema? Se comprueba una vez y se recuerda."""
    global _disponible
    if _disponible is None:
        _disponible = shutil.which("tesseract") is not None
        if not _disponible:
            log.info("OCR: tesseract no está instalado; las imágenes no se leen")
    return _disponible


def _leer_sincrono(datos: bytes) -> str:
    """Ejecuta Tesseract sobre los bytes de la imagen. Corre en un hilo."""
    with tempfile.TemporaryDirectory() as tmp:
        entrada = os.path.join(tmp, "img")
        with open(entrada, "wb") as f:
            f.write(datos)
        salida = os.path.join(tmp, "out")
        try:
            subprocess.run(
                ["tesseract", entrada, salida, "-l", idiomas(), "--psm", "6"],
                capture_output=True, timeout=TIMEOUT_S, check=False,
            )
            with open(salida + ".txt", encoding="utf-8", errors="replace") as f:
                return f.read()
        except (subprocess.TimeoutExpired, OSError) as exc:
            log.info("OCR: no se pudo leer la imagen (%s)", exc)
            return ""


async def leer(datos: bytes) -> str:
    """Texto de la imagen, o cadena vacía. Nunca lanza.

    Vacío significa «no hay texto que juzgar», y quien llama debe tratarlo como
    ausencia de información: jamás como «la imagen está limpia».
    """
    if not datos or len(datos) > MAX_BYTES or not disponible():
        return ""
    try:
        bucle = asyncio.get_running_loop()
        texto = await asyncio.wait_for(
            bucle.run_in_executor(None, _leer_sincrono, datos), TIMEOUT_S + 2)
    except asyncio.TimeoutError:
        log.info("OCR: se agotó el tiempo leyendo una imagen")
        return ""
    except Exception as exc:  # noqa: BLE001 — jamás puede tumbar la moderación
        log.info("OCR: fallo inesperado (%s)", exc)
        return ""
    limpio = " ".join(texto.split())
    return limpio if len(limpio) >= MIN_CARACTERES else ""
