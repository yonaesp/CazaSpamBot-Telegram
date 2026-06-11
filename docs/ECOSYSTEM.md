# Ecosistema antispam Telegram — qué se puede y qué no

> Documento de referencia técnica. Cita fuentes verificables. Actualizar cuando
> Telegram cambie su API.

## TL;DR

| Cosa | Posible | Cómo |
|---|---|---|
| Leer mensajes de grupos | ✅ | Bot admin + Privacy Mode OFF |
| Listar miembros de supergrupo | ❌ con bot · ✅ con cuenta admin via MTProto (Telethon `iter_participants aggressive=True`) |
| Banear federado cross-group | ✅ | Tabla local + `banChatMember` en cada chat |
| Descargar historial mensajes | ❌ con bot · ✅ con MTProto |
| Reportar spam a Telegram | ❌ con bot · ✅ via MTProto `channels.reportSpam` |
| Contribuir a CAS | ❌ **nadie puede** | CAS es read-only desde fuera |
| Consultar CAS | ✅ | `GET api.cas.chat/check?user_id=N` |
| Listar bots oficiales | ✅ parcial | Bot API expone `is_bot` en User |
| Detectar reaction-farming | ✅ desde Bot API 7.0 | `MessageReactionUpdated` + `allowed_updates` |

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
- **`/spam` desde otro bot**: ❌ Telegram bloquea bot-to-bot. *"Bots will not be able to see messages from other bots regardless of mode"*. Fuente: https://core.telegram.org/bots/faq
- **`/spam` desde humano admin**: ✅ funciona si @combot está en el grupo
- **`/ban`, `/kick`, `/warn` de @combot**: moderación local, no alimentan CAS

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
- Ver mensajes de otros bots (`can_read_all_group_messages=true` no afecta a esto)
- Iniciar conversaciones con usuarios (el user tiene que hacer "Start" primero)

### Bot API SÍ PUEDE (Bot API 7.0+)

- `MessageReactionUpdated` y `MessageReactionCountUpdated` (si es admin + `allowed_updates`)
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
- Resolución `@username → User` directa

### MTProto NO PUEDE

- Eludir el rate-limit anti-spam de Telegram (~30 msgs/s globales)
- Contribuir a CAS (CAS es de Combot, no es Telegram)
- Reports masivos sin riesgo de baneo de la cuenta cliente

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
- **lols.bot**: api.lols.bot — alternativa CAS con cobertura ligeramente distinta. Endpoint público de lookup (sin docs formales, ver `pyCombotCAS_API` para patrón)

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

Nuestro bot usa la opción 3 via Telethon (`la cuenta Telethon` admin).
