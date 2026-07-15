"""Paquetes de idioma. Añade un módulo por idioma y regístralo en STRINGS."""
from . import en, es

STRINGS = {
    "es": es.STRINGS,
    "en": en.STRINGS,
}
