# Listas negras personalizables

Las palabras y frases que disparan algunos detectores de spam se editan aquí,
en archivos de texto. **No hace falta tocar el código.** Edita el archivo,
reinicia el bot, y listo.

## Formato

- **Un patrón por línea.**
- Líneas vacías y las que empiezan por `#` se ignoran (comentarios).
- Cada línea puede ser una **palabra suelta** (`casino`) o un **regex**
  (`recuperaci[oó]n\s+de\s+dinero`). No se escapa nada: tienes el poder del regex.
- Si usas paréntesis para agrupar, usa **grupos no capturantes** `(?:...)`,
  nunca `(...)`, porque romperían el conteo interno de coincidencias.
- Las coincidencias son por palabra completa e ignoran mayúsculas/minúsculas.

Ejemplo (`bio_spam_keywords.txt`):

```
# Mis términos extra
chiringuito financiero
inversi[oó]n\s+garantizada
```

## Archivos

| Archivo | Lo usa | Qué detecta |
|---|---|---|
| `commercial_illegal_services.txt` | `commercial_ad` | servicios ilegales en anuncios (hacking, acceso a cuentas, recuperar dinero...) |
| `bio_spam_keywords.txt` | `bio_spam` | spam adulto/cripto/casino/préstamo en la bio del perfil |
| `bio_illegal_services.txt` | `bio_spam` | servicios de hacking/piratería declarados en la bio |
| `classifier_excluded_tokens.txt` | clasificador `/spam` `/legal` | (al revés: palabras NEUTRAS de tu temática que se ignoran para no ensuciar el aprendizaje) |

## Notas

- Si borras un archivo o lo dejas vacío, el detector usa una lista por defecto
  incluida en el código (el bot nunca se queda sin protección).
- Estos archivos **sí** se versionan en el repo (son genéricos, no sensibles):
  edítalos a tu gusto en tu propia copia.
- Hay más listas configurables por `.env`: acortadores de URL (`URL_BLOCKLIST`)
  y scripts Unicode permitidos (`ALLOWED_SCRIPTS`).
