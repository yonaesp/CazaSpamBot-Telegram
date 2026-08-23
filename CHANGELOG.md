# Changelog

Cambios relevantes de CazaSpamBot, lo más reciente arriba. Se anotan hitos, no
cada commit: para el detalle está el historial de git. Sin números de versión
porque el bot es un servicio en producción continua, no un paquete que se libera.

## 2026-08 · Un lote de borrados es UN aviso, y con todos dentro

Reportado por el admin: «cuando un admin borra varios mensajes de golpe, solo
llega el aviso de que se ha borrado uno de ellos… confunde». Dos causas sumadas:

1. La notificación se lanzaba **una vez por cada `msg_id`** del evento.
2. El contenido sale de `seen_users`, que guarda **solo el último mensaje de cada
   persona**. De ocho borrados, siete no tenían texto y se descartaban con un
   `return` silencioso.

Ahora sale un solo aviso con los que tienen texto y, debajo, los ids de los que
no, para que no falte ninguno. Se sigue callando cuando NINGUNO tiene contenido
(una lista de ids pelados no informa de nada), y se respetan igual los filtros de
siempre: lo que borra el propio bot moderando, los bots de automatización
conocidos y el ajuste de autoborrados.

De paso, el registro de administración se recorre **una sola vez por lote** en
vez de una por mensaje: los borrados de una tacada son una misma acción, así que
el actor es el mismo para todos.

## 2026-08 · Las horas de Telethon salían dos horas atrasadas

El bot mezcla dos orígenes de fechas y cada uno viene en una zona distinta: la
base y los logs guardan `time.time()` (zona del proceso, Madrid), y **Telethon
devuelve UTC**. Al formatearlos a pelo, `/quienfue` mostraba las horas del
registro de administración **dos horas antes** que `/recent`, sin que nadie lo
notara porque las dos parecen plausibles.

Costó tiempo real investigando la queja de un usuario: los logs decían 11:16 y el
registro de Telegram 09:16, y parecían eventos distintos cuando eran el mismo.

Nuevo módulo `fechas.py`: **toda fecha que ve una persona** pasa por
`cuando()` o `dia()`. Aceptan epoch, `datetime` con o sin zona y `date`, y
devuelven `?` ante cualquier basura, porque esto se usa dentro de avisos y una
fecha rara no puede tumbar el mensaje. Aplicado en `/quienfue`, `/warns`,
`/recent`, `/scanuser` y las señales de perfil.

Meta-test que barre `src/` buscando `.strftime(` a mano. Las dos excepciones
—`maintenance` usa UTC para un nombre de fichero, `topweekly` ya fija Madrid—
llevan el porqué al lado, y otro test comprueba que ese porqué sigue escrito.

## 2026-08 · Salir y volver a entrar no borra el nivel ganado

Un miembro **desde julio de 2022**, con 14 mensajes y trust 74, intentó borrar un
foro de Domótica, resultó que los foros van integrados en el grupo y se salió
entero sin querer. Al volver a unirse se encontró la verificación otra vez:
*«el bot me está pidiendo que verifique todo el tiempo o me banea y ya no sé
dónde ni cómo hacerlo»*.

El bot no le baneó nunca —verificó en 2 min 40 s— pero la queja era justa. La
causa: `on_join` miraba el perfil de **Telegram** (foto, antigüedad de la cuenta)
y **nunca el historial en el grupo**. Y la marca de «este ya se verificó» no
existía en ninguna parte, porque `pending_verifications` se vacía al verificar.

- Nueva columna `seen_users.verified_ts`, puesta al superar la verificación.
- `_ya_es_de_casa()` salta el botón si esa marca existe **o** si hay ≥3 mensajes
  previos en el chat, que cubre a quien se verificó antes de que la marca
  existiera y a quien ya estaba cuando llegó el bot.
- El historial (`first_seen_ts`, `msg_count`) ya sobrevivía al reingreso;
  `record_join` lo conserva con COALESCE. Hay test que lo fija.

