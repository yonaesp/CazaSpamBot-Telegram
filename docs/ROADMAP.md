# Roadmap

> Estado real del proyecto y qué falta, ordenado por impacto.
> Revisado item por item contra el código el 2026-07-19.
> La lista original (mayo 2026) salía de analizar tg-spam, shieldy, DaisyX y
> MissRose. Buena parte ya está hecha; lo que queda está abajo, sin inflar.

## Ya completado

Lo que sigue estaba en la lista de pendientes y hoy vive en el código. Se deja
anotado para no volver a proponerlo.

| Item original | Dónde vive ahora |
|---|---|
| Sistema de aprendizaje `/spam` `/ham` | `src/learning.py`. Muy por delante de lo planeado: ver `docs/LEARNING.md` |
| Clasificador Bayes + similitud | `src/learning.py`. **Sin sklearn**: char-ngrams y Naive Bayes en stdlib, con topes anti falso positivo. Se descartó sklearn por peso (~50MB) y porque no hacía falta |
| Lookup en lols.bot | `src/detectors/lols_bot.py`. Match = ban directo |
| Normalizador zero-width + NFKC | `learning.normalize()` (NFKC + zero-width + casefold) |
| Forward de canal sospechoso | `src/detectors/forward_first_msg.py`. Distinto de lo planeado: en vez de blocklist de canales concretos, dispara por *forward en los primeros mensajes*, que envejece mejor y no hay que mantener |
| Cleanup agresivo post-ban | `maintenance.aggressive_post_ban_cleanup()`, solo Bot API y verificando el autor antes de borrar |
| Detector de espaciado anómalo (era el 8) | `src/desofuscar.py`. Resuelto **al revés** de como estaba planteado: en vez de puntuar el espaciado, se DESHACE y deciden las reglas de contenido de siempre. Así no hay umbral nuevo que calibrar ni falso positivo que inventar. Medido: 11.560 mensajes reales, 0 tocados |
| Palabras que mezclan alfabetos | `src/desofuscar.py`. **No estaba en la lista y era el agujero más grave**: cambiar UNA letra por su gemela cirílica dejaba `commercial_ad` en 0 (de 75) sin que saltara `unicode_script`, que mide proporción sobre el total |
| Antiraid (era el 6) | `src/antiraid.py`. Resuelto como decía la nota: **no se cierra el grupo ni se silencia a nadie por entrar**, solo se bajan los umbrales unos minutos y **solo a quien llegó con la avalancha**. Umbral calibrado sobre las 881 entradas reales registradas: el máximo histórico en 60 s es 2 |
| Mensaje duplicado entre chats (era el 5) | `src/detectors/cross_post.py`. **No mira el contenido**, así que caza campañas cuyo vocabulario las listas todavía no conocen. Tres chats distintos como mínimo (con dos se equivocaba: quien tiene un problema pregunta en el de Windows 10 y en el de Windows 11) |
| Soft-ban (era el 7) | Columna `chat_settings.soft_ban` (NULL = hereda `SOFT_BAN` del .env) y botón en `/config`. Convierte `ban` en mute permanente, **salvo reglas duras**: a un spammer confirmado por CAS o lols dejarlo dentro mudo es dejarlo dentro |
| Veto por LLM (era el 11) | `src/llm_veto.py`. **Solo puede TUMBAR acciones, nunca crearlas**: en el peor caso deja pasar un spam (el error barato), jamás castiga a alguien legítimo (el caro). Apagado por defecto, solo en la zona gris (70-160), nunca en reglas duras, y cualquier fallo o espera mantiene lo que decidieron las reglas |
| Meta-checks (contacto, solo-emoji, solo-media) | `contact_spam.py`, `emoji_only.py`, `first_msg_media.py`, `inline_buttons.py` |
| Reputation graduation | `src/trust.py` + `src/gentle_warning.py`. Trust 0-100 que degrada, anula o manda a revisión |
| Antiflood por usuario | `flood_state` en `db.py`, graduado por trust (5/8/12 msgs en 10s) |
| `/warn` con escalado | `src/warns_mod.py` + submenú del panel (`/warnlimit`, `/warnaction`) |

Y esto ni siquiera estaba en la lista, pero se hizo:

- **Bilingüe es/en** completo (`src/locales/`, 973 claves por idioma) con
  autodescubrimiento: soltar un `fr.json` basta.
- **Panel visual `/config`** con todos los ajustes por chat, más sincronización
  a todos los grupos. Esto **sustituye al Web UI Flask** que proponía el item
  15: el admin ya modera desde el móvil sin abrir un puerto ni exponer nada.
- **Listas negras por idioma** (`config/blacklist/<lang>/`) y **términos
  editables desde Telegram** con vista previa sobre mensajes reales del grupo
  (`custom_terms.py`).
- **Top semanal** (`topweekly.py`), **detector de canal personal**
  (`personal_channel.py`), **reportes oficiales** vía Telethon con rate limit.

---

## P1. Pendiente de verdad, con impacto

### 1. Los `docs/` se desactualizan solos
**Dificultad**: MEDIA (el problema es de proceso, no de código).

Este mismo documento llevaba dos meses mintiendo, y `LEARNING.md` describía una
implementación con sklearn y TF-IDF que nunca existió. Cualquiera que llegue al
repo y lea los docs se hace una idea falsa del bot, y quien vuelva dentro de seis
meses también.

