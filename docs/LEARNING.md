# Sistema de aprendizaje activo del bot

> Cómo el bot mejora con cada decisión humana. Implementado 2026-05-23.

## Filosofía

Los detectores estáticos (URL blocklist, unicode script, CAS) tienen cobertura limitada. Para que el bot **mejore con el tiempo**, cada decisión del admin alimenta una base de samples local que un detector posterior usa para comparar.

Patrón inspirado en `umputun/tg-spam` adaptado a nuestro stack Python.

## Comandos de entrenamiento

| Comando | Cuándo se usa | Efecto |
|---|---|---|
| `/spam` (respondiendo a un mensaje) | El admin ve un mensaje claramente spam | Añade texto normalizado a `learning_samples` con `label='spam'` + opcionalmente bania al user |
| `/ham` (respondiendo a un mensaje) | El admin ve un mensaje legítimo que el bot marcó por error | Añade texto a samples con `label='ham'` + suprime regla 7 días |
| `/notspam <action_id>` (DM o grupo) | Tras ver una notificación con botones | Revierte ban + añade contexto a samples ham |

## Tabla SQLite

```sql
CREATE TABLE learning_samples (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    text_norm     TEXT NOT NULL,     -- texto post-normalización (NFKC + ZW strip + lowercase)
    text_hash     TEXT NOT NULL,     -- xxhash 64-bit para dedup rápido
    label         TEXT NOT NULL,     -- 'spam' | 'ham'
    added_by      INTEGER NOT NULL,  -- user_id del admin que etiquetó
    chat_id       INTEGER,           -- chat donde se vio originalmente
    source_user   INTEGER,           -- user_id del autor del mensaje
    ts            REAL NOT NULL
);
CREATE UNIQUE INDEX idx_samples_hash_label ON learning_samples(text_hash, label);
```

Dedup: un mismo texto solo se guarda 1 vez por label (índice único en `text_hash + label`).

## Detector `learned_similarity`

Compara cada mensaje nuevo (normalizado) contra los samples spam recientes (últimos 90 días). Usa **cosine similarity sobre TF-IDF char-ngrams** (3-5 chars) — barato, multi-idioma, robusto a typos.

Si similarity > 0.6 contra cualquier sample spam → score 70 (zona kick).
Si similarity > 0.8 → score 100 (zona ban).
Si similarity > 0.5 contra cualquier sample HAM → reduce score acumulado en 30 (penalización contra falsos positivos).

Implementación: `sklearn.feature_extraction.text.TfidfVectorizer` con `analyzer='char_wb', ngram_range=(3,5)`.

## Normalización (compartida con el resto de detectores)

```python
import re, unicodedata
ZW = re.compile(r'[​-‍⁠﻿᠎]')

def normalize(text: str) -> str:
    if not text:
        return ""
    t = ZW.sub("", text)
    t = unicodedata.normalize("NFKC", t)
    return t.casefold().strip()
```

Esto cierra evasiones comunes: zero-width chars, homoglyphs Unicode, casing.

## Ciclo de mejora

```
detección                etiqueta humana            entrena clasificador     mejor detección
─────────                ────────────────           ──────────────────        ────────────────
spam pasa filtros    →   admin /spam reply    →    spam_sample en SQLite  →  futuras vars similares
de reglas estáticas      añade sample              actualiza vectorizer       se cazan automáticamente

falso positivo       →   admin /ham reply     →    ham_sample en SQLite   →  reduce score en mensajes
del bot                  suprime regla 7d         actualiza vectorizer       similares
```

## Comandos auxiliares

| Comando | Para qué |
|---|---|
| `/samples` | Estadísticas: cuántos spam, ham, edad media |
| `/samples spam 20` | Lista últimos 20 samples spam (truncados) |
| `/samples ham 20` | Lista últimos 20 samples ham |
| `/forget <sample_id>` | Borra un sample si fue añadido por error |

## Persistencia y backup

- Los samples viven en `data/antispam.db` (mismo SQLite que todo).
- Conviene incluir `data/` en tus backups (la DB contiene el aprendizaje acumulado).
- Si se restaura el contenedor, los samples se conservan en el volumen `./data`.

## Métricas a vigilar

- **Crecimiento**: el bot debería acumular >100 samples spam en el primer mes
- **Ratio spam/ham**: idealmente 70/30. Si ham < 10%, el clasificador tendrá sesgo
- **Precisión esperada**: con 500+ samples spam, similarity 0.6+ debería detectar el 80% del spam con cadena/template repetida

## Limitaciones

- Solo detecta spam con **patrones de texto similares** a algo previamente etiquetado. Spam totalmente nuevo no se caza por aquí (lo harán los detectores estáticos).
- Mensajes muy cortos (<10 chars) tienen poca señal — el clasificador los ignora.
- Si el admin etiqueta mal (marca como spam algo legítimo), corromperá el clasificador. Usar `/forget` para corregir.