**Lo que no se relaja:** solo se salta el botón. Los detectores de perfil
(`obvious_spam_profile`, canal personal, bio, fotos en ráfaga) y los de mensaje
se aplican enteros a quien reentra, y un baneado en federación se resuelve antes
de llegar a la verificación. El botón, además, no protege de bots: en esta misma
instalación se pulsa en 3 segundos.

## 2026-08 · El aviso de «otro bot admin» no había avisado nunca

Salió de una pregunta del admin: por qué `@noarab_bot` baneaba en Windows 10 sin
que él hubiera recibido jamás un aviso de solape.

La causa: **`getChatAdministrators` devuelve la lista de admins excluyendo a los
demás bots**, que es justo lo único que este aviso busca. La función existía,
corría cada noche, recorría los cuatro grupos y no encontraba nada. Cero avisos,
cero logs, cero pistas: el mismo patrón que el detector con `tuple + list`.

Medido en los cuatro grupos reales:

```
sin return_bots → 0 bots
con return_bots → 7  (AlexaESPAli_bot, AlexaDomoChollosBot, noarab_bot, xxdamage2bot…)
```

El parámetro `return_bots` llegó con **Bot API 10.0**, así que hasta esa versión
esto era inviable; ahora es una palabra. El soporte se comprueba por **firma**
(`inspect.signature`) y no con un `except TypeError` alrededor de la llamada, que
se tragaría también un error de tipos de verdad y volvería a dejar esto mudo.

De paso, el censo de lo que hacen esos bots (últimos 500 eventos por grupo):
CazaSpamBot 143 bans y 33 borrados; `@noarab_bot` 1 ban y 1 borrado; el resto,
ninguna acción de moderación.

## 2026-08 · Cazar el cambio de nombre en el momento, no en el siguiente barrido

Pregunta del admin: si un cambio de nombre dejara algún registro, se podría
revisar al vuelo en vez de esperar al barrido. La respuesta tiene dos mitades:

- **Por Bot API, no.** Sus `chat_member` son cambios de ESTADO (entrar, salir,
  ban, promote); un cambio de perfil no genera ningún update. Por eso hasta ahora
  la única vía era preguntar cada 15 minutos.
- **Por MTProto, existe `updateUserName`**, con `user_id`, `first_name`,
  `last_name` y `usernames`: justo lo que hace falta. La documentación oficial
  **no dice para qué usuarios se entrega**, así que esto es defensa y experimento
  a la vez. Si Telegram lo manda para miembros de un supergrupo, el disfraz se
  caza en segundos; si no, el handler no se dispara jamás y el barrido sigue
  siendo la defensa. No se pierde nada por tenerlo, y el log lo dirá.

El update **no decide nada**: invalida las cachés de esa persona y lanza la
revisión normal (`revisar_ahora` → `_revisar_perfil`), para que no haya dos varas
de medir. Guardas: solo para gente bajo vigilancia y que aún no ha escrito, un
freno de 2 min por persona (si juegan a cambiarse el nombre en bucle, no vamos a
leerles el perfil por Telethon en cada cambio), y todo dentro de un `except` que
no puede tumbar el listener.

## 2026-08 · La red midió nuestra ventana y esperó a que venciera

Tercer asalto de la red 财天下/恒泰, y esta vez el hueco no era un detector: era
el **calendario**. El 7688429577 entró en Windows 10 el 14-ago a las 08:26 con el
perfil limpio (la traza del join lo prueba: `señales=sí canal=-`; con nombre Han
el join banea o silencia, y no pasó ninguna de las dos). Dejó pasar entera la
ventana de vigilancia de 24 h, se puso el nombre `六o0壹天` y el canal
`财天下飞机进群结演员结算频道` ya fuera de vigilancia, y escribió a las
**29,6 h** de entrar. Lo cazó el chequeo del primer mensaje con 440 puntos: la
última línea de defensa, porque todas las anteriores habían prescrito.

La secuencia de los tres casos lo dice todo: escribieron a las **5,7 h → 15 h →
29,6 h** de entrar. Se están adaptando a lo que medimos.

