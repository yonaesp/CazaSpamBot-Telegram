"""Paquetes de idioma en JSON, con autodescubrimiento y carga a prueba de fallos.

CÓMO AÑADIR UN IDIOMA (sin tocar una sola línea de código):
    1. Copia `es.json` a `<código>.json` (p.ej. `fr.json`, `pt.json`, `de.json`).
    2. Traduce los VALORES. No toques las claves ni los {placeholders}.
    3. Reinicia el bot. El idioma aparece solo y ya se puede elegir con /idioma.

POR QUÉ JSON Y NO .py (decidido tras investigarlo, 2026-07):
  - Estabilidad: un módulo Python de idioma se EJECUTA al importarse, así que una
    comilla mal puesta por un traductor (comillas tipográficas al pegar de Word, un
    apóstrofo sin escapar...) reventaba el arranque entero y dejaba el contenedor en
    bucle de reinicio. Con JSON el fallo es DATO, se captura aquí abajo y como mucho
    se pierde ESE idioma: el bot sigue funcionando en español.
  - Seguridad: importar ejecuta código arbitrario. Un archivo de idioma no debe poder
    hacer nada; en este bot el radio de daño incluiría la sesión de Telethon.
  - Herramientas: Weblate, Crowdin y Transifex leen JSON plano de forma nativa; un
    diccionario de Python no lo lee ninguna.

Se descartaron: gettext/.po (la stdlib solo carga .mo BINARIO → haría falta un paso de
compilación, incómodo con el código montado por volumen), YAML (dependencia extra y el
«problema de Noruega»: `no`, el código ISO del noruego, se interpreta como False) y
Fluent / python-i18n (sin mantenimiento).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent
FALLBACK = "es"  # idioma de referencia: siempre debe cargar

STRINGS: dict[str, dict[str, str]] = {}


def _load_one(path: Path) -> dict[str, str] | None:
    """Carga un archivo de idioma. Devuelve None si está roto (nunca lanza)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        # ValueError cubre JSONDecodeError. Un idioma roto NO puede tumbar el bot.
        log.error("Idioma %s ignorado (archivo inválido): %s", path.name, exc)
        return None
    if not isinstance(data, dict):
        log.error("Idioma %s ignorado: el JSON debe ser un objeto {clave: texto}", path.name)
        return None
    # Solo valores de texto: cualquier otra cosa rompería .format() en runtime.
    limpio = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
    if len(limpio) != len(data):
        log.warning("Idioma %s: %d entradas ignoradas por no ser texto",
                    path.name, len(data) - len(limpio))
    return limpio


def _load_all() -> None:
    # El fallback primero: garantiza que la cadena de respaldo existe aunque otro falle.
    for path in sorted(_DIR.glob("*.json"), key=lambda p: (p.stem != FALLBACK, p.stem)):
        data = _load_one(path)
        if data:
            STRINGS[path.stem] = data
    if FALLBACK not in STRINGS:
        log.critical("No se pudo cargar el idioma de referencia (%s.json): los textos "
                     "saldrán como claves crudas.", FALLBACK)


_load_all()

# Idiomas disponibles = archivos encontrados (autodescubrimiento).
AVAILABLE: tuple[str, ...] = tuple(sorted(STRINGS))
