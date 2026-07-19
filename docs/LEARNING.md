# Sistema de aprendizaje del bot

> Cómo el bot aprende de las decisiones del admin. Código: `src/learning.py`.

## Filosofía

Los detectores estáticos (blocklists, unicode, CAS, lols.bot) cubren el spam
conocido. El aprendizaje cubre el otro: el que se adapta al grupo concreto.
Cada vez que el admin marca un mensaje, esa decisión queda como muestra y un
detector posterior la usa para comparar.

La regla número uno del proyecto manda también aquí: **mejor dejar pasar spam
que castigar a un legítimo**. Todo lo que sigue está construido en esa
dirección, y por eso el clasificador es deliberadamente tímido.

## Cómo se etiqueta

| Comando | Qué hace |
|---|---|
| `/spam` (en reply) | Combo completo de máxima confianza: guarda la muestra como `spam`, banea al autor en toda la federación, reporta a Telegram por Telethon, borra el mensaje y publica el quip. Es una orden humana, no una detección |
| `/legal` (en reply, alias `/ham`) | Guarda la muestra como `ham`. **Solo aprende**: no revierte nada ni suprime reglas |
| `/notspam <action_id>` | Revierte un ban ya ejecutado y suprime esa regla para ese usuario durante 7 días |
| Botones ✅Legítimo / ❌Spam del DM de revisión | Guardan muestra `ham` o `spam` y resuelven el caso. Es la vía por la que más muestras entran sin esfuerzo |
| `/samples` / `/samples spam 20` | Recuento por clase, o listado con el `id` de cada muestra |
| `/forget <id>` | Borra una muestra mal etiquetada |

El texto debe tener al menos 5 caracteres para guardarse. Se normaliza antes y
se deduplica: el índice único `(text_hash, label)` impide que el mismo texto
entre dos veces con la misma etiqueta.

## Normalización y almacenamiento

```python
def normalize(text):          # NFKC + strip zero-width + casefold
def text_hash(text_norm):     # blake2b de 8 bytes, solo para deduplicar
```

Cierra las evasiones baratas: caracteres de ancho cero, homoglifos, mayúsculas.

```sql
CREATE TABLE learning_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_norm TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('spam','ham')),
    added_by INTEGER NOT NULL,
    chat_id INTEGER, source_user INTEGER, ts REAL NOT NULL
);
CREATE UNIQUE INDEX idx_samples_hash_label ON learning_samples(text_hash, label);
```

Vive en `data/antispam.db`. **Incluye `data/` en tus backups**: ahí está todo
lo aprendido, y no se puede reconstruir.

## Dos motores: coseno y Bayes

En cada mensaje se cargan las muestras de los últimos 90 días (máximo 200 por
clase) y se evalúan dos cosas distintas.

### 1. Similitud coseno sobre char-ngrams

Implementación en stdlib, sin sklearn ni TF-IDF: `Counter` de ngramas de 3 a 5
caracteres con los límites de palabra marcados, y coseno sobre las frecuencias
crudas. Es barato, funciona en cualquier idioma y aguanta las erratas y los
adornos con los que un spammer varía su plantilla.

Responde a una pregunta concreta: **¿este mensaje es una variante de algo que ya
marqué?** Para eso es muy bueno. Para reconocer spam nuevo no sirve.

Los textos de menos de 10 caracteres se descartan de entrada, tanto la consulta
como las muestras.

### 2. Naive Bayes multinomial

Bolsa de palabras con suavizado de Laplace, trabajando en log-odds y cerrando
con una sigmoide. Responde a otra pregunta: **¿el vocabulario de este mensaje se
parece globalmente al del spam más que al del resto?**

Exige `BAYES_MIN_SAMPLES_PER_CLASS = 10` muestras de **cada** clase. Por debajo
devuelve `None` y no aporta nada.

> **Dato de la instalación del autor: 36 muestras spam y 0 de ham.** El Bayes
> está dormido y todo el trabajo lo hace el coseno. No es un fallo, es lo
> normal: el admin marca spam a diario y casi nunca se acuerda de marcar lo
> legítimo. Si quieres que el Bayes despierte, la palanca es usar `/legal`, no
> tocar umbrales.

## Las salvaguardas (lo importante de este documento)

Un Bayes sin frenos aprende el vocabulario del grupo y lo confunde con spam. El
escenario no es hipotético: **en un grupo de fotografía basta con que varios
spammers vendan cámaras para que «cámara» pase a ser señal de spam**, y a partir
de ahí el bot castiga a quien pregunte por la suya. El clasificador acabaría
moderando el tema del grupo en vez del spam. Tres frenos lo evitan:

