<div align="center">

# 🛡️ CazaSpamBot: bot antispam para Telegram

### Analiza a quien escribe, no solo lo que escribe.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-22.8-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.44-blueviolet)](https://docs.telethon.dev/)
[![Idiomas](https://img.shields.io/badge/idiomas-es%20%7C%20en%20%7C%20a%C3%B1ade%20el%20tuyo-orange)](src/locales/README.md)
[![Tests](https://img.shields.io/badge/tests-1681%20passing-success)](#tests)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

🌍 [**English**](README.md) · **Español**

**[Qué lo hace distinto](#distinto)** · **[Instalar en 5 minutos](#instalacion)** · **[Preguntas frecuentes](#faq)**

</div>

---

**CazaSpamBot** es un bot antispam para quienes administran grupos de Telegram: gratuito, de código abierto y para instalar en tu propio servidor. Un bot normal solo ve el mensaje. CazaSpamBot puede analizar además el perfil de quien lo envía, el texto que va dentro de las imágenes y el contenido de las historias, y así caza el spam que, leyendo solo el mensaje, parece limpio.

- **Ve lo que un bot normal no ve.** Con una cuenta secundaria de Telegram que tú autorizas (opcional), lee la bio, el canal personal, las fotos de perfil y las historias de quien escribe.
- **Lee el texto de las imágenes.** Extrae con OCR el texto de carteles y capturas, en tu servidor y sin GPU, y lo juzga como si estuviera escrito.
- **Aprende de tu grupo.** De tus decisiones y, por su cuenta, de los bans seguros y de las conversaciones normales. Todo en local, sin IA externa.
- **Prudente y discreto.** Lo dudoso te lo consulta por privado, con botones, en lugar de banear, y no llena el grupo de avisos. Puedes empezar en modo prueba, sin banear a nadie.
- **Fácil de poner en marcha.** Se instala copiando y pegando unos pocos comandos y se maneja desde Telegram, con el panel `/config`.

> [!NOTE]
> **En producción.** Instalación de referencia: 4 grupos, de mayo a octubre de 2026.
> - Ha sacado él solo a **más de 1.300 cuentas** sospechosas o de spam, **casi 9 de cada 10 antes de que escribieran una sola palabra**.
> - Los bans que los admins tuvieron que hacer a mano bajaron de **41 en mayo a 4 o 5 al mes**: cada spam que se escapa le enseña a cazar el siguiente.
> - El spam sigue llegando, pero cae en la puerta y en el grupo apenas se nota.

---

<a id="distinto"></a>

## 👁️ Por qué caza más spam que un bot normal

Un bot de Telegram solo ve **el mensaje**. La mayoría de bots antispam, incluidos los más usados, se quedan ahí porque es lo único que da la Bot API.

CazaSpamBot puede usar además **una cuenta normal de Telegram que tú autorizas**, igual que cuando abres sesión en otro dispositivo (por **MTProto**, el protocolo de las apps oficiales). Con ella ve también **a quien escribe el mensaje**:

| Lo que mira | Un bot normal | CazaSpamBot con cuenta secundaria |
|:---|:---:|:---:|
| El texto del mensaje | ✅ | ✅ |
| La **bio** del perfil | ❌ | ✅ |
| El **canal personal** del perfil y lo que publica en él | ❌ | ✅ |
| **Cuándo se subió** cada foto de perfil (cuentas montadas en un rato) | ❌ | ✅ |
| Lo que dice una **historia** compartida en el grupo | ❌ le llega vacía | ✅ |
| **Reportar** el spam a Telegram de forma oficial | ❌ | ✅ |

En la instalación de referencia, a **165 spammers los delató solo su perfil** (la bio, el canal o las fotos): con ellos no saltó ninguna otra regla.

La cuenta **no se delata**: leer una historia o un canal no cuenta como visualización y no se une a nada. Es opcional: sin ella, el bot funciona igual con todo lo demás.

---

## ✨ Lo que lo hace distinto

🖼️ **Lee el texto de las imágenes (OCR).** Un cartel con «Windows, Office, Photoshop, AutoCAD… escríbeme por privado» no lleva ni una letra escrita, así que para un bot normal es un mensaje vacío. CazaSpamBot lo lee con Tesseract y lo juzga como si fuera texto. Lo mismo con la captura de un falso sorteo de cripto de Elon Musk. Sin GPU: 0,6 segundos por imagen.

🎭 **Desmonta el disfraz.** El truco de moda es entrar con un nombre normal y ponerse el de verdad justo antes de escribir. El bot vigila el nombre de cada recién llegado **durante 7 días** y vuelve a mirarle el perfil entero en su primer mensaje.

💸 **Entiende la estafa, no solo las palabras.** Reconoce cómo se construye: el testimonio «le di 500 y me devolvió 5.000», el falso cliente que contesta al anzuelo sin cifras ni enlaces («Saw your post and honestly thought it was a scam, but the money actually came through», caso real), el «dinero extra, escríbeme por privado» y el sorteo cripto que te manda a otra web a canjear un código.

🧠 **Aprende solo, sin IA externa.** Aprende de tus `/spam` y `/legal` y, sin que hagas nada, de los bans seguros y de cómo hablan tus veteranos. Todo se queda en tu servidor.

📖 **Lee las historias compartidas.** Telegram se las entrega a los bots sin texto ni enlace, y por ahí se colaba la publicidad. El bot pide el contenido real y lo analiza.

🧹 **Limpia lo que dejó el spammer.** Banear en Telegram no borra sus mensajes. CazaSpamBot borra los recientes en todos los grupos donde lo banea, junto con sus propios avisos.

🔗 **Ban en uno, ban en todos tus grupos.** Además consulta las listas mundiales de spammers [CAS](https://cas.chat) y lols.bot, y si quieres reporta el spam claro a Telegram.

🤝 **Respeta a la gente normal.** Cada miembro tiene una confianza del 1 al 10 según su historial en el grupo. Lo dudoso te llega **por privado con botones** (✅ Legítimo / ❌ Spam), y se puede arrancar en **modo prueba**, sin banear a nadie, para ver qué haría.

🌍 **Para cualquier comunidad.** Viene en español e inglés y otro idioma es un archivo JSON. Tú eliges qué alfabetos son normales en tu grupo.

<details>
<summary><b>🔍 Ver los 25 detectores</b></summary>

<br>

🔑 = necesita la cuenta secundaria.

| Detector | Qué caza |
|---|---|
| `unicode_script` | Texto en un alfabeto que tu grupo no usa (`/config` ▸ Alfabetos permitidos) |
| `external_mention` | Menciones y enlaces a otros grupos o canales |
| `url_blocklist` | Acortadores de enlaces típicos del spam |
| `tg_deeplink` | Enlaces `tg://` de phishing |
| `link_target` | El enlace lleva a un chat que se anuncia como spam |
| `commercial_ad` | Anuncios: sueldos, «trabaja desde casa», software pirata, «escríbeme por privado» |
| `investment_scam` | «Le di X y me devolvió Y», el falso cliente satisfecho y los sorteos cripto falsos |
| `offplatform_contact` | «Este es mi número de otra app, escríbeme ahí» |
| `contact_spam` | Una tarjeta de contacto cuyo nombre es el anuncio |
| `external_reply` | Promocionar un canal ajeno citando un mensaje suyo |
| `cross_post` | El mismo mensaje a la vez en varios de tus grupos |
| `forward_first_msg` | Primer mensaje reenviado desde un canal o un bot |
| `first_msg_media` | Primer mensaje que es solo una foto, un vídeo o un sticker |
| `inline_buttons` | Una persona (no un bot) que manda botones |
| `emoji_only` | Primer mensaje que es una ristra de emojis |
| `jfm_delta` | Escribir a los pocos segundos de entrar |
| `premium_new_link` | Cuenta Premium recién creada que entra con un enlace |
| `dormant_bot_mention` | Cuenta dormida más de un año que reaparece citando un bot (robada) |
| `reaction_farming` | Cuentas que solo reparten reacciones sin escribir nunca |
| `story_share` | Compartir la historia de otro canal nada más entrar (sin cuenta secundaria) |
| `bio_spam` 🔑 | Bio con promoción porno, comercial o de hacking |
| `personal_channel` 🔑 | El canal del perfil usado como escaparate de spam |
| `photos_batch` 🔑 | Varias fotos de perfil subidas en minutos: cuenta montada |
| `cas` · `lols_bot` | Spammers fichados en las listas mundiales |

Y además: perfil evidente de spam (nombre entero en otro alfabeto, letras disfrazadas con homoglifos), lo aprendido de tus `/spam`, el texto de las imágenes y las historias, y el antiflood por persona.
</details>

---

<a id="instalacion"></a>

## 🚀 Instalación en 5 minutos

Necesitas un Linux siempre encendido (un VPS barato, un mini PC o un servidor en casa). El bot gasta menos de 100 MB de RAM.

### Paso 0 · Prepara Telegram (2 minutos)

1. Abre [@BotFather](https://t.me/BotFather), envía `/newbot` y ponle nombre. Te da el **token**: guárdalo.
2. En @BotFather, `/setprivacy` → tu bot → **Disable**, para que vea todos los mensajes y no solo los comandos.
3. Escribe a [@userinfobot](https://t.me/userinfobot): te dice tu **user_id** (un número).
4. *(Recomendado)* Para la cuenta secundaria: con **otro** número de Telegram, entra en [my.telegram.org](https://my.telegram.org) → **API development tools**, crea una app y apunta el **api_id** y el **api_hash**.

### Paso 1 · Instala Docker y descarga el bot

```bash
sudo apt update && sudo apt install -y git curl python3
curl -fsSL https://get.docker.com | sudo sh
git clone https://github.com/yonaesp/CazaSpamBot-Telegram.git
cd CazaSpamBot-Telegram
```

### Paso 2 · Configúralo

Te hace unas preguntas: pega el token, tu user_id y, si quieres, los datos de la cuenta secundaria. Lo demás, Enter.

```bash
python3 scripts/setup.py
```

### Paso 3 · Arráncalo

```bash
sudo install -d -o 10112 -g 10112 data config/blacklist/custom
sudo docker compose up -d --build
sudo docker compose logs -f
```

Cuando veas `Bot @TuBot … listo`, ya está vivo (Ctrl+C sale del log; el bot sigue).

### Paso 4 · Ponlo en tus grupos

1. En cada grupo: *Administradores* → *Añadir administrador* → tu bot, con **Eliminar mensajes** y **Banear usuarios**.
2. Abre tu bot en Telegram y pulsa **Iniciar**. Sin eso, Telegram no le deja mandarte los avisos.
3. Cuando esté en todos tus grupos, cierra la puerta para que nadie lo meta en los suyos: @BotFather → `/mybots` → tu bot → **Bot Settings** → **Allow Groups?** → **Turn groups off**.

### Paso 5 · Conecta la cuenta secundaria *(si la configuraste)*

Añádela también como administradora de tus grupos, con los mismos permisos. Luego:

```bash
sudo docker compose exec antispam-bot python -m scripts.telethon_login request
```

Telegram le manda un código a esa cuenta. Cámbialo por el `12345` (si tiene verificación en dos pasos, pon la contraseña detrás):

```bash
sudo docker compose exec antispam-bot python -m scripts.telethon_login confirm 12345
sudo docker compose restart
```

En el log verás `Telethon=conectado`.

### Paso 6 · De prueba a real

Arranca en **modo prueba**: lo mira todo y apunta lo que haría, sin banear a nadie. Cuando lleves unos días mirando el log y te fíes:

```bash
sed -i 's/^MODE=.*/MODE=active/' .env && sudo docker compose up -d
```

> [!NOTE]
> Los reportes oficiales a Telegram vienen **apagados**. Actívalos con `REPORT_BEFORE_BAN=true` en el `.env` cuando confíes en los detectores: reportar a gente legítima puede hacer que Telegram limite la cuenta secundaria.

<details>
<summary><b>El día a día: actualizar, ver el log, parar</b></summary>

<br>

| Quiero… | Comando |
|---|---|
| Ver qué está haciendo | `sudo docker compose logs -f` |
| Actualizar a la última versión | `git pull && sudo docker compose up -d --build` |
| Aplicar un cambio del `.env` | `sudo docker compose up -d` (`restart` no relee el `.env`) |
| Reiniciarlo | `sudo docker compose restart` |
| Pararlo | `sudo docker compose down` (lo de `data/` se conserva) |

**Al actualizar no pierdes nada**: tu `.env`, la base de datos (`data/`) y las palabras que añadiste desde Telegram (`config/blacklist/custom/`) viven fuera de git, y lo nuevo de la base de datos se crea solo al arrancar. Si editaste a mano una lista versionada de `config/blacklist/` y git da conflicto: `git stash && git pull && git stash pop`.

**Haz copia** de la carpeta `data/` y del `.env`: es todo lo que necesitas para recuperarlo en otra máquina. El bot ya deja una copia diaria de la base de datos en `data/backups/` (7 días).

Si tu usuario está en el grupo `docker`, puedes quitar el `sudo` de todos los comandos.

</details>

<details>
<summary><b>Con Podman en vez de Docker</b></summary>

<br>

Los mismos pasos, cambiando `docker compose` por `podman compose`:

```bash
sudo apt install -y podman podman-compose     # Fedora: sudo dnf install -y podman podman-compose
mkdir -p data config/blacklist/custom
podman unshare chown -R 10112:10112 data config/blacklist/custom
podman compose up -d --build
```

- **Las carpetas van con `podman unshare`**: Podman sin root traduce el uid 10112 del contenedor a otro de tu máquina, así que el `sudo install` del paso 3 no sirve aquí.
- **Para que arranque solo tras reiniciar el servidor**, una vez: `systemctl --user enable --now podman-restart.service` y `loginctl enable-linger $USER`.
- **Fedora, RHEL y derivadas (SELinux)**: si no puede leer `config/` o escribir en `data/`, añade `Z` a cada volumen del `docker-compose.yml`, por ejemplo `./data:/app/data:Z` y `./config:/app/config:ro,Z`.

</details>

<details>
<summary><b>Configurar a mano, sin el asistente</b></summary>

<br>

```bash
cp .env.example .env && chmod 600 .env
nano .env
```

Solo hay dos valores obligatorios. Los de aquí son **inventados**, para que veas el formato:

```ini
TELEGRAM_BOT_TOKEN=8123456789:AAF-EsteTokenEsFalsoReemplazaloPorElTuyo00
ADMIN_USER_ID=123456789
```

Para la cuenta secundaria, `TG_API_ID`, `TG_API_HASH` y `TG_PHONE` (con prefijo, `+34600111222`). El `.env.example` explica cada variable con un ejemplo. Nunca subas tu `.env` a git (ya está en `.gitignore`).

</details>

<details>
<summary><b>Qué monta el <code>docker-compose.yml</code></b></summary>

<br>

No hace falta tocarlo. Por si quieres saber qué hace:

| Línea | Para qué sirve |
|---|---|
| `build: .` | La imagen se construye en tu máquina desde el `Dockerfile`: no se descarga nada de ningún registro |
| `user: "10112:10112"` | Corre sin root y con un uid que no es de nadie en tu máquina. Otro uid: `APP_UID`/`APP_GID` en el `.env` |
| `env_file: .env` | Tu configuración |
| `./data:/app/data` | Base de datos, sesión de la cuenta secundaria y copias diarias |
| `./config:/app/config:ro` | Listas negras y bienvenidas, en solo lectura |
| `./config/blacklist/custom` | La única parte de `config/` donde escribe: las palabras que añades desde Telegram |
| `./src` y `./scripts` (`:ro`) | El código, montado para que una actualización se aplique sin reconstruir |
| `restart: unless-stopped` | Vuelve a arrancar solo tras un fallo o un reinicio del servidor |
| `healthcheck` | Lo marca como `unhealthy` si deja de dar señales de vida 5 minutos |
| `logging` | El log rota en 3 ficheros de 10 MB, para no llenar el disco |

</details>

---

## ⚙️ Se maneja desde Telegram

Escribe **`/config`** en el grupo o en el privado del bot y sale un panel con botones. Sin comandos que recordar:

- 🛡️ **Verificación** con botón «Soy humano», 👋 **bienvenida** y 📜 **reglas**, cada una por separado
- 👁️ **Avisos de sospechosos** por privado, con tres niveles de rigor
- 🔤 **Alfabetos permitidos**: te enseña cuáles se escriben de verdad en tu grupo
- 🛡️ **Rigor con trabajo y dinero**: normal, suave o apagado
- 🚫 **Palabras bloqueadas**: antes de guardar te dice con cuántos mensajes reales de tu grupo habría coincidido
- ⚠️ **Warns**: límite, castigo y quién puede ponerlos
- 🔗 **Sincronizar**: un cambio vale para todos tus grupos (activado por defecto)

Por defecto el grupo queda **limpio y callado**: sin bienvenidas ni verificación, y la moderación funcionando igual.

> [!WARNING]
> **Si tu comunidad no escribe en alfabeto latino, ajusta esto lo primero.** Por defecto el bot solo considera normal el alfabeto latino, así que en un grupo árabe, ruso, griego o hindi marcaría a tus propios miembros. Se arregla en dos toques: `/config` ▸ 🔤 **Alfabetos permitidos** y activa el tuyo.

<details>
<summary><b>🎛️ Ajustes del <code>.env</code> y archivos editables</b></summary>

<br>

| Qué | Dónde |
|---|---|
| Grupos a moderar | `MODERATED_CHAT_IDS` (vacío = todos donde sea admin con permiso de banear) |
| Dónde te llegan los avisos | `ADMIN_NOTIFY_CHAT_ID` (vacío = tu privado; o el `chat_id` de un grupo de moderación) |
| Rigor con la lista CAS | `CAS_AUTOBAN_MIN`: `2` banea si está confirmado en 2+ grupos y te consulta el resto (recomendado); `1`, con cualquier señal |
| Idiomas de las listas de palabras | `BLACKLIST_LANGS` (por defecto, el del bot + inglés, la lengua franca del spam) |
| Idiomas que lee el OCR | `OCR_LANGS` (por defecto, los del bot) |
| Acortadores bloqueados | `URL_BLOCKLIST` |
| Umbrales de ban, expulsión y silencio | Las variables `*_SCORE` del `.env.example` |
| Listas de palabras y frases | `config/blacklist/` (un patrón por línea; [guía](config/blacklist/README.md)) |
| Bienvenidas con gracia por grupo | `config/welcomes/` ([guía](config/welcomes/README.md)) |

Lo que se toca desde `/config` se guarda en la base de datos y sobrevive a las actualizaciones.

</details>

<details>
<summary><b>💬 Todos los comandos</b></summary>

<br>

Solo el **admin del bot** (`ADMIN_USER_ID`) puede cambiar cosas. Los **admins de cada grupo** pueden consultar y poner warns. Al resto, el bot los ignora.

| Comando | Qué hace |
|---|---|
| `/config` (`/ajustes`, `/panel`) | Panel de ajustes con botones |
| `/ban @user motivo` · `/unban @user` | Ban o unban en todos tus grupos a la vez (acepta respuesta, @usuario o id) |
| `/warn` `/warns` `/rmwarn` `/resetwarns` `/warnlimit` `/warnaction` | Avisos progresivos |
| `/spam` · `/legal` | Enseña al bot (respondiendo a un mensaje) |
| `/scan` (`/analizar`) | ¿Detectaría este mensaje? (respondiendo a él) |
| `/notspam <id>` · `/forget <id>` | Deshace un falso positivo · borra una muestra aprendida |
| `/whitelist @user` | Marca a alguien como intocable |
| `/stats` `/recent` `/top` `/topweekly` | Estadísticas y rankings |
| `/verificacion` | Verificación humana por grupo |
| `/setwelcome` `/setrules` `/welcome` `/rules` | Bienvenida y reglas |
| `/cleanservice` · `/limpieza` | Borrar mensajes de servicio · ocultar y borrar los comandos en el grupo |
| `/alertas` | Qué avisos te llegan por privado |
| `/sync on\|off` | Ajustes iguales en todos los grupos |
| `/idioma <código>` (`/language`) | Idioma del bot |
| `/shadow on\|off` | Modo prueba |
| `/help` · `/comandos` | La guía completa dentro de Telegram |

Con **`/ban` y un motivo**, el bot publica el motivo en el grupo y ese aviso se queda; sin motivo, el ban es silencioso. Los miembros pueden avisarte respondiendo a un mensaje con **`@admin`**.

</details>

---

<a id="faq"></a>

## ❓ Preguntas frecuentes

**¿Puedo añadir @CazaSpamBot a mi grupo sin más?**
No: esa copia es privada y solo modera los grupos de su dueño. El código es gratis, así que montas tu propio bot con tu propio token y es enteramente tuyo. Son [5 minutos](#instalacion).

**¿Qué es eso de la cuenta secundaria? ¿Es seguro?**
Es una cuenta normal de Telegram, con otro número, que el bot usa como lo harías tú desde otro dispositivo. **No uses tu cuenta personal**: si Telegram limitara la secundaria por actividad automática, la tuya no se vería afectada. La sesión queda en `data/telethon.session` y hay que tratarla como una contraseña. Es opcional.

**¿Baneará a miembros legítimos?**
Es lo que más se esfuerza en evitar. Quien tiene historial en el grupo está protegido por su confianza, lo dudoso te llega con botones en vez de acabar en ban, y puedes arrancar en modo prueba para ver qué haría antes de dejarle actuar.

**¿En qué se diferencia de un bot de captcha?**
Un captcha solo frena a los bots tontos al entrar. Aquí la verificación es opcional y viene apagada, porque el spam de hoy la supera y luego escribe con calma. Lo importante es mirar quién es y qué publica, también días después.

**¿Mis datos salen del servidor?**
No. El aprendizaje y el OCR son locales. Fuera de Telegram, lo único que sale son las consultas a las listas CAS y lols.bot (con el id del usuario) y, si los activas, los reportes a Telegram.

**¿Es gratis? ¿Funciona en otros idiomas?**
Sí, gratis y de código abierto (GPL-3.0). La detección no depende del idioma del grupo, la interfaz viene en español e inglés, y añadir un idioma es un archivo JSON ([guía para traductores](src/locales/README.md)).

**¿Dónde pido ayuda?**
Abre una [incidencia en GitHub](https://github.com/yonaesp/CazaSpamBot-Telegram/issues). El soporte es gratuito.

---

## 🔒 Seguridad

- Corre **sin root**, con un uid que no es de nadie en tu máquina, y con el código y la configuración en **solo lectura**.
- Los secretos viven solo en `.env` (permisos `600`, fuera de git). La sesión de la cuenta secundaria nunca se sube.
- La cuenta secundaria reporta con criterios estrictos (reglas concretas, puntuación alta y límite por hora) para cuidar su reputación en Telegram.

<a id="tests"></a>

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 1681 tests
```

Cada detector tiene tests de lo que debe cazar **y de lo que no**, con casos reales. Un falso positivo es peor que un falso negativo.

<details>
<summary><b>📁 Estructura del código y documentación</b></summary>

<br>

```
src/
├── main.py              # arranque, handlers y tareas programadas
├── handlers.py          # cada mensaje y cada entrada al grupo
├── detectors/           # un módulo por detector
├── verification.py      # verificación «Soy humano» y perfiles evidentes
├── federation.py        # ban en todos tus grupos y limpieza de mensajes
├── learning.py          # Naive Bayes + coseno
├── autoaprendizaje.py   # lo que aprende solo
├── ocr.py               # texto dentro de imágenes
├── story_reader.py      # contenido de las historias (MTProto)
├── channel_reader.py    # canal personal del perfil (MTProto)
├── reporter.py          # reportes oficiales a Telegram (MTProto)
├── config_panel.py      # panel /config
├── locales/             # idiomas (es.json, en.json y el tuyo)
└── db.py                # SQLite + migraciones
config/
├── welcomes/            # bienvenidas editables
└── blacklist/           # listas de palabras editables
```

Más a fondo: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/LEARNING.md`](docs/LEARNING.md), [`config/blacklist/README.md`](config/blacklist/README.md) y [`CHANGELOG.md`](CHANGELOG.md).

</details>

## 📄 Licencia

[GPL-3.0](LICENSE): úsalo, modifícalo y compártelo libremente; los forks y derivados deben seguir siendo código abierto.

---

<div align="center">
<sub>Hecho con cariño y mucho café para mantener limpias las comunidades. · <a href="README.md">🇬🇧 English version</a></sub>
</div>
