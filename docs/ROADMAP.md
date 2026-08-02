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

### 5. Detector de mensaje duplicado entre chats
**Dificultad**: BAJA.
**Origen**: tg-spam `--duplicates.threshold`.

El mismo texto publicado en varios grupos federados en poco tiempo es spam de
cadena casi por definición, y hoy se le trata como mensajes independientes. Ya
tenemos `learning.text_hash()` y federación: hace falta una tabla
`recent_msgs(hash, user_id, chat_id, ts)` con ventana de una hora.

Señal de una limpieza notable y con muy pocos falsos positivos, porque exige
identidad exacta del texto normalizado. Es lo más rentable que queda por hacer.

### 6. Antiraid: N entradas en M segundos
**Dificultad**: BAJA-MEDIA.

Ventana sobre `seen_users.join_ts`: si entran más de 5 en 30 segundos, subir la
severidad temporalmente en ese chat. Hoy cada entrada se evalúa aislada, así que
una raid coordinada se cuela mientras cada cuenta individual parezca normal.

Cuidado con la acción: un mute global es tentador y castiga a los legítimos que
entraban en ese momento. Mejor endurecer los umbrales durante unos minutos que
cerrar el grupo.

---

## P2. Útil, pero sin urgencia

### 7. Soft-ban (mute permanente en vez de expulsar)
**Dificultad**: BAJA.

Un falso positivo con mute se revierte sin que el usuario se entere; uno con ban
requiere que vuelva a pedir entrar. Encaja con la filosofía del proyecto. El
motivo de que no esté es que el trust score ya degrada `ban` a `mute` en la zona
gris, que era el 80% del beneficio.

### 8. Detector de espaciado anómalo
**Dificultad**: BAJA.
**Origen**: tg-spam `--space.enabled`.

Ratio `espacios/caracteres > 0.4`, o más del 70% de palabras de 2 caracteres o
menos. Caza el «G A N A  D I N E R O» que rompe las blocklists.

Ojo con los falsos positivos: mensajes muy cortos y listas de siglas dan ese
ratio de forma natural. Debería exigir longitud mínima y limitarse a primeros
mensajes.

### 9. Normalizar emojis antes de pasar las blocklists
**Dificultad**: BAJA.

Sustituir emojis por su nombre (`emoji.demojize`) antes de aplicar los patrones,
para cazar el «💰💰 gana 500€ 💰» donde el emoji reemplaza a la palabra clave.
`emoji_only.py` cubre otro caso distinto (el mensaje que es solo emojis), no
este. Añade una dependencia por un beneficio moderado.

### 10. `/report` de miembros con umbral
**Dificultad**: BAJA de código, DUDOSA de diseño.

Que 3 miembros distintos reporten un mensaje en X minutos y eso lo mande a
revisión del admin. Suena bien y es un vector de abuso obvio: tres cuentas
coordinadas mandan a revisión a quien quieran. Solo tiene sentido si el resultado
es *revisión humana* y nunca una acción automática.

### 11. Blocklist de símbolos en el username
**Dificultad**: BAJA.

`_is_obvious_spam_profile` ya mira scripts no latinos en el perfil, pero no
zalgo ni ristras de emojis en el `username`. Hueco pequeño y algo anticuado:
Telegram ya restringe bastante los usernames.

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

*Actualizado: 2026-08-02. 1018 tests en verde, 22 detectores.*
