# Lecciones del CazaSpamBot

El relato íntegro de cada regla del `CLAUDE.md`: el caso real, la medida y el porqué. El `CLAUDE.md` guarda el
invariante y remite aquí con `(Ln)`. Se movieron sin recortar el 26-oct-2026 (dieta del CLAUDE.md para Opus 5.5).
Una lección nueva va al final, con el número siguiente y su línea en el índice.

## Índice

- [L1](#l1) · `.env` y `data/telethon.session` en 600
- [L2](#l2) · «Donde sea admin» no lo comprobaba nadie: `_se_modera`
- [L3](#l3) · Lo que ve un desconocido (`publico.py`)
- [L4](#l4) · «No es miembro» no es una duda (`_no_es_miembro`)
- [L5](#l5) · Salir y volver a entrar no borra el nivel ganado (`_ya_es_de_casa`)
- [L6](#l6) · Verificación, bienvenida y avisos de sospechosos: OFF por defecto, tres niveles
- [L7](#l7) · Nombre, bio o canal en un alfabeto no permitido: ban directo
- [L8](#l8) · Menos fricción: `no_username` no es señal fuerte y basta 1 foto
- [L9](#l9) · El perfil se mira en los tres momentos
- [L10](#l10) · La antigüedad sin participación no da confianza (`_sin_confianza_posible`)
- [L11](#l11) · Contenido opaco (`MessageMediaUnsupported`)
- [L12](#l12) · Banear no borra los mensajes: `_retirar_mensajes`
- [L13](#l13) · Detectores que dependen de Telethon e historias (`story_reader`)
- [L14](#l14) · El canal personal y la discordancia (`personal_channel_spam`)
- [L15](#l15) · El rótulo del canal lo elige el spammer (`channel_reader`)
- [L16](#l16) · Recién llegados: nombre visto, cambio en el momento y ventana de 7 días
- [L17](#l17) · El texto dentro de una imagen (`ocr.py`)
- [L18](#l18) · El catálogo de software pirata en inglés (Adobe)
- [L19](#l19) · El guion del «dinero extra» cerrado por privado (Natalia)
- [L20](#l20) · La variante del «trabajo extra» (María)
- [L21](#l21) · Las señales de forma no castigan solas (Kleo, el perdón y los `jfm_*`)
- [L22](#l22) · Los avisos por privado llevan enlace al mensaje
- [L23](#l23) · La cuenta robada de un veterano la para el destino (xevi)
- [L24](#l24) · Web porno: `adult_link` (Elxufas)
- [L25](#l25) · Referido publicado con un bot inline: `via_bot_referral` (Lil Pani)
- [L26](#l26) · Un @ mal escrito no es una mención externa: `errata_mencion`
- [L27](#l27) · El aviso suave se da por resuelto si el autor lo corrige
- [L28](#l28) · Escribir pronto no castiga a quien ya es legítimo (Saizor)
- [L29](#l29) · El perdón no alcanza al reenvío desde canal, chat o bot
- [L30](#l30) · Listas negras: las tres capas y la vista previa
- [L31](#l31) · El envoltorio de las listas: lookarounds, nunca `\b`
- [L32](#l32) · Anti falso positivo en los patrones (monedas, importes, América)
- [L33](#l33) · `investment_scam`: el molde para detectar sin falsos positivos
- [L34](#l34) · Alfabetos permitidos por chat
- [L35](#l35) · Ajuste `money_guard` por chat
- [L36](#l36) · Aprendizaje: salvaguardas, autoaprendizaje y la palabra nunca vista (Andre)
- [L37](#l37) · Quién puede warnear y el comando sin permiso que no puede ser silencioso
- [L38](#l38) · Qué avisos por privado suenan (`notify_prefs.sin_sonido`)
- [L39](#l39) · Bienvenidas y mensaje de verificación
- [L40](#l40) · Bots de otros admins en el grupo (`return_bots=True`)
- [L41](#l41) · Copia de seguridad de la BD (`VACUUM INTO`)
- [L42](#l42) · Analizar la base, no solo respaldarla
- [L43](#l43) · Horas: una sola zona para todo lo que ve una persona
- [L44](#l44) · Tests que pasan en verde sin comprobar nada
- [L45](#l45) · Cuando llega un aviso del bot pegado sin ninguna orden
- [L46](#l46) · Charlotte: el enlace de la bio sin `https://` y un aviso de ban manual que no dejaba ver el perfil
- [L47](#l47) · Repaso del 28-oct: lo que se escapaba, lo que hacen otros bots y lo que se añadió
- [L48](#l48) · Simulación del 29-oct: `calentamiento` expulsaba a gente normal y una red de reclutamiento no daba nada
- [L49](#l49) · Helen, Gloria y Brook: una red con el mismo enlace privado en la bio y 40 puntos cada una
- [L50](#l50) · Dos veteranos con la bio de spam tras años callados: cuentas robadas y destinos que se aprenden
- [L51](#l51) · Versiones, `update.sh` y la imagen para ARM: que otros la monten y la mantengan al día
- [L52](#l52) · ZERO: los «Posts» del perfil, un escaparate con OCR que el bot no miraba
- [L53](#l53) · Bots invitados: un spam que publica un bot que ni siquiera está en el grupo
- [L54](#l54) · Grupos con temas: un @admin que enlazaba otro tema y llegaba dos veces
- [L55](#l55) · El aviso de ban que no llegaba: la limpieza borraba el mensaje antes de copiarlo
- [L56](#l56) · Adelantarse a los bots de spam, y comprobaciones que se ejecutan solas
- [L57](#l57) · Auditoría del 7-nov: lo que no funcionaba como decía el CLAUDE.md
- [L58](#l58) · Rosario: un enlace privado en la bio que nadie fue a mirar
- [L59](#l59) · La cuenta secundaria: cualquiera podía meterla en un grupo

---

<a id="l1"></a>
## L1 · `.env` y `data/telethon.session` en 600

⚠️ **`.env` y `data/telethon.session` van en 600** (9-oct-2026, rotación de credenciales):
estaban en 644, legibles por cualquier usuario del N100 y de la réplica del N6005, y la
sesión da la cuenta secundaria entera. Nada de `.env.bak*` con secretos al lado. El
historial del repo público se revisó entero por hash: solo hay los ejemplos inventados.

---

<a id="l2"></a>
## L2 · «Donde sea admin» no lo comprobaba nadie: `_se_modera`

⚠️ **«Donde sea admin» no lo comprobaba nadie.** `cfg.is_moderated` devolvía True para
CUALQUIER chat en autodescubrimiento. Caso real (25/26-sep-2026): alguien metió el bot
como miembro normal en dos grupos de pesca ajenos; allí decidía «ban», avisaba al admin
de un «Baneado (sincronizado en todos los grupos)» que no podía ejecutar, el spammer
seguía dentro y cada ~4 h llegaba otro aviso idéntico. Y esos bans **entraban en la
federación**: un grupo ajeno podía banear gente en los propios. Las cuatro puertas
(join, mensaje, reacción, canal) pasan ahora por `_se_modera`: lista explícita si la
hay; si no, **admin con permiso de restringir** (`db.puede_moderar`). Hay test que
impide volver a usar `cfg.is_moderated` a pelo en una puerta.

---

<a id="l3"></a>
## L3 · Lo que ve un desconocido (`publico.py`)

**Lo que ve un desconocido** (`publico.py`, 4-oct-2026): la descripción del perfil
del bot (es/en, puesta al arrancar solo si cambia) y un privado o `/start` de quien
no es admin de ningún grupo reciben que el bot es de código abierto, que en su
grupo NO funcionará y el enlace a GitHub. **Una vez al día por persona**, para que
nadie use el bot de frontón. `REPO_URL=` vacío en `.env` lo apaga entero. A los
admins de los grupos no se les vende nada: siguen viendo el resumen de `/start`.

---

<a id="l4"></a>
## L4 · «No es miembro» no es una duda (`_no_es_miembro`)

⚠️ **«No es miembro» no es una duda.** `_is_admin_of_chat` cae del lado seguro
(«se asume admin, no se actúa») cuando no puede comprobar, y eso incluía `Member not
found`, que es una respuesta, y la contraria. Medido (24-sep a 1-oct-2026): **7
spammers fichados en lols.bot** que ya se habían ido los encontraba el repaso cada
6 h y la guarda los paraba siempre: **113 intentos**, ninguno baneado, libres para
volver. Ahora esa respuesta concreta (`_no_es_miembro`) es «no admin»; cualquier otro
fallo sigue cayendo del lado seguro.

---

<a id="l5"></a>
## L5 · Salir y volver a entrar no borra el nivel ganado (`_ya_es_de_casa`)

**Salir y volver a entrar no borra el nivel ganado.** El gate de verificación miraba el perfil de TELEGRAM (`_is_very_legit_profile`: foto, antigüedad de la cuenta) y nunca el historial EN EL GRUPO, así que a un miembro desde 2022 con 14 mensajes y trust 74 se le trataba como a un desconocido al reentrar. Caso real (2026-08-23): borró un foro sin saber que van integrados, se salió del grupo entero y se encontró la verificación otra vez «sin saber dónde ni cómo hacerlo». Ahora `_ya_es_de_casa()` salta el botón si ya se verificó aquí (`seen_users.verified_ts`, que antes no se guardaba en ninguna parte porque `pending_verifications` se vacía al verificar) **o** si tiene ≥`MIN_MSGS_DE_CASA` mensajes previos, que cubre a quien se verificó antes de existir esa marca. El historial (`first_seen_ts`, `msg_count`) ya sobrevivía al reingreso: `record_join` lo conserva con COALESCE. **Solo se salta el botón**: los detectores de perfil y de mensaje se aplican enteros, y un baneado en federación se resuelve antes de llegar aquí.

---

<a id="l6"></a>
## L6 · Verificación, bienvenida y avisos de sospechosos: OFF por defecto, tres niveles

8. `verification.on_join` — **default LIMPIO Y CALLADO**: verificación, bienvenida y **avisos de sospechosos, los tres OFF**. Los avisos estaban ON y llenaban el privado: saltaban por «sin foto de perfil», que cumple muchísima gente legítima, y un aviso que se acaba ignorando es peor que no tenerlo. Al encenderlos hay **tres niveles** (`chat_settings.review_level`, NULL = el más callado):
   - `alto` (defecto): solo señales que de verdad huelen a spam (nombre o usuario en otro alfabeto, nombre con homoglifos, cuenta nueva sin ninguna foto).
   - `medio`: el comportamiento anterior (una señal fuerte, o dos cualesquiera).
   - `bajo`: cualquier indicio, incluido no tener @usuario.
   Todo por chat vía `/config`.

---

<a id="l7"></a>
## L7 · Nombre, bio o canal en un alfabeto no permitido: ban directo

**Un nombre ENTERO en un alfabeto que el chat no permite es ban directo, sin
excepciones** (decisión explícita del admin, 13-sep-2026). Antes hacían falta DOS
campos y un nombre 100 % árabe sin apellido ni usuario solo llegaba a verificación,
que es lo que pasó con «محمد» el 12-sep. El criterio se evalúa **antes** del
salvoconducto de «cuenta antigua con foto», así que una cuenta de cinco años con
foto cae igual: se le presentó el coste al admin (cualquier persona real con nombre
en árabe, ruso, griego o hebreo queda fuera para siempre) y lo aceptó.

Tres cosas que no se deben romper:
- **Mínimo 3 letras** en el alfabeto no permitido. Sin ese mínimo el criterio
  revive el falso positivo de mayo por la puerta de atrás: `ツ` de apellido, `彡`
  o `♛` son adornos que usa muchísima gente legítima, y son campos de UNA letra
  con ratio 100 %. Los nombres reales cumplen de sobra (محمد=4, الحسن=5,
  Сервер=6). Hay test con los cinco adornos.
- **Los alfabetos son los DEL CHAT** (`chat_settings.allowed_scripts`, resuelto
  por `verification.allowed_scripts_de`), no una lista fija: un grupo ruso o árabe
  que configure el suyo no se autodestruye al actualizar. Ese helper vive en
  `verification` y no en `handlers` porque lo necesitan también `recien_llegados`
  y `scan_cmd`, que no pueden importar handlers sin ciclo.
- ⚠️ **Alcanza también al chino, y eso deja `han_requiere_decision` sin uso
  práctico** para nombres Han de 3+ letras: el ban ocurre antes de preguntar. Ese
  camino de «decide tú» sigue vivo solo para nombres cortos (`中文`, 2 letras).
  No es un descuido, es la consecuencia coherente de «sin excepciones».

**Y lo mismo para la BIO y el título del CANAL PERSONAL** (decisión del admin,
28-sep-2026): escritos en un alfabeto no permitido → ban directo, también antes del
salvoconducto (`_texto_en_otro_alfabeto`, mismas guardas: NFKC, mezcla decorativa,
≥70 % y ≥3 letras). Caso: «Mahmoud Rashed», nombre en latino y bio y canal
(«برامج و العاب», programas y juegos) en árabe; se saltó hasta la verificación (3
fotos, 650 días) y su único mensaje fue un comentario cebo en inglés para llevar
gente al canal. El nombre es justo la parte que se cambia para pasar los filtros.
**Tener canal a secas NO es ban**: es muy común en gente legítima. Una bio que mezcla
idiomas («Люблю Windows») tampoco cae. No se pudo medir el impacto: ni bios ni
canales de los miembros se guardan, y en tres semanas de logs solo entró este caso.

**Medido antes de aplicarlo** sobre las 566 personas con nombre registrado: el
criterio cambia el veredicto de **9**, todas con **0 mensajes**, y **5 ya estaban
baneadas** por otra vía. El único veterano con nombre exótico del censo
(`彡👽彡 - ꧁༒ 𝕄𝕧𝕀𝕚𝕀𝕒𝕏`, 220 mensajes desde 2022) **no se ve afectado**: tras NFKC
queda en 22 % no latino, lejos del 70 %. Los 4 que quedaban dentro se banearon a
mano al aplicar el cambio, con luz verde explícita.

---

<a id="l8"></a>
## L8 · Menos fricción: `no_username` no es señal fuerte y basta 1 foto

**Menos fricción para quien no la merece.** Dos criterios se relajaron con datos del propio grupo (30-ago-2026), a raíz de «mario»: nombre latino, **1 foto de hace 540 días**, sin @usuario, y le salió «verifica en 30 min o serás expulsado».
- **`no_username` NO es señal fuerte**: medido, **29 %** de los miembros de Windows 11 y **14 %** de Domótica no tienen username. Ya existía `_STRONG_SUSP_REASONS` excluyéndola, pero solo se usaba para avisar al admin; ahora también decide el tier. Sin ninguna señal fuerte se pasa al tier NORMAL (3 h + recordatorio), no se salta la verificación.
- **`_is_very_legit_profile` pide 1 foto, no 2**: sobre 20 usuarios asentados, **el 15 % tiene una sola**. Lo que esa condición prueba es la ANTIGÜEDAD, que sale de la foto más vieja: una de hace año y medio la demuestra igual que dos.

---

<a id="l9"></a>
## L9 · El perfil se mira en los tres momentos

**El perfil se mira en los TRES momentos**: al entrar, en el repaso de recién llegados y **en el primer mensaje**. Este último faltaba y se cobró casos: al hablar se juzgaba solo el texto, así que quien entraba con el perfil limpio y lo cambiaba justo antes de escribir pasaba. Caso medido (2026-08-09): «李大哥», nombre 100 % Han y canal `财天下飞机进群结演员结算频道`, entró limpio, se verificó en 4 segundos y escribió 15 h después; lo cazó `non_allowed_script`, o sea por el IDIOMA DEL TEXTO, y con un «hola buenas» habría pasado. En el primer mensaje se aplican los **mismos** criterios del join, sin umbrales propios. Dos guardas: solo si el bot presenció el join (`join_ts IS NOT NULL`, si no podría llevar años en el grupo) y **un solo `user_signals.fetch` por mensaje** (`_senales()`), porque había tres consumidores pidiéndolo por separado con 12 s de tope cada uno.

---

<a id="l10"></a>
## L10 · La antigüedad sin participación no da confianza (`_sin_confianza_posible`)

**La antigüedad sin participación no da confianza.** `user_trust_score` solo suma
los días en el grupo a partir de `MIN_MSGS_PARA_ANTIGUEDAD` (4: tres previos + el que
se juzga). Caso real (26-sep-2026, Windows 11): «Miguel Angel» entró el 24-jun, no
escribió nada en 3 meses y su primer mensaje fue un reenvío de un bot con publicidad
porno y un botón a una web: `forward_first_msg` dio 95 (kick), pero con 0 mensajes
tenía **trust 61, todo por días**, así que se preguntó al admin tres veces y el cuarto
mensaje pasó sin preguntar. Medido sobre las 15 decisiones ablandadas por trust:
**todas las de gente con ≤3 mensajes acabaron en ban**; las de quien participa,
ninguna. Una cuenta durmiente es justo lo que espera su momento, no un veterano.

**Y además, regla explícita** (decisión del admin, 26-sep): si alguien **nunca ha
escrito** (`msg_count ≤ 1`, que incluye el actual) y su primer mensaje es un **reenvío
de un bot** o llega **opaco**, el trust no ablanda nada, ni en la graduación suave ni
en el bloque de trust (`_sin_confianza_posible`). Va aparte de la fórmula a propósito:
la decisión no debe depender de cómo se calibre el trust.

---

<a id="l11"></a>
## L11 · Contenido opaco (`MessageMediaUnsupported`)

Ese contenido llegó **opaco**: MTProto lo da como `MessageMediaUnsupported` (sin texto
ni botón) y los detectores de contenido no vieron nada. Queda traza `mensaje opaco`
con las claves de la Bot API y su `api_kwargs` (donde PTB guarda lo que aún no
entiende): la próxima vez se sabrá si el botón llegaba y se podrá detectar.

---

<a id="l12"></a>
## L12 · Banear no borra los mensajes: `_retirar_mensajes`

**Banear en un supergrupo NO borra los mensajes del baneado.** Caso real
(26-sep-2026): cuatro reenvíos de spam, el admin pulsó «Spam» en uno y los otros tres
siguieron en el grupo, más dos avisos de «un administrador lo revisará» respondiendo a
un «mensaje eliminado». La función que debía limpiar (`aggressive_post_ban_cleanup`)
**no la llamaba nadie** y solo miraba `moderation_log`, donde el cuarto ni aparecía;
se retiró. Ahora `federate_ban`, por donde pasan TODOS los bans, llama al final a
`_retirar_mensajes`: `mensajes_recientes` ∪ `moderation_log` de los últimos 7 días,
solo en los chats donde el ban se aplicó, con `deleteMessages` (100 por llamada),
solo Bot API y sin poder tumbar el ban. Se lleva también los avisos del bot ligados a
esa persona: el «un admin lo revisará» se registra en `gentle_warnings` igual que el
aviso suave, así que además la cascada de borrados (Telethon) lo quita cuando el
mensaje se borra a mano sin pasar por los botones.

---

<a id="l13"></a>
## L13 · Detectores que dependen de Telethon e historias (`story_reader`)

`bio_spam`, `photos_batch`, `obvious_spam_profile` (parcial) y `personal_channel_spam` leen el perfil vía MTProto. **Sin Telethon no se activan** y el bot sigue funcionando con el resto. Documentado en ambos README, porque quien instale sin cuenta secundaria no sabría qué se pierde.

También depende de Telethon la lectura de **historias** (`story_reader.py`). La Bot API entrega una historia compartida con **solo `chat` e `id`**: sin texto, sin imagen, sin entidades y **sin marca de reenvío**, así que `forward_first_msg` tampoco salta. Para el bot es un mensaje vacío y el spam pasa limpio (caso real: publicidad de cripto con enlace de invitación). Se pide el contenido con `stories.getStoriesByID` y se sigue el flujo normal con ese texto: mismos detectores, mismos umbrales, porque la evidencia es el texto real.

Tres cosas que no se deben olvidar al tocarlo:
- **Las entidades hay que traducirlas** de MTProto a la Bot API. Los detectores de enlaces y menciones **no miran el texto plano, solo las entidades**: sin traducir se lee la publicidad pero se pierde el enlace, que es la prueba. Hay test que lo fija.
- **No delata la cuenta**: `getStoriesByID` no cuenta como visualización (eso es `incrementStoryViews`), así que la cuenta secundaria no aparece en la lista de espectadores. Era la condición para hacerlo.
- **Caducan entre 6 y 48 h.** Para moderar en vivo sobra; para analizar a posteriori un mensaje viejo ya no hay nada que leer, y `/scan` lo dice en vez de fingir un veredicto.

---

<a id="l14"></a>
## L14 · El canal personal y la discordancia (`personal_channel_spam`)

**El perfil tiene más de un escaparate.** Durante mucho tiempo solo leíamos `about` (la bio). El **canal personal** (Telegram 2024, `personal_channel_id`, disponible desde Telethon 1.36) es un campo SEPARADO: un perfil con la bio vacía puede tener ahí un canal entero de spam. Caso real que lo destapó: cuenta «Matthew», nombre latino, sin foto ni bio, con un canal chino reclutando mulas de blanqueo. Si aparece otro campo nuevo de perfil, mirarlo antes de fiarse de que el perfil está limpio.

El detector tuvo que ampliarse cuando la misma red volvió con el **nombre también en chino**: sin discordancia se quedaba en 40 de 100 y se colaba. Se sumaron los compuestos de la red (`结账通知`, `飞机加群`, nunca palabras sueltas como `结账`, que es corriente) y una señal de **cadenas generadas a máquina** en bio/usuario (`bhLQZZXwkU2M`): una bio de ruido informativamente es no tener bio. Esa señal mira **rachas de mayúsculas intercaladas**, no vocales, porque medir vocales marcaba a usuarios checos y polacos legítimos (`wchrzszcz`).

`personal_channel_spam` **no salta por tener canal**: eso es legítimo. La señal es la **discordancia** (nombre en alfabeto latino + canal en otro script), que es un disfraz deliberado. Ninguna señal suelta llega al umbral. Lección del caso: el bot ya cazaba a los de esta red que usaban nombre chino; los que se colaban eran los que se ponían nombre occidental.

---

<a id="l15"></a>
## L15 · El rótulo del canal lo elige el spammer (`channel_reader`)

**El rótulo del canal es la parte que el spammer elige.** Esa red renombra sus canales en cuanto se les caza, así que perseguir títulos siempre va por detrás. Caso medido (2026-08-08, Windows 11): «Vickycat46», nombre latino y **foto de perfil normal**, con el canal `恒泰招聘车队高速结算`; sumaba **85 de 100** y se libraba justo por tener foto. Su primer post decía `洗米来有码就要 无风险 日3-8k`, con `洗米` («lavar arroz») donde la lista esperaba `洗钱` («lavar dinero»): jerga para esquivar filtros. `channel_reader.py` lee ahora la descripción y los últimos posts, y ese texto pasa por las mismas listas (75 puntos, que siguen sin decidir solos). Tres cosas que no se deben romper:
- **Solo se paga cuando puede cambiar el veredicto**: primero el título (gratis, ya viene con las señales del perfil) y solo si no basta se hace la llamada de red. De 131 recién llegados en 14 días, 6 tenían canal.
- **No delata la cuenta ni se une a nada**: pedir el historial no cuenta como visualización (eso es `messages.getMessagesViews`), y un canal público se lee sin suscribirse. Mismo criterio que `story_reader`.
- **Usa la entidad que ya viene en `GetFullUser.chats`**, sin `contacts.ResolveUsername`, que es lo más propenso a FloodWait.

`recien_llegados` también mira ese escaparate, porque el canal se puede enlazar DESPUÉS de entrar y no se ve desde la Bot API. Allí el nombre puede estar limpio, así que hay que leer algunos perfiles «por si acaso»: de ahí el presupuesto de lecturas por vuelta, para no quemar la cuenta secundaria.

---

<a id="l16"></a>
## L16 · Recién llegados: nombre visto, cambio en el momento y ventana de 7 días

**Cada repaso deja constancia del nombre visto.** `seen_users.first_name` solo se escribía al HABLAR, así que de quien aún no ha escrito no había nada con que comparar y no se podía responder «¿lo miramos y no saltó, o cambió justo antes de escribir?». Caso del 1-sep-2026: el 8846717922 entró a las 06:28 con un nombre que no disparaba (traza del join: `señales=sí`, y fue a verificación, no a ban), y escribió a las 09:21 como `电我煮叶`; entre medias se le miró el nombre unas once veces sin saltar nada. Ahora el repaso guarda el nombre actual y registra el cambio (`se ha cambiado el nombre: X → Y`).

**El cambio de nombre se caza también en el momento.** La Bot API no entrega nada de esto (sus `chat_member` son cambios de ESTADO: entrar, salir, ban, promote), pero MTProto tiene `updateUserName`. `telethon_bridge` lo escucha y lanza `recien_llegados.revisar_ahora`, que **no decide nada**: invalida las cachés de esa persona y llama a la misma `_revisar_perfil` del barrido, para que no haya dos varas de medir. La documentación oficial no dice para qué usuarios se entrega ese update, así que es a la vez defensa y experimento: si llega, el disfraz cae en segundos; si no, el handler no se dispara y el barrido periódico sigue cubriendo. Frenos: solo gente vigilada que aún no ha escrito, y 2 min por persona.

**La ventana de vigilancia es de 7 DÍAS, con dos cadencias.** Estuvo en 24 h y la red lo midió: el 7688429577 entró limpio (traza del join: `señales=sí canal=-`), dejó vencer la ventana entera y escribió a las **29,6 h** con el nombre `六o0壹天` y el canal de la red puestos ya fuera de vigilancia. Los tres casos escribieron a las 5,7 h → 15 h → 29,6 h: se adaptan al plazo que ven. El primer día todo va a ritmo caliente (nombre cada vuelta, Telethon y listas cada 1 h); del segundo al séptimo, Telethon y listas cada 6 h, pero **el nombre se sigue mirando en cada vuelta los 7 días** porque es Bot API y es gratis. Cuentas medidas al calibrar (142 callados en la ventana, ~46 lecturas Telethon/h contra 48 de presupuesto) fijadas con test: quien mueva una constante tiene que rehacer la cuenta.

**Lo gratis no lleva el freno de lo caro.** En ese repaso hay dos ritmos distintos a propósito: el **nombre** se mira en CADA vuelta (`get_chat_member` es Bot API: gratis, sin límite práctico y sin tocar la cuenta secundaria), y las **listas externas** (CAS, lols) mantienen su espera de una hora porque son APIs de terceros. Estuvieron igualados y era regalarle al spammer una hora a cambio de nada: el nombre es justo lo que cambia, ya que el truco consiste en entrar con uno que pasa los filtros y ponerse el de verdad poco antes de hablar. Si alguien vuelve a igualar `MAX_NOMBRES_POR_CICLO` con `MAX_POR_CICLO`, ha perdido el porqué (hay test).

---

<a id="l17"></a>
## L17 · El texto dentro de una imagen (`ocr.py`)

Un cartel publicitario era, para el bot, un mensaje vacío: ningún detector tenía nada que mirar. Caso real (2026-09-06, Windows 11): imagen ofreciendo «INSTALACIÓN Y ACTIVACIÓN DE SOFTWARE — Windows, Office, Photoshop, AutoCAD (todas las versiones) — ESCRÍBEME POR INTERNO», sin una sola letra escrita.

**Tesseract**, no EasyOCR ni PaddleOCR: medido, **0,61 s** por imagen y sin GPU, contra cientos de megas de PyTorch/ONNX que aquí no hacen falta (el texto de un cartel es grande y con contraste, el caso más fácil). Volumen real: **2 primeros mensajes al día**, o sea ~1 s de CPU diario aunque todos llevaran foto.

Cuatro cosas que no se deben romper:
- **El OCR no decide nada**: solo aporta texto, y lo juzgan los MISMOS detectores con sus umbrales. Una foto de un ordenador sin letras da vacío y puntúa 0. Hay test que prohíbe que `ocr.py` mencione `Hit`, `score` o `rule`.
- **Corre en un hilo** (`run_in_executor`) con tope duro: PTB procesa los updates de uno en uno y 0,61 s bloqueando el bucle son 0,61 s sin moderar.
- **Solo primeros mensajes con imagen y SIN texto propio.** Aplicarlo a cada foto serían cientos de descargas diarias.
- **Sin tesseract el bot funciona igual**: se detecta una vez y no se reintenta.
- **Se apaga por chat** desde `/config` (`chat_settings.ocr_enabled`, defecto **1**). Ante un ajuste ilegible se deja ENCENDIDO, al revés que los demás: aquí «restrictivo» sería dejar de mirar, y el OCR no castiga por sí mismo.
- **Los idiomas salen de los del bot** (`wordlists.active_langs()`, o sea idioma activo + inglés, o `BLACKLIST_LANGS`), no de una lista aparte, y se filtran los que Tesseract no tenga instalados: pedirle uno que le falta hace fallar la llamada ENTERA. `OCR_LANGS` lo fija a mano si hace falta.
- **Si no llega para actuar pero deja dudas, avisa por privado** (`ocr_review`, silenciable desde `/alertas`): cuando el texto queda en la franja gris (≥`mute_score` y por debajo de la acción) o cuando NO hay texto y quien la manda es un desconocido con trust bajo, que es justo la forma de esquivar los detectores de contenido. Solo avisa, nunca actúa, y reutiliza los botones nada/avisar/banear del aviso de confianza. Con freno de media hora por persona: alguien asentado mandando una foto no genera nada.
- **Ese aviso se manda DESPUÉS de decidir, y solo si no se actúa** (`diferido` + `_soltar_aviso_imagen`, en los dos `return` sin hits y tras `decide()` con `noop`). Salía en cuanto acababa el OCR y medio segundo después las señales de forma baneaban: el admin recibió «No he hecho nada» de alguien ya baneado y creyó que se había colado (caso Joka, 3-oct-2026).
- **El vocabulario es el MISMO que el de los mensajes escritos** (decisión del admin: el spam es el mismo venga en texto o en cartel, y dos listas en paralelo acaban con una desactualizada). Quien quiera términos que solo valgan para carteles los pone en `config/blacklist/ocr/`, que se SUMA y está vacía por defecto. El modo se activa con `wordlists.modo_ocr()` y entra en la clave de la caché de patrones: sin eso, el primer cartel dejaría cacheado un patrón que luego se aplicaría a los mensajes normales.

**El vocabulario es la otra mitad, y sin él el OCR no sirve de nada**: el texto extraído puntuaba **0** con las listas de entonces. Al añadir el de venta de software pirata hay que recordar que el contexto son grupos de Windows, donde «activar», «instalación» y «licencia» son palabras del día a día: ninguna va suelta. Se probó `escríbeme por interno` y marcaba «escríbeme por interno y te paso el driver». Lo inequívoco es el CATÁLOGO (cinco programas de pago listados) y la estructura de oferta. Los patrones toleran ruido con `[\s\S]{0,N}` porque el OCR parte las palabras.

---

<a id="l18"></a>
## L18 · El catálogo de software pirata en inglés (Adobe)

**El mismo catálogo llega en inglés y en texto.** Caso real (30-sep-2026, Windows 10):
cuenta «Adobe» (@Adobe_Global) con «ADOBE REDEEM CODE ( 1month - 12months ) —>
( Warranty full )», Creative Cloud, CapCut Pro, Office Pro Plus, ChatGPT Pro… Puntuaba
45 (solo las líneas con emoji): el vocabulario de software pirata estaba en español.
Dos piezas: en `en/commercial_illegal_services.txt`, `redeem code`, `full warranty` y
el rango de duración `1month - 12months` (ninguna decide sola: una = 50 < 60); y la
señal de **catálogo** (`_marcas_distintas` ≥ `_CATALOGO_MIN` = 4 marcas de pago
DISTINTAS, lista editable en `commercial_software_catalog.txt`, +40, que sola tampoco
llega: un grupo de Windows nombra esas marcas a diario). Medido sobre **503 mensajes
reales**: solo cambia el spam, de 0 a 155.

---

<a id="l19"></a>
## L19 · El guion del «dinero extra» cerrado por privado (Natalia)

**El guion del «dinero extra» que se cierra por privado.** Caso real (8-oct-2026,
Windows 10): «Natalia», «Si alguna vez has querido ganar dinero extra pero no sabes
por dónde empezar, puedo compartir contigo algo que estoy haciendo… estoy
obteniendo buenos resultados… solo envíame un mensaje». Sin cifras ni enlace sumaba
50 (< 60) y solo lo paró `learned_similarity` con un mute. Tres piezas nuevas en
`commercial_ad`: oferta de dinero + petición de **privado** (`commercial_dm_cta.txt`)
= +35, el mismo peso que oferta + enlace, porque aquí el privado ES el enlace;
**frases gancho** (`commercial_teaser.txt`, 1 = +20, 2+ distintas = +45); y el
guion entero (dinero + privado + 2 ganchos) = +25. El caso da **155**: ban y
reporte. ⚠️ **Ni los ganchos ni el privado cuentan sin oferta de dinero o
trabajo**: «si no sabes por dónde empezar, escríbeme y te paso la guía» es ayuda
normal en un grupo de Windows (hay test). Medido sobre 524 textos reales: solo
cambia este (0 → 155).

---

<a id="l20"></a>
## L20 · La variante del «trabajo extra» (María)

**La variante del «trabajo extra»** (20-oct-2026, Windows 10, «María», cuenta
callada 42 días): «Tengo un trabajo extra al que solo le dedico unas pocas horas…
no se trata de ventas ni implica molestar a familiares… si les interesa, les envío
la información». Daba **0** y solo hubo mute por `learned_similarity`. Ahora es
oferta de trabajo **solo con «tengo un trabajo extra» / «trabajo extra al que…»**
(«me supone un trabajo extra» no cuenta), «les envío la información» hace de
privado y las objeciones («pocas horas», «no son ventas», «sin molestar a
familiares», «no hay nada igual») son ganchos: **135**. Medido sobre 669 textos
reales: solo cambia este. ⚠️ «Tengo un trabajo extra en una tienda, si os interesa
os paso la información» en un primer mensaje da **65** (mute de recién llegado,
nada para quien tiene confianza ≥40): es autopromoción y se aceptó así.

---

<a id="l21"></a>
## L21 · Las señales de forma no castigan solas (Kleo, el perdón y los `jfm_*`)

`forward_first_msg`, `first_msg_media` y los `jfm_*` no miran lo que DICE el
mensaje, solo su forma o su circunstancia: que sea un reenvío, que lleve foto, que
se escribiera a los pocos segundos de entrar. **Ninguna es prueba de spam por sí
misma**, y sumadas de dos en dos llegaban al umbral sin que nadie hubiera leído el
mensaje.

Caso real (7-sep-2026, Windows 11): «Kleo» entró, se verificó en 10 s y reenvió un
mensaje **suyo propio** con la captura de una compra y 165 caracteres preguntando
si la licencia que acababa de comprar era retail. Sumó `forward_first_msg` (80,
origen `user` = él mismo) + `first_msg_media` (70, con `is_suspicious: false` en su
propio payload) = **150 exactos**, que es a la vez el umbral de ban y el de
reporte: acabó **baneado en los cuatro grupos por federación y reportado dos veces
a Telegram**, sin que una sola regla de contenido disparara. Una pregunta sobre
licencias de Windows, en un grupo de Windows.

**Lo que dice el histórico** (`moderation_log`, 15 casos desde mayo):
`forward_first_msg` ha saltado 7 veces y **las 7 con origen CANAL**; con origen
`user` no ha cazado nunca nada. Y **todos** los bans acertados llevaban además una
señal de contenido (`commercial_ad`, `non_allowed_script`,
`external_mention_or_link`, `inline_buttons_from_user`) o el perfil marcado como
sospechoso. El de Kleo es el único sin ninguna de las dos.

Tres cambios, y ninguno toca los scores (cambiar un umbral sin datos es justo lo
que se desaconseja aquí):

1. **Reenviarse algo propio no es traer contenido de fuera** y no puntúa
   (`_es_reenvio_de_uno_mismo`): se compara el id del autor con el del origen, y
   con la privacidad de reenvío activada —donde no hay id— el nombre visible.
2. **`_perdon_por_contenido_limpio`**: si TODOS los hits son de forma, el reenvío
   no viene de canal/chat/bot, la persona escribió texto propio suficiente
   (≥40 caracteres y ≥6 palabras) que no dispara nada, y **lo que el OCR saca de la
   imagen tampoco**, no se castiga: se avisa al admin con los botones de siempre.
   Ese último paso es el que cierra el hueco de «caption inocente + cartel de
   spam», y **es la única vez que se lee una imagen que ya trae texto**: se paga
   solo donde puede cambiar el veredicto, igual que en `channel_reader`.
3. **No se reporta a Telegram por señales de pura forma.** Un reporte oficial quema
   la reputación de la cuenta secundaria, que es justo lo que `_REPORT_MIN_SCORE`
   pretendía proteger, y dos señales de forma llegaban a 150 sin evidencia.

⚠️ **«Parece estructural» no es lo mismo que «no ha cazado nada».** Al escribir el
perdón se metieron también los `jfm_*` (escribir a los pocos segundos de entrar) por
parecerse a los otros dos, y hubo que sacarlos el mismo día: `jfm_too_fast` ha
expulsado a 2 personas como regla única y **las 2 eran spam real** (PopcornTV con
enlace, 1xbet), o sea 2 aciertos de 2. Con ellos dentro, el perdón habría tapado los
dos. Antes de meter una regla en `_REGLAS_DE_FORMA` hay que mirar en
`moderation_log` qué ha cazado de verdad. De ahí salió la segunda red: **un texto con
enlace o mención no compra el perdón**, porque `astrurl.io` no estaba en ninguna
lista negra y aquel spam llegó a la decisión con una sola regla disparada.

⚠️ **El aviso del perdón NO puede decir «alguien de confianza».** Reutiliza
`_send_trust_notice`, que nació para el trust alto, y de sus cuatro llamadores **dos
avisan con el trust por los suelos** (este perdón y el veto del modelo): a «Eduardo»,
**confianza 1/10**, preguntando por qué su PC no se veía a sí misma en la red, le
salió «Algo raro de alguien de confianza… su historial le avala». Quien manda el
aviso sabe por qué lo manda, así que elige cabecera y pie con `avala_historial`. Hay
test que cuenta los llamadores: si aparece un quinto, hay que pensar su variante.

---

<a id="l22"></a>
## L22 · Los avisos por privado llevan enlace al mensaje

**Los cuatro avisos por privado llevan enlace al mensaje** (`enlaces.al_mensaje`,
módulo propio porque `admin_report` no puede importar `handlers` sin ciclo):
`t.me/<user>/<id>` en grupo público, `t.me/c/<id sin -100>/<id>` en supergrupo
privado, y **nada** en un grupo básico, donde no existe permalink y no se inventa
(ni `<a href="None">` ni `{enlace}` a medio rellenar). La forma plana vale también
con foros, sin `message_thread_id`. Es un privado al admin: la regla de «sin enlaces
clicables» rige para lo que se publica en el grupo.

Una sola clave `hdl.enlace_al_msg` para los cuatro (`trust_notice_dm`,
`ocr_review_dm`, `review_dm`, `report.admin_dm`): con una por aviso, la menos usada
se queda atrás en silencio. El del reporte enlaza al mensaje **reportado**, no al del
reportante, porque la copia que se manda llega sin el hilo alrededor. Hay test de que
los cuatro huecos se rellenan desde el código: un `{enlace}` que nadie rellene
revienta el aviso entero con un `KeyError` y el admin no se entera de nada.

---

<a id="l23"></a>
## L23 · La cuenta robada de un veterano la para el destino (xevi)

**La cuenta robada de un veterano la para el DESTINO, no la confianza.** Caso real
(1-oct-2026, Domótica): «xevi», en el grupo desde 2018 con 70 mensajes (confianza
9/10), publicó «t.me/+… Caseros Exclusivos, únete rápido!» hacia «Caseros Wild 🌎🌀»
(5.507 miembros). Por la confianza solo hubo aviso suave, y es correcto que la
confianza proteja a un veterano de una señal dudosa. Lo que faltaba era reconocer el
destino: «caseros» solo contaba junto a «packs». Se añadió emparejado con su reclamo
(wild, exclusivos, filtrados, xxx, hot…), nunca suelto («remedios caseros»), y como
`link_target_spam` es regla dura, la confianza ya no lo ablanda. Queda traza
`destino de enlace … → SPAM/limpio/sin ficha`: aquella vez no quedó ninguna. Y los
avisos con confianza dicen de dónde sale (`_porque_confianza`: desde cuándo, cuántos
mensajes, warns), a petición del admin: «9/10» a secas no explicaba nada.

---

<a id="l24"></a>
## L24 · Web porno: `adult_link` (Elxufas)

**Y lo mismo con una WEB porno: `adult_link`** (`link_target.check_anuncio`, regla
dura y reportable). Caso real (20-oct-2026, Windows 11): «Elxufas», en el grupo
desde 2025 con confianza 64, publicó tres veces «JERK OFF… leaked content… 🔞
http://nsfwlook.online»; solo saltó `learned_similarity` y la confianza lo anuló.
Una web no se lee como un t.me (salir a mirarla delataría al servidor), pero se
presenta sola: exige **enlace + dos señales explícitas distintas**, o una y un
dominio que se anuncia por el nombre (`adult_domains.txt`). ⚠️ **Fuera de
`adult_explicit.txt` todo lo que se dice al hablar de control parental**: «porno»,
«xxx», «contenido para adultos», «+18», «sexo explícito», «contenido filtrado» (el
test lo cazó: «cómo bloqueo el contenido xxx… pornhub.com» daba ban). La URL se
quita del texto antes de contar, para que el dominio no cuente dos veces. Medido
sobre 453 mensajes legítimos: ni una coincidencia de vocabulario.

---

<a id="l25"></a>
## L25 · Referido publicado con un bot inline: `via_bot_referral` (Lil Pani)

**Y el referido publicado con un bot inline: `via_bot_referral`**
(`inline_buttons.enlaces_de_referido`, regla dura). Caso real (21-oct-2026, Windows
11): «Lil Pani», miembro desde 2025 con 27 preguntas sobre Windows, publicó con
@case_rush_bot un anuncio de cajas de premios con un botón a
`t.me/case_rush_bot/app?startapp=r_<su id>`: cobra por cada uno que entre. El
camino `via_bot` solo borraba y avisaba «no le he baneado», **sin enseñar qué era**.
Ahora, un botón a un bot o mini-app cuyo `start`/`startapp` lleva **el id de quien
publica** o empieza por `ref`/`r_`/`invite`/`aff` = ban por `_apply_action` (que
copia el mensaje al privado antes de borrarlo). ⚠️ **El resto de botones vía bot
NO banea**: encuestas (@vote) y juegos llevan callbacks, y un cheque de cripto
(`t.me/send?start=CQ…`) lleva parámetro pero no es un referido (hay test). Esos
siguen en «borrar y avisar», ahora con copia y la lista de botones. Solo había un
caso en `moderation_log`: no hay más con qué medir.

---

<a id="l26"></a>
## L26 · Un @ mal escrito no es una mención externa: `errata_mencion`

**Un @ mal escrito no es una mención externa: `errata_mencion`.** Caso real
(25-oct-2026, Domótica): «Juan M.», confianza 9/10, escribió «Era porque @Moliko
tenía varios Spot…» por @Molkio (382 mensajes): aviso suave en el grupo y «Algo
raro de alguien de confianza» al admin, para nada. Ahora un @ que el bot **no
conoce** (si resuelve a alguien, es otra persona) y que está a una tecla del de un
miembro (`external_mention.posible_errata`: una edición o dos letras vecinas
cruzadas; dos si pasa de nueve letras; empate entre dos miembros = no se adivina)
no puntúa, y en las salidas sin acción el bot responde **citando justo el @ mal
escrito** (`ReplyParameters.quote`, posición en UTF-16; si Telegram rechaza la cita,
responde sin ella) «No encuentro a @x en el grupo. ¿Quizás te referías a @y?». Se borra al corregirlo editando
(`on_edited_message`, aunque el re-escaneo esté apagado) o a los 10 min; va en
`gentle_warnings` (columna `errata`) para heredar la cascada al borrar y la
limpieza al banear, y `barrido_job` cubre los reinicios. ⚠️ **Nunca en los
primeros mensajes**: parecerse por una tecla al @ de un admin es suplantarlo, y
ahí sigue puntuando. ⚠️ **Los @ van en `<code>`**: sin eso el bot mencionaría al
miembro y al dueño de lo mal escrito, que puede ser cualquiera de fuera. Medido
sobre 786 textos: de 111 menciones a desconocidos (casi todas bots de spam con
nombres al azar) solo esta se parece a un miembro.

---

<a id="l27"></a>
## L27 · El aviso suave se da por resuelto si el autor lo corrige

**Y si el aviso ya salió y el autor lo corrige editando** (petición del admin,
25-oct-2026): el camino del aviso suave (solo reglas borderline y alguien de
confianza) guarda en `avisos_admin` el id del privado, el del aviso del grupo y el
texto. Si una edición deja el mensaje sin ningún hit, `_aviso_resuelto_al_editar`
**edita** el privado a «✅ Corregido por su autor», sin botones y con «Antes decía:»
(editar no notifica, y la prueba queda por si era una cuenta robada borrando el
rastro), y borra el aviso del grupo. Una edición que sigue igual no repite ninguno de
los dos. ⚠️ **Solo ese camino se registra** (hay test): lo que el bot habría baneado
no se da por bueno porque se edite. Si el admin ya pulsó un botón, la fila se borra
y su decisión no se reescribe.

---

<a id="l28"></a>
## L28 · Escribir pronto no castiga a quien ya es legítimo (Saizor)

**Escribir pronto no castiga a quien el bot ya da por legítimo**
(`_solo_prisa_sin_contenido` + `_is_very_legit_profile`, tras `decide()`). Caso real
(6-oct-2026, Windows 11): «Saizor», cuenta de 2.885 días con 20 fotos, a quien al
entrar se le saltó la verificación por eso mismo, escribió «BUENAS» a los 3 s y lo
expulsó `jfm_too_fast`; volvió, «HOLA» a los 3 s, otra expulsión. Con esto el
historial de esa regla como única queda en 2 aciertos y 1 falso positivo, y los
aciertos llevaban contenido. Solo se perdona si **no hay nada más que la prisa**
(ni enlace, ni mención, ni reenvío, ni adjunto, ni botones, ni otra regla) **y** el
perfil es legítimo: PopcornTV, con su enlace, sigue cayendo. Queda auditado como
`noop_prisa_legitimo`. No se tocó el umbral ni se metieron los `jfm_*` en
`_REGLAS_DE_FORMA`: el perdón de forma exige texto largo, y un saludo no lo es.

---

<a id="l29"></a>
## L29 · El perdón no alcanza al reenvío desde canal, chat o bot

⚠️ **El perdón NO alcanza al reenvío desde un canal, un chat o un bot**: ese es el
patrón fuerte y el único que ha acertado. El caption lo escribe el spammer y le
sale gratis, así que un texto limpio no puede comprarlo. Si alguien mete en
`_REGLAS_DE_FORMA` una regla que sí mira el contenido, el perdón deja de exigir
evidencia y empieza a tapar spam real: hay test que lo impide.

---

<a id="l30"></a>
## L30 · Listas negras: las tres capas y la vista previa

Tres capas que se **acumulan** (el spam llega en cualquier idioma):

1. `config/blacklist/*.txt` — genéricas, versionadas (11 archivos).
2. `config/blacklist/<lang>/*.txt` — por idioma (`en/` con 9). Se cargan según el idioma activo + `BLACKLIST_LANGS`.
3. `config/blacklist/custom/*.txt` — **las que añade el admin desde Telegram**. Gitignored, para que un `git pull` no las pise.

Cada línea es un **regex**, salvo en `custom/`, donde todo se escapa: es imposible colar un regex activo desde Telegram (`custom_terms.py`). Un patrón inválido se ignora con un log, nunca tumba el bot.

**Añadir un término desde el panel pasa SIEMPRE por vista previa**: `custom_terms.preview_term()` dice con cuántos mensajes reales y recientes del grupo coincidiría, con ejemplos, antes de guardar. Un término como «oferta» caza 3 de cada 4 mensajes de un grupo de informática.

---

<a id="l31"></a>
## L31 · El envoltorio de las listas: lookarounds, nunca `\b`

`compile_alternation` envuelve los términos con `(?<!\w)…(?!\w)`. **No es un
detalle de estilo.** Con el `\b(?:…)\b` que había antes, cualquier alternativa
que empiece o acabe en algo que no sea carácter de palabra queda muerta: `\b`
exige una frontera pegada al símbolo y junto a `$`, `€` o un espacio no existe.

Medido el 2026-08-29: **ni `$500` ni `500€` casaban**, o sea que la señal de
dinero de `commercial_ad` llevaba muerta en silencio. Este mismo fichero afirmaba
lo contrario porque los tests usaban importes en palabra («500 euros»), que sí
pasan el `\b`. Comprobado tras el arreglo sobre 164 mensajes reales: **cero
cambios de puntuación** salvo el spam que lo destapó.

---

<a id="l32"></a>
## L32 · Anti falso positivo en los patrones (monedas, importes, América)

- Las palabras de moneda que son palabras comunes (`peso`, `real`, `sol`, `libra`, `corona`) **solo cuentan pegadas a una cifra**. Hay tests con «el peso del paquete», «hace un sol», «media libra de harina» para que nadie las añada sueltas.
- El importe se escribe distinto por región: `500€` (detrás) y `$500` (delante). Ambas formas soportadas, más `$2000` sin separador.
- Cubierto el español de América: monedas locales, «por día» (patrón central del spam laboral latinoamericano) y voseo (`escribime`, `ganá`, `trabajá`).

---

<a id="l33"></a>
## L33 · `investment_scam`: el molde para detectar sin falsos positivos

Caza el testimonio «di X y me devolvieron Y (mucho mayor)» (caso real: «I gave her 25,000 Rs … she gave me 318,000 Rs 👇 @X»). Sin él se colaba cuando no ponían `@usuario` final. Su diseño es el molde para cualquier detector de contenido nuevo:

- **La señal fuerte no es el tema, es la discordancia.** «Dinero» lo dice todo el mundo; lo raro es «di X y recibí mucho más». El **ancla** es esa estructura numérica (`_GIVE_BACK_RE`, retorno ≥1.5× la entrega), calculada comparando importes, no una palabra suelta.
- **Ninguna señal decide sola** (`señales_estafa < 2 → none()`). Con ancla basta una señal de apoyo; sin ancla hacen falta dos. Así «invertí 1000 y ahora vale 1500» (solo ancla, y `worth` está **fuera** de los verbos de retorno a propósito) no cae, ni «gracias John» (un elogio suelto) tampoco.
- **Refuerzos que nunca deciden**: tiempo («after 12 hours»), primer mensaje. Solo suman si ya hay estructura.

**El timo viene en DOS mitades, y la segunda no lleva cifras.** Uno publica el
anzuelo y un segundo perfil responde haciéndose pasar por cliente satisfecho. Caso
real (11-sep-2026, Windows 10): «Saw your post and honestly thought it was a scam,
but the money actually came through and I'm in shock». Ni cifras, ni @usuario, ni
enlace, así que el ancla numérica no casaba, `commercial_ad` daba 0 y al estar en
inglés tampoco saltaba `non_allowed_script`: **el detector puntuaba 0** y lo tuvo
que borrar y banear un admin a mano. Detalle que lo delata y conviene recordar: la
cuenta entró el **7** y escribió su primer y único mensaje el **11** — llega días
después precisamente porque el enlace lo pone el otro.

Se añadió `_SKEPTIC_FLIP_RE` como **segunda ancla del mismo peso** (45): admitir que
se sospechaba una estafa **y a continuación** decir que el dinero llegó. El conector
de reversión («pero», «but») es obligatorio; sin él, «pensé que era una estafa» y
«me pagaron» pueden ser dos frases de conversaciones distintas del mismo párrafo.
Es estructural, no vocabulario, así que **no se externaliza** (hay test). Lo que sí
es editable es `investment_testimony.txt`: las fórmulas de testimonio en primera
persona («I'm in shock», «saw your post»), que **por sí solas no deciden nada**.

Medido antes de desplegarlo sobre **365 mensajes reales** de los cuatro grupos:
disparan **dos**, y son las dos estafas conocidas. Cero falsos positivos.

**Tercera ancla: el sorteo cripto falso de un famoso** (`_GIVEAWAY_RE`, 45). Caso
real (3-oct-2026, Windows 10): captura de un tuit falso de Elon Musk, «New $2500
crypto giveaway | Is now LIVE on WexPred.com Use my promo code ElonX». El OCR lo
leyó entero y puntuó **0**; lo cazaron por suerte `jfm_fast` + `first_msg_media`.
La discordancia es regalar cripto y mandarte a canjearlo a otra web: exige
cripto + sorteo/airdrop **y** el mecanismo de canje (código o «live on x.com») a
≤160 caracteres. «Cuidado con los crypto giveaway» no cae. **El trozo del ancla no
cuenta además como vocabulario**: si no, una sola frase sumaba dos señales y la
guarda de dos señales dejaba de exigir nada. El caso real da 80 (kick); con la foto
del primer mensaje pasa de 150. Medido sobre 440 textos reales: el ancla no salta
en ninguno.

---

<a id="l34"></a>
## L34 · Alfabetos permitidos por chat

`ALLOWED_SCRIPTS` del `.env` era **global y sin interfaz**: quien instalara el bot en una comunidad árabe, rusa o griega tenía al bot marcando a sus usuarios normales (medido: un saludo en árabe puntúa 100 con el default `latin`). Ahora hay columna `chat_settings.allowed_scripts` (CSV) donde **NULL = hereda el `.env`**, resuelta por `_chat_allowed_scripts()` en `handlers.py`.

Dos guardas que no se deben quitar:
- **Nunca lista vacía**: sin ningún alfabeto permitido el bot marcaría TODOS los mensajes. El helper cae al `.env` y el panel rechaza quitar el último.
- **NULL = hereda**: con default `'latin'`, una instalación que ya permitía cirílico habría empezado a marcar a los suyos al actualizar.

El panel enseña **qué alfabetos se escriben de verdad en el grupo** (sobre `seen_users.last_msg_text`) y avisa de cuáles causarían falsos positivos: mismo patrón de «ver antes de decidir» que la vista previa de palabras bloqueadas.

---

<a id="l35"></a>
## L35 · Ajuste `money_guard` por chat

Modula la agresividad de **`commercial_ad` + `investment_scam`** (los de trabajo/dinero). Columna `chat_settings.money_guard` (`'normal'` | `'soft'` | `'off'`), filtro en `_apply_money_guard()` de `handlers.py`:
- `normal` (defecto): caza claros y borderline.
- `soft`: solo score ≥ `_MONEY_SOFT_MIN_SCORE` (100); el borderline de trabajo/dinero pasa. **No** sube la agresividad, solo la baja.
- `off`: esos dos detectores no actúan (el resto sigue).

El filtro vive en el handler, no en los detectores: siguen puros. Botón en el panel principal y por `/config`, respeta `/sync`.

---

<a id="l36"></a>
## L36 · Aprendizaje: salvaguardas, autoaprendizaje y la palabra nunca vista (Andre)

Naive Bayes + coseno sobre las muestras marcadas por el admin. `BAYES_MIN_SAMPLES_PER_CLASS = 10` de **cada** clase: con 0 muestras ham el Bayes está dormido y solo actúa el coseno.

Salvaguardas para que el bot no aprenda a castigar el vocabulario normal de su grupo:
- Ningún token decide solo el veredicto (tope al log-odds).
- El que aparece en spam Y en ham pesa la mitad: no separa nada.
- El visto una sola vez pesa un tercio: es ruido, no evidencia.
- `classifier_excluded_tokens.txt`: los defaults en código son palabras funcionales del idioma (valen para cualquier comunidad). **El vocabulario temático lo pone cada admin**: solo él conoce su grupo.

**Aprende solo, sin IA externa** (`autoaprendizaje.py`, decisión del admin 30-sep-2026:
de «juez con IA», «aprender solo» y «que proponga reglas» eligió las dos que no sacan
nada del servidor). **El clasificador llevaba dormido desde siempre**: solo mira 90
días y en esa ventana había **1** ejemplo de spam y **0** legítimos (pide 10 y 10).
- **Legítimos automáticos**: mensaje sin ningún hit de alguien con trust ≥70, ≥25
  caracteres y ≥5 palabras, sin enlaces ni menciones ni reenvíos; uno por persona y
  día, 40 al día, 400 en total. Si esa persona acaba baneada, se olvidan.
- **Spam automático** solo de bans SEGUROS: alguna regla de CONTENIDO (ni de forma,
  que es Kleo, ni de perfil) y además ≥150 o CAS/lols. `learned_similarity` no cuenta:
  aprender de lo que ya se parece a lo aprendido es un bucle. Al desbanear se olvida.
- `added_by = 0` marca lo automático: se deshace sin tocar lo que marcó el admin.
- **Un ban manual solo PROPONE** («¿era spam?» por privado con botones): se banea
  también por insultar, y aprender de eso enseñaría a castigar insultos.
- **Propuestas de FRASES**: solo si la frase ya salió en OTRO spam confirmado, lleva
  alguna palabra que nunca se ha dicho en la conversación legítima, y la vista previa
  sale limpia. Medido: entre 37 spams reales **solo una** frase se repetía («al mes»,
  corriente), y proponer frases de un único spam era proponer falsos positivos (a una
  pregunta normal le sugería «no me aparece»; del Adobe, «office pro plus»). Serán
  raras, a propósito. Se añaden a `commercial_illegal_services.txt` (35, no deciden
  solas).
- Ensayo en seco antes de activar, con 16 ejemplos de spam de los bans seguros de 90
  días y 12 legítimos simulados: de 327 mensajes legítimos **ninguno sube** salvo dos
  que resultaron ser spam (Mila y DARK VECTOR, cuyos bans nunca se federaron).

⚠️ **Una palabra NUNCA vista no es evidencia** (`naive_bayes_spam_prob` la salta).
Con Laplace pesa hacia la clase con MENOS texto. Al activar el autoaprendizaje esa
era el ham y el sesgo absolvía; el ham crece más rápido (40 al día) y el 24-oct ya
eran 91 legítimos frente a 30 spams, así que cada palabra nueva sumaba +0,37 a
spam y **un mensaje largo caía por ser largo**. Caso real (24-oct-2026, Windows
11): «Andre», recién llegado, preguntó en 500 caracteres por qué la instalación de
Windows no veía sus discos (partdisk, particionar, HDD…): p=0,997, mute y mensaje
borrado. Medido sobre los textos guardados: **47 de 421 legítimos** (el 11 %, casi
todo preguntas técnicas largas) puntuaban así y ahora **0**; de 169 spams, 18
pierden esa señal y 9 de ellos siguen cayendo por otros detectores. Hay test de
que la longitud no puede acusar.

**Las muestras se cachean** (`_vector_muestra`, `_modelo_bayes`): antes se recalculaban
TODAS en cada mensaje. Con 200 + 200 (el tamaño al que las lleva el autoaprendizaje)
eran **38 ms por mensaje** en serie; ahora **3 ms**, con **0 resultados distintos** en
352 mensajes reales (hay test de equivalencia del coseno).

`learned_similarity` **no** es HARD_RULE, así que el trust protege: con ≥70 se ignora, entre 40 y 69 va a revisión. El riesgo se concentra en usuarios nuevos.

---

<a id="l37"></a>
## L37 · Quién puede warnear y el comando sin permiso que no puede ser silencioso

Los grupos tienen **varios admins** y poner un warn es moderación del día a día, así que no puede depender de que esté el dueño del bot delante. La línea se traza entre aplicar el castigo y decidirlo:

- **`/warn` `/warns` `/rmwarn` `/resetwarns`** → los admins **de ese grupo** (`chat_settings.warn_quien`, defecto `'chat_admins'`; `'bot_admin'` lo deja como estaba). Se comprueba en el chat DONDE se escribe: ser admin de Windows 10 no da derecho a warnear en Domótica.
- **`/warnlimit` `/warnaction`** y todo lo demás → solo el dueño. Cambian el castigo, no lo aplican.

Un warn que llega al límite puede acabar en **ban federado a los cuatro grupos**, así que el alcance también es ajustable: `chat_settings.warn_ban_federado` (defecto **1**, federado, que es lo que el bot ha hecho siempre; **0** = solo ese grupo). Es lo prudente si no todos los admins son de la misma confianza.

Dos guardas que no se deben quitar: un ajuste **ilegible** cae al lado restrictivo (no abre la mano) salvo el de federación, que cae al comportamiento de siempre; y en **privado** no se abre nada, porque un ajuste por chat no significa nada en un DM.

**Un comando sin permiso NO puede ser silencioso.** La limpieza de comandos borra en los grupos cualquier mensaje que invoque un comando del bot, sin mirar quién lo escribe. Si además el comando se ignora en silencio, el admin ve desaparecer su `/warn` y cree que se aplicó: reportado como «el mensaje se borra pero no pone el warn», y es peor que no hacer nada. A quien es admin de algún grupo se le contesta que no se ha aplicado nada (aviso que se borra solo a los 45 s, sin repetirse en media hora); al usuario normal se le sigue ignorando, porque contestarle sería enseñarle qué comandos existen.

---

<a id="l38"></a>
## L38 · Qué avisos por privado suenan (`notify_prefs.sin_sonido`)

**Qué avisos por privado SUENAN** (`notify_prefs.sin_sonido`, petición del admin
25-oct-2026: hasta entonces sonaba casi todo, y lo que suena siempre se ignora).
Primer botón de `/alertas`, en ciclo: **solo lo importante** (defecto) · todo ·
nada. Importante = necesita que decidas o un grupo queda con menos protección:
reporte @admin de un miembro, avalancha, me quitan permisos o me echan, un admin
banea en masa, revisión «¿es spam?», readmiten a un baneado, Han mudo esperando,
error interno, y el aviso de confianza solo si un veterano habría caído baneado o
expulsado. Lo ya resuelto por el bot (bans, copias, antiflood) y lo leve (aviso
suave, OCR, perdones, propuestas) llega callado. ⚠️ **Todo envío nuevo al privado
tiene que llevar `disable_notification=notify_prefs.sin_sonido(db, importante=…)`**:
un meta-test (ast) lo exige y fija la lista de importantes; solo se libran las
respuestas a una orden tuya (`/scan`, acuses). En `/alertas`, «no recibir» es
dejar de mandarlo y «sonido» es si suena: antes los dos se llamaban «silenciar».

---

<a id="l39"></a>
## L39 · Bienvenidas y mensaje de verificación

`config/welcomes/<chat_id>.txt` (privado) → `generic.<lang>.txt` → `generic.txt` → fallback traducido.
El genérico por idioma va **antes** que `generic.txt` a propósito: `generic.txt` está en español y, como existe, ganaba al fallback traducido (un usuario inglés recibía bienvenidas en castellano).

El mensaje de verificación **se EDITA** al de «verificación correcta» (no se envía uno nuevo, para no dejar dos mensajes en el chat). Cuánto dura ese mensaje editado lo decide `chat_settings.verified_ttl_s` (**NULL = hereda `VERIFIED_WELCOME_DELETE_AFTER_S`**, defecto 5 min; **0 = no se borra nunca**), resuelto por `_verified_ttl()`.

Dos trampas de ese ajuste:
- **0 es un valor VÁLIDO**, así que no se puede resolver con un `or` (se comería el «nunca» y devolvería el default).
- Se borra en **dos sitios**: el `jq.run_once` al verificar y el **barrido por BD** del `cleanup_job` (que existe porque los jobs en memoria se pierden al reiniciar). Los dos respetan el 0; sin la guarda del barrido, el mensaje «permanente» sobrevivía hasta el siguiente reinicio y luego desaparecía.

**El mensaje de verificación se diseña para MÓVIL** (9-oct-2026). El botón era
«✅ SOY HUMANO (PULSA PARA ENTRAR)»: 33 caracteres en mayúsculas, y en el móvil se
cortaba («…PARA ENTRAR» sin el paréntesis). Ahora «✅ Soy humano · Entrar» (hay test:
≤22 caracteres y no todo en mayúsculas) y el texto y los pies lo citan por su nombre,
«Soy humano», así que **si cambia el botón hay que cambiar también los pies**. Y el pie
del sospechoso **ya no publica los motivos**: decía «Cuenta sospechosa (sin username,
sin foto)» delante de todo el grupo, que enseña al spammer qué mira el bot y señala
a gente legítima. La bienvenida propia de Windows 10 y 11 (en `chat_settings`, no en
el repo) se rehízo a juego; la de Domótica es otra y no se tocó.

Cada línea del catálogo es el saludo COMPLETO (`📥 Bienvenido/a {name}. <gracia temática>`); la cabecera de verificación no saluda, para no duplicar el «Bienvenido/a». El pie fijo y los botones se añaden aparte.

---

<a id="l40"></a>
## L40 · Bots de otros admins en el grupo (`return_bots=True`)

Un bot con botones inline **no es sospechoso**: es su forma normal de trabajar. El detector `inline_buttons` es solo para HUMANOS (que no pueden crearlos). Aplicarlo a bots expulsó a `@MissRose_bot` de los 4 grupos por publicar su aviso de warn, tras 685 mensajes legítimos. En la ruta de bots solo cuentan señales de spam REAL (URL en lista negra, anuncio comercial).

A un bot que es **admin** Telegram no permite banearlo, así que ahí no hay nada que hacer salvo avisar: `maintenance.notify_bot_overlap` manda **un solo aviso por pareja chat+bot** (dedupe en `bot_prefs`, prefijo `botoverlap_`) contando que puede haber solape en bienvenida, verificación y warns. No afirma qué hace el otro bot, porque no se puede saber. Silenciable desde `/alertas` (tipo `bot_overlap`).

**`getChatAdministrators` NO devuelve otros bots** salvo que se le pase `return_bots=True` (Bot API 10.0). Sin ese parámetro el aviso de solape recorría los cuatro grupos y no encontraba nada: cero avisos y cero logs desde que se escribió. Medido el 2026-08-21: sin él 0 bots, con él **7**, uno de ellos (`@noarab_bot`) baneando por su cuenta. Si alguna comprobación sobre bots ajenos «no encuentra nada», sospechar de esto antes que del grupo.

**Los warns NO salen en `/recent`**: viven en `user_warns` y `/recent` solo lee `moderation_log`. Se consultan con `/warns` respondiendo al usuario.

---

<a id="l41"></a>
## L41 · Copia de seguridad de la BD (`VACUUM INTO`)

`maintenance.backup_database()` corre al principio del job nocturno (antes de limpiar y compactar, para que la copia refleje el estado previo por si el borrado sale mal). Deja `data/backups/antispam-YYYYMMDD.db`, rotando **7 días**.

Usa **`VACUUM INTO`, no una copia del fichero**, por dos motivos medidos en producción:
1. En modo WAL el `.db` puede llevar **días sin checkpoint**: copiarlo a pelo perdía 5 baneos y 20 registros de auditoría.
2. Copiarlo mientras el bot escribe puede dar una foto **inconsistente**; `VACUUM INTO` es íntegra aunque haya escrituras a la vez (probado con 266 concurrentes).

`data/` es gitignored, así que las copias nunca llegan al repo, pero **sí van al N6005** en el rsync semanal (ese bloque no excluye nada). Si la copia falla, se avisa en el log y el mantenimiento continúa: nunca aborta el job.

---

<a id="l42"></a>
## L42 · Analizar la base, no solo respaldarla

`cp data/antispam.db /tmp/copia.db` da una foto **incompleta**, y no avisa de nada: se lee sin errores y con datos que parecen buenos. Error cometido el 2026-08-09 investigando un caso: la copia decía que un usuario **no estaba registrado**, y de ahí salió un diagnóstico entero equivocado sobre joins que el bot no anotaba. La fila existía; estaba en el WAL. Faltaban además **27 usuarios** del censo de recién llegados, que se quedaron sin revisar en el primer barrido.

Para trabajar sobre una copia, dos formas correctas:

```bash
# íntegra, aunque el bot esté escribiendo
sudo -n docker exec cazaspam-bot python -c \
  "import sqlite3; sqlite3.connect('/app/data/antispam.db').execute(\"VACUUM INTO '/tmp/copia.db'\")"
# o consultar en el sitio, sin copiar nada
sudo -n docker exec cazaspam-bot python -c "import sqlite3; ..."
```

Si aun así se copia a pelo, hay que llevarse **los tres ficheros** (`.db`, `.db-wal`, `.db-shm`). Y ante un resultado sorprendente («este usuario no existe», «no hay registro de esto»), sospechar primero de la copia y comprobarlo contra la base viva antes de construir una explicación encima.

---

<a id="l43"></a>
## L43 · Horas: una sola zona para todo lo que ve una persona

El bot mezcla dos orígenes de fechas y **cada uno viene en una zona distinta**:
la base de datos y los logs guardan `time.time()` (zona del proceso,
`Europe/Madrid` aquí), y **Telethon devuelve UTC** con `tzinfo` puesto
(admin_log, fotos de perfil, creación de cuenta).

Formatearlos a pelo con `.strftime()` los mezcla en la misma pantalla: `/quienfue`
mostraba las horas del registro de administración **dos horas atrasadas** respecto
a `/recent`, y nadie lo había notado porque las dos parecen horas plausibles.
Costó tiempo real el 2026-08-23 investigando la queja de un usuario: los logs
decían 11:16 y el registro de Telegram 09:16, y parecían eventos distintos cuando
eran el mismo.

**Regla: toda fecha que se le muestre a una persona pasa por `fechas.cuando()` o
`fechas.dia()`.** Aceptan epoch, `datetime` (con o sin zona) y `date`, y devuelven
`?` ante cualquier basura, porque esto se usa dentro de avisos y una fecha rara no
puede tumbar el mensaje. Hay meta-test que barre `src/` buscando `.strftime(` a
mano; las dos excepciones (`maintenance`, que usa UTC para un NOMBRE DE FICHERO, y
`topweekly`, que ya fija Madrid) llevan el porqué escrito al lado y el test
comprueba que sigue ahí.

---

<a id="l44"></a>
## L44 · Tests que pasan en verde sin comprobar nada

Dos formas medidas en este repo de tener un test inútil que además da confianza
falsa. Las dos costaron tiempo real:

**1. Un doble con firma genérica no ejerce el camino de verdad.** Los 18 tests de
`notify_bot_overlap` estaban en verde mientras la función **no había avisado
jamás**: sus dobles eran `AsyncMock`, cuya firma acepta cualquier cosa, así que
`inspect.signature` no veía el parámetro `return_bots` y el código bajo prueba
tomaba otra rama. Un doble debe imitar **cómo se comporta el servicio real**, no
solo devolver lo que al test le conviene: el de ahora filtra los bots igual que
hace Telegram, y con el código anterior falla.

**2. Un `index()` sobre el fuente casa con comentarios y prosa.** Pasó tres
veces: buscar `verification.on_join` encontró dos comentarios antes que la
llamada; buscar `JoinChannel` casó dentro del docstring que explica que NO se
usa; y medir sangría para comprobar que algo está fuera de un bucle falló porque
estaba dentro de un `try`. Para invariantes de estructura, usar `ast` (como en
`test_borrados_agrupados`) o anclar a la llamada literal (`await x.y(`), nunca al
nombre suelto.

Y una regla de trabajo que salió de romperlo: **antes de crear un fichero de
tests, comprobar si existe.** Un `cat >` sobre `test_bot_overlap.py` borró 18
tests ya escritos; solo se notó porque el total de la suite BAJÓ en vez de subir.
El contador de `test_docs_al_dia.py` es la red que lo detecta: si el número no
cuadra al alza, algo se ha perdido por el camino.

---

<a id="l45"></a>
## L45 · Cuando llega un aviso del bot pegado sin ninguna orden

El admin reenvía a menudo un aviso del bot (un ban, un error interno, una captura
de un perfil) **sin decir qué hacer**. Eso no es «solo para tu información»: es un
encargo. Hay que **deducir el trabajo y hacerlo entero**, no preguntar qué se
quiere ni limitarse a explicar lo que se ve.

El guion, en este orden:

1. **Reproducir el hecho contra los datos reales.** Nunca de memoria ni por lo
   que parece: `moderation_log`, `seen_users` y `docker logs` del contenedor. Y
   siempre sobre la base VIVA, que copiarla a pelo se deja el WAL fuera (ver
   arriba).
2. **Distinguir las dos causas posibles**, porque llevan a arreglos opuestos:
   - **el bot no lo detectó** → falta cobertura: vocabulario, umbral, o un
     escaparate del perfil que no se estaba mirando;
   - **lo detectó y se rompió** → hay un bug, y es más urgente, porque un fallo
     así no afecta a un mensaje sino a todos los que pasen por ahí.
   El log lo dice: un `Traceback` con la hora del mensaje es la segunda.
3. **Arreglar la causa raíz, y también la clase entera.** Si un detector tenía
   un `tuple + list`, buscar ese patrón en TODO `src/` (había otro igual) y
   dejar un meta-test que impida que vuelva.
4. **Comprobar qué habría pasado sin el fallo.** Pasar el texto real por los
   detectores. Si ya puntuaba para ban, el problema era el bug y **no hay que
   tocar las listas**; añadir vocabulario «por si acaso» solo sube el riesgo de
   falsos positivos.
5. **Cerrar el ciclo**: tests que fijen el caso real con su fecha y su medida,
   docs, `docker compose restart`, commit y push.
6. **Contar qué se hizo y qué no se pudo saber.** Si un dato no está registrado,
   decirlo y **añadir la traza** que lo responda la próxima vez, en vez de
   elegir la hipótesis que mejor suena.

Un ban manual de otro admin en el aviso es una **pista de que el bot falló**, no
el final de la historia: el admin tuvo que hacer a mano lo que debía ser
automático. Hay que averiguar por qué.

<a id="l46"></a>
## L46 · Charlotte: el enlace de la bio sin `https://` y un aviso de ban manual que no dejaba ver el perfil

28-oct-2026, Windows 10. Charlotte (id 5031063111) entró a las 19:59, el bot la dio por perfil legítimo (4 fotos
subidas de una vez en enero de 2022, cuenta de 1.755 días, nombre latino) y a las 20:05 un admin la baneó a mano sin
que hubiera escrito nada. El aviso de ban manual decía «sin mensajes registrados» y no dejaba ver por qué: tras el ban,
la mención `tg://user?id=` ya no abre el perfil de quien no es miembro.

Leído después con Telethon, la bio era «Reels are ready when you are — stake1036.com/?c=tg»: un espejo del casino
Stake con código de campaña. `bio_spam` sumó 0, por dos huecos:
- `_EXTERNAL_URL_RE` solo veía enlaces con `https://` o `www.`. Ahora `_BARE_URL_RE` cuenta también `dominio.tld/ruta`;
  exige la barra para no tomar por enlace un «trabajo en Google.com» ni un correo.
- No había ninguna marca de apuestas en `bio_spam_keywords.txt`. Se añadieron por dominio o marca (`stake\d*.com`,
  1xbet, mostbet, melbet, 1win, roobet, rollbit, bitstarz, bc.game, pin-up). «stake» suelto no: es una palabra corriente
  en inglés.
- Señal nueva, `_CAMPAIGN_PARAM_RE` (`?c=`, `?ref=`, `utm_source=`…), que suma 20: quien enlaza su web no le pone un
  rastreador. Con 20 y no 30, una tienda con `?ref=` y una llamada a la acción se queda en 50: hace falta además algo del
  tema. Charlotte da 15 + 20 + 30 = 65.

El aviso de ban manual lee ahora el perfil en el momento (`_perfil_para_aviso`: fotos, bio, canal personal y si la bio
es spam para `bio_spam`) y responde con la foto de perfil (`_foto_de_perfil`, Bot API). Sin Telethon no añade nada; si
no puede leerlo, lo dice.

<a id="l47"></a>
## L47 · Repaso del 28-oct: lo que se escapaba, lo que hacen otros bots y lo que se añadió

Pedido del admin: «investiga a fondo cómo mejorar aún más el bot pero sin exagerar». Medido sobre la base viva, 60 días
(unas 900 acciones):
- Los bans manuales (del dueño y de otros admins) que el bot se dejó ya estaban cubiertos por arreglos posteriores
  (María Casilla, Elxufas, Mila, Charlotte en L46); el único sin regla era «Mahmoudㅤ» (relleno invisible U+3164 en el
  nombre y «Your use What are its specifications?»). Nombres con relleno invisible en la base: 1 de 1.077. No compensa un
  detector.
- La verificación expulsó a 251 sospechosos; ninguno volvió a entrar ni escribió después. Sin falsos positivos a la vista.
- `learned_similarity` marcó 73 veces a veteranos (Ulises, Molkio…) con score 50 (Bayes), siempre salvados por la
  confianza; dejó de pasar el 22-oct. Sobre los mensajes de veteranos de la última semana da 0 positivos.
- Primeros mensajes idénticos de cuentas distintas en toda la historia: 1 (apuestas en chino), ya cazado. Reportes con
  @admin: 0.

Lo que hacen otros (investigado: `umputun/tg-spam` README y `lib/tgspam/detector.go`, CheeseSpamBot, `Priler/samurai`):
espaciado anómalo, alfabetos mezclados en una palabra y normalización de invisibles ya los cubre `desofuscar.py`;
avalanchas, `antiraid.py`. Se eligieron tres, con el OK del admin:
- **Botones en el aviso de ban manual** (`mban:all` / `mban:here`): Charlotte hubo que extenderla a todos a mano.
- **`oleada`** (de `--duplicates` de tg-spam): coseno ≥ 0,9, ≥ 40 caracteres y 6 palabras, en 1 h, solo para quien está
  en sus primeros mensajes. 35 puntos.
- **`calentamiento`** (de `--max-short-msg-count`): fuera de la ventana de primeros mensajes, entrada vista hace ≤ 7 días,
  ≤ 8 mensajes, ≥ 2 previos de ≤ 3 palabras en 24 h y un @ o enlace de Telegram de fuera ya puntuado. 25 puntos. Es
  una hipótesis sin datos que la midan: si empieza a aparecer en `moderation_log` junto a acciones dudosas, se baja.

Descartados por ahora: umbral de denuncias de miembros (0 reportes en la base), clasificador transformer local (no hay
modelo en español y el N100 no va sobrado), y el veto de IA con contexto (gasta API y saca texto del servidor).

<a id="l48"></a>
## L48 · Simulación del 29-oct: `calentamiento` expulsaba a gente normal y una red de reclutamiento no daba nada

Pedido del admin: «haz una simulación realista». Se pasaron conversaciones completas por `on_chat_member`, `on_message` y
`on_manual_ban_callback` con el código de `src/`, una copia de la copia nocturna de la base (muestras aprendidas, ajustes
por chat), updates en el formato exacto de la Bot API, el reloj avanzando de verdad entre mensajes (entrada, «hola» a
los 5 min, el enlace a los 50) y sin red: Telegram era un doble que apuntaba cada llamada, CAS y lols contestaban «no
fichado», Telethon apagado y el `.env` real sin cargar.

Dos fallos:
- **`calentamiento` con cualquier @ o enlace.** «buenas», «gracias!!», «ok» y luego «yo lo pregunté en
  t.me/WindowsAyuda y me ayudaron» daba 50 + 25 = 75: expulsión de una persona normal, cuando sin la señal era silencio.
  Con un @ la señal no cambiaba nada (40 + 25 sigue siendo silencio). Ahora solo suma ante una invitación privada
  (`t.me/+…`, `t.me/joinchat/…`, `calentamiento.es_invitacion`); un grupo público o un @ no cuentan. Hay test.
- **Reclutamiento sin vocabulario de oferta.** «busco 5 personas serias para un proyecto online, se gana entre 200 y
  300 euros al día desde el móvil, interesados escribidme por privado» daba 0: cifra periódica (25) + primer mensaje
  (15) = 40 < 60, y el «escribidme por privado» no cuenta sin `has_work`. Se añadieron a `commercial_work.txt` (y a
  `_DEFAULT_WORK`) «busco N personas serias/responsables/para trabajar», «se busca(n) N personas» y «gana… desde el
  móvil»: ahora da 90 (expulsión) y, con `oleada` en la segunda cuenta, 125 (ban). Medido antes sobre 633 mensajes
  legítimos de la base: 0 coincidencias. Se descartaron «interesados», «con ganas» y «trabajar desde casa» sueltos (los
  dice quien no ofrece nada), con test.

Lo que salió bien: los botones `mban:` (4 de 4 grupos y «Ya estaba baneado» al repetir) y `oleada`, que solo sumó 35 a
dos personas que pegaron el mismo error de Windows, sin acción.

El banco de pruebas quedó en `scripts/simular.py`, con la acción esperada de cada escena, y la suite lo pasa con
`--vacia` (`tests/test_simulacion.py`, en un proceso aparte porque cambia `time.time` y bloquea la red). Con
`MUTE_SCORE=45` falla en las dos escenas del @, que es lo que tiene que hacer.

<a id="l49"></a>
## L49 · Helen, Gloria y Brook: una red con el mismo enlace privado en la bio y 40 puntos cada una

El admin vio el 31-oct a «Helen» en Domótica: foto de modelo, sin @ y en la bio «Get inspired, then go. Cursway →
t.me/+3JVb6dw6WbI0ODk6». Había entrado a las 05:25, no escribió nunca y seguía dentro (muda por la verificación, pero
visible en la lista de miembros, que es lo que busca la red). Una muestra de 33 bios de quien nunca había escrito en
Domótica sacó dos más con el MISMO enlace: Gloria («Holidays made simple. Cursway → …», entró el 29) y Brook («Find
warm seas and good flights → …», el 28). Las tres: nombre suelto en inglés, sin apellido ni @, 4 fotos subidas en el
mismo minuto de dic-2021 o ene-2022 (por eso `photos_batch` las perdonaba: cuenta de más de un año) y una entrada cada
uno o dos días, que no es una oleada.

Por qué no saltó: `bio_spam` daba 40 por el enlace privado y nada más (sin emojis, sin palabras de spam, sin las frases
de llamada a la acción que conoce) y el umbral es 60. Además el repaso de recién llegados descargaba la bio para mirar el
canal personal y no la pasaba por `bio_spam`.

Lo que se añadió, probado con las tres bios reales antes de banearlas:
- **Red**: cada enlace privado de una bio se apunta en `bio_enlaces` (enlace, cuenta). Si otra cuenta lo lleva suma 15;
  si son dos o más, 30. El código del enlace distingue mayúsculas. Mirar dos veces a la misma cuenta no cuenta como red.
- **Flecha al enlace** (`→ ➡️ 👉 👇 ⬇️ » >>` pegada a un enlace) cuenta como llamada a la acción (el mismo +15 que las
  palabras, no se suma dos veces). Los dos puntos no: «Web: https://…» es lo normal. Una flecha sin enlace detrás, tampoco.
- Con eso, Brook (la primera) se queda en 55; Gloria, con la red de una cuenta, 70; Helen, 85; y Brook, al volver a
  mirarla el repaso, 85. Dos conocidos con el mismo grupo privado en la bio y nada más dan 55: no basta.
- El repaso de recién llegados pasa la bio por `bio_spam`, con la base, y banea igual que el join. Los cuatro que miran la
  bio de una persona (join, repaso, `/scan` y aviso de ban manual) pasan `db` y `user_id`: lo fija un test con `ast`.


El mismo día, a las 18:44, entró en Windows 10 una cuarta cuenta de la red («Waves, water temp, flights. Cursway → …»)
y el bot la baneó al segundo de entrar, con 85 puntos (la red ya sumaba 3 cuentas más).

**Barrido en seco de los 4 grupos** (31-oct, con el OK del admin; ni banea ni escribe en la base): 6.534 miembros sin
admins, leídos uno a uno con `GetFullUser` (la bio no viene en la lista de miembros) con una copia de la sesión. Listar
1.000 miembros cuesta 0,7 s; cada bio, ~1 s con 1 s de pausa. En 6.534 llamadas hubo un solo FloodWait, de 6 s, tras
125; con la pausa a 2 s ya no hubo más (unas 4 horas en total). Un `docker compose restart` mata lo lanzado con
`docker exec`, así que el barrido se reanuda pasando por stdin los ids ya hechos.
- 703 bios, 67 con algún enlace y 10 con enlace privado. El detector nuevo marca 7 cuentas y el viejo, 5. **Ninguna de
  las 7 ha escrito nunca** y todas estaban silenciadas hasta 2038; de quien ha escrito alguna vez no marca a nadie. Las
  3 personas con un enlace privado y nada más se quedan en 40.
- Una quinta cuenta de la red de Helen (Windows 11, 4 fotos en el mismo minuto) y otra red de 5 cuentas «my blog 18+»
  con el mismo enlace privado, en Domótica desde sep-2025: el viejo ya cazaba 4 con 70, pero el bot no tenía su entrada
  y no las había mirado nunca. La quinta solo cae por la red.
- **1.982 miembros no constan en `seen_users`**: entraron antes que el bot o su entrada no llegó (la quinta de la red
  entró el 29-oct, según Telegram, sin rastro en la base). El repaso de recién llegados no los ve; solo un barrido sí.
- Sin cazar: 3 cuentas con el mismo canal PÚBLICO de «señales» de trading en la bio (sin red posible: el canal público
  lo enlaza también gente normal, p. ej. un admin de comunidad) y un referido a bot con el propio id (`?start=<id>`).

Con el informe, el admin mandó banear las 7 y, por su criterio, las 3 de «señales» (`manual_admin_ban`). Antes de
banear se releyó cada bio, así que los dos enlaces de red quedaron apuntados (5 cuentas cada uno). El ban solo entró
en el grupo donde estaba cada una: en los otros, la Bot API responde `Participant_id_invalid` a quien no ha visto nunca.
Quedan en `banned_users`, y si entran en otro grupo el join las vuelve a banear.

**Barrido semanal** (`barrido_bios.py`, sábado 11:00): lee la bio de quien no está en `seen_users` ni se ha leído ya
(`barrido_bios`), 400 por pasada a 2 s (~15 min; los ~2.000 de partida salen en cinco semanas) y para con un FloodWait
de más de 60 s, el que Telethon no espera solo. No banea: lo que caza `bio_spam` va al privado con los botones de la
revisión de sospechosos (`susrev:`, suena: pide decisión) y queda un `noop` en `moderation_log`. Una bio con enlace
privado que no llega al umbral no se da por leída: la primera cuenta de una red se queda en 55, y cuando aparece la
segunda, a la semana siguiente salta también (lo fija un test).

<a id="l50"></a>
## L50 · Dos veteranos con la bio de spam tras años callados: cuentas robadas y destinos que se aprenden

El informe del barrido (L49) llevaba dos cuentas que sí habían escrito en Domótica: «BITNEST https://bitnest.me/QSZPR»
(8 mensajes, todos del 20 al 22-dic-2022) y «付费广告 https://t.me/ZOGJ001» («publicidad de pago»; 25 mensajes, del 28 y
29-dic-2019). El admin las vio el 1-nov: cuentas robadas. Nadie las había mirado, porque el perfil solo se lee al entrar,
en los 7 días siguientes y con el primer mensaje, y el barrido solo leía a quien no estaba en `seen_users`. Se banearon
con su OK, sin aviso en el grupo (llevaban años sin escribir).

Lo que no sirvió, medido antes de proponerlo: el admin vio un aviso de phishing al abrir `bitnest.me`, pero desde el
servidor la página carga sin aviso (HTTP 200, título «BITNEST»), el DNS de seguridad de Cloudflare (`1.1.1.2`) y el
familiar (`1.1.1.3`) la resuelven normal y Google Safe Browsing la da por limpia. Un comprobador de dominios no la habría
cazado; se descartó. Banear «cualquier t.me en la bio», tampoco: en el barrido, 9 veteranos legítimos lo llevan.

Lo que se hizo, con lo que decidió el admin:
- **Destinos fichados** (`destinos.py`): los enlaces de un ban con evidencia de spam quedan fichados por destino concreto
  (dominio, `t.me/canal` o invitación; `joinchat/X` y `+X` son la misma) y nunca una plataforma compartida. Suman 45 en
  `bio_spam` (con la web más barata, 15, llega justo a 60: la bio de BitNest) y cuentan como `url_blocklist` en mensajes.
  Un ban manual a secas no ficha (puede ser por insultar) y al desbanear se olvida lo fichado de esa cuenta.
- **Cuenta robada** (`cuenta_robada.py`): el barrido relee ahora a todos cada 90 días. Un veterano (≥3 mensajes, sin warns)
  con la bio de spam y que lleva ≥90 días sin escribir según Telegram se banea en todos los grupos, con un aviso de 24 h en
  el grupo («si os escribe por privado, no le hagáis caso; si es tu cuenta, escribe a @admin») y el privado con «Bien
  baneada / Desbanear». Si escribe a menudo o no se puede saber cuándo escribió, solo se avisa: su propio canal en la bio no
  es una cuenta robada. La mayoría de los veteranos se importaron del historial: 5.816 de 5.941 no tienen `last_msg_ts`,
  así que la fecha se pregunta a Telegram, una llamada y solo para quien ya ha dado positivo.
- La bio en un alfabeto que el grupo no permite y con un enlace también da positivo en el barrido («付费广告» se quedaba en
  25 en `bio_spam`). Los enlaces se quitan antes de medir: sus letras latinas bajaban la proporción por debajo del 70 %.
- El barrido lee también la ficha del grupo o canal que enlaza la bio (`link_reader` + `link_target`, lo mismo que con los
  enlaces de los mensajes, sin entrar en él). Los enlaces se pasan tal cual: las invitaciones distinguen mayúsculas, así
  que la clave en minúsculas de `destinos` no sirve para leerlas.

<a id="l51"></a>
## L51 · Versiones, `update.sh` y la imagen para ARM: que otros la monten y la mantengan al día

El admin (1-nov-2026) quiere que el código lo aproveche cuanta más gente mejor y que sea fácil de integrar, con
actualizaciones opcionales o automáticas. Hasta entonces no había versiones (el CHANGELOG lo decía a propósito: «servicio
en producción continua») y quien instalaba seguía `main` con `git pull`: se llevaba cada commit el mismo día, también los
que salían con la suite en rojo (0914fa6), sin aviso de que hubiera algo nuevo ni vuelta atrás si no arrancaba.

Lo que eligió, con sus razones:
- **Dos canales.** `main` es lo que corre en la instalación de referencia; `stable` apunta a la última versión
  (`vX.Y.Z`, SemVer), que sale cuando el cambio lleva ≥48 h en ese bot sin errores. La v1.0.0, también tras 48 h.
- **`update.sh`** sirve para las dos formas de instalar (clon de git o imagen publicada): copia la base (`VACUUM INTO`, a
  `data/backups/preupdate-*.db`, 3 copias; con el prefijo `antispam-` la rotación diaria las habría tomado por las más
  recientes y se habría comido las diarias), recrea el contenedor y da por buena la versión si el latido
  (`data/heartbeat`) llega ≥31 s después de arrancar: dos latidos, o sea que pasó el arranque. Si no, vuelve a la anterior
  (`git reset --keep` o reetiquetar la imagen vieja) y apunta la versión en `.update-failed` para que la noche no la
  repita. Si tampoco arranca la anterior, avisa por Telegram con el token por stdin (`curl -K -`), nunca en la línea de
  órdenes. `--auto` (temporizador de systemd, 04:00 + hasta 1 h al azar) solo en `stable` y sin saltar de versión mayor.
  En la carpeta de producción no se usa: va por `main` y dice «ya tienes la última».
- **El bot avisa** (`actualizaciones.py`, `UPDATE_CHECK`, encendido): una consulta anónima al día a la API de GitHub, un
  privado silencioso por versión. Antes de reiniciar, `update.sh` deja `data/update-pending.json` y el bot que arranca
  cuenta si se quedó la nueva o volvió a la anterior. Se escribe con `exec` dentro del contenedor (uid 10112): desde el
  host, `data/` no es escribible ni con Docker ni con Podman sin root. La pregunta «¿salen mis datos?» del README y de la
  web lo menciona.
- **Imagen para amd64 y arm64** (Raspberry Pi con sistema de 64 bits), publicada por GitHub Actions en
  `ghcr.io/yonaesp/cazaspambot` con cada etiqueta y cada lunes con los parches del sistema base (`no-cache`, por el
  `apt-get upgrade`). Las acciones van fijadas por SHA: una etiqueta se puede mover a otro código; un SHA, no.
  La imagen lleva `config/` (sin `custom/` ni las bienvenidas de cada grupo); `docker-compose.image.yml` usa `:1`.
- **CONTRIBUTING y SECURITY** (con el aviso privado de vulnerabilidades de GitHub), sin plantillas de issues ni CI.

Trampa que cazó el test: `def f(ruta=PENDIENTE)` fija el valor al definir la función, y un `monkeypatch` del módulo no
llega. Se resuelve al llamar (`ruta or PENDIENTE`). Cómo se publica una versión y cómo se escribe hacia fuera (notas,
listas, PR ajenos): skill `publicar`.

## L52 · ZERO: los «Posts» del perfil, un escaparate con OCR que el bot no miraba

1-nov-2026, Windows 11: «𝐙𝐄𝐑𝐎» (@zerotrace505) entró a las 21:36:45, la verificación lo marcó sospechoso y la pasó en
6 s, no escribió nada y a las 21:38:40 otro admin lo baneó a mano. Con el aviso del ban manual el admin pegó una captura
de su perfil: en la pestaña «Posts», carteles de «Recuperación de fondos», «Alerta de estafadores», «Quieres saber si tu
pareja te engaña», un WhatsApp con código OTP. Bio vacía, sin canal y nombre normal: nada de lo que el bot miraba. Pidió
«implementar el OCR a los posts de los usuarios».

Lo comprobado antes de escribir nada, leyendo sus posts con la cuenta secundaria:
- Los «Posts» son las historias que se dejan fijadas: `stories.getPinnedStories`. `GetFullUser`, que ya se pedía por la
  bio, trae `stories_pinned_available`: quien no tiene no cuesta ni una llamada. Ni la lista ni la descarga cuentan como
  vista (eso es `incrementStoryViews`/`readStories`).
- 12 de sus 15 posts en 0,09 s; cada foto (32-153 KB) en 0,05-0,23 s y su OCR en 0,3-2 s. Las miniaturas de los vídeos
  (3-15 KB) no dieron texto legible: de un vídeo cuenta solo el pie.
- El pie solo ya lo delataba («La recuperación de dinero es segura», «Vincula WhatsApp a tu dispositivo y espía»,
  «Espionaje🎭»), y el OCR añadía «NUESTRO SERVICIO · Recuperación de estafas de criptomonedas…» y «COMUNICATE CON
  NOSOTROS».
- Pero pasados post a post por los detectores de mensajes (`commercial_ad`, `investment_scam`, `offplatform_contact`)
  **ninguno puntuaba**: cada pie es una frase corta y suelta. Juntos, `commercial_ad` daba 60 y por las mayúsculas. Pasar
  OCR a los posts no bastaba: hacía falta juzgar el CONJUNTO, como con la bio.

Lo que se hizo:
- `posts_reader.py` lee 10 posts (pie, URL de las pegatinas de enlace y OCR de las fotos). El OCR de cada post se
  recuerda por (persona, post) y la lectura entera, 1 h.
- `detectors/posts_perfil.py` (`posts_spam`), molde de `investment_scam`: servicios ilegales en ≥2 posts distintos 60
  (uno, 30), ofrecerse a terceros 40, garantizar que se recupera el dinero estafado 45 (ancla estructural; su trozo no
  cuenta además como vocabulario, L33). Umbral 100; ninguna señal llega sola. El vocabulario es el de `bio_spam` y
  `commercial_ad` (sin lista nueva); «hacker», «hacking» o «hackeo» a secas no cuentan: en grupos de informática salen
  en memes y en cursos de hacking ético.
- **Nunca en la ruta de un update**: con OCR son segundos y PTB procesa los updates de uno en uno. El join y el primer
  mensaje lanzan `recien_llegados.revisar_posts_aparte` con `create_task` (espera 5 s para no dejar publicada una
  bienvenida de alguien ya baneado) y el repaso de recién llegados los mira con su presupuesto. Test con `ast`:
  `posts_reader.leer` solo se llama desde `recien_llegados`. `/scan` solo dice si los hay. El barrido semanal de bios no
  los lee (600 perfiles con OCR por pasada no compensan).
- No es reportable a Telegram (regla 9) hasta ver qué caza.

Medido el 2-nov-2026 antes de activarlo, leyendo con la cuenta secundaria a 524 cuentas: las 244 baneadas en 30 días y
las 280 no baneadas con actividad en 30 días (2 s entre cuentas, sin un solo FloodWait). Tienen Posts 12 baneadas (4,9 %)
y 22 no baneadas (7,9 %), una de ellas ZERO (al medir, su ban manual aún no estaba en `banned_users`).
- Con el vocabulario de partida cazaba a ZERO (145) y se quedaba en 45-70 con tres baneadas de la misma familia
  (hackeo de cuentas, «recuperación», espiar a la pareja). Con las frases que llevaban de verdad, añadidas a
  `bio_illegal_services.txt` («recuperar tu dinero», «Recuperar Facebook», «WhatsApp HACKEADO», «Pirater WhatsApp»,
  «¿Está su pareja mintiéndole?», «hacking/Recovery»), suben a 100, 105 y 100 sin tocar los umbrales. Las otras 9
  baneadas tenían fotos normales o un anuncio de otra cosa (un taxi): eso no es de este detector.
- De las 21 legítimas con posts, ninguna da ni una señal suelta (0 puntos todas).
- Las tres están en los tests con su texto (sin identificadores) y ZERO, en la escena de `scripts/simular.py`.

---

<a id="l53"></a>
## L53 · Bots invitados: un spam que publica un bot que ni siquiera está en el grupo

5-nov-2026, Domótica/Alexa. A las 16:10:58 una cuenta nueva escribe solo «@xcb1cv5fdbot @dsfsfds56bot @cxvxcrfdsfbot».
El bot la banea a las 16:10:59 por mencionar cuentas de fuera (130). Ella misma borra su mensaje ese segundo. A las
16:11:01 aparece el mensaje de @dsfsfds56bot y a las 16:11:07 el de @cxvxcrfdsfbot: el mismo anuncio en chino (billetes
falsos «que pasan la máquina», prostitución, blanqueo) con diez botones a un mismo `t.me/…`. La sonda que limpia tras un
ban se llevó el primero a las 16:11:02 (por los botones) y paró tras tres ids vacíos; el segundo llegó cinco segundos
después y se quedó en el grupo hasta que un miembro avisó con @admin a las 21:47.

Lo que se comprobó con la cuenta secundaria, solo leyendo:
- Ninguno de los tres bots es miembro del grupo y el registro de administración no tiene ni una entrada suya (ni entrada
  ni invitación). Los mensajes llevan `guestchat_via_from` = la cuenta baneada: son **bots invitados**, una función de la
  Bot API 10.0 (PTB 22.8 ya trae `Message.guest_bot_caller_user`, `Update.guest_message` y `answer_guest_query`). Se
  menciona el bot en un grupo cualquiera, Telegram le pasa la llamada y el bot contesta allí mismo. No hay ningún permiso
  de grupo para apagarlo (ni en los `ChatBannedRights` de MTProto ni en los `ChatPermissions` de la Bot API).
- Es el único caso en 30 días en los cuatro grupos.
- No se sabe si la Bot API entrega a los demás bots del grupo el mensaje de un bot invitado: la ruta de bots
  (`_moderate_bot_message`) no dejaba traza cuando no encontraba nada y solo mira URL fichadas y anuncios (L40), así que
  «no lo vio» y «lo vio y lo dio por limpio» no se distinguían.

Por qué la cuenta secundaria no lo pilló: no lee los mensajes de los grupos, a propósito (Telethon solo para lo que la
Bot API no puede). Y no era un reenvío: es el mensaje propio del bot.

Lo que se hizo (`bots_invitados.py`), sin depender de esa duda:
- Si el mensaje baneado mencionaba bots, la sonda vuelve a pasar a los ~8 y ~33 s, sin repetir lo ya visto, y banea con
  `bot_invitado` (sin frase pública ni reporte) lo que publicaron ESOS bots. Solo si el bot no es miembro del grupo: un
  bot de la casa que el spammer mencione (el de warns) no se toca, y si no se puede saber, tampoco.
- Si la respuesta llega por la Bot API y quien la llamó ya está baneado, lo mismo, y queda la traza
  `bot invitado @… llamado por …` en cualquier caso: la primera vez que salga dirá si la Bot API los entrega.
- Llamar a un bot no es spam por sí solo: si quien lo llama no está baneado, el mensaje del bot sigue la ruta de bots de
  siempre.

Ese mismo día, a la vista de esto, el admin decidió la regla general: **«debería de banear a cualquier bot que escriba
directamente si no ha sido añadido por un admin ese bot al grupo […] y si el bot nuestro no lo detecta solo, la cuenta
secundaria real de MTProto debería»**. Lo que se cambió:
- Al entrar, un bot añadido por alguien que no es admin de ese grupo se banea (`bot_no_autorizado`); lo que añade un admin
  se queda. Antes se expulsaba a todo bot, también al de un admin, y se le pedía volver a añadirlo.
- Al escribir, un bot que no es miembro se banea lo llame quien lo llame (antes, solo si quien lo llamó estaba baneado).
  Un bot miembro sigue la ruta de bots de siempre: quién lo añadió solo se sabe al entrar (la Bot API lo da en el
  `chat_member`; MTProto no guarda quién invitó a un miembro normal, y el registro de administración solo guarda 48 h).
- La cuenta secundaria mira los mensajes nuevos de los grupos moderados (`telethon_bridge._attach_bots_ajenos`): el de una
  persona se descarta sin ninguna llamada y solo el de un bot pasa a la misma regla. Es lo único que lee en directo.
- Los dos bans son solo de ese grupo. Federados, un bot legítimo que un miembro invocase caería también en el grupo
  donde lo metió un admin y quedaría en la lista federada, que lo rebanearía al entrar.
- «Algo que no permita a los bots escribir»: para los invitados no existe (ni en `ChatBannedRights` ni en
  `ChatPermissions`). Para los que añade un miembro, sí: quitar a los miembros el permiso «Añadir miembros».

Trampa cazada antes de desplegar: en un grupo, lo que se manda en nombre de un chat (un admin anónimo, un canal)
llega por la Bot API con un remitente FALSO que es un bot y no es miembro (`@GroupAnonymousBot`, `@Channel_Bot`; PTB lo
documenta como compatibilidad hacia atrás). `on_message` solo desviaba a la ruta de canales los mensajes sin `from`, así
que estos iban a la ruta de bots desde siempre (sin consecuencias: 0 acciones registradas sobre esas cuentas); con la
regla nueva se habría baneado al bot de los admins anónimos y borrado sus mensajes. Ahora se desvía por `sender_chat` y
esas cuentas (y 777000) no se tocan nunca.

Lo que sigue sin hacerse: banear por el texto en otro alfabeto de un mensaje (los alfabetos solo deciden en el nombre,
la bio y el canal).

---

<a id="l54"></a>
## L54 · Grupos con temas: un @admin que enlazaba otro tema y llegaba dos veces

5-nov-2026, Domótica/Alexa, un grupo con temas («categorías»). A las 18:50:28 un miembro escribe «@admin» en General, sin
responder a nada; justo encima estaba el anuncio de un bot invitado (L53). El admin dijo que el aviso le llegó «muy tarde» y
que «Ir al mensaje» le llevaba a un mensaje de otra categoría: «quizás este bug es por que no estaba previsto para esto,
debemos estar al día en estas cosas siempre».

Lo que pasó, comprobado con el log y leyendo los mensajes con la cuenta secundaria:
- Sin respuesta, `admin_report` suponía que lo reportado era `id - 1` (451505). En un grupo con temas los ids son del grupo
  entero: el 451505 era un mensaje del propio avisador de las 18:11, en otro tema. El spam era el 451503.
- El privado salió a las 18:50:28, en el mismo segundo. A las 21:47:29 el miembro EDITÓ su «@admin» (sin cambiar el texto),
  `on_edited_message` lo pasa por `on_message` como si fuera nuevo y el bot repitió la confirmación en el grupo y el
  privado. Ese segundo aviso es el que llegó «tarde».
- Nada en `src/` sabía de temas. En un tema la Bot API pone en `reply_to_message` el mensaje que creó el tema
  (`forum_topic_created`) aunque no se responda a nada, así que `/warn`, `/ban`, `/spam`, `/legal` y `/scan` sin responder
  iban contra quien abrió el tema, y `dormant_bot_mention` no saltaba nunca dentro de uno. Y lo que el bot publicaba a
  raíz de un mensaje (el resultado de `/scan`, el warn, el antiflood, el aviso de permisos) caía en General.

Lo que se hizo (`temas.py`): `respuesta()` (y un test con `ast` que prohíbe leer `.reply_to_message` fuera de ahí), `hilo()`
para publicar en el tema del mensaje, y `tema_mtproto()` para saber de qué tema es un mensaje leído con la cuenta
secundaria. El @admin sin respuesta busca el anterior DEL MISMO tema que no sea del avisador ni del bot; sin cuenta
secundaria, `id - 1` solo en un grupo sin temas. El privado sale siempre (antes, si la copia fallaba, se perdía también el
aviso), y si no se sabe qué se reporta enlaza al propio @admin, que está en su tema con lo reportado encima. Una edición de
un @admin ya registrado no repite nada. El agradecimiento sale en el tema del @admin (`admin_reports.thread_id`).

Trampa al probarlo: los tests viejos usan `MagicMock` como mensaje, que contesta a cualquier atributo; con `bool()` y
`is not None`, todo parecía un tema y 11 tests cayeron. `es_tema()` compara `is True` y el inicio de tema se reconoce por
el tipo de PTB (`ForumTopicCreated`): es lo correcto también con un mensaje real.

## L55 · El aviso de ban que no llegaba: la limpieza borraba el mensaje antes de copiarlo

Caso (7-nov-2026, 04:45, Windows 11): «Chelsea» (8686388890), que había entrado el día antes, escribió su primer
mensaje (61715) mencionando a @amsoslbot, @ybjsibot y @tbjsibot. Los tres contestaron como bots invitados (61716-61718).
El bot la baneó por `external_mention_or_link` (130) y baneó a los tres bots por `bot_invitado`. Al admin le llegaron los
tres avisos de los bots y no el de ella, y preguntó: «¿no podemos ver quién los mencionó?».

Lo que pasaba, desde el 26-sep (L12): `_apply_action` audita en `moderation_log`, banea con `federate_ban`, y después
copia el mensaje al privado, manda el aviso y borra el mensaje. Pero `federate_ban` acaba retirando los mensajes del
baneado (`mensajes_recientes` ∪ `moderation_log`), y el que se estaba juzgando ya estaba en `moderation_log`: se borraba
antes de copiarlo. La copia fallaba («Message to copy not found») y, como la copia y el aviso iban en el mismo `try` con
un `log.debug`, el aviso se perdía sin rastro. Solo quedaba un `delete_message fallo: Message to delete not found`. En la
última semana, 6 de 6 bans decididos sobre un mensaje; los de perfil (sin mensaje) y los `solo_aqui` sí avisaban. Los
tests no lo veían: sus dobles copiaban cualquier cosa.

Lo que se hizo:
- `federate_ban(..., conservar=(chat_id, message_id))`: la limpieza deja ese mensaje, que `_apply_action` copia y borra.
- La copia y el aviso, en `try` separados y con `log.warning`: si la copia falla, el aviso sale igual.
- Aviso de bot invitado: «🗣 Lo llamó: <nombre enlazado> (id)» (`_linea_llamante`, del payload `llamado_por` y
  `seen_users`), «Baneado (solo en este grupo)» cuando el ban no se federa (también con la federación apagada) y el
  nombre del grupo enlazado cuando llega por la cuenta secundaria sin título (`_chat_del_aviso`, de `bot_chats`).
- `tests/test_aviso_accion.py`, con un doble de Telegram en el que lo borrado ya no se puede copiar ni borrar; con el
  arreglo quitado, el test del caso real falla.

De paso quedó resuelto lo que L53 dejaba abierto: la Bot API SÍ entrega los mensajes de un bot invitado (las dos trazas,
`(cuenta secundaria)` a las 04:45:03,9 y `(Bot API)` a las 04:45:04,3; `marcar` evitó actuar dos veces).

## L56 · Adelantarse a los bots de spam, y comprobaciones que se ejecutan solas

Pedido del admin (7-nov-2026), tras L55: «si alguien mencionó a esos bots directamente se banee a esa persona y a los
bots mencionados antes de que lleguen incluso a escribir […] y usa hooks y scripts que revisen que el código está
perfectamente programado».

**Lo que no se puede**: adelantarse a la PRIMERA llamada. El bot invitado contesta en cuanto Telegram le entrega la
mención, a la vez que nos llega a nosotros (7-nov: llamada 61715 y respuestas 61716-61718 en el mismo segundo), y para
banear a un bot hace falta su id, que una mención no trae (resolverlo es `contacts.ResolveUsername`, el que da FloodWait).

**Lo que sí** (reutilizando `destinos`, la confianza y la ruta de bots invitados):
- Un bot invitado con señales de spam (`handlers._señales_bot_de_spam`): ya fichado; nombre o texto en un alfabeto que el
  chat no permite; la misma persona llamó a ≥2 bots en 2 min (`bots_invitados.anotar_llamada`); o quien lo llamó ya está
  baneado. Ninguna mira el tema: son las del caso real. Entonces (`_bot_de_spam`): se ficha como `t.me/<bot>` (una
  mención y un enlace al bot cuentan igual), se banea en todos los grupos moderados donde no es miembro
  (`bot_de_spam_preventivo`, auditado por grupo, en shadow solo se apunta; donde lo metió un admin se queda) y quien lo
  llamó se banea si su confianza es < 40 (`llama_bot_de_spam`, una vez aunque conteste más de un bot).
- Mencionar un bot fichado es `bot_fichado` (100) en `url_blocklist`. No es regla dura: un veterano que avisa «cuidado
  con @x_bot» no cae. La ruta de bots miembro no lo mira (un bot de moderación que cita al spammer no es spam).
- Un ban por contenido ficha los @bots que mencionaba (`destinos.aprender_bots_de_ban`, `REGLAS_QUE_FICHAN_BOTS`).
- `BOTS_CONOCIDOS` (los de `dormant_bot_mention`, ahora compartidos) nunca se fichan. Desbanear el bot lo olvida.
- Medido antes de activarlo: en 7 días, las únicas menciones de `@…bot` en `mensajes_recientes` eran los seis bots de
  spam (5 y 7-nov); ninguna persona legítima mencionó un bot.

**Comprobaciones que se ejecutan solas**:
- `ruff.toml` añade `B`, `ASYNC`, `RUF006` y `PLE`. Cazó un `lstrip("www.")` en `external_mention` (la misma trampa que ya
  documentaba `url_blocklist`: quita letras sueltas, no el prefijo), sets con repetidos y un espacio de ancho cero sin
  escapar.
- `tests/test_meta_avisos.py` (ast): ningún `try` con copia y aviso juntos (encontró otro: el aviso de modo shadow),
  `federate_ban` antes de copiar lleva `conservar=`, y «sincronizado en todos los grupos» solo con `_se_federa`. Pasados
  sobre el código de antes de L55, cazan sus dos fallos.
- `scripts/verificar.sh` lo junta todo. Lo lanzan el pre-commit (`.githooks/pre-commit`, con `core.hooksPath`) y el hook
  Stop de Claude Code (`.claude/settings.json`), que no deja dar un turno por acabado con la suite en rojo si el código
  cambió desde la última pasada en verde; el PostToolUse pasa ruff a cada fichero editado. En su primera pasada, el Stop
  ya cazó las cifras de tests desfasadas en los README.

## L57 · Auditoría del 7-nov: lo que no funcionaba como decía el CLAUDE.md

Pedido del admin (7-nov-2026): «haz un audit completo de todo el código para revisar que todo funciona como debe […] que no
se nos pase nada como lo de antes». Lo hizo un agente Opus (solo lectura, ~1 h, con reproducciones contra un doble fiel
de Telegram y medidas en la base viva). Lo confirmado y arreglado, cada uno con su test en `tests/test_auditoria_l57.py`:

1. **Cualquier «@admin» saltaba todos los detectores**: `on_message` atendía el reporte y hacía `return` antes de juzgar
   nada, así que «@admin 🔥 packs t.me/+XXXX» de una cuenta nueva pasaba entero. Ahora solo un aviso limpio
   (`_aviso_admin_limpio`: sin enlaces, sin otras menciones, sin reenvío, botones ni vía bot, ≤400 caracteres y, quitado
   el propio @admin, en un alfabeto permitido) toma el atajo; lo demás se juzga como cualquier mensaje. Sin explotar aún.
2. **`reaction_farming` copiaba y borraba el mensaje de OTRA persona**: le pasaba a `_apply_action` el mensaje al que se
   reaccionó. Ahora actúa sin mensaje. Activo pero sin saltar nunca (155 reacciones en 30 días).
3. **`link_target_spam` y `external_quote_channel` muertos en producción**: con `MODERATED_CHAT_IDS` vacío,
   `cfg.is_moderated` dice que sí a cualquier chat, y se pasaba como filtro de «grupo propio»: todo destino se descartaba.
   Además Telethon da el id crudo (positivo) y los grupos se guardan con el de la Bot API (`-100…`), y lo cacheado no pasaba
   el filtro (la primera lectura se descartaba y la segunda no). Arreglado con `_se_modera`, `link_reader._id_bot_api` y
   `_es_propio` también para la caché. 0 disparos desde que existen: conviene mirar las trazas «destino de enlace» unos días
   (`link_target_spam` es regla dura).
4. **Los botones «Legítimo/Spam» aprendían del último mensaje de la persona** (`last_msg_text`), no del revisado: en 4 de
   5 revisiones de la base ya era otro. Ahora `mensaje_reciente(chat, msg_id)` del mismo autor, o nada.
5. **El ban local por warns acababa federado**: `is_banned` no miraba `federated`. Latente (los 957 bans vigentes son
   federados). `is_banned` y la reconciliación nocturna, solo federados.
6. **`BadRequest` se trataba como «red transitoria»** en `_on_error` (en PTB hereda de `NetworkError`): un «Can't parse
   entities» no dejaba traceback ni aviso. El mismo fallo mudo de L55.
7. **«Levantar» en el aviso de readmisión** desbaneaba a mano y no olvidaba lo aprendido; ahora `unfederate_ban`.
8. **Bans sin auditar o auditados después de borrar**: /spam, el botón «Banear» de sospechosos, el límite de warns, la ruta
   de canales y /ban. Además `/warn` borraba el mensaje advertido sin guardarlo. Todos guardan antes.
9. Menores: la bio se perdía en `render_markup` con premium y dos fotos; títulos de grupo y texto sin escapar en tres
   avisos HTML; `es_miembro` guardaba en caché el «no se pudo saber»; el aviso de modo shadow tenía copia y aviso en el
   mismo `try`; `lstrip("www.")` en `external_mention` (L56).

Meta-tests nuevos (ast): `cfg.is_moderated` no se pasa sin llamar; `_apply_action` de `on_message_reaction` sin
mensaje; los botones de revisión no leen `last_msg_text`; quien banea audita, y antes de borrar; `revoke_ban` solo en
`federation`/`maintenance`; el atajo del @admin exige `_aviso_admin_limpio`.

**Pendiente de decisión del admin** (no se tocó):
- ~~Las revisiones humanas de CAS y lols~~: HECHO el mismo día con el OK del admin. Las de CAS (1 infracción) y las de
  lols/CAS con confianza ≥ 90 solo dejaban una fila `noop` (49 en silencio; 6 de esas personas acabaron baneadas); ahora
  van al privado con los botones de sospechosos (`_revision_humana`).
- Con modo suave (`soft_ban`, hoy apagado), el ban pasa a mute antes del bloque de confianza y desaparecen el aviso de
  «¿cuenta robada?» y la revisión.
- En modo shadow (hoy `active`) aún salen en público el aviso suave, la revisión y el antiflood, y `_moderate_via_bot_message`
  borra de verdad.

<a id="l58"></a>
## L58 · Rosario: un enlace privado en la bio que nadie fue a mirar

**El caso (8-nov-2026, Alexa).** «Rosario Vargas» (foto de una madre con su hijo, sin @usuario) entró el 28-oct a las
15:32 y pulsó «Soy humano» a los 47 s. Su bio era solo `https://t.me/+WcrsCd2W0ZZkYjM0`. Once días después, a las 09:01
del 8-nov, publicó un testimonio de inversión («Empecé con una pequeña inversión de 150 €… En 72 horas, recibí mi ganancia
de 1750 $…», @Trader_Alice00 y `t.me/+ALBlhFVEFx5kNGU0`) y cayó en 2 s por `external_mention_or_link` +
`learned_similarity` (210). El admin preguntó si no se podía haber evitado.

**Por qué entró.** `bio_spam` da 40 puntos a un enlace privado y el ban empieza en 60: sin emojis, llamada a la acción, red
ni palabras clave, la bio pasaba como inocente, a propósito (un enlace solo no prueba nada). Lo que habría decidido es
adónde lleva, y eso solo lo leía el barrido de los sábados (`barrido_bios._positivo`), que va de 600 en 600 y empieza por
quien no está en `seen_users`: a ella no había llegado. El join y el repaso de 7 días leían la bio, pero no el destino.
El enlace de la bio ya había caducado el 8-nov (`InviteHashExpiredError`): no se sabe adónde llevaba.

**El juez de destinos tampoco lo habría visto.** El enlace del mensaje llevaba a «Trade Republic investment Fx📊» (6.720
miembros): «La mejor compañía de inversión… 90% de precisión · 100% de rentabilidad · @Trader_Alice00». La traza dijo
`→ limpio`: `link_target` solo conocía sexo, blanqueo, documentos falsos y apuestas. Con una cuenta robada de un veterano
(confianza ≥70) no habría saltado nada: `link_target_spam` es la regla dura que debe pararlo.

**Medido antes de decidir.** De las 20 cuentas con un enlace privado en la bio que ha visto el bot (`bio_enlaces`, desde
el 31-oct), las 20 acabaron baneadas por spam (19 por `bio_spam` con más señales y esta). En los 600 veteranos que repasó
el primer barrido, ninguno lleva un enlace privado en la bio.

**Lo que se hizo (opción elegida por el admin: «leer el destino; ban o revisión»).**
- `recien_llegados.revisar_destino_bio`: si la bio lleva un enlace privado y `bio_spam` no basta, se lee el destino con
  `link_reader` (sin unirse ni contar como visita, el mismo camino que el barrido) y se juzga con `link_target`. Si se
  confiesa spam, ban con regla `bio_spam` y la bio en el payload (así `destinos` ficha el enlace). Si sale limpio, no se
  puede leer (caducado, sin cuenta secundaria) o lleva a uno de nuestros grupos (este último, nada), revisión al privado
  con los botones de sospechosos, una sola vez por persona: la fila `noop` `bio_enlace_privado` es la traza y el «ya
  avisado», y lleva `bio_preview` para que «Banear» fiche el enlace (`ultima_bio_vista`).
- En el join va en una tarea aparte (`revisar_destino_bio_aparte`, tras los mismos 5 s que los posts), porque es una
  llamada por la cuenta secundaria y PTB procesa los updates de uno en uno. En el repaso, justo después de `bio_spam`.
- `link_target.promesa_de_rentabilidad`, estructural y no en la lista: una garantía de beneficio («rentabilidad
  garantizada», «guaranteed profits») basta; un porcentaje de acierto o de rentabilidad («90% de precisión», «100% de
  rentabilidad», «95% accuracy») solo con vocabulario financiero en la ficha. Una negación delante lo anula («no existe la
  rentabilidad garantizada» es lo que escribe un canal que avisa de estafas). El vocabulario financiero deja fuera lo que
  en estos grupos es de casa: «broker» (MQTT), «señales» (wifi), «invest…» suelto (investigación), «cripto…» suelto
  (criptografía), «binary». Probado con frases de OCR, domótica e inversión honesta (`tests/test_bio_destino.py`).

**Los 20 enlaces, uno a uno (pregunta del admin: «¿ya los detectaría?»).** Eran 6 enlaces distintos: uno lo llevaban
11 cuentas («Cursway», un falso planificador de viajes con 2 miembros), otro 5 («Baby blog España 💦 🍑», 143), y cuatro
una cuenta cada uno («Private 💋.», 23.283; un grupo chino de blanqueo, 22.746; otro chino, «公群 2714», que Telegram
devolvió como `ChatInviteAlready` aunque la cuenta secundaria no es miembro (L59); y el de Rosario, caducado). Cinco estaban fichados en `destinos_spam` desde sus bans de `bio_spam`: una
cuenta nueva con cualquiera de ellos suma 40 + 45 y cae al entrar. El de Rosario no, porque su ban fue por
`external_mention_or_link`, que no ficha. Con el juez de entonces solo el chino de blanqueo se confesaba; el de los
emojis salía limpio, así que `link_target` cuenta ya dos emojis sexuales DISTINTOS de una lista estricta (💦 🍑 🍆 🥵 👅
💋 🔞 🫦, sin 🔥 ni 😈, que llevan medio Telegram). «Private 💋.», con uno solo, va a revisión. «Cursway» no se puede
generalizar: lo para la ficha del enlace y la red (11 cuentas con el mismo enlace).

**Lo que no se tocó.** `investment_scam` no cazó el testimonio («inversión de 150 €… ganancia de 1750 $» no casa con
`_GIVE_BACK_RE`), pero el mensaje ya puntuaba para ban (210) y la regla de la casa es no tocar un detector cuando el caso
ya se resolvió. Queda anotado por si vuelve con una cuenta de confianza media.

## L59 · La cuenta secundaria: cualquiera podía meterla en un grupo

**El caso (8-nov-2026).** Al leer los destinos de L58, una invitación a un grupo chino de blanqueo («公群 2714
-墨颜集团色料代收») contestó `ChatInviteAlready`, y se dio por hecho que la cuenta secundaria ya era miembro. No lo era:
el propio objeto traía `left=True` y `channels.getParticipant` dio `UserNotParticipantError`. Telegram devuelve
`ChatInviteAlready` también para un grupo que la cuenta puede ver sin estar dentro. **Antes de afirmar que la cuenta
está en un chat, `getParticipant` o la lista de diálogos; `ChatInviteAlready` no lo prueba.**

**Lo que sí estaba mal.** «¿Quién puede añadirme a grupos?» seguía en «Todos», lo que trae Telegram de serie: cualquiera
podía meter la cuenta en un grupo de spam, que la luciría de escaparate. Además, estar dentro de grupos así le resta
reputación, y es la que respalda los reportes a Telegram. El admin pidió «evita que otros puedan añadir esa cuenta a
otros grupos».

**Lo que se hizo (`src/cuenta_secundaria.py`).** Al arrancar (a los 5 min) y cada 24 h:
1. Si la privacidad de grupos está en «Todos» (cualquier regla `PrivacyValueAllowAll`, también «Todos menos…»), se
   cierra a los contactos y al admin del bot. Cualquier otra elección se respeta: la tomó alguien a propósito.
   Aplicada a mano el 8-nov con la misma función: quedó `AllowUsers(admin) + AllowContacts`, y la cuenta tiene 0
   contactos, así que solo puede añadirla el admin.
2. Un grupo o canal donde no está el bot (`bot_chats` o `_se_modera`) y al que la metió otra persona (ni el admin, ni un
   contacto, ni ella misma con un enlace o una solicitud, ni creado por ella) se abandona y se avisa al admin, en
   silencio porque ya está resuelto. Si no se sabe quién la metió, o no se pueden leer los contactos, no se sale de
   nada: un grupo legítimo perdido es peor que uno de spam un día más.

El alta en un grupo (`events.ChatAction` con `user_added`, en `telethon_bridge`) lanza la misma revisión en el momento,
pero no está garantizado que Telegram le mande ese aviso al recién añadido a un supergrupo: el job diario es la red. En
`MODE=shadow` no toca nada. Medido el 8-nov: la cuenta está en sus 5 grupos (los 4 moderados, más «Informática (PC)
en Español», que creó ella) y en ninguno ajeno. Tests: `tests/test_cuenta_secundaria.py`.
