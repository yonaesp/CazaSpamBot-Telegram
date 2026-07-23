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
  **Excepción:** `commercial_money.txt` y `commercial_money_periodic.txt` se
  cargan **sin** ese envoltorio, justo porque necesitan empezar por símbolo
  (`$500`, `R$`, `/day`). A cambio, cada patrón de esos dos archivos tiene que
  poner sus propios `\b` donde hagan falta (ver los comentarios de cabecera).
- Un patrón **mal escrito no tumba el bot**: se descarta, se avisa en el log
  (`Patrón de lista negra inválido, se ignora: ...`) y el resto siguen activos.

Ejemplo (`bio_spam_keywords.txt`):

```
# Mis términos extra
chiringuito financiero
inversi[oó]n\s+garantizada
```

## Cómo escribir un patrón

Cada línea es un **regex de Python** que se compila **ignorando mayúsculas y
minúsculas** (`re.IGNORECASE`), así que no repitas variantes por el caso: `oferta`
ya caza `OFERTA` y `Oferta`.

Reglas:

- **Agrupa con `(?:...)`, nunca con `(...)`.** Los grupos capturantes rompen el
  conteo interno de coincidencias del detector. `(?:diario|mensual)` sí, `(diario|mensual)` no.
- **La lista se envuelve en `\b(?:...)\b`** (palabra completa), salvo en los
  archivos marcados en la tabla como "sin `\b`" (`commercial_money.txt`,
  `commercial_money_periodic.txt`, `investment_cta.txt` y sus versiones en `en/`),
  donde cada patrón pone sus propios `\b`. Por eso, en las listas normales, **no
  empieces ni termines un patrón con un símbolo** (`$`, `%`, `/`, `@`): `\b` no
  casa junto a un símbolo y el patrón quedaría muerto en silencio.
- **Un patrón mal escrito no tumba el bot:** se descarta, se anota en el log
  (`Patrón de lista negra inválido, se ignora: ...`) y el resto siguen activos.

### El peligro: un patrón demasiado amplio banea gente legítima

Es la **regla número uno del proyecto: un falso positivo es peor que un falso
negativo.** Mejor dejar pasar un spam que expulsar a un usuario real. Un patrón
corto o genérico caza conversación normal. Antes de añadir uno, piensa qué
mensaje **legítimo** podría dispararlo; ante la duda, no lo pongas.

| | Patrón | Por qué |
|---|---|---|
| ✅ | `inversi[oó]n\s+garantizada` | frase compuesta que solo escribe un estafador |
| ✅ | `\b\d+\s*pesos\b` | pegado a una cifra: "20 pesos" es dinero, "el peso del paquete" no |
| ✅ | `(?:make\|earn)\s+\$\s?\d` | verbo + importe: construcción de anuncio, no de charla |
| ❌ | `dinero` | palabra suelta y corriente: cualquiera que hable de dinero suma puntos |

Un patrón compuesto (dos o tres piezas que solo aparecen juntas en un anuncio)
es casi siempre más seguro que una palabra suelta.

## Archivos