- **Ventana de vigilancia: 24 h → 7 días.** Contra un adversario que espera,
  cualquier plazo corto es un plazo que se puede esperar; una semana obliga a
  mantener la cuenta dormida tanto tiempo que deja de salirles a cuenta.
- El coste no se paga con más llamadas sino con **dos cadencias**: el primer día
  todo a ritmo caliente (nombre cada vuelta, perfil cada 1 h, listas cada 1 h);
  del segundo al séptimo, el perfil por Telethon y las listas pasan a cada 6 h.
- **El nombre no tiene ritmo frío**: es Bot API, gratis, y se mira en cada
  vuelta los 7 días (medido: 142 callados en la ventana ≈ 0,16 llamadas/s).
  Quien se pone el nombre chino el día 5 cae en ≤15 minutos igual que el día 1.
- Población medida al calibrar: 142 callados en 7 días, 27 de ellos del primer
  día. Presupuesto Telethon: ~46 lecturas/h necesarias contra 48 disponibles.
  Hay test con esta cuenta para que nadie mueva una constante sin rehacerla.

## 2026-08 · Los admins del grupo ya pueden warnear

Consecuencia del reporte anterior. El `CLAUDE.md` preveía este momento desde el
principio («hardcoded check, no role-based hasta que haya >1 admin»), y ya hay
varios admins por grupo.

La línea se traza entre **aplicar** el castigo y **decidirlo**:

- `/warn`, `/warns`, `/rmwarn`, `/resetwarns` → los admins **de ese grupo**. Es
  moderación del día a día y no puede depender de que el dueño esté delante.
- `/warnlimit`, `/warnaction` y todo lo demás → solo el dueño. Cambian el
  castigo, no lo aplican.

Se comprueba en el chat **donde se escribe**: ser admin de Windows 10 no da
derecho a warnear en Domótica.

Dos ajustes nuevos en **`/config` ▸ Warns ▸**, los dos por chat y respetando
`/sync`:

- **Quién puede warnear**: admins del grupo (defecto) o solo el dueño, que deja
  el comportamiento anterior.
- **Alcance del ban** al llegar al límite: todos los grupos (defecto, que es lo
  que el bot ha hecho siempre) o solo ese grupo. Existe porque un warn puede
  acabar en un ban federado a los cuatro, y eso es mucho poder si no todos los
  admins son de la misma confianza.

Guardas: un ajuste **ilegible** cae al lado restrictivo (no abre la mano), salvo
el de federación, que cae al comportamiento de siempre; y en **privado** no se
abre nada, porque un ajuste por chat no significa nada en un DM.

## 2026-08 · Un comando sin permiso parecía una avería

Reportado por un admin de grupo: «he usado `/warn`, el mensaje se borra pero no
pone el warn». No había ningún bug. Eran dos comportamientos correctos por
separado que juntos engañan:

1. la limpieza de comandos borra en los grupos **cualquier** mensaje que invoque
   un comando del bot, sin mirar quién lo escribe;
2. `/warn` lleva `@bot_admin_only`, cuyo docstring decía «Otros se ignoran
   silenciosamente».

Desde fuera: escribes `/warn`, tu mensaje desaparece —como si el bot lo hubiera
procesado— y no pasa nada. Peor que no hacer nada, porque el admin se queda
creyendo que el warn está puesto.

Ahora, a quien es **admin de algún grupo** se le contesta que ese comando es solo
del administrador del bot y que **no se ha aplicado nada**. El aviso se borra solo
a los 45 s y no se repite en media hora. A un usuario normal se le sigue
ignorando en silencio: contestarle sería enseñarle qué comandos existen.

**Lo que NO cambia**: quién puede warnear. Con la federación, un warn que alcanza
el límite puede acabar en un ban en los cuatro grupos, así que ampliar eso es una
decisión del dueño del bot, no un efecto secundario de arreglar un mensaje
confuso.

## 2026-08 · Un detector roto dejaba el mensaje sin moderar

Publicidad de servicios de hackeo entró en Windows 11 y **el bot no hizo nada**:
lo borró y baneó un admin a mano doce minutos después. En el log, a la hora exacta
del mensaje:

