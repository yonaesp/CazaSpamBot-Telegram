"""Detectores antispam. Cada uno devuelve un Hit con score y razón."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    rule: str
    score: int
    reason: str
    payload: dict | None = None

    @classmethod
    def none(cls) -> "Hit":
        return cls(rule="", score=0, reason="")

    def __bool__(self) -> bool:
        return self.score > 0


def trozo_entidad(texto: str, offset: int, length: int) -> str:
    """Recorta el texto que cubre una entidad de Telegram.

    NO se puede hacer `texto[offset:offset+length]`. Telegram cuenta los
    desplazamientos en unidades UTF-16, y Python en caracteres: cada emoji fuera
    del plano básico (que ocupa DOS unidades UTF-16 y UN carácter de Python)
    desplaza el corte. Y el spam va cargado de emojis justo delante del enlace.

    Efecto real medido: con «▶️▶️▶️ 👀Mira esto https://t.me/+abc» el corte ingenuo
    devolvía `ttps://t.me/+abc`. Con la URL mutilada, las listas negras no casan y
    `resolve_username` no encuentra al usuario: detección perdida en silencio.
    """
    if not texto:
        return ""
    b = texto.encode("utf-16-le")
    return b[offset * 2:(offset + length) * 2].decode("utf-16-le", errors="ignore")
