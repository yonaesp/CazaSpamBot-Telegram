<div align="center">

# 🛡️ CazaSpamBot

### Bot antispam para Telegram con bans sincronizados, aprendizaje y cero falsos positivos

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-21.6-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.36-blueviolet)](https://docs.telethon.dev/)
[![Tests](https://img.shields.io/badge/tests-227%20passing-success)](#-tests)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

*Modera todos los grupos que quieras, 24/7. Diseñado para que el usuario medio nunca note que existe… hasta que cae un spammer.*

</div>

---

## ✨ Qué hace

CazaSpamBot vigila tus grupos de Telegram y elimina el spam **antes de que moleste**, con una obsesión: **nunca banear a un usuario legítimo**. Prefiere dejar pasar un spam dudoso que expulsar a una persona real.

- 🔗 **Bans sincronizados** — un ban en un grupo = ban en **todos** tus grupos (lo que otros bots llaman *federación*). Sin primitiva nativa: itera sobre los chats donde es admin.
- 🧠 **19 detectores** combinados con un sistema de confianza graduado.
- 🤫 **Moderación silenciosa** — los bans automáticos no ensucian el chat.
- 📚 **Aprendizaje activo** — aprende de tus `/spam` y `/legal` (Naive Bayes + similitud coseno).
- 🛰️ **Reportes oficiales** a Telegram (Native Antispam) vía MTProto.
- ⚙️ **Personalizable sin tocar código** — bienvenidas, listas negras e idiomas permitidos se configuran en archivos de texto y `.env`.

Funciona con **cualquier número de grupos** (auto-descubre aquellos donde es admin, o limítalo con `MODERATED_CHAT_IDS`). Los textos del bot están en español, pero la detección es independiente del idioma del grupo: tú decides qué alfabetos son normales en tu comunidad.

---

## 🛡️ Cómo protege

### Al entrar alguien nuevo

```
¿Ya lo baneó antes el bot en otro de TUS grupos?  ──► re-ban
¿Perfil claramente spam?    ──► ban directo, silencioso
   · nombre en alfabetos no habituales (≥2 campos)
   · bio con invite porno/promo + emojis + keywords
   · fotos subidas todas de golpe (identidad robada)
¿En listas globales (CAS / lols.bot)?  ──► ban (umbral configurable)
¿Es un bot añadido al grupo?           ──► kick + aviso al admin
¿Perfil muy legítimo? (foto + >1 año + nombre normal)  ──► entra directo, saludo amistoso
El resto  ──► bienvenida con botón "SOY HUMANO" (muteado hasta pulsar)
```

> **Bans sincronizados ≠ listas globales.** La sincronización (la "federación" de Rose y otros bots) es interna: tus propios bans replicados entre tus grupos. **CAS** ([cas.chat](https://cas.chat), de Combot) y **lols.bot** son bases de datos colaborativas mundiales de spammers ya cazados en miles de grupos. Con CAS decides lo estricto con `CAS_AUTOBAN_MIN`: `2` (por defecto) banea solo si está confirmado en 2+ grupos y te manda a revisión los casos con 1; `1` banea con cualquier señal (más agresivo, más falsos positivos). Los usuarios de confianza alta nunca se banean por lista sin pasar antes por tu revisión.

### En cada mensaje

| Detector | Caza |
|---|---|
| `non_allowed_script` | Texto en alfabetos no permitidos (configurable con `ALLOWED_SCRIPTS`) |
| `external_mention` | Menciones/enlaces a otros grupos |
| `url_blocklist` · `tg_deeplink` | Acortadores y deep-links de phishing |
| `commercial_ad` | Anuncios (sueldos, "trabaja desde casa", cripto, servicios ilegales) |
| `contact_spam` | Tarjeta de contacto compartida cuyo nombre es el anuncio (otro alfabeto o con enlaces) |
| `external_reply` | Promoción de un canal externo mediante cita a otro chat (el "quote" que lleva fuera) |
| `bio_spam` | Bio del perfil con promo porno/comercial/hacking |
| `forward_first_msg` | Forward de canal en el primer mensaje |
| `first_msg_media` · `inline_buttons` | Foto/botones sospechosos al empezar |
| `photos_batch_upload` | 3+ fotos de perfil subidas en segundos |
| `obvious_spam_profile` | Perfil con múltiples señales de bot |
| `reaction_farming` | Cuentas que solo dan likes sin escribir |
| `dormant_bot_mention` | Cuenta dormida >1 año que reaparece citando un bot (hackeada) |
| `emoji_only` | Primer mensaje que es solo una ristra de emojis sin texto |
| `jfm_delta` | Primer mensaje sospechosamente rápido tras entrar (<90s = bot) |
| `premium_new_link` | Cuenta Premium recién creada que entra posteando enlaces |
| `cas` · `lols_bot` | Spammers fichados en las listas globales CAS y lols.bot |
| `learned_similarity` | Lo que aprendió de tus `/spam` |
| `antiflood` | Inundación de mensajes por usuario |

También banea el **spam publicado "en nombre de un canal"** (`sender_chat` → `banChatSenderChat`) en grupos de comentarios, cuando dispara una regla fuerte. Con **`/scan`** (responde a un mensaje reenviado) puedes comprobar de antemano si el bot detectaría cualquier mensaje y qué estructura tiene.

### Niveles de confianza (anti-falsos-positivos)

Cada usuario tiene un **nivel de confianza del 1 al 10** (sube con mensajes y antigüedad en el grupo, baja con warns; whitelist = 10 directo):

- **Nivel 7-10** (veteranos) → prácticamente intocables.
- **Nivel 4-6** + algo sospechoso → el bot **pregunta al admin por privado** con botones ✅ Legítimo / ❌ Spam, y **aprende** de la respuesta.
- **Nivel 1-3** (nuevos) → moderación normal.

Cada alerta incluye también un **nivel de spam 1-10** del mensaje, para que se entienda de un vistazo.

Refuerzos: **NFKC + [confusable_homoglyphs](https://github.com/vhf/confusable_homoglyphs) (UTS#39)** para no confundir nombres decorativos (Cherokee, matemáticos, mezclas) con spam. Bypass para cuentas antiguas con foto.

---

## 🎨 Personalización sin tocar código

| Qué | Dónde | Cómo |
|---|---|---|
| Saludos de bienvenida | `config/welcomes/` | Una frase por línea, `{name}` para el nombre. `generic.txt` para todos los grupos, `<chat_id>.txt` para frases temáticas de un grupo concreto. Desactivables con `FRIENDLY_WELCOMES_ENABLED=false`. |
| Palabras/frases de la lista negra | `config/blacklist/` | Un patrón por línea (palabra o regex). Anuncios ilegales, keywords de bio, etc. Si borras un archivo, el bot usa los valores por defecto. |
| Alfabetos permitidos | `.env` → `ALLOWED_SCRIPTS` | CSV: `latin`, `cyrillic`, `arabic`, `han`, ... según el idioma de tu comunidad. |
| Rigor con la lista CAS | `.env` → `CAS_AUTOBAN_MIN` | `2` = banear solo confirmados en 2+ grupos (recomendado); `1` = banear con cualquier señal. Por debajo del umbral, te lo manda a revisar. |
| Acortadores bloqueados | `.env` → `URL_BLOCKLIST` | CSV de dominios. |
| Umbrales y acciones | `.env` | Scores de ban/kick/mute, acción ante primer mensaje sospechoso, etc. |
| Bienvenida fija por grupo | comando `/setwelcome` | Sin tocar archivos, desde el propio Telegram. |
| Verificación humana por grupo | comando `/verificacion` | Desde Telegram, por grupo. Ver abajo. |

Cada carpeta tiene su `README.md` con el formato explicado.

### Panel de ajustes con botones (comando `/config`)

La forma **visual y recomendada** de configurar cada grupo, sin recordar subcomandos. Escribe `/config` (alias `/ajustes`, `/panel`) en el grupo, o **en el DM del bot** para elegir el grupo con botones. Aparece un panel que se actualiza al instante al pulsar:

- 🔗 **Sincronizar todos los grupos** on/off (ver abajo)
- 🛡️ **Verificación** on/off · 👁️ **Revisar sospechosos en privado** on/off · 🔔 **Recordatorios** on/off
- 🚪 **Al no verificar**: Expulsar / Silenciar · ⏱️ **Tiempos** (submenú con presets)
- 👋 **Bienvenida** on/off · ✏️ **Editar bienvenida** · 📜 **Editar reglas** (al editar eliges **Todos los grupos** o **uno concreto**, y el bot te muestra un ejemplo para escribir el texto directamente)
- 🧹 **Limpiar mensajes de servicio** on/off · 🔔 **Avisos informativos**

Es un atajo con la misma persistencia que los comandos sueltos de abajo; usa el que prefieras. Solo el admin del bot puede tocarlo.

**Bienvenida independiente de la verificación**: la bienvenida (👋) es un interruptor aparte. Puedes tener **bienvenida sin verificación** (saluda al entrar, sin botón *SOY HUMANO* ni mute, se autoborra), verificación sin más, o ambas. Por defecto la bienvenida está **OFF** (grupo silencioso).

### Sincronizar ajustes entre grupos (comando `/sync`, opción 🔗 en `/config`)

**Activada por defecto.** Cuando la sincronización está **ON**, cualquier cambio de ajuste se aplica **a la vez a todos los grupos** donde el bot es admin (quedan idénticos), el texto de bienvenida es común (usa `{chat}` para el nombre del grupo y `{name}` para el usuario), y el panel `/config` **no pide elegir grupo** (configuras "para todos"). Ponla **OFF** (`/sync off` o el botón 🔗) para configurar cada grupo por separado, con selector de grupo. `/sync` sin argumentos muestra el estado.

### Verificación humana (comando `/verificacion`)

**Por defecto viene en modo LIMPIO**: verificación y bienvenida **OFF** (el grupo no se
molesta con mensajes de bienvenida ni botón *SOY HUMANO*), y **revisión de sospechosos
por privado ON**: cuando entra un perfil claramente dudoso, te llega un aviso **privado**
(a tu DM o al chat/canal de `ADMIN_NOTIFY_CHAT_ID`) con botones **✅ Permitir** / **🔨 Banear**
y el usuario entra permitido por defecto. La moderación de mensajes (spam, contactos,
listas, etc.) sigue activa igualmente. Todo esto se cambia por grupo con `/config` o
`/verificacion`.

Todo por grupo, desde el propio Telegram (solo el admin del bot). `/verificacion` sin nada muestra el estado y las opciones:

| Subcomando | Qué hace |
|---|---|
| `/verificacion on\|off` | Activa/desactiva la verificación (botón *SOY HUMANO* + mute al entrar) **y** el mensaje de bienvenida a la vez. **OFF por defecto** = los nuevos entran directos. |
| `/verificacion revisar on\|off` | **Modo revisión** (**ON por defecto**). En vez de verificar en el grupo, cuando entra un perfil dudoso te llega un aviso **privado** (a tu DM o al canal configurado) con botones **✅ Permitir** / **🔨 Banear**. El usuario entra **permitido por defecto**; si no haces nada, se queda. Solo avisa de perfiles con señal real (nombre en otro alfabeto, sin foto, cuenta reciente…), no por cada usuario sin @username. El propio aviso trae además dos **toggles rápidos** (se actualizan al pulsar): **🛡️ Verificación humana ON/OFF** y **🔔 Avisos de sospechosos ON/OFF**, para activar la verificación del grupo o silenciar estos avisos sin salir de la notificación. |
| `/verificacion avisos on\|off` | Enviar (o no) un recordatorio a los normales antes de expulsarlos. |
| `/verificacion accion kick\|mute` | Qué pasa con un normal que no verifica: **kick** (expulsar) o **mute** (queda muteado para siempre, sin kick; puede verificar cuando quiera). |
| `/verificacion tiempos <susp_min> <recordatorio_h> <kick_h>` | Tiempos: sospechosos se expulsan a los `susp_min` minutos; a los normales se les avisa a las `recordatorio_h` horas y se les expulsa `kick_h` horas después. Ej: `/verificacion tiempos 30 3 6`. |

> Los usuarios con **perfil sospechoso** siempre se expulsan al pasar su tiempo (es la capa de seguridad); las opciones `avisos`/`accion` aplican a los usuarios **normales**. La moderación de mensajes (spam, listas negras, etc.) es independiente y sigue activa aunque desactives la verificación.

---

## 🧰 Stack

| Componente | Tecnología |
|---|---|
| Bot API (async polling) | `python-telegram-bot[ext]` 21.6 |
| MTProto (bio, fotos, reportes oficiales) | `Telethon` 1.36 |
| Base de datos | SQLite (WAL) |
| Clasificador | Naive Bayes + coseno (stdlib, sin sklearn) |
| Homóglifos | `confusable-homoglyphs` (UTS#39) |
| Despliegue | Docker Compose |

> **Telethon es opcional** (pero recomendable): requiere una cuenta de usuario secundaria. Sin configurarlo, o con `TELETHON_ENABLED=false`, el bot funciona solo con Bot API: las funciones que dependen de él (leer bios, fotos de perfil, reportes oficiales) simplemente no se activan y todo lo demás sigue igual.

---

## 🚀 Puesta en marcha

Configura las credenciales de una de estas dos formas (elige la que prefieras):

**Opción A — Asistente interactivo** (recomendado si es tu primera vez). Te
pregunta paso a paso y te dice de dónde sacar cada dato. No necesita nada
instalado (solo Python 3). Si ya está configurado, no molesta:

```bash
python3 scripts/setup.py          # crea el .env respondiendo unas preguntas
# (para rehacerlo a propósito:  python3 scripts/setup.py --force)
```

**Opción B — A mano** (si te manejas con archivos de texto):

```bash
cp .env.example .env
nano .env    # reemplaza TELEGRAM_BOT_TOKEN y ADMIN_USER_ID; el resto tiene defaults
```

En ambos casos, lo obligatorio son solo esos dos valores. Los de aquí son
**inventados**, solo para ver el formato:

```ini
# Token que te da @BotFather al crear el bot (/newbot):
TELEGRAM_BOT_TOKEN=8123456789:AAF-EsteTokenEsFalsoReemplazaloPorElTuyo00
# Tu user_id numérico de Telegram (te lo dice @userinfobot):
ADMIN_USER_ID=123456789
```

Después, levanta y verifica:

```bash
docker compose up -d --build
docker compose logs -f            # "Bot @... listo. Modo=shadow"
```

El `.env.example` está comentado paso a paso y cada variable trae un **ejemplo inventado** del formato: dónde crear el bot (@BotFather), cómo saber tu user_id (@userinfobot, @getidsbot), cómo obtener las credenciales de Telethon, etc.

> ⚠️ Los valores de ejemplo son **falsos**: reemplázalos siempre por los tuyos. Nunca subas tu `.env` a git (ya está en `.gitignore`).

**No tienes que crear ninguna carpeta a mano.** La carpeta `data/` (base de datos, sesión, heartbeat) se crea sola al levantar el contenedor, y `config/` (bienvenidas y listas negras) ya viene en el repo con valores por defecto. Solo escribes en `data/`, que es el único volumen con permiso de escritura.

*(Opcional, solo si activas Telethon)* la sesión se genera **dentro del contenedor**, una única vez:

```bash
# 1) Telegram envía un código a la app de la cuenta secundaria:
docker compose exec antispam-bot python -m scripts.telethon_login request
# 2) Confírmalo con el código recibido (añade tu contraseña 2FA al final si la tienes):
docker compose exec antispam-bot python -m scripts.telethon_login confirm 12345
```

**Requisitos del bot en Telegram**: admin de los grupos con permisos de *borrar mensajes* y *expulsar usuarios*, y **Privacy Mode desactivado** (BotFather → `/setprivacy` → Disable) para que vea todos los mensajes.

**¿Dónde recibes los avisos?** Dos opciones (`ADMIN_NOTIFY_CHAT_ID` en el `.env`): por **DM privado** contigo mismo (déjalo vacío) o en un **grupo de moderación** (pon su `chat_id`). Si eliges el DM, **abre tu bot y pulsa START una vez** — Telegram no deja que un bot te escriba primero, así que sin ese START no te llegarán los avisos.

**Consejo**: arranca en `MODE=shadow` (solo registra lo que haría, sin actuar), revisa unos días el log, y cuando confíes pásalo a `MODE=active`.

---

## 💬 Comandos principales

Solo el **admin del bot** (`ADMIN_USER_ID`) puede ejecutar acciones; los **admins de los grupos** pueden consultar información; al resto de usuarios el bot los ignora en silencio.

| Comando | Qué hace |
|---|---|
| `/help` · `/comandos` | Guía completa de cómo funciona el bot |
| `/ban @user razón` · `/unban @user` | Ban/unban en todos tus grupos a la vez (acepta reply, @username o id) |
| `/warn` `/warns` `/rmwarn` `/warnlimit` | Sistema de avisos progresivos |
| `/spam` · `/legal` | Enseña al clasificador (reply a un mensaje) |
| `/whitelist @user` | Marca a un usuario como inmune |
| `/stats` `/recent` `/top` `/topweekly` | Métricas y rankings |
| `/config` (alias `/ajustes` `/panel`) | Panel de ajustes con botones (verificación, bienvenida, reglas, tiempos...) |
| `/sync on\|off` (alias `/sincronizar`) | Sincronizar ajustes iguales en todos los grupos (ON por defecto) |
| `/setwelcome` `/setrules` `/welcome` `/rules` `/cleanservice` | Configurar bienvenida, reglas y limpieza de mensajes de servicio |
| `/scan` (alias `/analizar`) | Analiza un mensaje (responde a él): ¿lo detectaría? y qué estructura tiene |
| `/alertas` | Activa o silencia los avisos informativos (borrados, bans de otros admins...) |
| `/notspam <id>` | Revierte un falso positivo (deshace el ban y aprende) |
| `/forget <id>` | Borra una muestra del clasificador |
| `/shadow on/off` | Modo prueba (solo loggea) / activo |

Los miembros del grupo pueden reportar con **`@admin`** (reply a un mensaje); el bot avisa al admin y, si actúa, agradece al reporter.

---

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 227 tests
```

Cada detector tiene tests de casos positivos **y negativos** (énfasis en anti-falsos-positivos). Filosofía: *un falso positivo es peor que un falso negativo.*

---

## 📁 Estructura

```
src/
├── main.py              # entry point, handlers, jobs
├── handlers.py          # on_message, on_chat_member, _apply_action
├── verification.py      # bienvenida + botón SOY HUMANO + 3 tiers
├── federation.py        # ban federado cross-group
├── detectors/           # un módulo por detector
├── wordlists.py         # carga de listas negras editables
├── trust.py             # niveles 1-10 de confianza y spam
├── ban_announce.py      # consolidación de quips en ráfaga
├── learning.py          # Naive Bayes + coseno
├── reporter.py          # reportes oficiales (Telethon)
└── db.py                # SQLite + migraciones
config/
├── welcomes/            # saludos editables (genérico + por grupo)
└── blacklist/           # palabras/regex antispam editables
docs/                    # ARCHITECTURE, ROADMAP, ...
tests/                   # 227 tests
```

---

## 🔒 Seguridad

- Secretos e identificadores solo en `.env` (gitignored). `.env.example` con valores vacíos.
- Sesión Telethon (`*.session`) nunca se sube. Usa una **cuenta secundaria**, no la personal.
- La cuenta secundaria reporta con criterios estrictos (whitelist de reglas + rate limit) para no perder reputación en Telegram.

---

## 📄 Licencia

[GPL-3.0](LICENSE) — úsalo, modifícalo y compártelo libremente; los forks y derivados deben seguir siendo código abierto.

---

<div align="center">
<sub>Hecho con cariño y mucho café para mantener comunidades limpias.</sub>
</div>