```
File "/app/src/detectors/premium_new_link.py", line 20, in _has_link
  for ent in (msg.entities or []) + (msg.caption_entities or []):
TypeError: can only concatenate tuple (not "list") to tuple
```

En python-telegram-bot 22 las entidades son **tuplas**; un `caption_entities`
vacío hace que `or []` devuelva una **lista**, y `tuple + list` no existe. El
error subió hasta el handler global y **abortó `on_message` entero**, así que el
mensaje no pasó por ninguno de los otros veinte detectores. Comprobado después:
ese texto puntúa **120 en `commercial_ad`**, o sea que el bot lo habría baneado
solo. No hacía falta vocabulario nuevo; hacía falta que el pipeline no se cayera.

Lo peor no fue el TypeError sino cuánto llevaba ahí: el detector vivía dentro de
un `try/except` que lo tragaba con `log.debug`, así que llevaba **meses muerto en
silencio** desde la actualización de la librería, y solo se destapó al sacarlo de
ese `try` en una refactorización.

- Arreglados los **dos** sitios con ese patrón (`premium_new_link`,
  `dormant_bot_mention`) y **meta-test** que barre todo `src/`.
- **Los 16 detectores del pipeline van aislados**: uno que reviente no puede
  llevarse por delante a los otros quince, y el mensaje se sigue evaluando.
- Pero su fallo se registra con **WARNING y traza**, nunca en `debug`. Tragárselo
  en silencio es exactamente lo que dejó el detector roto tanto tiempo.

## 2026-08 · El canal aparece cuando al spammer le conviene

`RELECTURA_PERFIL_S` estaba en 6 horas, con este razonamiento escrito: «un canal
personal no aparece y desaparece, con mirarlo un par de veces en la ventana
basta». Es falso.

Caso medido (Windows 10): «Simongirl40», nombre latino y foto de perfil normal,
entró a las 09:49 y escribió a las 15:32 con el canal
`财天下飞机进群结演员结算频道` en el perfil, que puntúa **160 de los 100**
necesarios. Como su nombre es latino, verle el canal dependía del presupuesto de
lecturas, y con relectura de 6 h cayó justo en la ventana muerta: se le cazó al
escribir (por el detector nuevo del primer mensaje), no antes. En cualquier
momento de esas casi seis horas se le habría echado.

- **Relectura del perfil: 6 h → 1 h**, y presupuesto de 8 → 12 por vuelta. Con
  las 16-23 personas que hay de media en la ventana salen 4-6 lecturas por
  vuelta, que entran holgadas. Hay test que comprueba que la capacidad por ciclo
  cubre la ventana real.
- **El join deja constancia de lo que pudo ver** (`señales=sí|NO canal=...`).
  Sin esa traza no había forma de saber, después, si alguien pasó porque su
  perfil estaba limpio o porque Telethon no llegó a leerlo, y el join es
  justamente el peor momento para resolver una entidad recién creada.

## 2026-08 · El canal se mira antes de molestar al admin

Salió al comprobar si un perfil como el de «李大哥» se banearía ya sin llegar a
escribir. Sí, salvo en un caso: un nombre en Han que se libra por el salvoconducto
de «cuenta antigua con foto» acababa **mudo esperando decisión humana** aunque su
canal ya cantara, porque `han_requiere_decision` cortaba el flujo antes de llegar
al canal. El admin decidía a mano algo que el bot ya sabía, y aquí un aviso que se
acaba ignorando es peor que no tenerlo.

Orden nuevo en el join: perfil obvio → **canal** → decisión humana → bio → fotos.
Al privado del admin ya solo llega lo que de verdad es dudoso.

## 2026-08 · El nombre es gratis; las listas externas no

Los dos frenos del repaso de recién llegados eran el mismo (una hora), y no
tienen por qué serlo:

- **`get_chat_member` es Bot API**: gratis, sin límite práctico y sin tocar la
  cuenta secundaria de Telethon. Y el nombre es justo lo que cambia, porque el
  truco consiste en entrar con uno que pasa los filtros y ponerse el de verdad
  poco antes de hablar.
