# Arquitectura — CazaSpamBot

> Última actualización: 2026-05-23. Documento vivo: actualizar tras cada cambio
> arquitectónico relevante. Este doc es la **fuente de verdad** para futuras
> sesiones de Claude Code: leerlo ANTES de proponer rediseños.

## Stack

- **Python 3.11+** · `python-telegram-bot[ext]==21.6` (Bot API async, polling)
- **Telethon 1.36** (MTProto cliente, cuenta admin `la cuenta Telethon`) — solo para
  analyze de miembros y `channels.reportSpam`
- **SQLite con WAL** (sin BD externa, single-file `data/antispam.db`)
- **Docker + docker-compose** (contenedor único `cazaspam-bot`, volumen `./data`)
- **systemd** NO usado (decisión: Docker por portabilidad open-source)

## Componentes (`src/`)

| Módulo | Responsabilidad |
|---|---|
| `main.py` | Entry point, registro de handlers, post_init/shutdown, job_queue |
| `config.py` | Carga `.env`, dataclass `Config` inmutable, helpers `_csv/_bool/_int` |
| `db.py` | SQLite WAL, todas las tablas y CRUD. Single-writer thread-safe |
| `handlers.py` | `on_message`, `on_chat_member`, `on_my_chat_member`, `on_message_reaction`, `_apply_action`, `_ensure_chat_registered` |
| `admin.py` | Comandos admin con decorador `_only_admin`. `/start /help /stats /chats /recent /shadow /ban /unban /whitelist /notspam` |
| `detectors/` | Un fichero por regla. Cada uno devuelve `Hit(rule, score, reason, payload)` |
| `scoring.py` | Combina hits → `Decision(action, score, rule, reason)` con thresholds |
| `federation.py` | `federate_ban` itera `bot_chats` y aplica `banChatMember` en todos |
| `notifier.py` | Notificaciones via Casa_Yona con botones inline (Era spam / No / Whitelist) |
| `quips.py` | Catálogo de frases sarcásticas en plural y singular. `pick()` y `batch_summary()` |
| `reporter.py` | `SpamReporter` con cola async + worker Telethon. Estrategia 3-step: `channels.reportSpam` → `messages.report` → `account.reportPeer` |

## Tablas SQLite (`db.py`)

| Tabla | Para qué |
|---|---|
| `bot_chats` | Chats donde el bot está + permisos (am_admin, can_restrict, can_delete). Auto-discovery via `my_chat_member`. |
| `seen_users` | (chat_id, user_id) con first_msg_ts, msg_count, reaction_count, reputation, whitelisted. Base del análisis pasivo. |
| `banned_users` | Federación interna: user_id baneados con razón, regla, chat_origen, federado, revoked_at. |
| `moderation_log` | Auditoría completa de toda acción (incl. shadow). Cada `_apply_action` mete fila. |
| `reaction_events` | (ts, chat_id, user_id, message_id, new_emojis). Window-based para reaction-farming. |
| `cas_cache` | (user_id, offenses, checked_at). TTL 24h. Evita llamadas repetidas a api.cas.chat. |
| `username_map` | (username_lower → user_id). Permite validar menciones a externos. |
| `suppressions` | (user_id, rule, suppressed_until). Tras "No era spam" del admin → no se repite la regla 7 días. |

## Detectores (cada uno → `Hit`)

| Regla | Cómo funciona | Score |
|---|---|---|
| `non_allowed_script` | `unicodedata` clasifica chars por bloques Unicode. Si ratio scripts no permitidos > 0.3 en primeros N msgs | 100 (first) / 30 (late) |
| `external_mention_or_link` | Itera `message.entities` MENTION/TEXT_MENTION/URL/TEXT_LINK. Valida con `is_user_in_chat()` y host `t.me/...` | 100 (first) / 40-50 (late) |
| `url_blocklist` | urllib.parse host vs blocklist coma-separada en .env | 60 (first) / 25 (late) |
| `reaction_farming` | Sliding window N reacciones en M segundos con `total_msgs_user == 0` | 100 |
| `cas_match` | GET api.cas.chat/check. Score solo si `offenses >= CAS_AUTOBAN_MIN` | 100 |

Scoring acumulado en `scoring.decide()` con thresholds `BAN_SCORE=100`, `KICK_SCORE=70`, `MUTE_SCORE=40`. Override `FIRST_MSG_ATTACK_ACTION` fuerza acción concreta cuando dispara primer mensaje.

## Flujo de una acción de moderación

```
detección                       persistencia            acción real             reporte                     publicación
─────────────                   ──────────────         ──────────────          ─────────────                ─────────────
on_message              ──→     log_action()    ──→    delete_message()    ──→ reporter.enqueue()    ──→   quip público
on_chat_member (join)           +                      ban/kick/mute            (channels.reportSpam        + notifier
on_message_reaction             federation                                       o messages.report           Casa_Yona
                                table                                            o account.reportPeer        admin DM
```

