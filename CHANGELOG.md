# Changelog

Cambios relevantes de CazaSpamBot, lo más reciente arriba. Se anotan hitos, no
cada commit: para el detalle está el historial de git. Sin números de versión
porque el bot es un servicio en producción continua, no un paquete que se libera.

## 2026-08 · Historias, avisos que llegan y bienvenidas que se van

Dos días largos a raíz de un spam que se coló: publicidad de cripto compartida
como **historia** (story). El bot no estaba roto, estaba ciego.

### Historias (stories)

- Telegram entrega a los bots una historia con **solo `chat` e `id`**: ni texto, ni
  imagen, ni entidades, **ni marca de reenvío**, así que `forward_first_msg` tampoco
  saltaba. Para el bot era un mensaje vacío.
- Detector nuevo **`story_share`**, que **no necesita Telethon**: cubre compartir la
  historia de otro canal nada más entrar, o venir de un canal con nombre de spam
  siendo alguien que apenas participa.
- **`story_reader.py`** recupera el texto real por MTProto (`stories.getStoriesByID`)
  y lo pasa por los detectores de siempre, con los mismos umbrales. Comprobado en la
  documentación oficial antes de usarlo: **leer una historia no cuenta como
  visualización**, así que la cuenta secundaria no aparece en la lista de espectadores.
- Las **entidades hay que traducirlas** de MTProto a la Bot API: los detectores de
  enlaces no miran el texto plano, así que sin traducir se leía la publicidad pero se
  perdía el enlace, que es la prueba.
- Lista editable `config/blacklist/story_source.txt`, de **parejas** y nunca palabras
  sueltas. Lección cara: «insider» a secas casaba con «Windows Insider Program» y
  «pump» con «Heat Pump UK», o sea ban federado a usuarios legítimos en los grupos de
  Windows y de domótica.
- **Ninguna señal decide sola**, que es la doctrina que ya seguía `investment_scam`:
  la estructura por sí misma no llega al umbral de acción.

### Avisos que sí llegan

- **Bug real**: un `/ban` en respuesta baneaba y federaba bien, pero el admin solo veía
  desaparecer su comando. El acuse salía únicamente por el notificador externo, que es
  **opcional**, así que sin configurar se perdía en silencio. Ahora hay respaldo por el
  propio bot. Afectaba a 11 puntos de los comandos admin.
- **`/ban` y `/unban` no registraban en `moderation_log`**: no salían en `/recent` ni
  contaban en `/stats`.
- Con **trust alto** el bot ya no se calla: si a un veterano le salta una regla, llega
  aviso **por privado** con botones **Nada / Avisar / Banear**. Silenciable en `/alertas`.
- El botón **Avisar** hace ya lo mismo que `/warn` (publica, borra y respeta el límite).
  Al unificarlo apareció un `NameError` en `/warn`: con la acción por defecto (`ban`),
  llegar al límite reventaba, el contador no se reseteaba y el grupo no veía nada.

### Bienvenidas y `/ban`

- La **bienvenida del baneado se borra**, venga el ban de donde venga: `/ban`, el combo
  de `/spam`, una regla automática o un ban a mano desde la app de Telegram. Antes el id
  del mensaje solo se guardaba con la verificación activa, y el modo limpio (sin
  verificación) es el que viene por defecto.
- **`/ban` con reply borra el mensaje** del spammer, y el **motivo actúa como
  consentimiento**: sin motivo el ban sigue mudo; con motivo se publica y **se queda**
  (`BAN_NOTICE_DELETE_AFTER_S=0`).

### `/scan`

- Ahora **espera el mensaje**: escribe `/scan` y reenvía después, no solo al revés.
- Distingue **«no dispararía ninguna regla»** de **«no he podido leerlo»**, que es lo que
  pasaba con las historias y llevaba a dar por limpio un mensaje que nadie había leído.
- Explica **qué pasaría según quién comparta** el mensaje, y por qué
  `forward_first_msg` no puede saltar en una historia.

### Dependencias y arreglos

- **PTB 21.6 → 22.8** y **Telethon 1.36 → 1.44** (Bot API 7.10 → 10.0).
- Los **desplazamientos de las entidades** se calculaban en caracteres y Telegram los
  manda en unidades UTF-16: cada emoji antes de un enlace desviaba el corte. Estaba mal
  en 5 sitios; en las menciones dejaba un espacio pegado y no se encontraba al usuario.
- Aviso cuando **otro bot admin** del grupo puede solapar funciones.
- El HTML de los avisos al admin **se escapa**: el título de un canal lo elige el
  spammer, y un `<b>` suelto hacía que Telegram rechazara el aviso entero.

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
