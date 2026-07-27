# CazaSpamBot — Bot Antispam Telegram

Bot de moderación antispam **en producción 24/7**, multi-grupo, federado y **bilingüe** (es/en).
~14.400 LOC, Docker, **882 tests**, 21 detectores.

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

**Federación**: ban en uno = ban en todos (`federation.py`). No hay primitiva
nativa; se itera `banChatMember` sobre los chats donde el bot es admin.

## Stack

- Python 3.11 + `python-telegram-bot[ext]` 21.6 (async polling)
- Telethon 1.36 (MTProto) — **solo** para lo que Bot API no puede: reportes oficiales (`channels.reportSpam`), leer bio/fotos de perfil, admin_log, iter_messages histórico
- SQLite WAL (`data/antispam.db`)
- `confusable-homoglyphs` (UTS#39) para detección de nombres decorativos
- Docker (`docker compose`), contenedor `cazaspam-bot`

## Idiomas (i18n)

**Todo el texto que ve el usuario vive en `src/locales/<código>.json`.** Nada de textos en el código.

- `es.json` / `en.json`, **889 claves** cada uno. Idioma GLOBAL de la instancia.
- **Autodescubrimiento**: soltar un `fr.json` basta para que `/idioma fr` funcione. Cero cambios de código.
- **Fallback por clave** al español: un idioma al 40 % ya es usable.
- **A prueba de fallos**: un JSON roto se ignora con un log y el bot sigue. Por eso son JSON y no módulos `.py` (un `.py` se ejecuta al importarse: una comilla mal puesta tumbaba el arranque).
- Se elige con `/idioma` (persiste) o se detecta de `BOT_LANG`/`LC_ALL`/`LANG` al arrancar.
- Guía para traductores: `src/locales/README.md`.

### Reglas al tocar i18n

1. **Toda clave nueva va a `es.json` Y `en.json`** (test de paridad lo exige).
2. `t(key, _lang=None, **fmt)`. El selector se llama **`_lang` con guion bajo a propósito**: con el nombre `lang` colisionaba con un placeholder llamado igual y el usuario veía `{lang}` literal (bug real).
3. `t()` devuelve **la propia clave** si no existe. Nunca uses su resultado en un `or` sin comprobarlo antes: `explain(x) or respaldo` mostraba «rule.xxx» en pantalla. Ver la doble guarda de `rule_explain.explain()`.
4. **HTML balanceado** en cada texto: Telegram rechaza el mensaje ENTERO si un `<b>` queda abierto, y un aviso de ban se pierde en silencio. Hay test.
5. **Frases alternativas** (quips, acuses) son claves numeradas `.1`, `.2`… y cada idioma puede tener SU propio número (`i18n.variant_keys`, `quips._phrases`). Se leen del paquete directamente, sin fallback, para no mezclar idiomas dentro de una misma categoría.
6. **NO se traducen**: logs y mensajes de arranque (los lee el operador y traducirlos impide buscarlos), ni los regex de detección.
7. Nombres de comando traducibles vía `cmd.name.<default>`, validados contra `^[a-z0-9_]{1,32}$` antes de publicarlos: si no, `setMyCommands` falla y el bot se queda **sin menú**.

## Arquitectura del flujo

**`on_chat_member` (join)** — orden de evaluación, cada uno con `return` al actuar:
1. `is_banned` federado → re-ban
2. trust precalculado (`rejoin_trust`) — si ≥70 salta verificación y protege de CAS/lols
3. `obvious_spam_profile` (≥2 campos no-latín; NFKC + confusable_homoglyphs anti-FP)
4. `bio_spam` (bio con invite link + emojis sexuales/comerciales + keywords)
5. `photos_batch_upload` (≥3 fotos en ≤2min = identidad robada; bypass si cuenta >1 año)
6. `lols.bot` lookup → ban (review humano si trust≥90)
7. `cas` lookup → ban si offenses≥2 (review si =1 o trust≥90)
8. `verification.on_join` — **default LIMPIO**: verificación/bienvenida OFF + revisión de sospechosos por privado ON. Todo por chat vía `/config`.

**`on_message`** — recolecta hits, `decide()`, luego trust score:
- trust ≥70 → SKIP (excepto HARD_RULES: `cas_match`, `lols_match`, `federation_known_ban`, `reaction_farming`)
- trust 40-69 + acción severa → review-with-buttons al admin DM (✅Legítimo/❌Spam, aprende)
- trust 40-69 + acción leve → degrada/noop
- antiflood per-user graduado por trust (5/8/12 msgs en 10s)

## Detectores (`src/detectors/` + `verification.py`)

21 detectores: `obvious_spam_profile`, `bio_spam`, `photos_batch`, `commercial_ad`, `investment_scam`, `contact_spam`, `forward_first_msg`, `first_msg_media`, `inline_buttons`, `external_mention`, `external_reply`, `url_blocklist`, `tg_deeplink`, `non_allowed_script` (unicode_script), `reaction_farming`, `jfm_delta`, `premium_new_link`, `emoji_only`, `dormant_bot_mention`, `cas`, `lols_bot`, `learned_similarity`, `personal_channel_spam`.
También banea spam publicado en nombre de un canal (`sender_chat` → `banChatSenderChat`).

`rule_explain.py` traduce el id técnico de regla a la explicación que lee el admin. **Es el texto más visible del bot** y tiene prioridad sobre el `reason` del detector.

### Los que dependen de Telethon

`bio_spam`, `photos_batch`, `obvious_spam_profile` (parcial) y `personal_channel_spam` leen el perfil vía MTProto. **Sin Telethon no se activan** y el bot sigue funcionando con el resto. Documentado en ambos README, porque quien instale sin cuenta secundaria no sabría qué se pierde.

**El perfil tiene más de un escaparate.** Durante mucho tiempo solo leíamos `about` (la bio). El **canal personal** (Telegram 2024, `personal_channel_id`, disponible desde Telethon 1.36) es un campo SEPARADO: un perfil con la bio vacía puede tener ahí un canal entero de spam. Caso real que lo destapó: cuenta «Matthew», nombre latino, sin foto ni bio, con un canal chino reclutando mulas de blanqueo. Si aparece otro campo nuevo de perfil, mirarlo antes de fiarse de que el perfil está limpio.

`personal_channel_spam` **no salta por tener canal**: eso es legítimo. La señal es la **discordancia** (nombre en alfabeto latino + canal en otro script), que es un disfraz deliberado. Ninguna señal suelta llega al umbral. Lección del caso: el bot ya cazaba a los de esta red que usaban nombre chino; los que se colaban eran los que se ponían nombre occidental.

### Listas negras (`config/blacklist/`)

Tres capas que se **acumulan** (el spam llega en cualquier idioma):

1. `config/blacklist/*.txt` — genéricas, versionadas (11 archivos).
2. `config/blacklist/<lang>/*.txt` — por idioma (`en/` con 9). Se cargan según el idioma activo + `BLACKLIST_LANGS`.
3. `config/blacklist/custom/*.txt` — **las que añade el admin desde Telegram**. Gitignored, para que un `git pull` no las pise.

Cada línea es un **regex**, salvo en `custom/`, donde todo se escapa: es imposible colar un regex activo desde Telegram (`custom_terms.py`). Un patrón inválido se ignora con un log, nunca tumba el bot.

**Añadir un término desde el panel pasa SIEMPRE por vista previa**: `custom_terms.preview_term()` dice con cuántos mensajes reales y recientes del grupo coincidiría, con ejemplos, antes de guardar. Un término como «oferta» caza 3 de cada 4 mensajes de un grupo de informática.

### Anti falso positivo en los patrones

- Las palabras de moneda que son palabras comunes (`peso`, `real`, `sol`, `libra`, `corona`) **solo cuentan pegadas a una cifra**. Hay tests con «el peso del paquete», «hace un sol», «media libra de harina» para que nadie las añada sueltas.
- El importe se escribe distinto por región: `500€` (detrás) y `$500` (delante). Ambas formas soportadas, más `$2000` sin separador.
- Cubierto el español de América: monedas locales, «por día» (patrón central del spam laboral latinoamericano) y voseo (`escribime`, `ganá`, `trabajá`).

### `investment_scam`: cómo detectar sin falsos positivos (patrón a seguir)

Caza el testimonio «di X y me devolvieron Y (mucho mayor)» (caso real: «I gave her 25,000 Rs … she gave me 318,000 Rs 👇 @X»). Sin él se colaba cuando no ponían `@usuario` final. Su diseño es el molde para cualquier detector de contenido nuevo:

- **La señal fuerte no es el tema, es la discordancia.** «Dinero» lo dice todo el mundo; lo raro es «di X y recibí mucho más». El **ancla** es esa estructura numérica (`_GIVE_BACK_RE`, retorno ≥1.5× la entrega), calculada comparando importes, no una palabra suelta.
- **Ninguna señal decide sola** (`señales_estafa < 2 → none()`). Con ancla basta una señal de apoyo; sin ancla hacen falta dos. Así «invertí 1000 y ahora vale 1500» (solo ancla, y `worth` está **fuera** de los verbos de retorno a propósito) no cae, ni «gracias John» (un elogio suelto) tampoco.
- **Refuerzos que nunca deciden**: tiempo («after 12 hours»), primer mensaje. Solo suman si ya hay estructura.

### Convenciones al escribir/editar patrones de detección

- Cada línea de `config/blacklist/**.txt` es un **regex Python** (case-insensitive), acumulativo entre capas. Grupos **NO capturantes** `(?:...)`, nunca `(...)`: rompen el conteo de coincidencias en `compile_alternation`. Un patrón inválido se ignora con un log, no tumba el bot.
- Las listas de vocabulario de `commercial_ad` e `investment_scam` (`*_cta.txt`, `*_work.txt`, `investment_*.txt`) son **editables**; el ancla estructural NO se externaliza (es el núcleo). Documentado en `config/blacklist/README.md`.
- **Nunca un término genérico**: «money», «job», «oferta» solo cazan pegados a estructura. Ante la duda, no se añade. FP > FN.

### Alfabetos permitidos por chat (`/config`)

`ALLOWED_SCRIPTS` del `.env` era **global y sin interfaz**: quien instalara el bot en una comunidad árabe, rusa o griega tenía al bot marcando a sus usuarios normales (medido: un saludo en árabe puntúa 100 con el default `latin`). Ahora hay columna `chat_settings.allowed_scripts` (CSV) donde **NULL = hereda el `.env`**, resuelta por `_chat_allowed_scripts()` en `handlers.py`.

Dos guardas que no se deben quitar:
- **Nunca lista vacía**: sin ningún alfabeto permitido el bot marcaría TODOS los mensajes. El helper cae al `.env` y el panel rechaza quitar el último.
- **NULL = hereda**: con default `'latin'`, una instalación que ya permitía cirílico habría empezado a marcar a los suyos al actualizar.

El panel enseña **qué alfabetos se escriben de verdad en el grupo** (sobre `seen_users.last_msg_text`) y avisa de cuáles causarían falsos positivos: mismo patrón de «ver antes de decidir» que la vista previa de palabras bloqueadas.

### Ajuste `money_guard` por chat (`/config`)

Modula la agresividad de **`commercial_ad` + `investment_scam`** (los de trabajo/dinero). Columna `chat_settings.money_guard` (`'normal'` | `'soft'` | `'off'`), filtro en `_apply_money_guard()` de `handlers.py`:
- `normal` (defecto): caza claros y borderline.
- `soft`: solo score ≥ `_MONEY_SOFT_MIN_SCORE` (100); el borderline de trabajo/dinero pasa. **No** sube la agresividad, solo la baja.
- `off`: esos dos detectores no actúan (el resto sigue).

El filtro vive en el handler, no en los detectores: siguen puros. Botón en el panel principal y por `/config`, respeta `/sync`.

## Aprendizaje (`/spam`, `/legal`)

Naive Bayes + coseno sobre las muestras marcadas por el admin. `BAYES_MIN_SAMPLES_PER_CLASS = 10` de **cada** clase: con 0 muestras ham el Bayes está dormido y solo actúa el coseno.

Salvaguardas para que el bot no aprenda a castigar el vocabulario normal de su grupo:
- Ningún token decide solo el veredicto (tope al log-odds).
- El que aparece en spam Y en ham pesa la mitad: no separa nada.
- El visto una sola vez pesa un tercio: es ruido, no evidencia.
- `classifier_excluded_tokens.txt`: los defaults en código son palabras funcionales del idioma (valen para cualquier comunidad). **El vocabulario temático lo pone cada admin**: solo él conoce su grupo.

`learned_similarity` **no** es HARD_RULE, así que el trust protege: con ≥70 se ignora, entre 40 y 69 va a revisión. El riesgo se concentra en usuarios nuevos.

## Panel `/config` y comandos

Todo ajuste por chat se toca **desde el panel visual y por comando en paralelo**. Con `/sync` ON (por defecto) cada cambio se aplica a TODOS los grupos y el panel no pide grupo.

Panel: sincronización · verificación · revisión de sospechosos · recordatorios · acción al no verificar · tiempos · **Bienvenida ▸** (texto, botones, autoborrado) · reglas · limpiar servicio · **Warns ▸** · top semanal · **Alfabetos permitidos ▸** · **Rigor trabajo/dinero ▸** (`money_guard`) · **Palabras bloqueadas ▸** · **Frases al banear ▸** (con ejemplo real antes de activar) · avisos informativos.

- **Moderación**: `/ban` `/unban` (aceptan @username o reply), `/whitelist`, `/warn` `/warns` `/rmwarn` `/resetwarns` `/warnlimit` `/warnaction`
- **Aprendizaje**: `/spam` `/legal` (alias `/ham`)
- **Info** (chat_admin read-only): `/help` `/comandos` `/stats` `/chats` `/recent` `/samples` `/top` `/topweekly` `/quips` `/scan`
- **Config**: `/config` `/verificacion` `/welcome` `/setwelcome` `/rules` `/setrules` `/cleanservice` `/setwelcomebutton` `/limpieza` `/idioma` `/alertas` `/sync`
- **Alias en inglés** (33 comandos en el menú): `/verification` `/language` `/alerts` `/cleanup` `/commands`. **Los nombres en español SIEMPRE deben seguir funcionando.**

### Bienvenidas

`config/welcomes/<chat_id>.txt` (privado) → `generic.<lang>.txt` → `generic.txt` → fallback traducido.
El genérico por idioma va **antes** que `generic.txt` a propósito: `generic.txt` está en español y, como existe, ganaba al fallback traducido (un usuario inglés recibía bienvenidas en castellano).

El mensaje de verificación **se EDITA** al de «verificación correcta» (no se envía uno nuevo, para no dejar dos mensajes en el chat). Cuánto dura ese mensaje editado lo decide `chat_settings.verified_ttl_s` (**NULL = hereda `VERIFIED_WELCOME_DELETE_AFTER_S`**, defecto 5 min; **0 = no se borra nunca**), resuelto por `_verified_ttl()`.

Dos trampas de ese ajuste:
- **0 es un valor VÁLIDO**, así que no se puede resolver con un `or` (se comería el «nunca» y devolvería el default).
- Se borra en **dos sitios**: el `jq.run_once` al verificar y el **barrido por BD** del `cleanup_job` (que existe porque los jobs en memoria se pierden al reiniciar). Los dos respetan el 0; sin la guarda del barrido, el mensaje «permanente» sobrevivía hasta el siguiente reinicio y luego desaparecía.

Cada línea del catálogo es el saludo COMPLETO (`📥 Bienvenido/a {name}. <gracia temática>`); la cabecera de verificación no saluda, para no duplicar el «Bienvenido/a». El pie fijo y los botones se añaden aparte.

## Jobs programados (`main.py`)

- `_heartbeat_job` (30s) — healthcheck Docker
- `verification.cleanup_job` (15min) — 3 tiers: kick suspicious 30min, reminder normal 3h, kick post-reminder +6h
- `maintenance.cleanup_nightly_job` (24h) — **copia de seguridad** + limpieza + **reconciliación banned_users↔Telegram**
- `topweekly.weekly_top_job` (domingo 20:00 Madrid)

### Copia de seguridad de la BD

`maintenance.backup_database()` corre al principio del job nocturno (antes de limpiar y compactar, para que la copia refleje el estado previo por si el borrado sale mal). Deja `data/backups/antispam-YYYYMMDD.db`, rotando **7 días**.

Usa **`VACUUM INTO`, no una copia del fichero**, por dos motivos medidos en producción:
1. En modo WAL el `.db` puede llevar **días sin checkpoint**: copiarlo a pelo perdía 5 baneos y 20 registros de auditoría.
2. Copiarlo mientras el bot escribe puede dar una foto **inconsistente**; `VACUUM INTO` es íntegra aunque haya escrituras a la vez (probado con 266 concurrentes).

`data/` es gitignored, así que las copias nunca llegan al repo, pero **sí van al N6005** en el rsync semanal (ese bloque no excluye nada). Si la copia falla, se avisa en el log y el mantenimiento continúa: nunca aborta el job.

## Reglas críticas de diseño (lecciones de producción)

1. **NUNCA acciones masivas sin dry-run.** `seen_users.msg_count` NO refleja historial previo al bot: para "nunca escribió" usar Telethon `iter_messages` filtrando service messages (`m.action is None`).
2. **Falsos positivos > falsos negativos**: mejor dejar pasar spam que banear a un legítimo. Ante la duda, no se añade el patrón.
3. **Anti-FP de nombres**: NFKC + `confusable_homoglyphs.is_dangerous`. Cherokee/Thai decorativos NO son spam. Bilingües tampoco. Bypass si cuenta >1 año con foto.
4. **Telethon es último recurso**: solo reportes/bio/fotos/admin_log/histórico. Usar `reporter.get_client()` o copiar la session a `/tmp`, nunca parar el contenedor.
5. **Quips opacos**: no revelar el mecanismo de detección en público. No mencionar lols.bot/CAS por nombre en el grupo.
6. **Sin links clicables a perfiles de spammers** en público: `nombre (id: N)`. Excepción: DM al admin y top semanal.
7. **Castellano correcto**: `Bienvenido/a`, nunca `@`/`x` inclusivo. **Sin em dashes** en textos visibles.
8. **Consentimiento explícito** antes de anclar/editar anclados o cualquier acción pública no reversible.
9. **Reportes a Telegram con criterio**: whitelist de reglas + score alto + rate limit. Protege la reputación de la cuenta secundaria.
10. **Ajustes nuevos que hereden del `.env`**: usar columna NULLable donde NULL = «hereda» (ver `quips.quips_on`). Con default `0`, quien lo tuviera activo por `.env` se queda sin ello al actualizar, en silencio.

## Convenciones de código

- Type hints en funciones públicas. `async def` para todo lo que toque Telegram API.
- Cada detector `check()` con tests (positivos + negativos, **foco en anti-FP**). `ruff check` limpio.
- `seen` es `sqlite3.Row`, NO dict: usar `row["col"]`; **`.get()` NO existe en Row** (causó un bug que impedía ejecutar bans). Hay meta-test.
- `callback_data` tiene **64 BYTES** de tope: nunca metas texto del usuario dentro, usa un hash o índice.
- Migraciones de BD: `ALTER TABLE` blando en `_migrate()`, y añadir el campo a `ALLOWED` de `update_chat_setting`.
- Commits convencionales. Co-Author: `Claude Opus`.

## Flujo de trabajo típico

```bash
.venv/bin/python -m pytest tests/ -q          # 798 tests
.venv/bin/ruff check src/ tests/
sudo -n docker compose restart                # o up -d si cambia .env o requirements
sudo -n docker logs cazaspam-bot --tail 5     # verificar "Bot ... listo"
git add -A && git commit -m "..." && git push
```

**`restart` recarga el código (src/ montado por volumen) pero NO el `.env`**: para eso hace falta `up -d`.

## Docs detalladas

`docs/ARCHITECTURE.md`, `docs/ECOSYSTEM.md`, `docs/ROADMAP.md`, `docs/LEARNING.md`.
`CHANGELOG.md` (hitos por fecha, lo más reciente arriba).
`src/locales/README.md` (traductores) · `config/blacklist/README.md` (listas) · `config/welcomes/README.md`.

## Tráfico del repo (visitas y clones)

GitHub solo guarda **14 días** de tráfico y luego lo tira. `scripts/traffic_log.py`
lee esa ventana vía `gh` y la **acumula** en `traffic/history.json`, para construir
el histórico que GitHub no conserva. **Ejecutarlo un par de veces al mes** (dentro
de esos 14 días) basta para no perder ningún día.

```bash
.venv/bin/python scripts/traffic_log.py          # lee vía gh y fusiona por fecha
.venv/bin/python scripts/traffic_log.py --show    # muestra lo guardado sin llamar a la API
```

Idempotente: fusiona por fecha, así que ejecutarlo de más nunca infla las cifras.
El histórico vive en `traffic/` (**gitignored**, no en `data/`, que es del contenedor
Docker como root). Ojo al leer los números: los **clones** suelen ser bots que
rastrean GitHub, no gente; la señal de interés real son los **visitantes web únicos**.

*Actualizado: 2026-07-23 — bilingüe es/en, 21 detectores (+investment_scam), 831 tests, panel completo, ajuste money_guard, registro de tráfico local.*