- **CAS y lols.bot son APIs de terceros**, y ahí sí conviene espaciar.

Ponerle a lo gratis el freno de lo caro era regalarle al spammer esa hora a
cambio de nada. Ahora el nombre se mira **en cada vuelta** (cada 15 min, tope de
100 por vuelta para que una avalancha no se convierta en mil llamadas seguidas) y
las listas externas mantienen su espera. El presupuesto de lecturas de perfil por
Telethon, que es lo caro de verdad, no cambia.

## 2026-08 · El perfil también se mira al escribir

Faltaba el tercer momento. El perfil se revisaba al entrar y en el repaso de
recién llegados, pero **al hablar se juzgaba solo el texto**, así que quien entra
con el perfil limpio y lo cambia justo antes de escribir cabía entero por ahí:
entre la última pasada del repaso y el mensaje van minutos, y contra eso ninguna
cadencia de repaso sirve.

Caso medido (Domótica): «李大哥», nombre 100 % Han y con el canal
`财天下飞机进群结演员结算频道` en el perfil. Entró a las 00:39 pasando los filtros,
se verificó **en 4 segundos** y escribió 15 horas después. Lo cazó
`non_allowed_script`, o sea **por el idioma del texto**: con un «hola buenas»
habría pasado limpio, igual que habría pasado «Vickycat46», de la misma red pero
con nombre latino.

- En el primer mensaje se aplican los **mismos** criterios del join, sin umbrales
  propios: si con ese perfil no habría entrado, tampoco habla.
- **Guarda de usuario pre-bot**: solo si el bot presenció el join. Con `join_ts` a
  NULL el usuario ya estaba antes que el bot y esto no es su primer mensaje.
- **Un solo `fetch` por mensaje**: había hasta tres consumidores del perfil en el
  mismo mensaje, cada uno con su llamada y su tope de 12 s, en una ruta donde PTB
  procesa los updates de uno en uno.

Medido antes de tocar nada y **descartado**: usar el tiempo que tardan en pulsar
el botón de verificación. Suena a señal perfecta (los tres spammers del mes
pulsaron en 3, 4 y 5 segundos), pero sobre las 18 verificaciones registradas los
baneados tardaron 3,5-5,1 s y el resto 2,6-4,1 s: **no separa**. Cortar por ahí
habría echado a gente por ser rápida con el móvil.

## 2026-08 · El canal del perfil, leído por dentro

`personal_channel_spam` juzgaba el canal enlazado en el perfil **por su título**, y
esa red lo renombra en cuanto se le caza. Caso que lo destapó (Windows 11):
«Vickycat46», nombre latino y **foto de perfil normal**, con el canal
`恒泰招聘车队高速结算`. Sumaba **85 de los 100 puntos** necesarios y se libraba justo
por tener foto, que le quitaba los 25 de «perfil sin nada que mirar». Su primer post
era una confesión entera de blanqueo, con `洗米` («lavar arroz») donde la lista
esperaba `洗钱` («lavar dinero»): jerga hecha para esquivar filtros de palabras.

- **`channel_reader.py`** lee la descripción y los últimos posts del canal, y ese
  texto pasa por las mismas listas (75 puntos, que siguen sin decidir solos). Misma
  decisión que ya se tomó en `story_reader` y `link_reader`: cuando la evidencia
  existe y se puede leer, se lee. Solo se paga la llamada cuando el título **no** ha
  bastado para decidir; de 131 recién llegados en 14 días, apenas 6 tenían canal.
  No se une a ningún canal ni cuenta como visualización, así que la cuenta
  secundaria no aparece en ninguna parte.
- **Vocabulario al día** con los compuestos que usa la red ahora (`招聘车队`,
  `车队高[效速]结算`, `担保公群`, ingresos diarios con la cifra pegada). Un test cazó
  un falso positivo del primer intento: el patrón de ingresos casaba con
  `8月9日 10-12点 直播`, que es una fecha con su horario.
