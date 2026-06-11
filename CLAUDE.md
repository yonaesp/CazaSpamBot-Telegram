# CazaSpamBot — Bot Antispam Telegram

Bot de moderación antispam **en producción 24/7**, multi-grupo y federado (textos del bot en español). ~9500 LOC, Docker, 227 tests.

> **Estado: PRODUCCIÓN.** No es un esqueleto. Cualquier cambio afecta grupos reales con miles de usuarios. **Investiga > Confirma > Actúa.**

## Identidad

Todos los identificadores reales viven en `.env` (gitignored), NO en el repo.
Configúralos a partir de `.env.example`:

| | Variable en `.env` |
|---|---|
| Bot (ej. `@CazaSpamBot`) | `TELEGRAM_BOT_TOKEN` (su user_id se obtiene en runtime) |
| Admin del bot | `ADMIN_USER_ID` — único con permisos de escritura |
| Cuenta Telethon (MTProto, opcional) | `TG_API_ID` / `TG_API_HASH` + `data/telethon.session` |
| Notificaciones a admin | DM directo del propio bot |

## Grupos federados

Los chats que modera se configuran en `MODERATED_CHAT_IDS` (CSV de chat_ids) o,
si se deja vacío, modera todos los grupos donde el bot sea admin (auto-discovery).
Los welcomes temáticos por grupo viven en `config/welcomes/<chat_id>.txt` (gitignored)
y las listas negras editables en `config/blacklist/` (ver READMEs de cada carpeta).

**Federación**: ban en uno = ban en todos (`federation.py`). No hay primitiva
nativa; se itera `banChatMember` sobre los chats donde el bot es admin.

## Stack

