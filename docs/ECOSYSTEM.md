# Ecosistema antispam Telegram — qué se puede y qué no

> Documento de referencia técnica. Cita fuentes verificables. Actualizar cuando
> Telegram cambie su API.

## Versión de API sobre la que corre este bot

| | Versión | Nota |
|---|---|---|
| Bot API publicada por Telegram | **10.2** (2026-07-14) | [changelog oficial](https://core.telegram.org/bots/api-changelog) |
| Bot API que alcanza este bot | **10.0** | `python-telegram-bot==22.8` ([docs v22.8](https://docs.python-telegram-bot.org/en/v22.8/)) |
| MTProto (Telethon) | `telethon==1.44.0` | capa TL con `personal_channel_id` disponible |

**Hay tres versiones mayores de distancia.** Todo lo que este documento marca como
«Bot API 8/9/10» existe en la plataforma pero **no es invocable sin subir PTB**.
Antes de dar por imposible algo, mirar si el bloqueo es de Telegram o de nuestro pin.

## TL;DR

| Cosa | Posible | Cómo |
|---|---|---|
| Leer mensajes de grupos | ✅ | Bot admin + Privacy Mode OFF |
| Listar miembros de supergrupo | ❌ con bot · ✅ con cuenta admin via MTProto (Telethon `iter_participants aggressive=True`) |
| Banear federado cross-group | ✅ | Tabla local + `banChatMember` en cada chat |
| Banear a un CANAL que postea en el grupo | ✅ desde Bot API 6.0 | `banChatSenderChat(chat_id, sender_chat_id)` |
| Leer la **bio** de un usuario | ❌ con bot · ✅ MTProto `users.getFullUser` |
| Leer el **canal personal** del perfil | ❌ con bot · ✅ MTProto `userFull.personal_channel_id` |
| Ver fotos de perfil con fecha | ❌ con bot · ✅ MTProto `get_profile_photos` |
| Descargar historial mensajes | ❌ con bot · ✅ con MTProto `iter_messages` |
| Reportar spam a Telegram | ❌ con bot · ✅ via MTProto `channels.reportSpam` |
| Saber quién borró un mensaje | ❌ con bot · ✅ MTProto `iter_admin_log` |
| Contribuir a CAS | ❌ **nadie puede** | CAS es read-only desde fuera |
| Consultar CAS | ✅ | `GET api.cas.chat/check?user_id=N` |
| Listar bots oficiales | ✅ parcial | Bot API expone `is_bot` en User |
| Detectar reaction-farming | ✅ desde Bot API 7.0 | `MessageReactionUpdated` + `allowed_updates` |
| Ver citas de OTRO chat en un mensaje | ✅ desde Bot API 7.0 | `Message.external_reply` (`ExternalReplyInfo`) |
| Que un bot hable con otro bot | ✅ **desde Bot API 10.0** | ver «Bot-to-bot», era imposible hasta 2026-05 |

## CAS (Combot Anti-Spam)

- **URL**: https://cas.chat · API: https://api.cas.chat
- **Endpoints públicos** (solo lectura):
  - `GET /check?user_id=<id>` → `{ok, result: {offenses, time_added, messages?}}`
  - `GET /export.csv` → dump completo (~MB)
- **POST/submit**: NO existe. La lista solo se alimenta del algoritmo interno de Combot.
- **Cómo entra alguien en CAS**:
  1. Filtros automáticos de `@combot` en grupos con Combot como admin
  2. Comando `/spam` por admins en esos grupos (= 1 offense)
  3. Reportes API privados de Combot a sus propios sistemas
- **Falsos positivos comunes**: cuentas hackeadas + recuperadas, reportes malintencionados, dedazos
- **Recomendación**: usar `CAS_AUTOBAN_MIN=2` (varios admins independientes confirmaron); offenses=1 → revisión humana
- **Cliente Python** (referencia, no usado): https://github.com/nunopenim/pyCombotCAS_API

## Combot y comandos

- **@combot** bot oficial (combot.org): moderación + analytics + escalado a CAS
- **`/spam` desde humano admin**: ✅ funciona si @combot está en el grupo
- **`/ban`, `/kick`, `/warn` de @combot**: moderación local, no alimentan CAS
- **`/spam` desde otro bot**: ver abajo. **Este documento lo daba por imposible y ya no lo es.**

## Bot-to-bot: lo que este documento decía mal

Hasta 2026 aquí ponía: *«❌ Telegram bloquea bot-to-bot. "Bots will not be able to see
messages from other bots regardless of mode"»*, citando la FAQ. **Esa frase ya no
describe la plataforma.** El bloqueo por diseño se levantó en **Bot API 10.0
(2026-05-08)**: *"Added the ability to send messages to other bots via username if both
bots enabled bot-to-bot communication"* y *"Added the ability to see certain messages
sent by other bots in groups"*.

Fuentes: [changelog Bot API](https://core.telegram.org/bots/api-changelog) ·
[doc bot-to-bot](https://core.telegram.org/api/bots/bot-to-bot).

Condiciones reales (no es barra libre):

- En **grupo**, enviar es mensajería normal. Lo que se regula es **recibir**.
- Un bot **sin** Bot-to-Bot Communication Mode solo recibe de otros bots si el mensaje
  lleva **command mention dirigida a él** (`/spam@combot`) o es reply a un mensaje suyo.
- Un bot **con** ese modo activo recibe todos los mensajes de bots del grupo si es
  **admin** y tiene **Privacy Mode desactivado**.
- Al menos **uno de los dos** bots debe tener el modo activado.

Qué significa para nosotros, siendo honestos sobre lo no probado:

1. La vía `/spam@combot` emitida por nuestro bot **ya no está prohibida por diseño**.
   Lo que falta por comprobar es si @combot acepta órdenes de un bot (puede filtrarlo
   por su cuenta, es decisión suya, no de Telegram) y si basta con que el modo lo
   active nuestro lado. **Nadie lo ha probado en este proyecto.**
2. No es alcanzable hoy de todas formas: PTB 22.8 se queda en Bot API 10.0.
3. Aunque funcionase, **no sustituiría al reporte MTProto**: `/spam` a Combot alimenta
   la lista de Combot, no a los moderadores de Telegram. Son cosas distintas (ver
   «Tres tipos de reporte»).
4. Riesgo nuevo a tener presente: si el modo se activa, **otros bots pueden hablarle al
   nuestro**. Eso es superficie de ataque, no solo una función. La propia doc de
   Telegram avisa de bucles infinitos y pide dedup, rate limit y profundidad máxima.

**Corolario de mantenimiento**: este es el segundo documento donde una cita literal de
la FAQ envejeció mal. Una restricción de plataforma no es una ley física; revalidar
contra el changelog antes de apoyar un diseño en un «no se puede».

## Native Antispam de Telegram

- **Doc oficial**: https://core.telegram.org/api/antispam
- Telegram tiene su propio sistema interno separado de CAS
- Se alimenta de:
  - Botón "Report → Spam" del cliente humano
  - Reports via MTProto (`channels.reportSpam`, `messages.report`, `account.reportPeer`)
  - Heurísticas internas (no documentadas)
- Efecto: cuentas con muchos reports entran en **"aggressive mode"** que restringe mensajes a chats donde el user no es miembro
- Throttling: no documentado pero existe; cuentas reportando masivamente desde una sola IP son penalizadas

## Limitaciones Bot API vs MTProto

### Bot API NO PUEDE

- Iterar miembros de un supergrupo grande (>200) — solo `getChatAdministrators` y `getChatMember(user_id)`
- Descargar historial de mensajes anterior a su entrada al grupo
- Resolver `@username → user_id` directamente (hay que mantener mapping local viendo mensajes)
- Reportar spam a Telegram (`reportSpam` no existe en Bot API)
- **Leer NADA del perfil**: ni bio, ni fotos con fecha, ni canal personal. `getChat`
  sobre un usuario no los devuelve. Es el hueco que obliga a usar MTProto en este bot.
- Saber **quién** borró un mensaje (no hay update de borrado ajeno)
- Iniciar conversaciones con usuarios (el user tiene que hacer "Start" primero)
- ~~Ver mensajes de otros bots~~ **obsoleto**: parcialmente posible desde Bot API 10.0,
  ver «Bot-to-bot» arriba

### Bot API SÍ PUEDE

- `MessageReactionUpdated` y `MessageReactionCountUpdated` (Bot API 7.0, si es admin + `allowed_updates`)
- **`Message.external_reply`** (`ExternalReplyInfo` + `TextQuote`, **Bot API 7.0**,
  2023-12-29): la cita de un mensaje de OTRO chat embebida en el mensaje. Vector real
  de spam: el CTA visible es mínimo («Please Join») y el reclamo va dentro de la cita,
  con el canal alcanzable al pulsar. No lleva link ni @mención en el texto, así que
  **`external_mention` no lo ve**. Lo cubre `detectors/external_reply.py`.
- **`banChatSenderChat` / `unbanChatSenderChat`** (**Bot API 6.0**, 2022-04-16): banea
  al **canal** que postea en el supergrupo, no al usuario. Necesario porque el spam
  publicado «en nombre de un canal» llega con `sender_chat` y **`banChatMember` no
  sirve** ahí. Usado en `handlers.py`.
- `ChatMemberUpdated` para tracking de joins (necesita `chat_member` en `allowed_updates`)
- `MyChatMember` para tracking de cambios en el propio bot (sin permisos)
- `banChatMember/unbanChatMember/restrictChatMember/deleteMessage`
- `forward_origin` con info de canales sospechosos (typical crypto spam)

### MTProto (Telethon/Pyrogram) SÍ PUEDE

- Iterar miembros con `aggressive=True` (busca A-Z, hasta ~10k en grupos grandes)
- Si la cuenta es admin: lista completa de miembros sin restricciones
- Descargar historial completo paginado (`iter_messages`)
- `channels.ReportSpamRequest`, `messages.ReportRequest`, `account.ReportPeerRequest`
- `get_profile_photos(user, limit=N)` con `date` por foto (señal de antigüedad de cuenta)
- `iter_admin_log` (quién borró qué)
- Resolución `@username → User` directa
- **Leer el perfil completo con `users.getFullUser`**, incluido el canal personal (abajo)

### El perfil tiene más de un escaparate: `personal_channel_id`

Punto ciego real de este bot durante meses. `userFull` **no es solo `about`**. Campos
del constructor ([core.telegram.org/constructor/userFull](https://core.telegram.org/constructor/userFull)):

| Campo | Qué es |
|---|---|
| `about` | la bio, lo único que mirábamos |
| **`personal_channel_id`** (`flags2.6?long`) | canal público asociado al perfil |
| **`personal_channel_message`** (`flags2.6?int`) | id del último mensaje de ese canal |
| `profile_photo` · `birthday` · `stories` | otros campos del perfil |

- Es una función de Telegram de **2024** y un campo **SEPARADO** de la bio:
  **un perfil con la bio vacía puede tener ahí un canal entero de spam.**
- **Telethon 1.44 ya lo expone** (el pin actual del proyecto). No hace falta subir nada.
- El **título** del canal no viene en `full_user`: hay que cruzar el id contra
  `full.chats`, que trae las entidades relacionadas. Ver `src/user_signals.py`.
- **No existe en Bot API**, en ninguna versión. Es motivo suficiente por sí solo para
  mantener Telethon.

Caso que lo destapó: cuenta «Matthew», nombre latino, sin foto ni bio, con un canal
chino reclutando mulas de blanqueo. El bot ya cazaba a los de esa red que usaban nombre
chino; se colaban justo los que se ponían nombre occidental.

Por eso `personal_channel_spam` **no dispara por tener canal** (eso es legítimo y
común), sino por la **discordancia** nombre latino + canal en otro script, que es un
disfraz deliberado. Ninguna señal suelta llega al umbral.

**Regla general que deja este caso**: si Telegram añade otro campo de perfil, mirarlo
antes de dar por limpio un perfil. «La bio está vacía» no significa «no hay escaparate».

### MTProto NO PUEDE

- Eludir el rate-limit anti-spam de Telegram (~30 msgs/s globales)
- Contribuir a CAS (CAS es de Combot, no es Telegram)
- Reports masivos sin riesgo de baneo de la cuenta cliente

### Qué exige Telethon en ESTE bot (y qué se pierde sin él)

`TELETHON_ENABLED=false` deja el bot funcionando solo con Bot API. Lo que se apaga:

| Función | Llamada MTProto | Detector / módulo afectado |
|---|---|---|
| Bio del usuario | `users.getFullUser` → `about` | `bio_spam`, `obvious_spam_profile` (parcial) |
| **Canal personal** | `users.getFullUser` → `personal_channel_id` | `personal_channel_spam` |
| Fotos de perfil con fecha | `get_profile_photos` | `photos_batch` |
| Reportes oficiales | `channels.reportSpam`, con fallback a `messages.report` | `reporter.py` |
| Quién borró un mensaje | `iter_admin_log` | `telethon_bridge.py`, `NOTIFY_SELF_DELETES` |
| Historial previo al bot | `iter_messages` | backfill de trust, dry-runs |

Los detectores que solo dependen de Bot API (`url_blocklist`, `external_reply`,
`inline_buttons`, `commercial_ad`, `cas`, `lols_bot`, `reaction_farming`…) siguen
activos. Quien instale sin cuenta secundaria pierde **el bloque de perfil entero**,
que es justo donde se esconde el spam más difícil de cazar por texto.

## Top repos antispam Telegram (referencia)

| Repo | Lenguaje | Stars aprox | Lo notable |
|---|---|---|---|
| [umputun/tg-spam](https://github.com/umputun/tg-spam) | Go | ~430 | Bayes + similarity + LLM veto + web UI + CAS integrado |
| [1inch/shieldy](https://github.com/1inch/shieldy) | TS | ~950 | Captcha inline botones (estándar de facto) |
| [TeamDaisyX/DaisyX](https://github.com/TeamDaisyX/DaisyX) | Python/Pyrogram | - | Feds (federaciones inter-grupo privadas) |
| [SophieBot](https://gitlab.com/SophieBot) | Python/Pyrogram | - | Feds + extensa moderación |
| [MissRose](https://missrose.org) | Python | - | Federations + warns escalado |
| [Priler/samurai](https://github.com/Priler/samurai) | Python | - | NSFW siglip + DistilBERT |
| [englishtea21/spammers-hunter](https://github.com/englishtea21/spammers-hunter) | Python | - | DistilBERT RU/EN |
| [pugson/telegram-crypto-antispam-bot](https://github.com/pugson/telegram-crypto-antispam-bot) | JS | - | Regex crypto-spam reusables |
| [OriginProtocol/telegram-moderator](https://github.com/OriginProtocol/telegram-moderator) | Python | - | Regex MESSAGE_BAN_PATTERNS / NAME_BAN_PATTERNS |
| [igrishaev/teleward](https://github.com/igrishaev/teleward) | Clojure | - | Captcha "responde con número" anti-bot |
| [lilydjwg/spamfightbot](https://github.com/lilydjwg/spamfightbot) | Python | - | CAS-lookup + heurística minimalista |
| [xvitaly/ecasbot](https://github.com/xvitaly/ecasbot) | Python | - | Forward sospechoso detection |
| [TheHamkerCat/telegram-antispam-rs](https://github.com/TheHamkerCat/telegram-antispam-rs) | Rust | - | Dataset propio |

## Listas / datasets / regexes reusables

- **CAS export**: https://api.cas.chat/export.csv — dump completo, precarga local
- **tg-spam data dir**: https://github.com/umputun/tg-spam/tree/master/data — `stop-words.txt`, `spam-samples.txt`, `ham-samples.txt`, `exclude-tokens.txt` (multi-idioma, RU/EN heavy)
- **CryptoScamDB**: https://github.com/CryptoScamDB/blacklist — URLs/handles fraudulentos JSON
- **spmedia threat-intel feed**: https://github.com/spmedia/Crypto-Scam-and-Crypto-Phishing-Threat-Intel-Feed — ~700 dominios scam, update diario
- **OriginProtocol regex patterns**: MESSAGE_BAN_PATTERNS / NAME_BAN_PATTERNS — incluye regex ETH/BTC addresses
- **HuggingFace datasets**:
  - `RUSpam/spam_dataset_v6` (ruso)
  - `RUSpam/spam_deberta_v4` (modelo pre-entrenado)
- **lols.bot**: `GET https://api.lols.bot/account?id=<user_id>`, alternativa a CAS con
  cobertura ligeramente distinta. Sin docs formales. Responde
  `{ok, user_id, banned, when}`. Ambos endpoints (CAS y lols) **verificados en vivo el
  2026-07-19**: siguen respondiendo con el mismo contrato que usa el código.

## Anti-evasión

Técnicas que los spammers usan y cómo combatirlas:

| Evasión | Contramedida |
|---|---|
| Zero-width chars (`​-‍`, `﻿`, `⁠`) | NFKC + strip antes de regex/blocklist |
| Homoglyphs (cirílico que parece latino) | `unidecode` antes de matchear; o normalización de scripts |
| Emoji-substitution (💳 = "credit card") | `emoji.demojize()` antes de blocklist |
| Espaciado anómalo ("c o m p r a") | Ratio spaces/chars > 0.4 → señal |
| Username con símbolos/zalgo | Filtro de caracteres en `User.username` |
| Forwards de canales spam | Blocklist de `forward_origin.chat.id` o username |
| Premium emoji para obfuscar | Treat como emoji normal post-NFKC |

Referencia: [TechRadar emoji obfuscation 2025](https://www.techradar.com/pro/security/this-creates-a-layered-form-of-obfuscation-new-report-says-criminals-are-using-emojis-to-avoid-detection) · [Visual Spoofing arxiv](https://arxiv.org/pdf/2004.05265)

## Tres tipos de "reporte" — no confundirlos

1. **Botón "Report" del cliente Telegram** (humano) → moderadores Telegram (Native Antispam)
2. **`/spam` de @combot** (humano en grupo con Combot) → lista privada Combot + posible escalado CAS
3. **`messages.report` / `channels.reportSpam`** via MTProto (userbot) → moderadores Telegram = idéntico a opción 1

Nuestro bot usa la opción 3 via Telethon (`la cuenta Telethon` admin): intenta primero
`channels.reportSpam` (mejor cuando somos admin del supergrupo y hay `msg_id`) y cae a
`messages.report` si falla.

No se confundan destinos: la 2 alimenta a **Combot**, la 1 y la 3 alimentan a
**Telegram**. Que Bot API 10.0 abra la puerta al `/spam@combot` desde un bot no
convierte esa vía en un reporte a Telegram.

## Cómo mantener este documento

Lo más valioso de aquí no es la lista de lo que se puede: es **lo que dábamos por
imposible y dejó de serlo**. Dos ejemplos ya materializados: el bloqueo bot-to-bot
(cayó en Bot API 10.0) y el canal personal del perfil (existía desde 2024 y no lo
mirábamos). Al revisar:

1. Comparar contra el [changelog](https://core.telegram.org/bots/api-changelog); sale
   versión nueva cada pocos meses.
2. Distinguir siempre **«Telegram no lo permite»** de **«nuestro pin de PTB no llega»**.
   Son problemas distintos y el segundo se arregla con un `pip install`.
3. Verificar contra el código lo que se afirme del propio bot, no de memoria.
4. Cuando algo se caiga, **dejar escrito que era falso** en vez de borrarlo en
   silencio: el error corregido enseña más que el dato correcto.

*Actualizado: 2026-07-19. Verificado contra Bot API 10.2, PTB 22.8 y Telethon 1.44.*