- **`recien_llegados` mira también ese escaparate**, porque el canal se puede
  enlazar DESPUÉS de entrar y no se ve desde la Bot API. Como ahí el nombre puede
  estar limpio, se leen algunos perfiles «por si acaso», con presupuesto por vuelta
  y una relectura cada 6 h para no quemar la cuenta secundaria.

Comprobado sobre los perfiles reales: de 131 recién llegados que aún no habían
escrito, **7 tenían un canal de esa red y los 7 caen**; los **124 sin canal quedan
intactos**.

## 2026-08 · Lo que faltaba del repaso a otros bots

Cuatro piezas que salieron de comparar con `tg-spam` y del propio roadmap, más un
bloque de mantenimiento.

### Antiraid — mirar el grupo, no a cada uno por separado

Todo lo demás razona persona a persona, y contra una raid eso no vale: el ataque
no está en ninguna cuenta, está en el conjunto. **No se cierra el grupo ni se
silencia a nadie por entrar** (eso convierte un ataque en una caída del grupo, que
es lo que busca quien lo lanza): el chat entra en alerta unos minutos y los
umbrales bajan un peldaño **solo para quien llegó con la avalancha**. El umbral se
calibró sobre las **881 entradas reales** registradas: el máximo histórico en 60 s
es **2**, así que con 6 hay un margen de tres veces.

### El mismo mensaje en varios grupos a la vez

Aprovecha la **federación**, que casi ningún bot tiene: quien modera un grupo no
puede ver esto. **No mira el contenido**, así que caza campañas cuyo vocabulario
las listas todavía no conocen. Tres chats como mínimo (con dos se equivocaba: quien
tiene un problema pregunta en el de Windows 10 y en el de Windows 11), ventana de
15 min, textos cortos fuera, y comparación sobre el texto normalizado.

### Modo suave por grupo

Silenciar para siempre en vez de expulsar: un falso positivo con mute se deshace
sin que la persona se entere. Apagado por defecto, por chat desde `/config`. **Las
reglas duras no se ablandan**: a un spammer confirmado por CAS o lols, dejarlo
dentro mudo es dejarlo dentro.

### Veto por LLM — solo puede TUMBAR acciones

La idea de `tg-spam` que sí merecía la pena, y solo en su modo veto. El modelo **no
acusa**: se le pregunta por lo que las reglas ya marcaron, y si dice que aquello no
es spam, se anula el castigo. Encaja con la primera regla del proyecto porque solo
puede **reducir** acciones: en el peor caso deja pasar un spam (el error barato) y
jamás castiga a alguien legítimo (el caro).

Apagado por defecto y con cinturones por todas partes: sin `ANTHROPIC_API_KEY` no
se activa aunque esté a true; solo se pregunta en la zona gris (70-160 puntos) y
nunca por las reglas duras; tope de 8 s porque los updates se procesan de uno en
uno; y **cualquier** problema — timeout, error de red, respuesta ambigua, paquete
ausente — mantiene lo que decidieron las reglas. El silencio no perdona a nadie.
Cada veto queda anotado en `moderation_log` y avisa al admin.

### Mantenimiento

- **Los contadores de los docs ya no se pudren**: un test compara lo que presumen
  README/ARCHITECTURE/ROADMAP con la realidad. Nada más escribirlo encontró dos
  desfases (el README decía 1018 con 1146 tests; ARCHITECTURE, «los 15 detectores»
  con 24).
- **Aviso cuando le recortan permisos sin echarlo**, que era el fallo más
  silencioso: el bot se quedaba dentro, aparecía en `/chats`, detectaba el spam y
  no podía tocarlo.
- **Se guarda el primer mensaje de cada usuario**: `last_msg_text` se pisa, y de
  una cuenta cuyo último texto era «0.1» no había forma de saber qué escribió al
  entrar.
- Fuera dos duplicados que iban a divergir (la tabla de tiempos de verificación,
  el pintado del top semanal).
- **`external_mention` deja de estar atado al español**: puntuaba 130 en vez de 60
  cuando el texto «no parece español», con la heurística clavada en el código.

## 2026-08 · Quitarle el disfraz al texto

