# Roadmap — gaps priorizados

> Lista de mejoras pendientes ordenadas por impacto/dificultad.
> Fuente: análisis de los líderes GitHub (tg-spam, shieldy, DaisyX, MissRose, etc.) 2026-05-23.
> Cada item: descripción, repo de origen, dificultad (LOW/MED/HIGH), código de ejemplo si aplica.

## P1 — Prioritarios (alto impacto, baja/media dificultad)

### ✅ 1. Sistema de aprendizaje básico (/spam /ham)
**Estado**: implementado 2026-05-23.
**Origen**: umputun/tg-spam
**Cómo**: tabla `learning_samples(text_norm, label, user_id, ts)` + comandos `/spam` reply (label=spam) y `/ham` reply (label=ham). Detector `learned_similarity` compara cosine TF-IDF con samples spam recientes.

### 2. Lookup en lols.bot API
**Origen**: lols.bot
**Dificultad**: LOW
**Cómo**: Drop-in al lado del CAS lookup. `GET https://api.lols.bot/check?user_id=N`. Suma score. Mayor cobertura combinada.

### 3. Bayes/similarity classifier completo
**Origen**: umputun/tg-spam
**Dificultad**: MED
**Cómo**: TF-IDF light con `sklearn.feature_extraction.text` (sklearn = ~50MB, pero potente). Threshold cosine=0.5 contra samples. Cada `/notspam`/`/spam` del admin alimenta.

### 4. Abnormal-spacing detector
**Origen**: tg-spam `--space.enabled`
**Dificultad**: LOW
**Detalle**: ratio `spaces/chars > 0.4` o `>70% palabras de ≤2 chars` → score alto.

### 5. Zero-width + NFKC normalizer pre-detección
**Origen**: arxiv visual spoofing
**Dificultad**: LOW
**Código**:
```python
import re, unicodedata
ZW = re.compile(r'[​-‍⁠﻿᠎]')
def normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', ZW.sub('', text))
```
Llamar en `detectors/__init__.py` antes de cada detector que mire texto.

### 6. Emoji-substitution detection
**Origen**: TechRadar 2025 + tg-spam
**Dificultad**: LOW
**Cómo**: `emoji.demojize(text)` antes de blocklist. Sumar `emoji_ratio > 0.3` como señal.

### 7. Forward de canal sospechoso
**Origen**: pugson/telegram-crypto-antispam-bot, ecasbot
**Dificultad**: LOW
**Cómo**: `message.forward_origin.chat.id` o `username` contra blocklist en `.env`. Especialmente útil para spam crypto/casino que se reenvía masivamente.

### 8. Duplicate-message detector cross-chat
**Origen**: tg-spam `--duplicates.threshold`
**Dificultad**: LOW
**Cómo**: hash xxhash o md5 del texto normalizado en tabla `recent_msgs(hash, user_id, chat_id, ts)`. Window 1h. 3 idénticos en N chats = spam de cadena → ban federado.

### 9. Aggressive cleanup post-ban
**Origen**: tg-spam `--aggressive-cleanup`
**Dificultad**: LOW
**Cómo**: al banear, borrar todos los mensajes recientes del user (últimas 100 o últimas 24h) en TODOS los chats federados. Usa `moderation_log` para encontrar `message_id`s.

### 10. Meta-checks (contact, image-only, video-only, sticker spam)
**Origen**: tg-spam meta filters
**Dificultad**: LOW
**Detalle**: `if message.contact and len(text)<10` → spam ("te dejo mi WhatsApp"). Sticker-only en primer mensaje = bot.

## P2 — Secundarios

### 11. Soft-ban (mute permanente sin echar)
**Origen**: tg-spam `--soft-ban`
**Dificultad**: LOW
**Razón**: falsos positivos reversibles más fácilmente.

### 12. Reputation graduation explícita
**Origen**: tg-spam approved-users
**Dificultad**: LOW
**Cómo**: N=5 mensajes "normales" → user pasa a "approved" → skip checks. Auto-whitelist progresivo.

### 13. Antiraid (detecta N joins en M segundos)
**Origen**: MissRose, SophieBot
**Dificultad**: LOW
**Cómo**: window check sobre `seen_users.join_ts`. Si >5 joins en 30s → mute global X minutos.

### 14. Antiflood per-user
**Origen**: MissRose, tg-spam `--max-short-msg-count`
**Dificultad**: LOW
**Cómo**: N mensajes en M segundos del mismo user → mute.

### 15. Web UI / dashboard local Flask
**Origen**: tg-spam web UI
**Dificultad**: MED
**Cómo**: `/check`, `/samples`, `/stats`, `/users`. Endpoint en :3580. Útil con ttyd ya montado en el servidor.

### 16. Comandos /warn con escalado
**Origen**: tg-spam, MissRose
**Dificultad**: LOW
**Cómo**: 3 warns en 720h → ban. Tabla `user_warns(user_id, chat_id, ts, reason)`.

### 17. Crowdsourced /report con threshold
**Origen**: tg-spam
**Dificultad**: LOW
**Cómo**: 3 reports independientes de 3 users distintos en X minutos → revisión admin.

### 18. Username-symbol blocklist
**Origen**: tg-spam `meta.username-symbols`
**Dificultad**: LOW
**Cómo**: emojis/zalgo en username = baneo inmediato al join. Lista de chars sospechosos.

### 19. ML-based clasificador (DistilBERT/siglip)
**Origen**: englishtea21/spammers-hunter, Priler/samurai
**Dificultad**: HIGH (CPU/RAM)
**Razón**: precisión alta pero pesa modelo ~250MB + carga RAM. Solo si vemos muchos falsos negativos.

### 20. LLM veto opcional para zona gris
**Origen**: tg-spam OpenAI/Gemini veto
**Dificultad**: MED
**Cómo**: si score entre `MUTE_SCORE` y `BAN_SCORE`, pasar al LLM (Claude Haiku) con prompt cache. Coste bajo (~$0.001/msg gris).

## DESCARTAR (no implementar)

- **Captcha de join** (shieldy, teleward): el usuario lo rechazó explícitamente
- **NSFW detection de fotos** (Priler/samurai): coste CPU alto en N100
- **Auto-traducción Google Translate** (OriginProtocol): el detector unicode ya cubre
- **Federation cross-org pública**: vector de envenenamiento, riesgo > beneficio
- **Lua plugins** (tg-spam): overkill, Python directo es suficiente
- **Postgres support**: SQLite WAL sobra para volumen actual
- **Profanity filter**: antispam ≠ moderación de lenguaje (scope creep)

## Orden sugerido de implementación

1. ✅ Sistema /spam /ham + tabla samples (P1.1) — base para el resto
2. Zero-width + NFKC + emoji-demojize normalizer (P1.5+P1.6) — fácil y mejora TODOS los detectores
3. Forward de canal sospechoso (P1.7) — alta efectividad contra spam crypto
4. lols.bot lookup (P1.2) — más cobertura sin esfuerzo
5. Abnormal spacing + duplicate detector (P1.4+P1.8) — cierra evasiones comunes
6. Aggressive cleanup (P1.9) — UX importante post-ban
7. Antiraid + antiflood (P2.13+P2.14) — defensa contra ataques organizados
8. Reputation graduation + soft-ban (P2.11+P2.12) — UX para falsos positivos
9. (opcional) Web UI dashboard (P2.15)
10. (opcional) LLM veto (P2.20) o ML classifier (P2.19)
