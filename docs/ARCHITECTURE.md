# Arquitectura de CazaSpamBot

> Última actualización: 2026-07-19. Documento vivo: actualizar tras cada cambio
> arquitectónico relevante. Este doc es la **fuente de verdad técnica** para futuras
> sesiones de Claude Code: leerlo ANTES de proponer rediseños.
>
> Aquí se explica **cómo está montado y por qué se decidió así**. El uso está en los
> README; las reglas de estilo y las convenciones de trabajo, en `CLAUDE.md`. No se
> duplica ninguno de los dos.

## Índice

Es largo a propósito: recoge el porqué de cada decisión, que es lo que se pierde
cuando solo queda el código. No hace falta leerlo entero, salta a lo que toques.

| | Sección | Cuándo leerla |
|---|---|---|
| 1 | [Visión general](#1-visión-general) | primera vez que tocas el proyecto |
| 2 | [Decisiones de diseño registradas](#2-decisiones-de-diseño-registradas) | **antes de proponer un rediseño** |
| 3 | [Mapa de módulos](#3-mapa-de-módulos) | para ubicar dónde vive algo |
| 4 | [Flujo de un join](#4-flujo-de-un-join-on_chat_member) | tocas verificación o detección de perfil |
| 5 | [Flujo de un mensaje](#5-flujo-de-un-mensaje-on_message) | tocas detectores, trust o scoring |
| 6 | [`_apply_action`](#6-_apply_action) | tocas bans, kicks o reportes |
| 7 | [Datos](#7-datos) | añades una columna o una tabla |
| 8 | [i18n](#8-i18n) | añades cualquier texto que vea el usuario |
| 9 | [Configuración por chat](#9-configuración-por-chat) | añades un ajuste o un botón al panel |

## 1. Visión general

Bot de moderación antispam para Telegram, multi-grupo y federado, en producción 24/7.

- **18.117 líneas** en `src/` (68 módulos), **11.016** en `tests/` (91 ficheros, 1296 tests).
- **25 detectores**, tres capas de listas negras, clasificador propio, panel de ajustes
  por chat, i18n con autodescubrimiento de idiomas.
- Un solo proceso Python, una sola base SQLite, un contenedor Docker.

La forma más corta de entender el diseño es esta: **el bot decide con señales baratas y
locales, y solo escala a lo caro cuando hace falta**. Bot API para todo, MTProto solo
para lo que la Bot API no puede ver. SQLite en vez de servidor de base de datos. Regex y
Naive Bayes en vez de LLM. Nada de esto es por ahorro: es porque cada dependencia externa
es un modo de fallo nuevo, y un bot de moderación caído deja el grupo indefenso sin que
nadie se entere.

### Stack

| Pieza | Versión | Papel |
|---|---|---|
| Python | 3.11 | |
| `python-telegram-bot[ext]` | 22.8 | Bot API async, polling |
| `telethon` | 1.44.0 | MTProto, solo para lo que la Bot API no expone |
| `aiohttp` | 3.10.10 | consultas a CAS y lols.bot, notificaciones externas |
| `confusable-homoglyphs` | 3.3.1 | UTS#39, anti falso positivo en nombres decorativos |
| `python-dotenv` | 1.0.1 | carga del `.env` |
| SQLite (stdlib) | WAL | `data/antispam.db`, fichero único |
| Docker | | contenedor `cazaspam-bot` |

Las 10 dependencias van pineadas con `==`. `pytest`, `pytest-asyncio` y `ruff` se instalan
también en la imagen de producción: no hay `requirements-dev.txt` separado.

## 2. Decisiones de diseño registradas

Las que condicionan todo lo demás. Antes de proponer cambiar alguna, leer el porqué.

**Falsos positivos por encima de falsos negativos.** Es la regla número uno y explica la
mitad del código. Banear a un usuario legítimo cuesta la confianza del grupo y es
irreversible en la práctica; dejar pasar un spam cuesta un mensaje. De ahí salen el trust
score, los topes asimétricos del Bayes, los bypass por antigüedad de cuenta y la
insistencia en tests negativos.

**SQLite y no Postgres.** El volumen no lo justifica y una base externa añade un servicio
que puede caer, una credencial que rotar y un backup que olvidar. WAL con un solo escritor
sobra para este perfil de carga.

**Docker y no systemd.** Portabilidad: el proyecto es público y debe arrancar en cualquier
sitio con un `docker compose up`.

**Federación interna, no inter-organizacional.** Abrir la lista de baneos a terceros es un
vector de envenenamiento: cualquiera que consiga escribir en la federación puede banear a
quien quiera en todos los grupos a la vez. La lista `banned_users` es local y la fuente de
verdad es este bot.

**Sin captcha de join por defecto.** Rechazado por fricción. El bot arranca en "modo
limpio": verificación y bienvenida apagadas, y solo la revisión de sospechosos por privado
encendida. Quien quiera más lo activa desde `/config`.

**Sin LLM por defecto.** Coste por mensaje, latencia y dependencia externa en el camino
crítico de moderación.

**`MODE=shadow` es el default.** Una instalación recién clonada no banea a nadie: registra
en `moderation_log` lo que habría hecho. Pasar a `active` es explícito (`./ctl.sh active`).
Es fail-safe deliberado: el error de configuración más probable es arrancar el bot antes de
haberlo calibrado.

**Cuenta secundaria para Telethon.** La sesión MTProto vive en `data/telethon.session`. Si
se filtra, el radio de daño es una cuenta desechable, no la cuenta personal del admin.

**El quip es cosmético y jamás bloquea un ban.** `quips.quips_on()` cae al `.env` ante
cualquier excepción. Ninguna función decorativa puede impedir una acción de moderación.

## 3. Mapa de módulos

### Núcleo

| Módulo | Líneas | Responsabilidad |
|---|---|---|
| `main.py` | 410 | Entry point: registro de handlers, `post_init`/`post_shutdown`, jobs, error handler global |
| `config.py` | 232 | Carga del `.env` en un `@dataclass(frozen=True) Config` de 50 campos. 46 variables de entorno |
| `db.py` | 1359 | SQLite: 21 tablas, todo el CRUD, migraciones, cálculo del trust score |
| `handlers.py` | 2177 | Los dos caminos críticos (`on_message`, `on_chat_member`) más `_apply_action`, antiflood y reacciones |
| `scoring.py` | 58 | `decide()`: combina hits en una `Decision` con umbrales |
| `federation.py` | 62 | `federate_ban()`: itera los chats donde el bot es admin aplicando `banChatMember` |

### Detección

| Módulo | Responsabilidad |
|---|---|
| `detectors/` | 21 ficheros, uno por regla. Cada `check()` devuelve un `Hit(rule, score, reason, payload)` |
| `verification.py` | Flujo de entrada: perfil sospechoso, botón SOY HUMANO, bienvenida, `cleanup_job` |
| `user_signals.py` | Lector de perfil vía MTProto: fotos, bio, premium, canal personal |
| `trust.py` | Presentación: convierte scores internos a niveles 1-10 para el admin. **No calcula el trust** |
| `learning.py` | Naive Bayes + coseno sobre las muestras marcadas con `/spam` y `/legal` |
| `wordlists.py` | Carga y compilación de las tres capas de listas negras |
| `rule_explain.py` | Inventario canónico de reglas (36) y su explicación traducible |

### Configuración y panel

| Módulo | Responsabilidad |
|---|---|
| `config_panel.py` | Panel `/config`: 12 pantallas, 28 acciones de callback |
| `settings_sync.py` | Modo sync: propaga un ajuste a todos los grupos moderados |
| `chat_settings_cmd.py` | Los mismos ajustes por comando (`/welcome`, `/rules`, `/verificacion`...) |
| `custom_terms.py` | Alta y baja de términos desde Telegram, con validación y vista previa |
| `chat_picker.py` | Selector de grupo para comandos ejecutados por DM |
| `notify_prefs.py` | Qué avisos quiere recibir el admin |

### Salida y servicios

| Módulo | Responsabilidad |
|---|---|
| `i18n.py` + `locales/` | `t()`, `variant_keys()`, autodescubrimiento de idiomas |
| `quips.py` | Frases de humor al banear, catálogo en los paquetes de idioma |
| `ban_announce.py` | Publicación del quip en el grupo con autoborrado |
| `notifier.py` | Aviso al admin, opcionalmente vía un segundo bot |
| `reporter.py` | Cola async + worker Telethon para reportes oficiales a Telegram |
| `telethon_bridge.py` | Listener `MessageDeleted` para borrar avisos en cascada |
| `admin.py` | Comandos de admin (1238 líneas) |
| `warns_mod.py`, `topweekly.py`, `group_clean.py`, `admin_report.py`, `gentle_warning.py`, `greetings.py`, `maintenance.py`, `scan_cmd.py`, `lang_cmd.py`, `permissions.py` | Funciones acotadas, ver docstring de cada uno |

## 4. Flujo de un join (`on_chat_member`)

El camino más delicado del bot: aquí se decide sobre alguien de quien no se sabe nada. El
orden importa y cada paso corta el flujo con un `return` al actuar.

```
join
 │
 ├─ ¿es realmente un join?          _is_join()             si no → return
 ├─ record_join(cmu.date)           hora del EVENTO, no de proceso
 │
 ├─ 1. federación                   db.is_banned()         → ban, score 999
 ├─ 2. ¿es un bot?                  user.is_bot            → kick + aviso al admin
 │
 ├─ 3. trust precalculado           rejoin_trust >= 70 ────────────┐
 │                                                                 │ (veterano:
 │   ┌── MUTE PROVISIONAL ──────────────────────────────┐          │  salta todo,
 │   │  4. obvious_spam_profile   (≥2 campos no latinos)│          │  nunca se
 │   │  5. bio_spam               (Telethon)            │          │  le mutea)
 │   │  6. personal_channel_spam  (Telethon)            │          │
 │   │  7. photos_batch_upload    (Telethon)            │          │
 │   └───────────────────────────────────────────────────┘          │
 │                                                                 │
 ├─ 8. lols.bot                     trust >= 90 → revisión humana  │
 ├─ 9. CAS                          offenses >= 2 → ban            │
 │                                  offenses == 1 → log, sigue     │
 └─ 10. verification.on_join() ◄────────────────────────────────────┘
```

**El mute provisional es la pieza no obvia.** Entre el join y el veredicto pasan varios
segundos: bio y fotos por MTProto, CAS y lols.bot por red. Sin mute, el spammer escribe
antes de que el bot termine de mirarle el perfil y el botón SOY HUMANO llega tarde. Se
mutea primero y se pregunta después.

Ese mute solo se deshace dentro de `verification.on_join`. De ahí dos consecuencias que hay
que respetar al tocar este código:

1. **Los cuatro detectores de perfil van envueltos en `try/except` amplios.** Una excepción
   que escape de `on_chat_member` deja al usuario **muteado para siempre** y sin fila en
   `pending_verifications`, es decir invisible para el `cleanup_job`, que se apoya en esa
   tabla. Lo mismo vale para el `.format()` de la bienvenida en `verification.py:768`: una
   llave rara en el texto que escribió el admin (`{algo}`, `{}`, `:-{`) lanzaría, y el
   resultado sería idéntico.
2. **En modo shadow no se mutea.** `verification.on_join` retorna temprano en shadow sin
   desmutear, así que mutear ahí dejaría al usuario mudo indefinidamente.

**`join_ts` guarda `cmu.date`, la hora del evento de Telegram, no `time.time()`.** Si el bot
procesa el join con retraso (backlog tras un reinicio), usar la hora de proceso inflaría la
rapidez aparente del primer mensaje y `jfm_delta` dispararía un falso positivo. Es un bug
real, documentado en el código como "caso Yorscluni".

**El trust protege antes de mirar las listas externas.** Un veterano con trust ≥ 90 que
aparece en lols.bot o en CAS no se autobanea: se manda a revisión humana. Las listas
externas fallan, y quien lleva un año escribiendo en el grupo merece el beneficio de la duda.

### `verification.on_join`

Tres modos, en este orden:

1. **Revisión de sospechosos** (default ON): el usuario entra sin fricción, y el admin
   recibe un privado con el perfil y botones Permitir / Banear.
2. **Modo limpio** (verificación OFF, el default): desmutea y, si la bienvenida está
   activada, saluda.
3. **Verificación completa**: mute definitivo, mensaje con botón SOY HUMANO, fila en
   `pending_verifications` y borrado programado del mensaje de bienvenida.

Antes del modo 3 hay un atajo: `_is_very_legit_profile` deja pasar sin verificar a quien
tiene un perfil claramente asentado.

## 5. Flujo de un mensaje (`on_message`)

```
mensaje
 │
 ├─ A. GUARDS       sender_chat → moderación de canal · chat no moderado → return
 │                  bot externo → rama propia · via_bot → rama propia
 │
 ├─ B. REGISTRO     whitelist / admin → solo contar y return
 │                  dormant_bot_mention (usa el last_msg_ts ANTERIOR)
 │                  record_message → msg_count → is_first
 │
 ├─ C. PRE          antiflood · saludo amistoso · mención a @admin → return
 │                  learning.normalize(text)   NFKC + strip zero-width + casefold
 │
 ├─ D. DETECTORES   14 sobre el mensaje, en orden fijo, acumulando hits
 │                  unicode_script · external_mention · url_blocklist · tg_deeplink
 │                  premium_new_link* · jfm_delta* · inline_buttons · contact_spam
 │                  external_reply · commercial_ad · emoji_only · forward_first_msg
 │                  first_msg_media* · learned_similarity
 │                  (* condicionados a primer mensaje o a Telethon)
 │
 ├─ E. FILTRADO     hits vacíos → return · supresiones del admin → return
 │                  solo reglas borderline + usuario de confianza → aviso suave
 │                  decide(hits) → Decision(action, score, rule, reason)
 │
 ├─ F. TRUST        (salvo HARD_RULES)
 │                    40-69 + ban/kick  → revisión al admin, return
 │                    >= 70             → no se actúa, PERO aviso al admin por
│                                        privado con botones Nada/Avisar/Banear
│                                        (regla admin_trust_notice, silenciable
│                                        desde /alertas como trust_skip)
 │                    40-69 + leve      → degrada (ban→mute, mute→noop)
 │                    < 40              → acción intacta
 │
 └─ G. _apply_action()
```

### El trust score

Se calcula en `db.user_trust_score()`, escala 0-100:

| Factor | Peso |
|---|---|
| Whitelist explícita | devuelve 100 y corta |
| Mensajes vistos | `min(msg_count * 1.0, 40)` |
| Días en el grupo | `min(days * 1.5, 30)` |
| Cuenta con más de 30 días vista | +20 |
| El bot presenció el join | +10 |
| Warns activos | `-min(warns * 10, 40)` |

Un usuario nunca visto puntúa 0. El máximo sin whitelist es exactamente 100.

`trust.py` **no calcula nada de esto**: solo convierte scores a niveles 1-10 con emoji para
enseñárselos al admin sin revelar el número crudo (hay test que lo verifica).

### `HARD_RULES`

```python
HARD_RULES = {"cas_match", "lols_match", "federation_known_ban", "reaction_farming"}
```

Definida **dentro de la función** en `handlers.py:1001`, no a nivel de módulo. Si alguna
regla disparada pertenece al conjunto, todo el bloque de degradación por trust se salta. Son
las señales que no admiten interpretación: una lista externa confirmada, un ban federado ya
decidido, o el patrón de granja de reacciones (cero mensajes y cinco reacciones en un
minuto), que no tiene lectura inocente por veterano que sea el usuario.

`learned_similarity` **no** está en el conjunto, a propósito: el clasificador aprende del
grupo y puede equivocarse, así que el trust lo modera. El riesgo se concentra en usuarios
nuevos, que es donde importa.

### `scoring.decide()`

```python
decide(hits, ban_score, kick_score, mute_score,
       first_msg_attack_action, is_first_msg_attack) -> Decision
```

Suma aritmética simple de los scores de los hits con `score > 0`, y cascada de umbrales:
`>= 100` ban, `>= 70` kick, `>= 40` mute, **por debajo `noop`**.

Ese último tramo era `delete` y se cambió a `noop` deliberadamente: `jfm_fast` puntúa 30 y
estaba borrando mensajes inocentes de gente que simplemente escribió rápido tras entrar.

Detalle a tener presente: `Hit.__bool__` es `score > 0`, así que los hits negativos que emite
el clasificador (`learned_negative`, -30 y -20) quedan filtrados antes de sumar y **nunca
restan**. Si algún día se quiere que resten, hay que tocar `combine()`, no el detector.

El override `first_msg_attack_action` se evalúa **antes** que los umbrales y por tanto ignora
el score por completo. Solo se activa con `non_allowed_script` o `external_mention_or_link`
en el primer mensaje.

### Antiflood

Ventana de 60 segundos, umbral graduado por confianza sobre `FLOOD_MAX_MSGS` (6):

| Situación | Umbral |
|---|---|
| El admin confirmó que es humano | 12 |
| Trust ≥ 70 | 10 |
| Resto | 6 |

Al disparar: mute de 6 horas, aviso público con autoborrado a la hora, y botones al admin
(No es bot / Es bot) **solo la primera vez**. Las reincidencias se re-mutean en silencio. Hay
guarda anti doble disparo: no se actúa dos veces sobre la misma clave en menos de 60 segundos.

## 6. `_apply_action`

Punto único por el que pasa toda acción de moderación. Orden exacto:

1. **Guarda de admin**: si el objetivo es admin del chat, la decisión se reescribe a `noop`.
   En shadow esta guarda no corre.
2. **Persistencia**: `db.log_action()` siempre, incluso para `noop` y en shadow. Nunca se
   borra un mensaje sin haberlo guardado antes.
3. **Limpieza de verificación huérfana**: si el usuario tenía una bienvenida y una fila
   pendiente, se borran. Sin esto queda basura visible en el grupo.
4. **Reporte oficial a Telegram**, ANTES del ban (después ya no habría mensaje que reportar).
5. **Ban primero, borrado después.** El orden está optimizado contra la ventana de carrera del
   spammer: banear corta el flujo aguas arriba en Telegram, y los mensajes en vuelo dejan de
   propagarse. Copiar al DM del admin y borrar el original van después.
6. **Cleanup retrospectivo** de la ráfaga, en una tarea aparte.
7. **Quip público** si está activado y la acción es ban o kick.
8. **Notificación al admin**, enriquecida con señales de perfil si hay Telethon.

**Contrato del modo shadow**: persiste y notifica exactamente igual, marcando `[SHADOW]`,
pero no ejecuta ban/kick/mute/delete, no reporta, no limpia pendientes y no publica quip. La
federación se simula solo para poder contar en la notificación cuántos chats se verían
afectados. Notificar en shadow es deliberado: lo útil al calibrar es ver los "habría baneado"
en Telegram, no en `docker logs`.

### Reportes oficiales (`reporter.py`)

CAS no acepta envíos. La única vía de contribuir a un sistema antispam global es el Native
Antispam de Telegram, vía MTProto. Estrategia en tres pasos: `channels.reportSpam` (preferida,
requiere ser admin del supergrupo), `messages.report`, `account.reportPeer`.

Los reportes van **deliberadamente restringidos**: whitelist de 12 reglas, score mínimo 150
(salvo `cas_match`, `lols_match` y `federation_known_ban`, que lo bypassean), y límites de 20
por hora y 100 por día. Reportar de más quema la reputación de la cuenta secundaria como
reporter, y una cuenta quemada no sirve para nada. Las reglas con posibilidad de falso
positivo (`url_blocklist`, mención suelta, script suelto) están fuera de la whitelist.

## 7. Datos

Una sola conexión SQLite compartida por el proceso, en autocommit:

```python
sqlite3.connect(path, check_same_thread=False, isolation_level=None)
row_factory = sqlite3.Row
PRAGMA journal_mode=WAL; synchronous=NORMAL; foreign_keys=ON;
```

No hay `Lock`. El modelo de concurrencia es "WAL más un solo escritor", y ese único escritor
es el handler async. Es una invariante que sostiene la arquitectura, no el código: si algún
día se introduce un segundo hilo escritor, hay que revisarlo.

No se configura `busy_timeout`, así que rige el default de la stdlib (5 segundos). Importa
porque `maintenance` ejecuta `VACUUM`, que pide lock exclusivo.

### Tablas (21)

| Tabla | Para qué |
|---|---|
| `bot_chats` | Chats donde está el bot y con qué permisos. Auto-discovery |
| `seen_users` | Perfil por (chat, usuario): contadores, reputación, último mensaje. Base del trust |
| `banned_users` | Federación: baneados con razón, regla, chat de origen y `revoked_at` |
| `moderation_log` | Auditoría completa, incluido shadow. Se conserva íntegra |
| `learning_samples` | Corpus de entrenamiento. Se conserva íntegro. Índice único `(hash, label)` |
| `chat_settings` | Ajustes por chat (ver sección 9) |
| `pending_verifications` | Cola de verificación de entrantes |
| `reaction_events` | Reacciones, ventana para `reaction_farming` |
| `cas_cache` | Caché del lookup a CAS |
| `username_map` | `username_lower` a `user_id` |
| `suppressions` | Reglas silenciadas por usuario tras un "no era spam" del admin |
| `user_warns` | Avisos estilo Rose |
| `welcome_buttons` | Botones de bienvenida |
| `gentle_warnings` | Avisos suaves, ligados al mensaje original para borrado en cascada |
| `weekly_msg_log` | Log ligero para el top semanal |
| `friendly_greeters` | Usuarios que reciben reacción amistosa automática |
| `admin_reports` | Reportes de usuarios mencionando a @admin |
| `flood_state` | Estado antiflood: mutes acumulados, "confirmado humano" |
| `admin_ban_events` | Baneos manuales de otros admins, para detección de abuso |
| `bot_prefs` / `bot_text_prefs` | Preferencias globales de runtime (incluido `config_sync` y el idioma) |

Dos índices llevan su justificación en el propio esquema. `idx_seen_lastmsg` documenta el
coste medido de no tenerlo: 2,7 ms por lookup, 271 ms de event loop bloqueado al limpiar 100
mensajes. En un bot async eso es una eternidad.

### Migraciones

Introspección más `ALTER TABLE` condicional, sin tabla de versiones ni números de revisión:

```python
cols = {r[1] for r in conn.execute("PRAGMA table_info(chat_settings)")}
if "welcome_delete_after_s" not in cols:
    conn.execute("ALTER TABLE chat_settings ADD COLUMN ...")
```

Se ejecuta en cada arranque, después de `executescript(SCHEMA)`. El orden importa:
`CREATE TABLE IF NOT EXISTS` no añade columnas a tablas que ya existen, así que `_migrate()`
es lo único que cierra ese hueco. Es idempotente por construcción: en una base al día no
ejecuta ni un `ALTER`. No hay `try/except`: el error se evita comprobando antes, no capturando
después.

Alguna migración toca **datos** además de esquema, y lo hace con cuidado: al cambiar los
tiempos de verificación por defecto, solo se reescriben las filas que aún tenían el default
antiguo exacto, para no pisar configuraciones a medida.

**Cuidado con una divergencia real**: `verification_reminder_hours` nace con default 3 en el
esquema y 6 en el `ALTER`, y `verification_review_suspicious` con 1 en el esquema y 0 en el
`ALTER`. Por eso `ensure_chat_settings()` fija esos valores a mano en el `INSERT OR IGNORE` en
vez de confiar en los defaults: una base antigua migrada y una base nueva no coincidirían.

### Limpieza nocturna

`maintenance.cleanup_nightly_job`, cada 24 horas. Retenciones: 30 días para
`reaction_events`, `cas_cache`, verificaciones muertas y reportes sin resolver; 14 días para
`weekly_msg_log`; 7 días para `admin_ban_events`, verificaciones ya cumplidas y reportes
resueltos; 24 horas para `gentle_warnings`. `moderation_log` y `learning_samples` no se tocan
nunca.

`VACUUM` solo si se borraron más de 1000 filas, y envuelto en `try/except` por un bug ya
sufrido: pedía lock exclusivo, fallaba con "database is locked" si había una lectura abierta,
y la excepción abortaba el job entero, de modo que **la reconciliación no llegaba a correr esa
noche**.

### Reconciliación de baneos

Si un admin desbanea a alguien manualmente en Telegram, el bot no se entera y su
`banned_users` seguiría disparando `federation_known_ban` al reentrar. El job consulta
`get_chat_member` para los baneados de los últimos 30 días y revoca los que ya no lo están.

La pieza que hace correcto ese job es el flag `lookup_ok`: si **ninguna** consulta respondió
(red caída, error de Telegram, flood-wait, el bot perdió admin), un fallo es indistinguible de
"no está baneado". Revocar ahí borraría un ban real y el spammer volvería a entrar sin que
nadie lo re-banease. Ante la duda no se toca y se reintenta al día siguiente.

## 8. i18n

Todo el texto que ve el usuario vive en `src/locales/<código>.json`. Hoy `es.json` y
`en.json` con **973 claves cada uno y paridad total** (0 claves exclusivas en ninguno de los dos).

### Por qué JSON y no módulos `.py`

Un `.py` **se ejecuta al importarse**. Una comilla mal puesta por un traductor tumbaba el
arranque y dejaba el contenedor en bucle de reinicio. Además el radio de daño de un fichero
ejecutable aportado por terceros incluye la sesión de Telethon. Y como beneficio colateral,
Weblate, Crowdin y Transifex leen JSON de forma nativa.

Se descartaron: gettext (la stdlib solo carga `.mo` binario, ilegible en un PR), YAML (el
"problema de Noruega": `no` se parsea como `False`) y Fluent o `python-i18n` (sin
mantenimiento).

### Autodescubrimiento

Los idiomas soportados son literalmente los ficheros `*.json` que hay en el directorio. Soltar
un `fr.json` basta para que `/idioma fr` funcione, cero cambios de código. La carga ordena el
fallback (`es`) el primero a propósito, para garantizar que la cadena de respaldo existe aunque
otro idioma reviente.

### A prueba de fallos

`_load_one()` nunca lanza. Un JSON inválido se ignora con un `log.error` y el bot sigue con el
resto. Un fichero que no sea un objeto plano se descarta. Los valores que no sean texto se
filtran uno a uno, porque romperían `.format()` en runtime. Si faltase incluso el fallback, se
loguea `CRITICAL` y los textos salen como claves crudas, pero **el bot arranca**.

### `t()` y sus dos trampas

```python
def t(key: str, _lang: str | None = None, **fmt) -> str
```

**El selector se llama `_lang` con guion bajo a propósito.** Con el nombre `lang`, una llamada
como `t("lang.set", lang=x)` enlazaba `x` al selector en vez de a `**fmt`, `.format()` no
llegaba a ejecutarse y el usuario veía `{lang}` literal. Sin excepción ni log.

**`t()` devuelve la propia clave si no existe.** Es útil (lo pendiente de traducir se ve en
pantalla) y peligroso: `explain(x) or respaldo` nunca cae al respaldo, porque `"rule.xxx"` es
una cadena no vacía. Ese bug llegó a producción y por eso `rule_explain.explain()` lleva doble
guarda. **Nunca usar el resultado de `t()` en un `or` sin comprobar antes que no es la clave.**

El fallback es **por clave, no por fichero**: cada clave que falte cae individualmente al
español, así que un idioma al 40 % ya es usable.

### Frases alternativas

Los textos que el bot alterna al azar viven como claves numeradas `prefix.1`, `prefix.2`... y
**cada idioma puede tener su propio número**. Se recorre desde 1 y se para en el primer hueco.

Se leen del paquete **directamente, sin el fallback de `t()`**, y esa es la razón de que exista
`variant_keys()` en vez de un bucle sobre `t()`: un idioma con 3 frases donde el español tiene
17 acabaría colando castellano de la cuarta en adelante, y el grupo vería el catálogo mezclado.
El fallback es todo o nada por categoría.

Consecuencia operativa: **un índice saltado deja inalcanzables las frases posteriores**. Si
existen `.1`, `.2` y `.4`, la `.4` no sale nunca.

`quips._phrases()` implementa el mismo algoritmo pero devuelve textos y **sí puede devolver
lista vacía**, en cuyo caso el ban es silencioso. `i18n.variant_keys()` nunca devuelve vacío,
porque `random.choice([])` lanzaría `IndexError` en mitad de un ban.

### Nombres de comando traducibles

Viven en `group_clean.py`, no en `i18n.py`. Seis comandos tienen nombre traducible
(`comandos/commands`, `legal/ham`, `limpieza/cleanup`, `idioma/language`,
`verificacion/verification`, `alertas/alerts`) sobre un menú de 33 entradas.

Cada nombre se valida contra `^[a-z0-9_]{1,32}$` **antes** de publicarlo: Telegram rechaza
`setMyCommands` entero si un solo nombre trae mayúsculas, acentos o espacios, y el bot se
queda **sin menú**. También se deduplica, porque un nombre repetido tiene el mismo efecto.

Detalle elegante: para los comandos sin traducción, `t()` devuelve la clave cruda
`cmd.name.<x>`, que lleva puntos y por tanto no pasa la validación, cayendo sola al nombre por
defecto. No hace falta ningún caso especial.

**Los nombres en español siempre deben seguir funcionando**, pase lo que pase con los alias.

## 9. Configuración por chat

Dos superficies sobre el mismo almacén: el panel visual `/config` y los comandos sueltos. Los
dos escriben en `chat_settings` y los dos pasan por `settings_sync`.

### Modo sync

Preferencia global `config_sync` en `bot_prefs`, **ON por defecto** (un `None` sin escribir se
lee como `True`, así que una instalación nueva ya sincroniza). Con sync ON, cualquier cambio se
escribe en todos los grupos donde el bot es admin y el panel no pide grupo. Con sync OFF, el
panel pregunta a qué grupo aplicar.

`target_ids()` lleva un `or [chat_id]` que es el fallback importante: si la lista de moderados
sale vacía (bot recién añadido, `bot_chats` aún sin poblar), el ajuste no se pierde.

Regla de arquitectura: **todo el que escriba un ajuste debe pasar por `apply_setting()` o
`apply_welcome()`**, nunca por `db.update_chat_setting()` directo. Es disciplina, no hay nada
que lo impida técnicamente.

Los botones de bienvenida son el caso especial: sus ids son autoincrementales globales, así que
"el mismo botón" en otro grupo tiene otro id. Con sync ON el gemelo se identifica por texto más
URL, que es lo que el admin ve y lo que se replicó al crearlo.

La edición de textos libres (bienvenida y reglas) **ignora el modo sync y pregunta siempre** el
alcance. Escribir un texto largo es caro y pisarlo en todos los grupos por descuido lo es más.

### El patrón NULL igual a "hereda del `.env`"

`quips_enabled` es hoy la única columna con esta semántica, y el patrón es de aplicación
general para cualquier ajuste nuevo que ya existiera en el `.env`.

Si la columna naciera con `DEFAULT 0`, quien tuviera los quips activados por `.env` se quedaría
sin ellos al actualizar, **en silencio y sin haberlo pedido**. Con `DEFAULT NULL`, NULL
significa "nadie ha opinado, mira el `.env`", y en cuanto el admin toca el botón el chat deja
de heredar.

La resolución vive en `quips.quips_on()` y cae al `.env` por tres caminos: excepción al leer,
chat sin fila de settings, o valor NULL.

El panel tiene su propia trampa aquí y está resuelta: `_quips_state()` delega en `quips_on()` en
vez de leer la columna con el helper genérico. Con el helper genérico el panel enseñaría OFF a
quien tiene los quips funcionando desde siempre por `.env`, y **el admin pulsaría el botón
creyendo activarlos cuando en realidad los estaría apagando**.

### El límite de 64 bytes del `callback_data`

Telegram impone 64 **bytes** al `callback_data` de un botón inline. En el panel de términos los
datos los escribe un humano: un término largo, con acentos o con emojis se pasa de largo él
solo. Así que **el término nunca viaja dentro del callback**. Dos indirecciones:

- **La lista, por índice** sobre la tupla cerrada `custom_terms.MANAGEABLE_LISTS`. Beneficio
  colateral de seguridad: es la única puerta por la que un nombre de fichero entra desde
  Telegram, y al ser un índice sobre una tupla fija no hay forma de colar una ruta arbitraria.
- **El término, por hash corto** de 8 caracteres, que se resuelve contra la lista viva al
  recibirlo. Se eligió hash y no índice porque **los botones ya enviados sobreviven a cambios de
  la lista**: con un índice, borrar el primer término y luego pulsar un botón viejo borraría el
  término equivocado. El hash o encuentra el suyo o no encuentra ninguno.

El callback más largo del panel es ASCII fijo y ronda los 47 bytes. Al añadir acciones nuevas,
contar bytes.

Prefijos registrados: `cfg:`, `pick:`, `verify:`, `prev:`, `flood:`, `abuse:`, `susrev:`,
`npref:`, `twk:`, `clean:`.

## 10. Detección y listas

### Los 25 detectores

Cada `check()` devuelve un `Hit(rule, score, reason, payload)`. Agrupados por lo que miran:

**Perfil y cuenta** (los cuatro primeros solo en el join): `obvious_spam_profile` (200),
`bio_spam` (60-200), `personal_channel_spam` (100-200), `photos_batch_upload` (100),
`premium_new_link` (80), `dormant_bot_mention` (120).

**Contenido**: `commercial_ad` (60+), `inline_buttons` (90), `external_mention_or_link` (40-130),
`url_blocklist` (25-60), `tg_deeplink` (50-90), `non_allowed_script` (30-100), `contact_spam`
(80-90), `external_reply` (35-80), `emoji_only` (45-60), `forward_first_msg` (70-100),
`first_msg_media` (70-140), `learned_similarity` (50-100).

**Comportamiento**: `jfm_delta` (30-80), `reaction_farming` (100).

**Listas externas**: `cas_match` (100), `lols_match` (100).

Más las reglas que no vienen de `detectors/`: `federation_known_ban` (999), `manual_admin_ban`
(200), `flood_confirmed_bot` (200), `antiflood`, `warns_limit`, `via_bot_spam` y los timeouts de
verificación. El inventario canónico son las 40 entradas de `rule_explain.KNOWN_RULES`, que se
mantiene a mano y no derivado de los JSON a propósito: así añadir un detector obliga a pasar por
ese fichero aunque el texto viva en otro sitio.

**`rule_explain` es el texto más visible del bot** y tiene prioridad sobre el `reason` del
detector. El motivo que lee el admin nunca puede quedar vacío: explicación mapeada, si no la
razón del detector, y si no un genérico.

### El perfil se mira en los TRES momentos, no solo al entrar

Había una asimetría que se cobró varios casos: el perfil se revisaba al entrar y (desde
el 2026-08-09) en el repaso de recién llegados, pero **al escribir se juzgaba solo el
texto**. Quien entra con el perfil limpio y lo cambia justo antes de hablar cabía entero
por ahí, porque entre la última pasada del repaso y el mensaje van minutos y contra eso
ninguna cadencia de repaso sirve.

Caso medido (9-ago-2026, Domótica): «李大哥», nombre 100 % Han y con el canal
`财天下飞机进群结演员结算频道` en el perfil. Entró a las 00:39 pasando los filtros, se
verificó **en 4 segundos** y escribió 15 horas después. Lo cazó `non_allowed_script`, o
sea **por el idioma del texto**: con un «hola buenas» habría pasado limpio, igual que
habría pasado «Vickycat46», de la misma red pero con nombre latino.

Ahora `on_message` aplica en el primer mensaje los **mismos** criterios del join
(`_is_obvious_spam_profile` + `personal_channel`), sin umbrales propios: si con ese perfil
no habría entrado, tampoco habla. Dos guardas:

- **Solo si el bot presenció el join** (`join_ts IS NOT NULL`). Con `join_ts` a NULL el
  usuario ya estaba en el grupo antes que el bot y esto no es su primer mensaje: podría
  llevar años participando. Es la misma guarda de `first_msg_media`, puesta ahí tras un
  falso positivo real.
- **Un solo `fetch` por mensaje.** Antes había hasta tres consumidores del perfil en el
  mismo mensaje (premium, media y ahora este), cada uno con su llamada y su tope de 12 s,
  en una ruta donde PTB procesa los updates de uno en uno. El ayudante `_senales()` lo
  pide una vez y lo reparte.

Lo que esto **no** puede hacer: evitar que el mensaje llegue a publicarse. Telegram no
tiene moderación previa; el bot borra y banea un segundo después. Lo que se gana es cazar
al que el texto no delata.

### El perfil tiene más de un escaparate

Durante mucho tiempo solo se leía `about`, la bio. El **canal personal**
(`personal_channel_id`, novedad de Telegram 2024 disponible desde Telethon 1.36, hoy 1.44) es un campo
**separado**: un perfil con la bio vacía puede tener ahí un canal entero de spam. El caso que lo
destapó fue una cuenta llamada "Matthew", nombre latino, sin foto, sin username y con la bio
vacía (por eso pasó todos los filtros anteriores), que tenía un canal chino reclutando mulas de
blanqueo.

**Si aparece otro campo nuevo de perfil, mirarlo antes de dar el perfil por limpio.**

`personal_channel_spam` no salta por tener canal, que es legítimo. La señal es la
**discordancia**: nombre en alfabeto latino y canal en otro script, que es un disfraz
deliberado. Los pesos están calibrados para que **ninguna señal suelta llegue al umbral de 100**.
La lección del caso: el bot ya cazaba a los de esa red que usaban nombre chino; los que se
colaban eran justo los que se ponían nombre occidental.

#### El rótulo no basta: hay que leer lo que el canal publica

Juzgar el canal por su título es juzgarlo por la parte que el spammer elige sabiendo que se ve,
y esa red **renombra sus canales en cuanto se les caza**. Medido el 2026-08-08 en Windows 11:
«Vickycat46», nombre latino y foto de perfil normal, con el canal `恒泰招聘车队高速结算`.
Sumaba **85 de los 100 puntos** necesarios y se libraba justo por tener foto (no le tocaban los
25 de «perfil sin nada que mirar»). Su primer post era una confesión entera:

```
洗米来有码就要 无风险 日3-8k ... 担保公群 https://t.me/+...
```

Nótese `洗米` («lavar arroz») donde la lista esperaba `洗钱` («lavar dinero»): jerga hecha para
esquivar filtros de palabras.

`channel_reader.py` lee la descripción y los últimos posts del canal, y ese texto pasa por las
mismas listas (`SCORE_CHANNEL_CONTENT`, 75 puntos, que **siguen sin decidir solos**). Tres
decisiones de diseño:

- **Solo se paga cuando puede cambiar el veredicto.** Primero se juzga el título, que es gratis
  porque ya viene con las señales del perfil; la llamada de red solo se hace si el título no ha
  bastado. Medido: de 131 recién llegados en 14 días, apenas 6 tenían canal.
- **No delata la cuenta ni se une a nada.** Pedir el historial no cuenta como visualización (el
  contador solo sube con `messages.getMessagesViews`), y un canal público se lee sin
  suscribirse. Mismo criterio que ya se aplicó en `story_reader`.
- **Usa la entidad ya resuelta** que viene en `GetFullUser.chats`, así que no hay
  `contacts.ResolveUsername` de por medio, que es la llamada más propensa a FloodWait.

El repaso de recién llegados (`recien_llegados.py`) también mira este escaparate, porque el
canal se puede enlazar **después** de entrar y no se ve desde la Bot API. Como ahí el nombre
puede estar perfectamente limpio, hay que leer algunos perfiles «por si acaso»: de ahí el
presupuesto de `MAX_PERFILES_POR_CICLO` lecturas por vuelta y una relectura por persona cada
6 h, para no quemar la cuenta secundaria.

### Anti falso positivo

Las guardas más importantes, y el caso real que originó cada una:

**Nombres decorativos**. NFKC para normalizar Mathematical Alphanumeric y Fullwidth Latin, más
`confusable_homoglyphs.is_dangerous` (UTS#39) para no contar como "no latino" lo que solo es
decorativo. Cherokee y Thai decorativos no son spam, y los bilingües tampoco. Detalle fino: los
homoglifos se comprueban sobre el string **original antes de NFKC**, porque NFKC y
`confusables.txt` discrepan en 31 caracteres.

**Bypass por antigüedad**: cuenta de más de un año con foto nunca se banea directamente por el
nombre, y `photos_batch` se desactiva entera. Un spammer con identidad robada sube el lote de
fotos al crear la cuenta; una cuenta vieja con fotos viejas subidas de golpe puede ser
simplemente alguien que subió su galería.

**Monedas que son palabras comunes** (`peso`, `real`, `sol`, `libra`, `corona`) solo cuentan
pegadas a una cifra. Hay tests con "el peso del paquete", "hace un sol" y "media libra de
harina" para que nadie las añada sueltas. Los códigos ISO exigen mayúsculas con `(?-i:...)`,
porque en minúscula "try" y "cup" son palabras normales.

**`first_msg_media` solo aplica si el bot presenció el join.** Si `join_ts` es NULL, el usuario
ya estaba en el grupo antes que el bot y no se sabe si es realmente su primer mensaje: podría
llevar años.

**Si Telethon no responde, no se marca "sospechoso" por defecto.** Marcarlo provocaba falsos
positivos cada vez que el reporter estaba desconectado.

**Timeout de 5 segundos** en las llamadas Telethon de `photos_batch`. Telethon trae
`flood_sleep_threshold=60` y `request_retries=5`, y PTB corre con `concurrent_updates=1`: un
FloodWait congelaría la moderación de **todos** los grupos a la vez. Con la cota, degrada a "sin
veredicto" en 5 segundos.

**Quien menciona a @admin no entra en el pipeline antispam**: está reportando algo, no
haciendo spam.

### Listas negras: tres capas que se acumulan

```
1. config/blacklist/*.txt           12 ficheros, genéricos, versionados
2. config/blacklist/<lang>/*.txt    10 en en/, por idioma
3. config/blacklist/custom/*.txt    las que añade el admin desde Telegram, gitignored
```

Se **suman, nunca se sustituyen**, con deduplicación por `casefold()`. El spam llega en
cualquier idioma. Los idiomas activos son el actual más inglés siempre, por ser la lengua franca
del spam en Telegram; `BLACKLIST_LANGS` lo sustituye por completo.

No existe `config/blacklist/es/` y es coherente: el bot es de origen español, así que la capa
genérica de la raíz **es de facto la capa española**, y `en/` es la capa acumulativa.

Cada línea es un regex, **salvo en `custom/`**, donde todo se escapa. El escapado ocurre **al
cargar, no al guardar**, y es deliberado: así el admin ve en el listado exactamente lo que
escribió, y la garantía "aquí no entra un regex activo" se mantiene aunque alguien edite el
fichero a mano. Si se guardase ya escapado, bastaría escribir `.*` a mano en el fichero para
colar un comodín.

Un patrón inválido se ignora con un log, nunca tumba el bot. Hay defensa en dos niveles: se
compila cada término por separado, y luego se comprueba la alternancia completa, porque varios
patrones que compilan sueltos pueden romper juntos (por ejemplo un `\1` que apunta a un grupo de
otro término). Si la lista queda vacía se usa un patrón imposible. Antes de esto, un fichero mal
editado reventaba el import del detector y el bot ni arrancaba.

Relacionado: la lectura usa `errors="replace"`. No es cosmético, un fichero en latin-1 lanzaba
`UnicodeDecodeError`, que **no es `OSError`** y se llevaba por delante la carga entera.

La caché de compilación incluye en su clave el `mtime` y el tamaño del fichero custom, para que
un término recién añadido desde el panel se recoja al vuelo sin reiniciar.

### Alta de términos desde Telegram

Cadena de validación ordenada de lo barato a lo caro: lista conocida, longitud entre 4 y 120
caracteres, al menos dos alfanuméricos, y **bordes alfanuméricos si la lista usa `\b`**. Este
último es fino y por eso está: `\b` exige un carácter de palabra al lado, así que un término que
empiece por símbolo **quedaría muerto en silencio** y el admin creería estar protegido. Luego,
duplicado, tope de 300 términos por lista, y "ya cubierto por otro patrón".

**Toda alta pasa por vista previa.** `preview_term()` mira dos fuentes: hasta 300 mensajes
reales y recientes del grupo, y las muestras marcadas como legítimas con `/legal`, donde una
coincidencia es un falso positivo **confirmado por el propio admin**. Un término como "oferta"
caza tres de cada cuatro mensajes de un grupo de informática. Esta pantalla es la red de
seguridad del sistema: enseña al admin que su término pillaría a doce vecinos legítimos antes de
que empiece a banearlos.

La escritura es atómica (`os.replace`) porque el bot está sirviendo: un corte a media escritura
dejaría la lista truncada y el detector cargaría media protección sin avisar.

## 11. Aprendizaje

Naive Bayes más similitud coseno sobre char-ngrams (3 a 5), entrenados con las muestras que el
admin marca con `/spam` y `/legal`. `BAYES_MIN_SAMPLES_PER_CLASS = 10` de **cada** clase: con 0
muestras legítimas el Bayes está dormido y solo actúa el coseno.

### Las salvaguardas, y por qué existen

El riesgo de un clasificador entrenado por el propio grupo es que aprenda a castigar el
vocabulario normal de ese grupo. Cuatro medidas:

**Tope al log-odds por token** (`BAYES_MAX_TOKEN_LOGRATIO = 1.1`, unos 3 a 1 de odds). Sin tope,
una palabra que aparece en 10 muestras de spam y en ninguna legítima decide ella sola el
veredicto. En un grupo de fotografía basta con que varios spammers vendan cámaras para que
"cámara" pase a ser señal de spam y quien pregunte por la suya se lleve un mute. Con tope hacen
falta varias palabras sospechosas.

**El tope es asimétrico a propósito.** La evidencia que **exculpa** pasa entera, sin tope. Por la
regla número uno del proyecto: para acusar se exigen varias señales, para absolver basta con una.

**Token que aparece en las dos clases: pesa la mitad** (`BAYES_SHARED_TOKEN_FACTOR = 0.5`). No
separa nada.

**Token visto una sola vez en todo el corpus: pesa un tercio**
(`BAYES_RARE_TOKEN_FACTOR = 0.34`). Es ruido, no evidencia.

Los topes efectivos quedan en 1.1 (exclusivo de spam y visto dos o más veces), 0.55 (compartido)
y 0.374 (visto una vez). Las penalizaciones no se acumulan.

**`COSINE_MEDIUM_MIN_CHARS = 40`**, con caso medido: el coseno de char-ngrams se infla en textos
cortos porque comparten pocos ngramas en total. Con una sola muestra de spam
("hola busco gente para trabajar desde casa escribeme"), el mensaje inocente
"hola busco gente para jugar escribeme" daba 0.67 y se llevaba un mute. Por debajo de 40
caracteres se exige similitud superior a 0.8, que ya es prácticamente calcar el mensaje.

### Tokens excluidos

Dos fuentes. Los **defaults en código** son palabras funcionales del idioma (68 en español, 59 en
inglés): valen para cualquier comunidad, sea de cocina, fotografía o domótica. El **vocabulario
temático lo pone cada admin** en `classifier_excluded_tokens.txt`, porque solo él conoce su
grupo.

Ese fichero es la única lista que va **al revés** que las demás (palabras que el clasificador
ignora, no que caza) y no se compila como regex. Por eso está deliberadamente **fuera** de las
listas gestionables desde el panel.

`learned_similarity` no es HARD_RULE, así que el trust lo modera: con trust ≥ 70 se ignora, entre
40 y 69 va a revisión.

## 12. Dependencias externas

### Bot API frente a MTProto

**Telethon es último recurso.** Solo se usa para lo que la Bot API no puede hacer:

| Necesidad | Por qué Bot API no llega |
|---|---|
| `channels.reportSpam` | la Bot API no tiene primitiva de reporte |
| Bio del perfil | no expuesta a bots |
| Canal personal del perfil | no expuesto a bots |
| Fotos de perfil y sus fechas | no expuestas a bots |
| `admin_log` (quién borró un mensaje) | no expuesto a bots |
| Histórico de mensajes (`iter_messages`) | un bot no ve lo anterior a su llegada |

### Qué se pierde sin Telethon

Master switch `TELETHON_ENABLED`. Con él en `false` el bot funciona solo con Bot API y lo avisa
por log al arrancar, enumerando lo que queda desactivado. Además, `_warn_telethon_requirements()`
avisa específicamente si hay opciones **activadas en el `.env`** que requieren Telethon y por
tanto quedan muertas: ese es el momento en que el usuario se entera, no meses después.

| Detector | Sin Telethon |
|---|---|
| `photos_batch_upload` | no dispara |
| `bio_spam` | no dispara |
| `personal_channel_spam` | no dispara |
| `premium_new_link` | no dispara |
| `first_msg_media` | funciona, pierde el refuerzo de perfil sospechoso |
| `obvious_spam_profile` | funciona, pierde la rama de "1 campo no latino más cuenta nueva sin foto" |

El resto de detectores funcionan igual. Está documentado en ambos README porque quien
instale sin cuenta secundaria no sabría qué se está perdiendo.

`reporter.get_client()` devuelve el cliente **aunque los reportes estén desactivados**: bio,
fotos y admin_log siguen disponibles. Son dos interruptores distintos.

### Federación

No hay primitiva nativa en la Bot API. El patrón es: auto-discovery de chats vía
`my_chat_member`, iteración de `banChatMember` sobre los chats donde el bot es admin, y
`banned_users` como fuente de verdad local. Al reentrar, `on_chat_member` consulta `is_banned()`
y re-banea con la regla `federation_known_ban`.

El `AIORateLimiter` va configurado con `group_max_rate=0` a propósito: ese límite es de
**mensajes** a un grupo, no de acciones de admin, y aplicarlo a `banChatMember` encolaría los
bans justo durante una raid, que es cuando más urgen. Se mantiene el global de 30 por segundo,
que es el límite real de la Bot API. Sin rate limiter, un 429 durante un ban federado se
capturaba como error genérico y **el ban se perdía en silencio, sin reintento**.

### Jobs programados

| Job | Cadencia |
|---|---|
| `_heartbeat_job` | 30 s, toca el fichero que lee el healthcheck de Docker |
| `verification.cleanup_job` | 15 min, tres tramos: kick sospechosos a 30 min, recordatorio a 3 h, kick post-recordatorio a +6 h |
| `maintenance.cleanup_nightly_job` | 24 h, primera a la hora del arranque |
| `topweekly.weekly_top_job` | domingos 20:00 Europe/Madrid |

## 13. Tests

**1296 tests en 8,3 segundos**, sin red ni base real. Cada detector tiene sus casos positivos y
negativos, con foco en los negativos: un falso positivo es peor que un falso negativo.

Aparte de los tests de lógica, hay **tests meta que protegen invariantes del proyecto**. Cada uno
nació de un bug real y son los que evitan que vuelva:

**`test_no_row_get.py`**: `seen` y compañía son `sqlite3.Row`, no `dict`, y **`.get()` no
existe**. Escanea `src/` buscando `row.get(`, `seen.get(`, `settings.get(`. Origen: `cmd_ban`
usaba `chat_row.get("chat_id")` dentro de un `except`; cuando `get_chat_member` fallaba de
verdad, el propio log petaba con `AttributeError`, la excepción escapaba y **el baneo no se
ejecutaba**, con toda la apariencia de haber funcionado.

**`test_i18n_calls.py`**: recorre el AST buscando llamadas a `t()` y verifica que la clave existe
en todos los paquetes y que los placeholders cuadran exactamente con los kwargs, ni de más ni de
menos. Origen: el bug de `_lang` descrito en la sección 8.

**`test_locales.py`**: JSON plano y solo texto, placeholders idénticos al español, paridad total
es/en y **HTML balanceado**. Este último es crítico: Telegram rechaza el mensaje **entero** si un
`<b>` queda abierto, y en un bot de moderación eso significa un aviso de ban perdido en silencio.
La cobertura de idiomas de la comunidad es informativa y nunca falla el build: lo que falte cae
al español.

**`test_command_aliases.py`**: lee los `CommandHandler` de `main.py` por AST (no construye la
`Application`, que exigiría token y base). Verifica que cada par es/en apunta a la **misma
función por identidad**, que todo nombre publicado en el menú tiene handler ("de nada sirve
publicar `/alerts` si nadie lo atiende") y que un paquete de idioma roto cae al nombre por
defecto en vez de dejar al bot sin menú.

**`test_config_files.py`**: contrato de los ficheros editables (listas, bienvenidas, niveles de
trust). Incluye un test contra un gotcha real: `Path("")` es igual a `Path(".")` y su `exists()`
devuelve `True`, porque es el directorio actual, así que un `EXTERNAL_NOTIFY_ENV_PATH` vacío daba
`IsADirectoryError` en un despliegue limpio. El arreglo es usar `is_file()`.

## 14. Despliegue

Contenedor único `cazaspam-bot`, `restart: unless-stopped`. Cuatro volúmenes: `./data` de
lectura y escritura (la base y el heartbeat, única superficie persistente), y `./src`,
`./scripts` y `./config` en solo lectura.

`./config` se monta pero el `Dockerfile` **no lo copia**: la imagen a secas no lleva las listas ni
las bienvenidas, y caería a los defaults en código. Es precisamente lo que cubre
`test_config_files.py`.

Healthcheck: comprueba que `/app/data/heartbeat` existe y tiene menos de 5 minutos. Con
`interval: 2m` y 3 reintentos, el peor caso hasta marcar unhealthy es de unos 6 minutos.

**`docker compose restart` recarga el código (`src/` va montado) pero NO el `.env`.** Para eso
hace falta `up -d`. Es el gotcha operativo que más veces ha costado una sesión de depuración.

El logger de `httpx` está subido a WARNING a propósito: loguea a INFO la URL completa de cada
petición, que en la Bot API **incluye el token**. Y `apscheduler` también, porque el heartbeat
cada 30 segundos generaba unas 5.700 líneas diarias de puro ruido.

## 15. Trampas conocidas

Resumen de lo que cuesta un bug si se olvida. El detalle está en la sección correspondiente.

| Trampa | Consecuencia |
|---|---|
| `sqlite3.Row` no tiene `.get()` | `AttributeError` dentro de un `except`, acción perdida en silencio |
| `t()` devuelve la clave si no existe | un `or` de respaldo nunca se activa, el usuario ve `rule.xxx` |
| HTML desbalanceado en un texto | Telegram rechaza el mensaje entero, el aviso se pierde |
| `callback_data` tiene 64 **bytes** | nunca meter texto de usuario dentro, usar hash o índice |
| Mute provisional sin `try/except` | usuario muteado para siempre e invisible al `cleanup_job` |
| Columna nueva con `DEFAULT 0` | quien lo tenía activo por `.env` se queda sin ello, en silencio |
| Índice saltado en frases numeradas | las posteriores no salen nunca |
| Campo nuevo sin añadir a `ALLOWED` | `ValueError` al guardar desde el panel |
| `restart` en vez de `up -d` | el `.env` no se recarga |
| `seen_users.msg_count` como historial | no refleja lo anterior a la llegada del bot; para "nunca escribió" usar Telethon |
| Acción masiva sin dry-run | irreversible sobre usuarios reales. Nunca, sin lista previa y luz verde |

## Docs relacionadas

`docs/ECOSYSTEM.md`, `docs/ROADMAP.md`, `docs/LEARNING.md`,
`src/locales/README.md` (traductores), `config/blacklist/README.md`,
`config/welcomes/README.md`.