De repasar qué hacen mejor otros bots conocidos. `tg-spam` (umputun, el más
completo de los abiertos) tiene dos comprobaciones que aquí no existían: palabras
que **mezclan alfabetos** y **espaciado anómalo**. Al probarlo contra este bot, el
agujero era peor de lo que parecía:

    «Gana 500 euros al dia trabajando desde casa»   commercial_ad = 75
    «Gana 500 eurоs al dia trabajando desde casa»   commercial_ad =  0

La única diferencia es la `о` de «euros», que es **cirílica**. Una letra, y el
mensaje se volvía invisible entero: tampoco saltaba `unicode_script`, porque mide
la PROPORCIÓN de caracteres ajenos y una entre cuarenta y siete no llega al umbral.
Con el espaciado (`G a n a  5 0 0  e u r o s`) pasaba lo mismo.

- **`desofuscar.py`** lo resuelve al revés que `tg-spam`, y sale más barato: en vez
  de una regla nueva que puntúe el disfraz, se **deshace el disfraz** y deciden las
  reglas de siempre con sus umbrales de siempre. Si el texto desenmascarado no dice
  nada punible, no pasa nada: **quitar el disfraz no puede inventar un falso
  positivo que no existiera ya**.
- **Solo se tocan las palabras MEZCLADAS.** Una palabra entera en cirílico, griego
  o árabe es una palabra de ese idioma y se deja intacta; «traducirla» a letras
  latinas convertiría la conversación de un grupo ruso en galimatías que podría
  casar con cualquier patrón por casualidad. Lo que delata el disfraz es la mezcla
  DENTRO de una palabra, que nadie escribe queriendo.
- La sustitución **conserva la longitud** (una letra por una letra): los
  desplazamientos de las entidades de Telegram se cuentan sobre el texto y
  cambiarla rompería enlaces y menciones. El desespaciado sí acorta, y por eso su
  texto solo lo ven los detectores que no miran entidades.
- Los dos disfraces combinados también caen: con las letras separadas no hay mezcla
  que ver, así que se vuelve a pasar el esqueleto **después** de juntarlas.
- `/scan` avisa de que el texto venía camuflado, para que el motivo no parezca un
  error del bot.
- **Medido contra el tráfico real: 11.560 mensajes, 0 tocados, 0 falsos positivos
  nuevos.** Ω y µ (grupo de domótica), «H O L A» de énfasis y los mensajes en ruso,
  griego, árabe y chino salen intactos.

## 2026-08 · La ventana ciega entre entrar y escribir

El bot miraba a cada usuario **dos veces**: al entrar y al escribir su primer
mensaje. Entre las dos pueden pasar horas, y en ese hueco no volvía a mirar nunca.

- **lols.bot ficha tarde**, porque se alimenta de denuncias: un spammer recién
  creado está limpio cuando entra. Medido en el grupo de domótica: **1 h 35 min**,
  **12 h 14 min** y **27 h** entre la entrada (limpio) y el primer mensaje (ya
  fichado). No es que el bot esperase a que escribieran: preguntó al entrar y le
  dijeron que no había nada.
- **El nombre se cambia después de verificarse.** Una cuenta pulsó el botón de
  verificación **en 3 segundos** y doce horas más tarde escribía como `唔活诗我`.
  Con ese nombre no habría entrado (`_is_obvious_spam_profile` lo banea al join):
  se lo puso ya dentro, y el perfil no se volvía a mirar.
- **`recien_llegados.py`**: cada 15 min repasa a quien entró hace menos de 24 h y
  **aún no ha escrito**, y le aplica **los mismos criterios del join**, listas
  externas y perfil incluidos. Ningún umbral nuevo: si la lista ya lo tiene o el
  nombre ya no es el de antes, se actúa igual que si acabara de entrar. La
  protección al veterano (trust ≥ 90 → revisión humana, nunca autoban) también.
- Topes: ventana de 24 h, una consulta por persona y hora como mucho, 25 personas
  por vuelta. Un fallo con una persona no interrumpe el repaso de las demás.
- **Dry-run antes de activarlo: 20 candidatos, 3 ya fichados** esperando dentro de
  los grupos sin haber escrito todavía.

