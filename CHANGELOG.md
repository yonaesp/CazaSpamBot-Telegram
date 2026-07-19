# Changelog

Cambios relevantes de CazaSpamBot, lo más reciente arriba. Se anotan hitos, no
cada commit: para el detalle está el historial de git. Sin números de versión
porque el bot es un servicio en producción continua, no un paquete que se libera.

## 2026-07 · Bilingüe y configurable desde el móvil

Salto grande: el bot deja de ser una herramienta de un solo grupo en español y
pasa a poder instalarse y administrarse desde fuera.

### Idiomas
- **Todo el texto que ve el usuario vive en `src/locales/<código>.json`**, ninguno en el código.
- **Bilingüe es/en** completo (unas 900 claves por idioma), con **autodescubrimiento**: soltar un `fr.json` basta para que `/idioma fr` funcione, sin tocar código.
- **Fallback por clave** al español, así un idioma traducido al 40 % ya es usable.
- **A prueba de fallos**: un JSON roto se ignora con un log y el bot sigue. Se eligió JSON frente a módulos `.py` porque un `.py` se ejecuta al importarse y una comilla mal puesta por un traductor tumbaba el arranque.
- Nombres de comando traducibles (`/verification`, `/language`, `/alerts`, `/cleanup`, `/commands`); los nombres en español siguen funcionando siempre.
- Guía para traductores en `src/locales/README.md`.

### Panel visual `/config`
- Casi todo ajuste por chat se toca desde botones **y** por comando en paralelo.
- Modo **sincronización** (por defecto ON): cada cambio se aplica a todos los grupos a la vez.
- Subpantallas de Bienvenida (texto, botones del mensaje, autoborrado), Warns, top semanal, tiempos de verificación, Frases al banear (con ejemplo real antes de activar) y avisos informativos.
- **Palabras bloqueadas desde Telegram**: añadir y quitar términos sin acceso al servidor. Lo que se escribe se trata como literal (imposible colar un regex), y antes de guardar el bot enseña con cuántos mensajes reales del grupo coincidiría, para no bloquear conversación normal.

### Detección
- Nuevo detector **`personal_channel_spam`**: mira el canal enlazado en el perfil, un campo separado de la bio. Un perfil con la bio vacía puede tener ahí un canal entero de spam. No salta por tener canal (es legítimo): la señal es la discordancia, nombre en alfabeto latino con canal en otro alfabeto. Descubierto por un caso real de una red de blanqueo.
- **Listas negras por idioma** (`config/blacklist/<lang>/`, variable `BLACKLIST_LANGS`) que se acumulan, y `config/blacklist/custom/` para lo que añade el admin.
- Español de América: monedas locales, «por día» y voseo (`escribime`, `ganá`). El importe se reconoce con el símbolo delante (`$500`) o detrás (`500€`).

### Aprendizaje más prudente
- Salvaguardas para que el bot no aprenda a castigar el vocabulario normal de su grupo: ningún token decide solo (tope al log-odds), el que aparece en spam y en ham pesa la mitad, y el visto una sola vez pesa un tercio.
- Los tokens excluidos por defecto pasan a ser palabras funcionales del idioma (útiles a cualquiera); el vocabulario temático lo pone cada admin.

### Quips
- Configurables por chat (`quips_enabled`), heredando de `PUBLIC_QUIP_ENABLED` del `.env` mientras nadie lo toque. Adaptados al inglés, no traducidos literalmente.

## 2026-05 / 2026-06 · Núcleo antispam

La base sobre la que se construyó todo lo anterior.

### Detectores y anti falso positivo
- Batería de detectores de perfil, contenido y comportamiento: `obvious_spam_profile`, `bio_spam`, `photos_batch_upload`, `commercial_ad`, `forward_first_msg`, `inline_buttons_from_user` y más.
- **Trust score 0-100** (msgs + días + antigüedad + warns): ≥70 salta la detección blanda, 40-69 va a revisión o degrada, <40 flujo normal.
- **Revisión con botones**: trust medio + acción severa manda un DM al admin con Legítimo/Spam, y el bot aprende del veredicto.
- **NFKC + confusable_homoglyphs** (UTS#39) para nombres decorativos. Nace de un incidente real: una regla de Cherokee llegó a banear a más de 100 usuarios legítimos, se revirtió y se blindó.

### Aprendizaje activo
- Naive Bayes + similitud coseno sobre las muestras que marca el admin con `/spam` y `/legal`.

### Mensajería
- Quips opacos que no revelan el mecanismo de detección.
- Consolidación de ráfagas: varios bans seguidos se agrupan en un mensaje.
- Bienvenidas temáticas por grupo, en castellano correcto.
- Verificación en tres niveles según lo sospechoso que sea quien entra.

### Robustez y despliegue
- Reconciliación nocturna `banned_users` con Telegram, antiflood graduado por trust, limpieza post-ban solo con Bot API.
- `TELETHON_ENABLED` como interruptor: sin Telethon el bot corre solo con Bot API (se pierden bio, fotos, canal del perfil y reportes oficiales, el resto sigue).
- Secretos fuera del repo: `.env` y `*.session` gitignored, `.env.example` con valores vacíos.