Si `MODE=shadow`: solo persiste y notifica, no actúa.
Si `cfg.public_quip_enabled and action in (ban, kick)`: publica quip en grupo con autoborrado configurable.
Si `cfg.federation_enabled`: itera `bot_chats(am_admin=1)` con `banChatMember`.

## Federación cross-group

No hay primitiva nativa Bot API. Patrón implementado (inspirado en DaisyX feds):

1. Auto-discovery: `on_my_chat_member` registra cada chat donde el bot es admin
2. Al banear: `federate_ban()` itera `bot_chats(am_admin=1)` con `banChatMember`
3. Lista local `banned_users` actúa de fuente de verdad
4. Reentry: `on_chat_member` chequea `is_banned(user_id)` → ban inmediato con regla `federation_known_ban`

## Auto-discovery + auto-recovery de chats

- `on_my_chat_member` (cuando el bot es promovido/quitado): upsert `bot_chats`
- `on_message` y `on_message_reaction`: si el chat no está en cache local, llama `getChatMember(bot.id)` y lo registra. Esto cubre updates perdidos en arranque.

## Scripts auxiliares (`scripts/`)

| Script | Para qué |
|---|---|
| `telethon_login.py` | Login MTProto en 2 fases (`request` / `confirm <code>`) sin TTY |
| `list_my_groups.py` | Lista grupos donde la cuenta Telethon es miembro (diagnóstico) |
| `analyze_members.py` | Itera miembros vía Telethon agresivo, score por heurísticas, autoban CAS>=N, review CAS=1 a casa_tg con foto info |

## Modo `shadow` vs `active`

- `shadow`: registra todo en `moderation_log` pero NO ejecuta `ban/kick/delete`. Sirve para calibrar.
- `active`: ejecuta acciones reales + publica quips + reporta via Telethon.
- Switch: `./ctl.sh active` (con confirmación interactiva).

## Notificaciones a admin

Por defecto, el propio bot manda DM directo al `ADMIN_USER_ID` con cada acción.
Opcionalmente puede reenviar también a un segundo bot de notificaciones
(`NOTIFY_VIA_CASA_YONA=true` + `CASA_YONA_ENV_PATH` apuntando a un `.env` con
el token de ese bot). Cada acción incluye botones inline:

- ✅ Confirmar (no-op, solo cierra)
- ❌ No era spam (`unban` + `suppress` regla 7d)
- 🛡️ Whitelist user

**Limitación**: los botones inline solo funcionan si el bot que envió el mensaje
los procesa: un bot secundario NO procesa callbacks de este. Workaround: comandos
`/notspam <action_id>` por DM al bot directo.

## Reporte oficial a Telegram (`reporter.py`)

⚠️ **CAS no acepta submits**. La única forma de contribuir a sistemas anti-spam globales es vía Telegram Native Antispam.

Worker async con cola `asyncio.Queue`. Cada `_apply_action` con `action in (ban, kick)` y `MODE=active` encola tarea. El worker procesa con prioridad:

1. `channels.ReportSpamRequest(channel, participant, [msg_ids])` — solo si somos admin del supergrupo y hay message_id. **Es la opción preferida**.
2. `ReportRequest(peer, [ids], reason, message)` — reporte estándar de mensaje
3. `ReportPeerRequest(peer, reason, message)` — fallback si no hay message_id

Efecto: alimenta el "Native Antispam" de Telegram. Cuentas con muchos reports independientes entran en "aggressive mode" global.

## Rendimiento esperado

- **Memoria**: contenedor ~80-120 MB RSS (PTB + Telethon + SQLite)
- **CPU**: <1% en idle, picos breves al recibir bursts de mensajes
- **Disco**: `data/` crece ~10 MB/mes para grupos medianos (~1k mensajes/día)
- **Red**: polling cada ~10s + ocasionales requests a api.cas.chat + Telethon
- **Tests**: 62/62 pasan en <1s

## Decisiones arquitectónicas registradas

- **No usar systemd**: Docker para portabilidad (open-source futuro)
- **No Postgres**: SQLite WAL sobra para este volumen, evita dependencia externa
- **Federación interna, no inter-organizacional**: abrir feds a terceros = vector de envenenamiento
- **No captcha de join**: rechazado por el usuario, fricción excesiva
- **No LLM por defecto**: coste y dependencia externa, opcional vía `LLM_ENABLED=true`
- **Cuenta secundaria para Telethon**: `la cuenta Telethon` separada de cuenta principal. Si se filtra `.session`, no afecta cuenta personal del admin
- **CAS_AUTOBAN_MIN=2**: solo autobaneo si confirmado por 2+ admins/filtros independientes. `=1` va a revisión humana