| Archivo | Lo usa | Qué detecta |
|---|---|---|
| `commercial_illegal_services.txt` | `commercial_ad` | servicios ilegales en anuncios (hacking, acceso a cuentas, recuperar dinero...) |
| `commercial_cta.txt` | `commercial_ad` | llamadas a la acción publicitarias (postúlate, contáctanos, apply now...) |
| `commercial_work.txt` | `commercial_ad` | vocabulario de oferta de empleo / dinero fácil (vacantes, sueldo, now hiring...) |
| `commercial_money.txt` | `commercial_ad` **y** `bio_spam` | importes con moneda (500€, $500, R$ 2.000, 20000 ARS...). **Aquí añades tu moneda** |
| `commercial_money_periodic.txt` | `commercial_ad` | periodicidad pegada al importe (al mes, /day, mensuales...). No lleva monedas: se combina con la lista de arriba |
| `commercial_urgency.txt` | `commercial_ad` | urgencia gritada de scam (URGENTE, HOY MISMO, act now...) |
| `commercial_domestic.txt` | `commercial_ad` | scam de trabajo doméstico ("busco persona responsable para cuidar mi casa") |
| `investment_praise.txt` | `investment_scam` | elogio a "quien te hace ganar" en el testimonio de estafa ("es de confianza", "changed my life") |
| `investment_cta.txt` | `investment_scam` | llamada a contactar a esa persona ("contáctala", "DM her now", 👇👉📲). **Se carga sin `\b(?:...)\b`** (lleva emojis): pon tú los `\b` en los patrones de texto |
| `investment_vocab.txt` | `investment_scam` | vocabulario de reclutamiento del timo ("inversión garantizada", "guaranteed profit", "passive income") |
| `bio_spam_keywords.txt` | `bio_spam` | spam adulto/cripto/casino/préstamo en la bio del perfil |
| `bio_illegal_services.txt` | `bio_spam` | servicios de hacking/piratería declarados en la bio |
| `bio_cta.txt` | `bio_spam` | llamadas a la acción promocionales en la bio (escríbeme, DM me...) |
| `personal_channel_keywords.txt` | `personal_channel` | vocabulario ilícito en el **título del canal** enlazado en el perfil. **Se carga sin `\b(?:...)\b`** (el chino no separa palabras): pon tú los `\b` en los patrones latinos. No se gestiona desde el panel de Telegram |
| `classifier_excluded_tokens.txt` | clasificador `/spam` `/legal` | (al revés: palabras NEUTRAS de tu temática que se ignoran para no ensuciar el aprendizaje) |

## `classifier_excluded_tokens.txt`: el vocabulario de TU grupo

Esta lista va **al revés** que las demás. En el resto pones lo que quieres
cazar; aquí pones lo que quieres que el bot **ignore al aprender**.

El bot aprende de lo que le marcas con `/spam` y `/legal`. El problema es que
los spammers hablan del tema del grupo: en uno de fotografía venden cámaras, en
uno de coches venden coches. Si marcas varios de esos anuncios con `/spam`, la
palabra del tema (`cámara`, `coche`, `receta`) aparece en muchas muestras de
spam y en ninguna de las legítimas, así que el clasificador aprende que huele a
spam. A partir de ahí, quien entre al grupo y pregunte por su cámara empieza a
sumar puntos hacia un mute.

**Qué hacer:** abre el archivo, borra el vocabulario del autor (domótica y
Windows) y escribe las 10-20 palabras que tu comunidad escribe a diario. Es un
minuto de trabajo y es la protección más barata que tienes.

**Si no lo haces**, el bot no se rompe. El clasificador lleva salvaguardas para
que ninguna palabra suelta pueda decidir por sí sola:

- ninguna palabra puede aportar más de un tope fijo de evidencia hacia spam, así
  que hacen falta **varias** señales juntas (vender + barato + "escríbeme al
  privado") para actuar;
- una palabra que aparece **en las dos clases** (spam y legítimo) pesa la mitad,
  porque no distingue nada;
- una palabra vista **una sola vez** en todo el historial pesa un tercio: es
  ruido, no evidencia;
- el tope es **asimétrico**: limita lo que acusa, no lo que exculpa. Una palabra
  claramente del vocabulario legítimo puede tirar la probabilidad abajo sin
  límite. Es la regla número uno del proyecto: mejor dejar pasar spam que
  castigar a un legítimo.

Aun así, la lista sigue mereciendo la pena: las salvaguardas evitan el desastre,
tu lista evita el ruido.

Un detalle que conviene saber: **lo aprendido es común a todos los grupos** que
modera una misma instalación del bot, no por grupo. Si moderas un grupo de
cocina y otro de coches con el mismo bot, marca en la lista el vocabulario de
los dos.

## `commercial_money.txt`: tu moneda

Un anuncio spam casi siempre promete dinero, así que el importe es una de las
señales que más pesan. El bot trae de fábrica el euro, el dólar, la libra y las
monedas de Latinoamérica y de buena parte de Europa (pesos, reales, soles,
quetzales, bolívares, guaraníes, córdobas, złoty, coronas, francos...). Si la
tuya no está, añádela **aquí** y funcionará también en `bio_spam` y en la
detección de "tanto al mes", sin tocar nada más.

Fíjate en cómo se escribe el importe en tu país: el símbolo puede ir delante
(`$500`) o detrás (`500€`), y los miles se separan con punto, con coma, con
apóstrofo (`1'500`) o con un espacio fino.

### El peligro: monedas que son palabras corrientes

Es la regla número uno del proyecto (**mejor dejar pasar spam que banear a un
legítimo**) y aquí es especialmente fácil pegarse un tiro en el pie, porque
media docena de monedas se llaman como cosas normales:

> «el **peso** del paquete», «esto es **real**», «hace un **sol** increíble»,
> «media **libra** de harina», «la **corona** del diente», «un **franco**
> partidario de...»

Si metes `peso` o `libra` como palabra suelta, el bot empieza a sumar puntos a
gente que habla de recetas o de paquetería. Tres formas seguras de añadirlas:

| ❌ No | ✅ Sí | Por qué |
|---|---|---|
| `peso` | `\b\d+\s*pesos\b` | pegada a una cifra: «20 pesos» es dinero, «el peso del paquete» no |
| `libra` | `£`, `GBP`, `libras\s+esterlinas` | el símbolo y el código no son ambiguos; el nombre en compuesto tampoco |
| `corona` | `coronas\s+(?:suecas\|noruegas\|danesas)` | el compuesto solo lo escribe quien habla de dinero |

Y ojo también con los **códigos ISO**: en minúscula, `try`, `cup`, `cop`, `pen`,
`bob` y `ron` son palabras normales en inglés o en español. Por eso en la lista
van dentro de `(?-i:...)`, que **apaga el ignorar-mayúsculas solo en ese trozo**:
«2 cup of flour» no dispara, «2 CUP» sí. Si añades un código nuevo, mételo en
ese mismo grupo y déjalo pegado a una cifra.

Añade siempre un caso a `tests/test_money_regional.py`: uno de que tu moneda se
reconoce, y otro de una frase legítima de tu idioma que **no** debe disparar.

## `custom/`: los términos que añade el bot

La carpeta `config/blacklist/custom/` **la gestiona el bot**. Ahí van los
términos que el admin añade desde Telegram, sin entrar al servidor. Se cargan
**sumándose** a la lista genérica y a las de idioma, con la misma mecánica.

```
config/blacklist/
├── commercial_work.txt        ← del repo, se versiona
├── en/commercial_work.txt     ← del repo, se versiona
└── custom/commercial_work.txt ← lo escribe el bot, NO se versiona
```

Va **fuera de git** (está en `.gitignore`) por un motivo práctico: si
estuviera versionada, cada `git pull` daría conflictos con los archivos del
repo o directamente pisaría lo que haya añadido el admin.

Diferencias con el resto de listas:

- **Son texto literal, no regex.** Se escapan con `re.escape()` al cargarlas,
  así que `oferta 100% garantizada` funciona tal cual: los `%`, `.`, `(` o `*`
  valen como los símbolos que son, no como sintaxis de regex. Es imposible
  colar un patrón activo por aquí, y eso vale **también si editas el archivo a
  mano**: escribir `.*` en una línea busca un punto seguido de un asterisco.
- Si quieres un regex de verdad, ponlo en la lista normal del repo.
- El bot valida lo que entra: mínimo 4 caracteres (uno de 2 letras casaría con
  media conversación), máximo 300 términos por lista, sin duplicados, y nada
  que empiece o acabe en símbolo en las listas que usan `\b(?:...)\b`.
- Antes de guardar, el bot enseña una **vista previa**: cuántos mensajes
  recientes de verdad del grupo cazaría ese término. Si tu «oferta» pilla a 12
  vecinos legítimos, lo ves antes de banear a nadie, no después.
- **No hace falta reiniciar**: los cambios se aplican al instante.

Puedes editar los archivos a mano si prefieres (uno por línea, UTF-8, `#` para
comentar). Las líneas vacías, la basura y los caracteres raros se ignoran sin
tumbar nada.

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