## 2026-08 · «Escríbeme a este otro sitio»

Segundo de los dos spams que había que borrar a mano, y por un motivo **distinto**
al del enlace: a este no lo tapó ninguna regla, es que **no había regla**.

- **Lo que pasó** (07/08, Windows 10): cuenta nueva, catorce minutos después de
  entrar, primer y único mensaje: *«Este es mi número de Zangi; puedes escribirme
  ahí ahora mismo 👉👉 …  Cariño, este es mi nuevo número de Zangi: … Escríbeme
  ahora 💞❤️❤️»*. Ni enlace, ni @mención, ni alfabeto raro, y en español correcto:
  **ningún detector tenía nada que mirar**. Hora y cuarto en el grupo hasta que un
  admin lo borró y baneó a mano.
- Detector **`offplatform_contact`**. Es la entrada del timo romántico y de la
  estafa de inversión: sacar a la víctima de Telegram, donde nadie modera, antes de
  pedirle nada.
- Diseñado con el molde de `investment_scam`, porque el riesgo es el mismo: **la
  señal fuerte no es el tema, es la discordancia**. Dar un teléfono no es spam y
  decir «escríbeme por privado» tampoco; lo raro es un número **de otra app** más
  una llamada a seguir la conversación **allí**. El adverbio de destino («ahí»,
  «there») es justo lo que separa el spam del mensaje legítimo que más se le parece.
- **Ninguna señal decide sola**: sin ancla no se mira nada, y con ancla hace falta
  al menos un apoyo (redirección, gancho afectivo o «número nuevo»). El primer
  mensaje solo refuerza. Así «mi whatsapp es 600123456» NO cae.
- Cuatro listas editables (`offplatform_apps` · `_cta` · `_hook` · `_newnumber`).
- **Medido contra el tráfico real de los tres grupos: 11.560 mensajes, 0 falsos
  positivos.**

## 2026-08 · A dónde lleva el enlace

Un enlace `t.me` a otro chat era una señal **a ciegas**: el bot sabía que existía,
no adónde iba. Con esa duda solo se puede ser blando, y por ahí se coló un caso
real que estuvo dos semanas a la vista de todos.

- **Lo que pasó** (24/07, grupo de domótica): una cuenta con dos años y 34 mensajes
  publica un enlace a un canal de packs. El bot **sí lo detectó**
  (`external_mention_or_link`, 50 puntos), pero al ser su autor un veterano aplicó
  el **aviso suave**: recordatorio de normas que se autoborra a los 5 minutos y el
  enlace intacto en el grupo. Una hora más tarde otro miembro escribía «este se le
  ha escapado al bot». Ni ban fallido ni detector ciego: una decisión deliberada
  que no contemplaba la **cuenta robada**.
- **`link_reader.py`** va a ver el destino antes de juzgarlo: título y descripción
  públicas del chat enlazado. Incluye los **enlaces privados** (`t.me/+HASH`), que
  se leen con `messages.checkChatInvite` **sin entrar** al chat. Mismo principio
  que `story_reader`: se juzga la evidencia, no el indicio.
- Detector **`link_target`**: si ese destino se anuncia solo con vocabulario de
  spam, el enlace deja de ser borderline. Lista editable
  `config/blacklist/link_target_keywords.txt`, que **suma** la de `personal_channel`
  (mismo criterio, una sola lista que mantener). Verificado contra Telegram real:
  el canal del caso puntúa 100 y los canales legítimos de control, cero.
- Es **regla dura**, así que el trust ya no puede taparla. Era justo el agujero:
  una cuenta veterana robada seguía spameando con toda la protección del historial.
- **El aviso suave deja de ser un silencio.** Ahora se avisa al admin por privado
  con los mismos botones que el atajo por trust alto (nada / avisar / banear).
  Antes, el bot veía spam, decidía no tocarlo y no se enteraba nadie.
- Topes pensados para que no congele el bot (los updates se procesan de uno en
  uno): 5 s por llamada, 6 s en total, 2 enlaces por mensaje y caché de 6 h que
  guarda también los resultados negativos.

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
