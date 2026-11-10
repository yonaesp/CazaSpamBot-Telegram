"""Si el bucle de eventos se queda colgado, salir para que el contenedor se relance (L61).

El healthcheck solo marca el contenedor como `unhealthy`: ni Docker ni Podman
reinician por eso. Un bucle bloqueado (una expresión regular que no termina con un
texto hecho a propósito, una llamada síncrona que no vuelve) dejaba al bot sin
moderar hasta que alguien lo viera. Aquí un hilo aparte mira si el latido del bucle
avanza; si lleva `TICKS_SIN_LATIDO` comprobaciones seguidas parado, vuelca dónde está
cada hilo, deja una marca para contarlo al arrancar y sale con código distinto de
cero: la política `restart: unless-stopped` levanta el proceso (comprobado en Podman
con un contenedor de prueba).

Se cuenta en comprobaciones del propio vigía y no en segundos de reloj a propósito:
si el sistema congela el proceso entero (un cgroup sin memoria), el vigía tampoco
corre, y al descongelarse no hay que matar a un bucle que va a seguir solo.
"""
from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("antispam")

CADA_S = 15.0
# 20 comprobaciones de 15 s = 5 min con el bucle parado. El latido es cada 30 s, así
# que en marcha normal nunca pasan de 2 seguidas, y nada legítimo bloquea el bucle
# más de unos milisegundos (el OCR corre en otro hilo).
TICKS_SIN_LATIDO = 20
CODIGO_SALIDA = 70
MARCA = Path("/app/data/cuelgue.txt")

_latidos = 0
_hilo: threading.Thread | None = None


def latido() -> None:
    """Lo llama el bucle de eventos (el job de latido, cada 30 s)."""
    global _latidos
    _latidos += 1


class Contador:
    """Cuenta comprobaciones seguidas sin latido nuevo."""

    def __init__(self, limite: int = TICKS_SIN_LATIDO) -> None:
        self.limite = limite
        self.parado = 0
        self._visto: int | None = None

    def comprobar(self, latidos: int) -> bool:
        """True si el bucle lleva `limite` comprobaciones seguidas sin latir."""
        if self._visto is None or latidos != self._visto:
            self._visto = latidos
            self.parado = 0
            return False
        self.parado += 1
        return self.parado >= self.limite


def _morir(marca: Path, salir: Callable[[int], None]) -> None:
    log.critical(
        "el bucle de eventos lleva %.0f s sin responder: vuelco los hilos y salgo para que "
        "el contenedor se relance", TICKS_SIN_LATIDO * CADA_S)
    try:
        marca.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass
    try:
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001 — salir importa más que la traza
        pass
    salir(CODIGO_SALIDA)


def _vigilar(marca: Path, cada: float, limite: int, salir: Callable[[int], None],
             dormir: Callable[[float], None]) -> None:
    contador = Contador(limite)
    while True:
        dormir(cada)
        if contador.comprobar(_latidos):
            _morir(marca, salir)
            return


def arrancar(marca: Path = MARCA, cada: float = CADA_S, limite: int = TICKS_SIN_LATIDO,
             salir: Callable[[int], None] = os._exit,
             dormir: Callable[[float], None] = time.sleep) -> threading.Thread:
    """Lanza el hilo vigía (una sola vez). `salir` y `dormir` se inyectan en los tests."""
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return _hilo
    latido()
    _hilo = threading.Thread(target=_vigilar, args=(marca, cada, limite, salir, dormir),
                             name="vigia-cuelgue", daemon=True)
    _hilo.start()
    return _hilo


def cuelgue_anterior(marca: Path = MARCA) -> float | None:
    """La hora del último cuelgue, si lo hubo, y borra la marca: se cuenta una vez."""
    try:
        cuando = float(marca.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        marca.unlink()
    except OSError:
        pass
    return cuando
