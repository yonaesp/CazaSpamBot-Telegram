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
- **No empieces ni termines un patrón con un símbolo** (`$`, `%`, `+`, `/`).
  El bot envuelve la lista en `\b(?:...)\b` y `\b` nunca casa junto a un símbolo:
  el patrón quedaría muerto sin avisar. En vez de `\$\d+\s*/\s*day`, ancla el
  patrón a una palabra: `(?:make|earn)\s+\$\s?\d+`.
- Un patrón **mal escrito no tumba el bot**: se descarta, se avisa en el log
  (`Patrón de lista negra inválido, se ignora: ...`) y el resto siguen activos.

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
| `commercial_cta.txt` | `commercial_ad` | llamadas a la acción publicitarias (postúlate, contáctanos, apply now...) |
| `commercial_work.txt` | `commercial_ad` | vocabulario de oferta de empleo / dinero fácil (vacantes, sueldo, now hiring...) |
| `bio_spam_keywords.txt` | `bio_spam` | spam adulto/cripto/casino/préstamo en la bio del perfil |
| `bio_illegal_services.txt` | `bio_spam` | servicios de hacking/piratería declarados en la bio |
| `bio_cta.txt` | `bio_spam` | llamadas a la acción promocionales en la bio (escríbeme, DM me...) |
| `classifier_excluded_tokens.txt` | clasificador `/spam` `/legal` | (al revés: palabras NEUTRAS de tu temática que se ignoran para no ensuciar el aprendizaje) |

## Listas por idioma

El spam llega en cualquier idioma, así que las listas **se acumulan**:

```
config/blacklist/
├── bio_spam_keywords.txt        <- lista general (se carga SIEMPRE)
├── en/
│   └── bio_spam_keywords.txt    <- se SUMA a la anterior
└── de/
    └── bio_spam_keywords.txt    <- solo si el alemán está activo
```

Se cargan las listas de la carpeta raíz **más** las de:

1. el **idioma activo del bot** (el de `/idioma`), y
2. **inglés** (`en/`), siempre. Es la lengua franca del spam en Telegram:
   ofertas de trabajo falsas, cripto y "recovery experts" llegan en inglés a
   grupos de cualquier idioma, así que un grupo español también los caza.

Los patrones repetidos se descartan (comparando sin distinguir mayúsculas), así
que puedes repetir un término en varias listas sin preocuparte.

### Cargar otros idiomas

Con la variable de entorno `BLACKLIST_LANGS` (CSV) decides tú la lista exacta,
sustituyendo el comportamiento por defecto:

```env
BLACKLIST_LANGS=es,en,pt
```

### Añadir un idioma nuevo

1. Crea la carpeta con el código de dos letras: `config/blacklist/pt/`.
2. Copia dentro los archivos que quieras traducir, **con el mismo nombre**
   (`bio_spam_keywords.txt`, `commercial_work.txt`...). No hace falta crearlos
   todos: los que falten simplemente no aportan nada.
3. Escribe los patrones **de ese idioma** (no repitas los de la lista general).
4. Actívalo con `/idioma pt` o añádelo a `BLACKLIST_LANGS`.
5. Reinicia el bot.

### Al traducir, sé específico

Es la regla número uno del proyecto: **mejor dejar pasar spam que banear a un
legítimo.** Traducir palabra por palabra es la forma más rápida de banear gente.
Palabras sueltas y comunes (`money`, `job`, `free`, `click`, `win`, `salary`)
aparecen a diario en conversaciones normales. Usa **expresiones compuestas**,
cifras con símbolo de moneda y construcciones que solo escribe un anunciante:

| ❌ No | ✅ Sí |
|---|---|
| `job` | `job\s+(?:vacanc(?:y\|ies)\|openings?)` |
| `salary` | `monthly\s+salary`, `salary\s+(?:up\s+to\|range\|of)\s+\$?\s?\d` |
| `money` | `(?:make\|earn)\s+\$\s?\d[\d.,]*` |
| `hiring` | `now\s+hiring`, `(?:we\s+are\|we're)\s+hiring` |
| `work from home` | `work\s+from\s+home\s+(?:job\|opportunit(?:y\|ies))` |

Antes de añadir un patrón, piensa qué mensaje **legítimo** podría dispararlo.
Ante la duda, no lo incluyas. Y añade un caso a `tests/test_wordlists_langs.py`.

## Notas

- Si borras un archivo o lo dejas vacío, el detector usa una lista por defecto
  incluida en el código (el bot nunca se queda sin protección).
- Estos archivos **sí** se versionan en el repo (son genéricos, no sensibles):
  edítalos a tu gusto en tu propia copia.
- Hay más listas configurables por `.env`: acortadores de URL (`URL_BLOCKLIST`)
  y scripts Unicode permitidos (`ALLOWED_SCRIPTS`).