- Python 3.11 + `python-telegram-bot[ext]` 21.6 (async polling)
- Telethon 1.36 (MTProto) — **solo** para lo que Bot API no puede: reportes oficiales (`channels.reportSpam`), leer bio/fotos de perfil, admin_log, iter_messages histórico
- SQLite WAL (`data/antispam.db`)
- `confusable-homoglyphs` (UTS#39) para detección de nombres decorativos
- Docker (`docker compose`), contenedor `cazaspam-bot`

## Arquitectura del flujo

**`on_chat_member` (join)** — orden de evaluación, cada uno con `return` al actuar:
1. `is_banned` federado → re-ban
2. trust precalculado (`rejoin_trust`) — si ≥70 salta verificación y protege de CAS/lols
3. `obvious_spam_profile` (≥2 campos no-latín; NFKC + confusable_homoglyphs anti-FP)
4. `bio_spam` (bio con invite link + emojis sexuales/comerciales + keywords)
5. `photos_batch_upload` (≥3 fotos en ≤2min = identidad robada; bypass si cuenta >1 año)
6. `lols.bot` lookup → ban (review humano si trust≥90)
7. `cas` lookup → ban si offenses≥2 (review si =1 o trust≥90)
8. `verification.on_join` — welcome con botón SOY HUMANO, o welcome amistoso si perfil legítimo (≥2 fotos + ≥365d + nombre latino)

**`on_message`** — recolecta hits de detectores, `decide()`, luego trust score:
- trust ≥70 → SKIP (excepto HARD_RULES: cas/lols/federation/reaction_farming)
- trust 40-69 + acción severa → review-with-buttons al admin DM (✅Legítimo/❌Spam, aprende)
- trust 40-69 + acción leve → degrada/noop
- antiflood per-user graduado por trust (5/8/12 msgs en 10s)

## Detectores (`src/detectors/` + `verification.py`)

`obvious_spam_profile`, `bio_spam`, `photos_batch`, `commercial_ad`, `forward_first_msg`, `first_msg_media`, `inline_buttons`, `external_mention`, `url_blocklist`, `tg_deeplink`, `non_allowed_script` (unicode_script), `reaction_farming`, `jfm_delta`, `premium_new_link`, `emoji_only`, `dormant_bot_mention`, `cas`, `lols_bot`, `learned_similarity` (Naive Bayes + cosine sobre samples). Listas negras de keywords editables en `config/blacklist/` (cargadas por `wordlists.py`).

## Comandos

- **Moderación** (bot_admin): `/ban` `/unban` (aceptan @username o reply), `/whitelist`, `/warn` `/warns` `/rmwarn` `/resetwarns` `/warnlimit` `/warnaction`
- **Aprendizaje**: `/spam` `/legal` (alias `/ham`) — reply a un mensaje; borra el comando y confirma por DM
- **Info** (chat_admin read-only): `/help` `/comandos` `/stats` `/chats` `/recent` `/samples` `/top` `/topweekly`
- **Config chat**: `/welcome` `/setwelcome` `/rules` `/setrules` `/cleanservice` `/setwelcomebutton` ...
- **Greeters**: `/setgreeter` `/rmgreeter` `/listgreeters`
- **Otros**: `/shadow`, `/notspam`, `/forget`

## Jobs programados (`main.py`)

- `_heartbeat_job` (30s) — healthcheck Docker
- `verification.cleanup_job` (15min) — verificación 3 tiers: kick suspicious 30min, reminder normal 3h, kick post-reminder +6h
- `maintenance.cleanup_nightly_job` (24h) — limpieza de tablas + **reconciliación banned_users↔Telegram**
- `topweekly.weekly_top_job` (domingo 20:00 Madrid) — ranking semanal

## Reglas críticas de diseño (lecciones aprendidas en producción)

1. **NUNCA acciones masivas sin dry-run.** Sweep/bans bulk → lista previa + luz verde por id. `seen_users.msg_count` NO refleja historial previo al bot (los grupos suelen ser más viejos que él): para "nunca escribió" usar Telethon `iter_messages` **filtrando service messages** (`m.action is None`).
2. **Falsos positivos > falsos negativos**: mejor dejar pasar spam que banear a un legítimo.
3. **Anti-FP de nombres**: NFKC + `confusable_homoglyphs.is_dangerous`. Cherokee/Mathematical/Thai decorativos NO son spam. Bilingües (árabe/cirílico + username latino) tampoco. Bypass si cuenta >1 año con foto.
4. **Telethon es último recurso**: solo reportes/bio/fotos/admin_log/histórico. No abusar. Usar `reporter.get_client()` o copiar la session a `/tmp`, nunca parar el contenedor para usarla.
5. **Quips opacos**: no revelar el mecanismo de detección en mensajes públicos (los spammers estudian las pistas). No mencionar lols.bot/CAS por nombre en el grupo.
6. **Sin links clicables a perfiles de spammers** en público: `nombre (id: N)`, nunca @username ni tg://user. Excepción: DM al admin + top semanal (recompensa).
7. **Castellano correcto**: `Bienvenido/a`, nunca `@`/`x` inclusivo. Sin em dashes en textos visibles.
8. **Welcomes**: frase corta graciosa + footer fijo separado. Humor de complicidad, sin condescender al usuario.
9. **Reportes a Telegram con criterio**: whitelist de reglas + score alto + rate limit (ver `REPORTER_RATE_*`), solo bans. Protege la reputación de la cuenta secundaria.
10. **Consentimiento explícito del admin** antes de anclar/editar anclados o cualquier acción pública no reversible.

## Convenciones de código

- Type hints en funciones públicas. `async def` para todo lo que toque Telegram API.
- Cada detector `check()` con tests (positivos + negativos, foco en anti-FP). `ruff check` limpio.
- `seen` es `sqlite3.Row`, NO dict: usar `row["col"]` (la columna existe, `or` maneja NULL); `.get()` NO existe en Row.
- Commits convencionales (`feat:`/`fix:`/`tweak:`...). Tests verde + restart Docker + push tras cada cambio.
- Co-Author en commits: `Claude Opus`.

## Flujo de trabajo típico

```bash
# tras editar código:
.venv/bin/python -m pytest tests/ -q          # 227 tests
sudo -n docker compose restart                # o up -d --build si cambia requirements
sudo -n docker logs cazaspam-bot --tail 5     # verificar "Bot ... listo"
git add -A && git commit -m "..." && git push
```

## Docs detalladas

`docs/ARCHITECTURE.md`, `docs/ECOSYSTEM.md`, `docs/ROADMAP.md`, `docs/LEARNING.md` (actualizados 2026-05).

*Actualizado: 2026-06-11 — bot en producción, 17 detectores, 227 tests.*