| Constante | Valor | Por qué |
|---|---|---|
| `BAYES_MAX_TOKEN_LOGRATIO` | `1.1` (~3:1 de odds) | Tope al peso de UN token suelto. Sin él, una palabra que sale en 10 spams y en ningún ham decide ella sola el veredicto. Con tope hacen falta **varias** palabras sospechosas para pasar el umbral, que es justo lo que separa un anuncio de una pregunta normal |
| `BAYES_SHARED_TOKEN_FACTOR` | `0.5` | Un token que aparece en las dos clases no separa nada: pesa la mitad. Es exactamente el caso de «cámara» en el grupo de fotografía |
| `BAYES_RARE_TOKEN_FACTOR` | `0.34` (si aparece 1 sola vez) | Un token visto una única vez en todo el corpus es ruido: pudo entrar de rebote en una muestra. No se descarta, porque con corpus pequeños casi todo es hapax y el clasificador se quedaría mudo, pero pesa un tercio |

**El tope es asimétrico a propósito.** Solo se aplica a la evidencia que acusa.
La que exculpa, el token que empuja hacia ham, pasa entera y sin recortar. Para
acusar exigimos varias señales; para absolver, con una basta.

### Tokens neutros: dónde acaba el código y empieza el admin

Antes de contar se descartan los tokens que no distinguen nada. Hay dos fuentes
y la separación es deliberada:

- **En código**: palabras funcionales del español y del inglés (`que`, `para`,
  `hola`, `the`, `you`, `thanks`...). Valen para cualquier comunidad, sea de
  cocina, fotografía o domótica, así que las pone el bot.
- **En `config/blacklist/classifier_excluded_tokens.txt`**: el vocabulario
  temático de TU grupo, una palabra por línea. Aquí **no hay defaults en
  código** a propósito. El vocabulario de un grupo solo lo conoce su admin, y
  meter el de otra comunidad no ayuda a nadie: la lista de un grupo de fotografía
  es ruido en uno de domótica.

Si el archivo no existe no se excluye nada más allá de las palabras funcionales.

### Guarda de longitud en el coseno

`COSINE_MEDIUM_MIN_CHARS = 40`. El coseno de char-ngrams se infla en textos
cortos: comparten pocos ngramas en total, así que unos pocos en común disparan
el porcentaje.

Caso medido con una sola muestra de spam («hola busco gente para trabajar desde
casa escribeme»): el mensaje inocente «hola busco gente para jugar escribeme»
daba 0.67 y se llevaba un mute. Por debajo de 40 caracteres se exige similitud
alta (>0.8), que ya es prácticamente calcar el mensaje.

## Cómo se combina todo (`check_against_samples`)

| Condición | Score |
|---|---|
| Coseno spam >0.8 **y** Bayes >0.8 | `100` |
| Coseno spam >0.8 | `80` |
| Coseno spam >0.6 **y** texto ≥40 chars | `60` |
| Bayes >0.85 | `50` |
| Coseno ham >0.5 | `-30` |
| Bayes <0.2 | `-20` |

Los positivos entran al pipeline como regla `learned_similarity`; los negativos
como `learned_negative`, que **resta** al score acumulado por otros detectores.
Esa resta es tan importante como la suma: es lo que permite que un mensaje que
se parece a algo ya aprobado cancele un falso positivo de otro detector.

## Interacción con el trust score

**`learned_similarity` NO es HARD_RULE.** Las HARD_RULES son solo `cas_match`,
`lols_match`, `federation_known_ban` y `reaction_farming`. La consecuencia es la
red de seguridad más importante del sistema:

- **trust ≥70**: la acción se anula. Un veterano del grupo **nunca** será baneado
  por el clasificador, por muy alto que puntúe.
- **trust 40-69** con acción severa: no se actúa, se manda a revisión al DM del
  admin con botones. Y la respuesta vuelve a entrar como muestra, así que el
  caso dudoso alimenta el clasificador en lugar de romperlo.
- **trust 40-69** con acción leve: se degrada o se anula.

**El riesgo se concentra en los usuarios nuevos**, que es donde el trust es bajo
y donde el clasificador manda de verdad. Es una elección: un recién llegado
puede llevarse un falso positivo, pero un miembro establecido está protegido.

`learned_similarity` sí está en `_REPORTABLE_RULES`, pero solo genera reporte
oficial a Telegram si el score combinado llega a 150, nunca por sí sola.

## Limitaciones conocidas

- **El clasificador es global, no por chat.** Lo que se aprende en un grupo se
  aplica a todos los federados. Con grupos de temática parecida va bien; con
  temáticas dispares, el vocabulario de uno contamina al otro.
- **Solo caza lo parecido a algo ya etiquetado.** El spam de plantilla nueva lo
  tienen que coger los detectores estáticos.
- **Una mala etiqueta envenena.** Si marcas como spam algo legítimo, se queda.
  Corrígelo con `/forget <id>`, y usa `/samples spam 20` para ver los `id`.
- **Sin muestras de ham no hay Bayes**, y tampoco hay señal negativa que cancele
  falsos positivos. Marcar legítimos con `/legal` es la mitad del trabajo que
  casi nadie hace.

*Actualizado: 2026-07-19.*