No hay solución perfecta. Lo que sí es viable: un test que compruebe que las
constantes citadas en los docs (`BAYES_MIN_SAMPLES_PER_CLASS`, umbrales de
score, nombres de las HARD_RULES) coinciden con el código, y falle si alguien
cambia el valor sin tocar el documento. No cubre la prosa, pero sí lo que más se
cita y más engaña cuando está mal.

### 2. `external_mention.py` está atado al español
**Dificultad**: MEDIA.

El detector sube a 130 puntos, que es ban directo, cuando el texto que acompaña
a una mención externa **no parece español** (`lang.likely_spanish()`, que mira
acentos y una lista de stop-words castellanas). Para el grupo del autor funciona;
para cualquier otra instalación es un desastre silencioso: en un grupo inglés,
**todo** el texto legítimo deja de parecer español y cada mención acompañada de
una frase normal se convierte en ban.

Es el único punto del bot donde queda lógica de idioma cableada, y contradice el
trabajo de i18n ya hecho. La corrección natural: sustituir «no parece español»
por «no parece ninguno de los idiomas activos» reusando `active_langs()`, con
listas de stop-words por idioma junto a las locales. Mientras no esté, quien
instale en otro idioma debería bajar ese score.

### 3. Las listas negras de idiomas más allá de es/en están vacías
**Dificultad**: BAJA por línea de código, ALTA por trabajo humano.

`config/blacklist/` tiene el genérico (español) y `en/`. Nada más. La
infraestructura para `pt/`, `fr/` o cualquier otro ya está hecha y probada:
basta con crear el directorio. El problema es que **alguien tiene que escribir
los patrones**, y hacerlo mal es peor que no hacerlo, porque un patrón demasiado
amplio banea legítimos.

Quien instale el bot en portugués hoy arranca con la mitad de los detectores
mudos y no se entera. Como mínimo, el arranque debería avisar de qué listas de
idioma faltan para el idioma activo.

### 4. El clasificador es global, no por chat
**Dificultad**: MEDIA.

`recent_sample_texts()` no filtra por `chat_id`, aunque la columna existe en
`learning_samples` desde el principio. Lo que se aprende en un grupo se aplica a
todos los federados.

Con grupos de temática parecida es una ventaja: se aprende una vez y protege a
todos. Con temáticas dispares es un riesgo real, porque el vocabulario normal de
un grupo puede ser señal de spam en otro, y las salvaguardas del Bayes mitigan
eso pero no lo eliminan. El cambio en sí es pequeño (filtrar por chat con
fallback al corpus global cuando el chat tiene pocas muestras); lo que hay que
pensar bien es el criterio, porque partir el corpus con 36 muestras totales deja
a cada grupo sin nada.

## P2. Útil, pero sin urgencia

### 7. Normalizar emojis antes de pasar las blocklists
**Dificultad**: BAJA.

Sustituir emojis por su nombre (`emoji.demojize`) antes de aplicar los patrones,
para cazar el «💰💰 gana 500€ 💰» donde el emoji reemplaza a la palabra clave.
`emoji_only.py` cubre otro caso distinto (el mensaje que es solo emojis), no
este. Añade una dependencia por un beneficio moderado.

### 8. `/report` de miembros con umbral
**Dificultad**: BAJA de código, DUDOSA de diseño.

Que 3 miembros distintos reporten un mensaje en X minutos y eso lo mande a
revisión del admin. Suena bien y es un vector de abuso obvio: tres cuentas
coordinadas mandan a revisión a quien quieran. Solo tiene sentido si el resultado
es *revisión humana* y nunca una acción automática.

### 9. Blocklist de símbolos en el username
**Dificultad**: BAJA.

`_is_obvious_spam_profile` ya mira scripts no latinos en el perfil, pero no
zalgo ni ristras de emojis en el `username`. Hueco pequeño y algo anticuado:
Telegram ya restringe bastante los usernames.

### 10. Contexto de conversación en los detectores

**Dificultad**: MEDIA. **Origen**: tg-spam (`context window`).

Hoy cada mensaje se juzga solo. Un mensaje inocuo puede ser spam por lo que va
antes o después (el clásico: primero «hola», luego el enlace). Guardar los últimos
N mensajes del usuario y juzgarlos juntos cambiaría bastantes umbrales, así que no
es un cambio pequeño.

---

## Descartado (con motivo)

- **Web UI Flask**: lo cubre el panel `/config` de Telegram, y sin abrir puerto.
- **Captcha de join**: rechazado explícitamente por el usuario.
- **Clasificador DistilBERT / siglip**: ~250MB de modelo más RAM en un N100 que
  ya lleva Home Assistant y ocho webs. La ganancia no compensa el riesgo de OOM.
- **Veto por LLM en la zona gris**: técnicamente viable y barato, pero la zona
  gris ya va a revisión humana por DM, que es más fiable y además genera
  muestras. Un LLM aquí sustituiría un juicio bueno por uno mediocre.
- **Detección NSFW de fotos**: coste de CPU alto, fuera del alcance del antispam.
- **Federación pública entre organizaciones**: vector de envenenamiento evidente.
- **Plugins Lua**: sobredimensionado, Python directo basta.
- **Soporte Postgres**: SQLite WAL sobra de largo para este volumen.
- **Filtro de palabrotas**: antispam no es moderación de lenguaje.

*Actualizado: 2026-08-02. 1273 tests en verde, 25 detectores.*
