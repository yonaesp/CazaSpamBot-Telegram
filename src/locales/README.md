# Paquetes de idioma / Language packs

Todos los textos que ve el usuario viven aquí, en un JSON por idioma.
**No hace falta tocar ni una línea de código para añadir un idioma nuevo.**

*All user-facing text lives here, one JSON per language. Adding a language requires no code changes.*

---

## Añadir un idioma / Adding a language

1. Copia `es.json` (referencia) o `en.json` a `<código>.json`, con el código ISO 639-1
   de 2 letras: `fr.json`, `pt.json`, `de.json`, `it.json`, `ru.json`...
2. Traduce **solo los valores** (la parte a la derecha de los `:`).
3. Reinicia el bot. El idioma aparece solo y ya se puede elegir con `/idioma <código>`.

```bash
cp src/locales/es.json src/locales/fr.json
# traducir los valores...
docker compose restart
```

No hace falta traducirlo entero: **lo que falte cae automáticamente al español**, así que
un idioma al 40 % ya es útil y se puede ir completando poco a poco.

---

## Reglas al traducir

| Regla | Por qué |
|---|---|
| **No cambies las claves** (`"warn.usage"`) | Es como el código encuentra el texto. |
| **No cambies los `{placeholders}`** | `{n}`, `{name}`, `{chat}`... los rellena el bot. Si escribes `{nombre}` en vez de `{name}`, el texto sale sin sustituir. |
| **Cierra todas las etiquetas HTML** | Telegram rechaza el mensaje **entero** si el HTML está mal cerrado. Un `<b>` sin `</b>` puede hacer que un aviso de ban se pierda en silencio. |
| **Solo `<b> <i> <u> <s> <code> <pre> <a>`** | Es lo único que acepta Telegram en `parse_mode="HTML"`. |
| **`{{` y `}}` son llaves literales** | `{{name}}` se muestra como `{name}` (se usa en las plantillas de bienvenida). |
| **Guarda en UTF-8** | Los acentos y emojis dependen de ello. |

### Comprueba tu traducción antes de enviarla

```bash
.venv/bin/python -m pytest tests/test_locales.py -q
```

Verifica automáticamente, para **todos** los idiomas: que el JSON es válido, que los
placeholders coinciden con los del español y que el HTML está balanceado. La cobertura
incompleta **no** hace fallar los tests, solo se informa del porcentaje.

---

## Si te equivocas, el bot no se cae

Un archivo de idioma roto (JSON inválido, mal codificado) se **ignora con un aviso en el
log** y el bot sigue funcionando en español. Es la razón principal de usar JSON en lugar
de módulos Python: un archivo de datos no puede tumbar el arranque.

```
[ERROR] Idioma fr.json ignorado (archivo inválido): Expecting ',' delimiter: line 12
```

---

## Para desarrolladores: añadir textos nuevos

1. Añade la clave a **`es.json` y `en.json`** (los dos idiomas oficiales; el test
   `test_paridad_total_es_en` falla si uno se queda atrás).
2. Úsala con `t("mi.clave", nombre=x)`.
3. El selector de idioma de `t()` se llama `_lang` con guion bajo **a propósito**: así
   nunca choca con un placeholder que se llame `lang`.
4. Agrupa la clave por temas, junto a las de su misma zona del archivo. El orden se
   conserva para que traducir sea legible.

Textos **opcionales y desactivados por defecto** (los quips de humor de las bienvenidas)
no están aquí: son contenido editable por el administrador, no interfaz del bot.
