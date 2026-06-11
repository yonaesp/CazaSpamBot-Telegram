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
