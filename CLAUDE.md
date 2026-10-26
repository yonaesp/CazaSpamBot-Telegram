# CazaSpamBot — Bot Antispam Telegram

Bot de moderación antispam **en producción 24/7**, multi-grupo, federado y **bilingüe** (es/en). ~23.000 LOC en `src/`, Podman, **1759 tests**, 25 detectores (un módulo cada uno en `src/detectors/`).

> **Estado: PRODUCCIÓN.** No es un esqueleto. Cualquier cambio afecta grupos reales con miles de usuarios. **Investiga > Confirma > Actúa.**

Cada `(Ln)` remite a `docs/lecciones.md#ln`: el caso real, la medida y el porqué de esa regla. Léela entera antes de tocar esa zona.

## Identidad

Todos los identificadores reales viven en `.env` (gitignored), no en el repo. Configúralos a partir de `.env.example`:

| | Variable en `.env` |
|---|---|
| Bot (ej. `@CazaSpamBot`) | `TELEGRAM_BOT_TOKEN` (su user_id se obtiene en runtime) |
| Admin del bot | `ADMIN_USER_ID` — único con permisos de escritura |
| Cuenta Telethon (MTProto, opcional) | `TG_API_ID` / `TG_API_HASH` + `data/telethon.session` |
| Notificaciones a admin | DM directo del propio bot |

⚠️ `.env` y `data/telethon.session` van en **600**: en 644 los leía cualquier usuario del N100 y de la réplica del N6005, y la sesión da la cuenta secundaria entera. Nada de `.env.bak*` con secretos al lado (L1).

## Grupos federados

- `MODERATED_CHAT_IDS` (CSV de chat_ids) o, vacío, autodescubrimiento. Las cuatro puertas (join, mensaje, reacción, canal) pasan por `_se_modera`: la lista explícita si la hay; si no, ser **admin con permiso de restringir** (`db.puede_moderar`). Un test impide usar `cfg.is_moderated` a pelo en una puerta: daba True en cualquier chat, y un grupo ajeno metía bans en la federación (L2).
- **Federación**: ban en uno = ban en todos (`federation.py`). No hay primitiva nativa; se itera `banChatMember` sobre los chats donde el bot es admin.
- `_is_admin_of_chat` cae del lado seguro («se asume admin, no se actúa») si no puede comprobar, salvo `Member not found` (`_no_es_miembro`), que es «no admin»: por eso 7 spammers fichados se libraron 113 veces (L4).
- Un privado o `/start` de quien no es admin de ningún grupo recibe que el bot es de código abierto, que en su grupo no funcionará y el enlace a GitHub, una vez al día por persona (`publico.py`; `REPO_URL=` vacío lo apaga). La descripción del perfil (es/en) se pone al arrancar solo si cambia (L3).

## Stack

- Python 3.11 + `python-telegram-bot[ext]` 22.8 (async polling, Bot API 10.0) · SQLite WAL (`data/antispam.db`) · `confusable-homoglyphs` (UTS#39) para detección de nombres decorativos
- Telethon 1.44 (MTProto) — **solo** para lo que Bot API no puede: reportes oficiales (`channels.reportSpam`), leer bio/fotos de perfil, admin_log, iter_messages histórico
- **Podman con root** (en el servidor no hay Docker). `sudo docker …` es un envoltorio (`/usr/local/bin/docker`): `docker compose` = el cliente compose sobre la API de Podman, y lo demás, `podman`. Sin `buildx`. Contenedor `cazaspam-bot`, **sin root: uid 10112** (registro `/home/docs/uids-contenedores.md`); `docker exec` también corre como 10112.
- Escribe solo en `data/` y en `config/blacklist/custom/` (montada aparte con escritura: con todo `config/` en `:ro`, guardar palabras desde Telegram fallaba siempre). Si se añade otra ruta donde el bot escriba, hay que montarla y darle el dueño 10112, o fallará en silencio. Instalación nueva: `sudo install -d -o 10112 -g 10112 data config/blacklist/custom` (y `main()` avisa claro si `data/` no es escribible).

## Idiomas (i18n)

Todo el texto que ve el usuario vive en `src/locales/<código>.json` (`es.json` / `en.json`, **1.185 claves** cada uno), nunca en el código. Idioma global de la instancia: `/idioma` (persiste) o `BOT_LANG`/`LC_ALL`/`LANG` al arrancar. Soltar un `fr.json` basta para que `/idioma fr` funcione; fallback por clave al español (un idioma al 40 % ya es usable); un JSON roto se ignora con un log (por eso JSON y no `.py`: un `.py` con una comilla mal puesta tumbaba el arranque). Guía para traductores: `src/locales/README.md`.

1. **Toda clave nueva va a `es.json` y `en.json`** (test de paridad lo exige).
2. `t(key, _lang=None, **fmt)`. El selector se llama **`_lang` con guion bajo a propósito**: con el nombre `lang` colisionaba con un placeholder llamado igual y el usuario veía `{lang}` literal (bug real).
3. `t()` devuelve **la propia clave** si no existe. Nunca uses su resultado en un `or` sin comprobarlo antes: `explain(x) or respaldo` mostraba «rule.xxx» en pantalla. Ver la doble guarda de `rule_explain.explain()`.
4. **HTML balanceado** en cada texto: Telegram rechaza el mensaje entero si un `<b>` queda abierto, y un aviso de ban se pierde en silencio. Hay test.
5. **Frases alternativas** (quips, acuses) son claves numeradas `.1`, `.2`… y cada idioma puede tener su propio número (`i18n.variant_keys`, `quips._phrases`). Se leen del paquete directamente, sin fallback, para no mezclar idiomas dentro de una misma categoría.
6. **No se traducen**: logs y mensajes de arranque (los lee el operador y traducirlos impide buscarlos), ni los regex de detección.
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
8. `verification.on_join` — por defecto verificación, bienvenida y avisos de sospechosos, **los tres OFF** (los avisos por «sin foto» llenaban el privado). Encendidos, tres niveles por chat (`chat_settings.review_level`, NULL = el más callado): `alto` (defecto: otro alfabeto, homoglifos, cuenta nueva sin fotos), `medio` (una señal fuerte o dos cualesquiera) y `bajo` (cualquier indicio, también no tener @usuario). Todo por chat vía `/config` (L6).

**`on_message`** — recolecta hits, `decide()`, luego trust score:
- trust ≥70 → SKIP, salvo `HARD_RULES_BAN` (`cas_match`, `lols_match`, `federation_known_ban`, `reaction_farming`, `link_target_spam`, `adult_link`, `via_bot_referral`)
- trust 40-69 + acción severa → review-with-buttons al admin DM (✅Legítimo/❌Spam, aprende); + acción leve → degrada/noop
- antiflood per-user graduado por trust (5/8/12 msgs en 10s)

**Perfil y confianza**:
- **Un nombre entero en un alfabeto que el chat no permite es ban directo, sin excepciones** (decisión del admin), evaluado antes del salvoconducto de «cuenta antigua con foto». Mínimo **3 letras** de ese alfabeto (`ツ`, `彡`, `♛` son adornos de gente legítima; hay test). Los alfabetos son los del chat (`chat_settings.allowed_scripts`, vía `verification.allowed_scripts_de`, que vive ahí para que `recien_llegados` y `scan_cmd` lo usen sin ciclo). Incluye el chino; `han_requiere_decision` queda para los nombres Han de 2 letras (L7).
- Lo mismo para la **bio y el título del canal personal** (`_texto_en_otro_alfabeto`: NFKC, mezcla decorativa, ≥70 % y ≥3 letras). Tener canal a secas no es ban, ni una bio que mezcla idiomas («Люблю Windows») (L7).
- `no_username` no es señal fuerte (29 % de Windows 11 y 14 % de Domótica no tienen): sin señal fuerte, tier normal (3 h + recordatorio). `_is_very_legit_profile` pide 1 foto: lo que prueba es la antigüedad (L8).
- Quien ya se verificó aquí (`seen_users.verified_ts`) o tiene ≥`MIN_MSGS_DE_CASA` mensajes no repite el botón al volver (`_ya_es_de_casa`; `record_join` conserva el historial con COALESCE). Solo se salta el botón: los detectores se aplican enteros (L5).
- El perfil se mira **en los tres momentos** (join, repaso de recién llegados y primer mensaje) con los mismos criterios; en el primer mensaje, solo si el bot vio el join (`join_ts IS NOT NULL`) y con un solo `user_signals.fetch` por mensaje (`_senales()`) (L9).
- La antigüedad sin participación no da confianza: los días cuentan a partir de `MIN_MSGS_PARA_ANTIGUEDAD` (4). Si alguien **nunca ha escrito** (`msg_count ≤ 1`) y su primer mensaje es un reenvío de un bot o llega opaco, el trust no ablanda nada (`_sin_confianza_posible`, aparte de la fórmula a propósito) (L10). Lo opaco (`MessageMediaUnsupported`) deja traza `mensaje opaco` con su `api_kwargs` (L11).
- **Banear en un supergrupo no borra los mensajes**: `federate_ban`, por donde pasan todos los bans, llama al final a `_retirar_mensajes` (`mensajes_recientes` ∪ `moderation_log` de 7 días, solo donde se aplicó el ban, `deleteMessages` de 100 en 100, solo Bot API, sin poder tumbar el ban) y se lleva los avisos del bot de esa persona, que van en `gentle_warnings` (L12).

## Detectores (`src/detectors/` + `verification.py`)

25 detectores en `src/detectors/`: `bio_spam`, `cas`, `commercial_ad`, `contact_spam`, `cross_post`, `dormant_bot_mention`, `emoji_only`, `external_mention`, `external_reply`, `first_msg_media`, `forward_first_msg`, `inline_buttons`, `investment_scam`, `jfm_delta`, `link_target`, `lols_bot`, `offplatform_contact`, `personal_channel`, `photos_batch`, `premium_new_link`, `reaction_farming`, `story_share`, `tg_deeplink`, `unicode_script` (`non_allowed_script`), `url_blocklist`. Fuera de esa carpeta deciden también `obvious_spam_profile` (`verification.py`) y `learned_similarity` (`learning.py`). También banea spam publicado en nombre de un canal (`sender_chat` → `banChatSenderChat`).

`rule_explain.py` traduce el id técnico de regla a la explicación que lee el admin. **Es el texto más visible del bot** y tiene prioridad sobre el `reason` del detector.

**Telethon y el perfil**:
- `bio_spam`, `photos_batch`, `obvious_spam_profile` (parcial) y `personal_channel_spam` leen el perfil vía MTProto: sin Telethon no se activan y el resto sigue (documentado en los dos README) (L13).
- Historias (`story_reader.py`): la Bot API las da con solo `chat` e `id`. Se leen con `stories.getStoriesByID` (no cuenta como visualización; `incrementStoryViews` sí) y pasan por los mismos detectores. Las entidades MTProto se traducen a la Bot API, porque los detectores de enlaces y menciones solo miran entidades (hay test). Caducan en 6-48 h y `/scan` lo dice en vez de fingir un veredicto (L13).
- El canal personal (`personal_channel_id`) es un escaparate aparte de la bio; si aparece otro campo de perfil, mirarlo. `personal_channel_spam` no salta por tener canal: la señal es la discordancia (nombre latino + canal en otro alfabeto), más compuestos de la red (nunca sueltos como `结账`) y cadenas a máquina medidas por rachas de mayúsculas, no por vocales (marcaba apellidos checos y polacos). Ninguna señal suelta llega al umbral (L14).
- `channel_reader.py` lee la descripción y los últimos posts (75 puntos, no deciden solos): solo si el título no basta, sin unirse ni contar como visualización (`messages.getMessagesViews` no se usa), con la entidad de `GetFullUser.chats` y sin `contacts.ResolveUsername` (FloodWait) (L15).
- Recién llegados: vigilancia de **7 días** (con 24 h, la red escribía a las 29,6 h). El nombre se mira en cada vuelta los 7 días (`get_chat_member`, gratis); Telethon y listas, cada 1 h el primer día y cada 6 h después. No igualar `MAX_NOMBRES_POR_CICLO` con `MAX_POR_CICLO` (hay test; las cuentas del presupuesto también). El repaso guarda el nombre y registra el cambio; `updateUserName` lanza `recien_llegados.revisar_ahora`, que no decide nada y usa la misma `_revisar_perfil` (solo vigilados que no han escrito, 2 min por persona) (L16).

**OCR** (`ocr.py`, Tesseract: 0,61 s por imagen y sin GPU) (L17):
- **No decide nada**: aporta texto que juzgan los mismos detectores (test: `ocr.py` no menciona `Hit`, `score` ni `rule`).
- Solo primeros mensajes con imagen y sin texto propio (única excepción: `_perdon_por_contenido_limpio` lee también la imagen de un mensaje con texto antes de perdonar); corre en un hilo (`run_in_executor`) con tope duro; sin tesseract el bot funciona igual.
- Por chat en `/config` (`chat_settings.ocr_enabled`, defecto 1; ilegible = encendido). Idiomas: `wordlists.active_langs()` filtrados por los instalados (pedir uno que falta tumba la llamada entera); `OCR_LANGS` los fija.
- El aviso de imagen dudosa (`ocr_review`) solo avisa, con freno de 30 min por persona, y sale **después de decidir y solo si no se actúa** (`diferido` + `_soltar_aviso_imagen`; caso Joka).
- Mismo vocabulario que el texto; `config/blacklist/ocr/` se suma y está vacía. `wordlists.modo_ocr()` entra en la clave de la caché de patrones. Patrones con `[\s\S]{0,N}` porque el OCR parte palabras; «activar», «instalación» o «licencia» nunca van sueltas en grupos de Windows.

**Contenido comercial**: el catálogo pirata (`_marcas_distintas` ≥ `_CATALOGO_MIN` = 4 marcas de pago distintas; la lista por defecto es `commercial_ad._DEFAULT_SOFTWARE_CATALOG` y un `commercial_software_catalog.txt` la sustituye entera) suma 40 y no decide solo (L18). Oferta de dinero + privado (`commercial_dm_cta.txt`) = +35; ganchos (`commercial_teaser.txt`) 1 = +20, 2+ = +45; guion entero +25. Sin oferta de dinero o trabajo, ni ganchos ni privado cuentan (hay test) (L19). «Trabajo extra» es oferta solo como «tengo un trabajo extra» / «trabajo extra al que…» (L20).

**Las señales de forma no castigan solas** (`forward_first_msg`, `first_msg_media`, `jfm_*`; Kleo: 80 + 70 = 150, baneado y reportado por una pregunta) (L21):
- Reenviarse algo propio no puntúa (`_es_reenvio_de_uno_mismo`: id, o nombre visible con la privacidad activada).
- `_perdon_por_contenido_limpio`: todos los hits de forma, reenvío que no viene de canal/chat/bot, texto propio de ≥40 caracteres y ≥6 palabras que no dispara nada ni lleva enlace o mención, y el OCR de la imagen tampoco → no castiga y avisa. Es la única vez que se lee una imagen con texto. El reenvío desde canal, chat o bot no tiene perdón (L29).
- Los `jfm_*` no van en `_REGLAS_DE_FORMA`: `jfm_too_fast` como regla única acertó 2 de 2. Antes de meter una regla ahí, mirar en `moderation_log` qué ha cazado; una que mire contenido rompería el perdón (hay test).
- **No se reporta a Telegram por señales de pura forma**: el reporte quema la reputación de la cuenta secundaria.
- La prisa sola no castiga a un perfil legítimo (`_solo_prisa_sin_contenido` + `_is_very_legit_profile` tras `decide()`, auditado `noop_prisa_legitimo`) si no hay nada más que la prisa (L28).

**Avisos al privado**: `_send_trust_notice` tiene cuatro llamadores y dos avisan con trust bajo (el perdón y el veto del modelo, `llm_veto`), así que la cabecera la elige `avala_historial`; un test cuenta los llamadores (L21). Los cuatro avisos (`trust_notice_dm`, `ocr_review_dm`, `review_dm`, `report.admin_dm`) enlazan al mensaje con `enlaces.al_mensaje` y una sola clave `hdl.enlace_al_msg`: `t.me/<user>/<id>`, `t.me/c/<id sin -100>/<id>` y nada en un grupo básico; un `{enlace}` sin rellenar revienta el aviso con `KeyError` (hay test) (L22). Los de confianza dicen de dónde sale (`_porque_confianza`) (L23).

**Destinos, reglas duras**:
- La cuenta robada de un veterano la para el destino, no la confianza: `link_target_spam`; «caseros» solo emparejado con su reclamo, nunca suelto. Traza `destino de enlace … → SPAM/limpio/sin ficha` (L23).
- `adult_link` (`link_target.check_anuncio`, dura y reportable): enlace + dos señales explícitas distintas, o una + dominio de `adult_domains.txt`; la URL se quita antes de contar. Fuera de `adult_explicit.txt` lo que se dice hablando de control parental («porno», «xxx», «+18», «contenido filtrado»…) (L24).
- `via_bot_referral` (`inline_buttons.enlaces_de_referido`): botón a bot o mini-app cuyo `start`/`startapp` lleva el id de quien publica o empieza por `ref`/`r_`/`invite`/`aff` = ban por `_apply_action` (copia antes de borrar). El resto de botones vía bot no banea (encuestas, juegos, cheques `t.me/send?start=CQ…`) (L25).

**Menciones**: un @ que el bot no conoce y está a una tecla del de un miembro (`external_mention.posible_errata`: una edición o dos vecinas cruzadas; dos si pasa de 9 letras; empate = nada) no puntúa, y en las salidas sin acción `errata_mencion` responde citando ese @ (`ReplyParameters.quote`, posición UTF-16; si se rechaza, sin cita). **Nunca en los primeros mensajes** (sería suplantar a un admin); los @ van en `<code>` para no mencionar a nadie; se borra al corregirlo editando (`on_edited_message`, aunque el re-escaneo esté apagado) o a los 10 min (`gentle_warnings.errata`; `barrido_job` cubre los reinicios) (L26). Si el aviso suave ya salió y una edición deja el mensaje sin hits, `_aviso_resuelto_al_editar` edita el privado a «✅ Corregido por su autor» con «Antes decía:» y borra el aviso del grupo; solo el camino del aviso suave guarda en `avisos_admin` (hay test) y una decisión ya tomada con los botones no se reescribe (L27).

### Listas negras (`config/blacklist/`)

Tres capas que se acumulan: `*.txt` genéricas versionadas, `<lang>/*.txt` (idioma activo + `BLACKLIST_LANGS`) y `custom/*.txt` (las del admin desde Telegram, gitignored, donde todo se escapa: no se puede colar un regex activo, `custom_terms.py`). Añadir un término desde el panel pasa siempre por la vista previa (`custom_terms.preview_term()`: «oferta» cazaba 3 de cada 4 mensajes de un grupo de informática) (L30).
- `compile_alternation` envuelve con `(?<!\w)…(?!\w)`, **nunca `\b`**: con `\b`, ni `$500` ni `500€` casaban y la señal de dinero estuvo muerta en silencio (L31).
- Monedas que son palabras comunes (`peso`, `real`, `sol`, `libra`, `corona`) solo pegadas a una cifra (hay tests). `500€`, `$500` y `$2000`; español de América («por día», voseo) (L32).
- `investment_scam` es el molde de un detector de contenido: la señal fuerte es la **discordancia**, no el tema (anclas `_GIVE_BACK_RE` con retorno ≥1.5×, `_SKEPTIC_FLIP_RE` con conector de reversión obligatorio y `_GIVEAWAY_RE` con el canje a ≤160 caracteres, 45 cada una, estructurales y no externalizadas); **ninguna señal decide sola** (`señales_estafa < 2 → none()`), los refuerzos no deciden, y el trozo del ancla no cuenta además como vocabulario (L33).

### Convenciones al escribir/editar patrones de detección

- Cada línea de `config/blacklist/**.txt` es un **regex Python** (case-insensitive), acumulativo entre capas. Grupos **no capturantes** `(?:...)`, nunca `(...)`: rompen el conteo de coincidencias en `compile_alternation`. Un patrón inválido se ignora con un log, no tumba el bot.
- Las listas de vocabulario de `commercial_ad` e `investment_scam` (`*_cta.txt`, `*_work.txt`, `investment_*.txt`) son **editables**; el ancla estructural no se externaliza (es el núcleo). Documentado en `config/blacklist/README.md`.
- **Nunca un término genérico**: «money», «job», «oferta» solo cazan pegados a estructura. Ante la duda, no se añade. FP > FN.

### Ajustes por chat de detección

- **Alfabetos** (`chat_settings.allowed_scripts`, CSV; **NULL = hereda `ALLOWED_SCRIPTS` del `.env`**, resuelto por `_chat_allowed_scripts()`): nunca lista vacía (el helper cae al `.env` y el panel no deja quitar el último), y el panel enseña qué alfabetos se escriben de verdad en el grupo antes de decidir (L34).
- **`money_guard`** (`'normal'` | `'soft'` | `'off'`, en `_apply_money_guard()` del handler, no en los detectores): `soft` deja solo score ≥ `_MONEY_SOFT_MIN_SCORE` (100) de `commercial_ad` + `investment_scam`; `off` los apaga; nunca sube la agresividad; respeta `/sync` (L35).

## Aprendizaje (`/spam`, `/legal`)

Naive Bayes + coseno sobre las muestras marcadas. `BAYES_MIN_SAMPLES_PER_CLASS = 10` de **cada** clase (si no, solo actúa el coseno). Salvaguardas: tope al log-odds por token; el que sale en spam y en ham pesa la mitad; el visto una vez, un tercio; **una palabra nunca vista no es evidencia** (`naive_bayes_spam_prob` la salta: con Laplace un mensaje largo caía por ser largo, hay test); `classifier_excluded_tokens.txt` (el vocabulario temático lo pone cada admin) (L36).

Autoaprendizaje (`autoaprendizaje.py`, sin IA externa: lo que aprende no sale del servidor):
- Legítimos: sin hits, trust ≥70, ≥25 caracteres y ≥5 palabras, sin enlaces, menciones ni reenvíos; 1 por persona y día, 40 al día, 400 en total; se olvidan si la persona acaba baneada.
- Spam: solo de bans seguros (alguna regla de contenido, ni de forma ni de perfil, y además ≥150 o CAS/lols). `learned_similarity` no cuenta (sería un bucle). Al desbanear se olvida. `added_by = 0` marca lo automático.
- Un ban manual solo propone («¿era spam?» con botones): se banea también por insultar.
- Frases: solo si ya salió en otro spam confirmado, lleva una palabra nunca dicha en lo legítimo y la vista previa sale limpia; van a `commercial_illegal_services.txt` (35, no deciden solas).
- Las muestras se cachean (`_vector_muestra`, `_modelo_bayes`; 38 → 3 ms por mensaje; test de equivalencia del coseno).

`learned_similarity` **no** es HARD_RULE, así que el trust protege: con ≥70 se ignora, entre 40 y 69 va a revisión. El riesgo se concentra en usuarios nuevos. `llm_veto.py` (opcional y apagado por defecto: `LLM_VETO=true` + `ANTHROPIC_API_KEY`): segunda opinión de un modelo solo para ban/kick con score 70-160 y sin regla dura; solo puede anular, y ante cualquier fallo se mantiene la decisión. Es lo único que manda texto fuera del servidor (≤1.500 caracteres, las reglas que saltaron y el título del grupo).

## Panel `/config` y comandos

Todo ajuste por chat se toca **desde el panel visual y por comando en paralelo**. Con `/sync` ON (por defecto) cada cambio se aplica a todos los grupos y el panel no pide grupo.

Panel: sincronización · verificación · revisión de sospechosos · recordatorios · acción al no verificar · tiempos · **Bienvenida ▸** (texto, botones, autoborrado) · reglas · limpiar servicio · **Warns ▸** (límite, castigo, quién puede warnear, alcance del ban) · top semanal · **Alfabetos permitidos ▸** · **Rigor trabajo/dinero ▸** (`money_guard`) · **Palabras bloqueadas ▸** · **Frases al banear ▸** (con ejemplo real antes de activar) · avisos informativos.

- **Moderación**: `/ban` `/unban` (aceptan @username o reply), `/whitelist`, `/warn` `/warns` `/rmwarn` `/resetwarns` `/warnlimit` `/warnaction` · **Aprendizaje**: `/spam` `/legal` (alias `/ham`)
- **Info** (chat_admin read-only): `/help` `/comandos` `/stats` `/chats` `/recent` `/samples` `/top` `/topweekly` `/quips` `/scan`
- **Config**: `/config` `/verificacion` `/welcome` `/setwelcome` `/rules` `/setrules` `/cleanservice` `/setwelcomebutton` `/limpieza` `/idioma` `/alertas` `/sync`
- **Alias en inglés** (33 comandos en el menú): `/verification` `/language` `/alerts` `/cleanup` `/commands`. **Los nombres en español deben seguir funcionando siempre.**

Warns (L37): `/warn` `/warns` `/rmwarn` `/resetwarns` los usan los admins **de ese grupo**, comprobado en el chat donde se escribe (`chat_settings.warn_quien`, defecto `'chat_admins'`; `'bot_admin'` = solo el dueño); `/warnlimit`, `/warnaction` y todo lo demás, solo el dueño. `chat_settings.warn_ban_federado` (defecto 1 = federado; 0 = solo ese grupo). Un ajuste ilegible cae al lado restrictivo, salvo el de federación (al comportamiento de siempre), y en privado no se abre nada. Un comando sin permiso no puede ser silencioso: a quien es admin de algún grupo se le dice que no se aplicó (se borra a los 45 s, una vez cada media hora); al usuario normal se le ignora.

**Qué avisos por privado suenan** (`notify_prefs.sin_sonido`): primer botón de `/alertas`, en ciclo **solo lo importante** (defecto) · todo · nada. Importante = necesita que decidas o un grupo queda con menos protección (reporte @admin, avalancha, me quitan permisos o me echan, un admin banea en masa, revisión «¿es spam?», readmiten a un baneado, Han mudo esperando, error interno, y el aviso de confianza solo si un veterano habría caído baneado o expulsado). ⚠️ **Todo envío nuevo al privado lleva `disable_notification=notify_prefs.sin_sonido(db, importante=…)`**: un meta-test (ast) lo exige y fija la lista de importantes; solo se libran las respuestas a una orden tuya (`/scan`, acuses). «No recibir» es dejar de mandarlo; «sonido», si suena (L38).

Bienvenidas (L39): `config/welcomes/<chat_id>.txt` → `generic.<lang>.txt` → `generic.txt` → fallback traducido (el genérico por idioma va antes porque `generic.txt` está en español). El mensaje de verificación se edita al de «verificación correcta»; su vida la da `chat_settings.verified_ttl_s` (NULL = hereda `VERIFIED_WELCOME_DELETE_AFTER_S`, 5 min; **0 = no se borra nunca**, así que no se resuelve con un `or`; lo resuelve `_verified_ttl()`), y se borra en dos sitios que respetan el 0 (el `jq.run_once` y el barrido del `cleanup_job`). Botón «✅ Soy humano · Entrar» (test: ≤22 caracteres, no todo en mayúsculas): si cambia, cambian los pies que lo citan. El pie del sospechoso no publica motivos. Cada línea del catálogo es el saludo completo (`📥 Bienvenido/a {name}. <gracia temática>`).

## Jobs programados (`main.py`)

- `_heartbeat_job` (30s) — healthcheck del contenedor
- `verification.cleanup_job` (15min) — 3 tiers: kick suspicious 30min, reminder normal 3h, kick post-reminder +6h
- `recien_llegados.revisar_job` (15min) — repaso de recién llegados que aún no han escrito (L16)
- `errata_mencion.barrido_job` (5min) — borra las sugerencias de errata vencidas que dejó un reinicio (L26)
- `maintenance.cleanup_nightly_job` (24h) — **copia de seguridad** + limpieza + **reconciliación banned_users↔Telegram**
- `topweekly.weekly_top_job` (domingo 20:00 Madrid)

Bots de otros admins (L40): `inline_buttons` es solo para humanos (aplicado a bots expulsó a `@MissRose_bot` de los 4 grupos); en la ruta de bots solo cuenta spam real (URL en lista negra, anuncio comercial). A un bot admin no se le puede banear: `maintenance.notify_bot_overlap` avisa una vez por pareja chat+bot (`bot_prefs`, prefijo `botoverlap_`). **`getChatAdministrators` no devuelve otros bots sin `return_bots=True`** (sin él, 0 bots; con él, 7). Los warns no salen en `/recent` (viven en `user_warns`): se miran con `/warns`.

Copia de la BD (L41): `maintenance.backup_database()` al principio del job nocturno, con **`VACUUM INTO`** (no una copia del fichero: en WAL el `.db` puede llevar días sin checkpoint) a `data/backups/antispam-YYYYMMDD.db`, 7 días. Si falla, avisa en el log y el mantenimiento sigue. Para **analizar** la base vale lo mismo: `cp data/antispam.db` da una foto incompleta sin avisar (se deja el WAL: el 2026-08-09 faltaban 27 usuarios y una fila «inexistente» llevó a un diagnóstico falso) (L42).

```bash
# íntegra, aunque el bot esté escribiendo
sudo -n docker exec cazaspam-bot python -c \
  "import sqlite3; sqlite3.connect('/app/data/antispam.db').execute(\"VACUUM INTO '/tmp/copia.db'\")"
# o consultar en el sitio, sin copiar nada
sudo -n docker exec cazaspam-bot python -c "import sqlite3; ..."
```

Si aun así se copia a pelo, los tres ficheros (`.db`, `.db-wal`, `.db-shm`). Ante «este usuario no existe», sospechar primero de la copia y comprobarlo contra la base viva.

## Reglas críticas de diseño (lecciones de producción)

1. **Ninguna acción masiva sin dry-run.** `seen_users.msg_count` no refleja historial previo al bot: para "nunca escribió" usar Telethon `iter_messages` filtrando service messages (`m.action is None`).
2. **Falsos positivos > falsos negativos**: mejor dejar pasar spam que banear a un legítimo. Ante la duda, no se añade el patrón.
3. **Anti-FP de nombres**: NFKC + `confusable_homoglyphs.is_dangerous`. Cherokee/Thai decorativos no son spam. Bilingües tampoco. Bypass si cuenta >1 año con foto.
4. **Telethon es último recurso**: solo reportes/bio/fotos/admin_log/histórico. Usar `reporter.get_client()` o copiar la session a `/tmp`, nunca parar el contenedor.
5. **Quips opacos**: no revelar el mecanismo de detección en público. No mencionar lols.bot/CAS por nombre en el grupo.
6. **Sin links clicables a perfiles de spammers** en público: `nombre (id: N)`. Excepción: DM al admin y top semanal.
7. **Castellano correcto**: `Bienvenido/a`, nunca `@`/`x` inclusivo. **Sin em dashes** en textos visibles.
8. **Consentimiento explícito** antes de anclar/editar anclados o cualquier acción pública no reversible.
9. **Reportes a Telegram con criterio**: whitelist de reglas + score alto (`_REPORT_MIN_SCORE` = 150) + rate limit (20/h y 100/día, `REPORTER_RATE_PER_HOUR`/`DAY`), y solo bans. Protege la reputación de la cuenta secundaria.
10. **Ajustes nuevos que hereden del `.env`**: usar columna NULLable donde NULL = «hereda» (ver `quips.quips_on`). Con default `0`, quien lo tuviera activo por `.env` se queda sin ello al actualizar, en silencio.

## Horas: una sola zona para todo lo que ve una persona

La base y los logs guardan `time.time()` (Europe/Madrid) y **Telethon devuelve UTC** con `tzinfo`. Toda fecha que se le muestre a una persona pasa por `fechas.cuando()` o `fechas.dia()` (aceptan epoch, `datetime` y `date`, y devuelven `?` ante basura). Un meta-test barre `src/` buscando `.strftime(`; las dos excepciones (`maintenance`, UTC para un nombre de fichero, y `topweekly`, que fija Madrid) llevan el porqué al lado (L43).

## Tests que pasan en verde sin comprobar nada

Un doble con firma genérica (`AsyncMock`) no ejerce el camino real: el doble imita cómo se comporta el servicio. Un `index()` sobre el fuente casa con comentarios y prosa: para invariantes de estructura, `ast` o la llamada literal (`await x.y(`). Antes de crear un fichero de tests, comprobar si existe; si el total de la suite baja, algo se ha perdido (lo vigila el contador de `test_docs_al_dia.py`) (L44).

## Convenciones de código

- Type hints en funciones públicas. `async def` para todo lo que toque Telegram API.
- Cada detector `check()` con tests (positivos + negativos, **foco en anti-FP**). `ruff check` limpio.
- `seen` es `sqlite3.Row`, no dict: usar `row["col"]`; **`.get()` no existe en Row** (causó un bug que impedía ejecutar bans). Hay meta-test.
- `callback_data` tiene **64 bytes** de tope: nunca metas texto del usuario dentro, usa un hash o índice.
- Migraciones de BD: `ALTER TABLE` blando en `_migrate()`, y añadir el campo a `ALLOWED` de `update_chat_setting`.
- Con `MODE=shadow` el bot solo registra lo que habría hecho, y toda acción se audita en SQLite antes de borrar el mensaje; el detalle, en `.claude/rules/antispam-conventions.md`.
- Commits convencionales. Co-Author: `Claude Opus`.

## Cuando llega un aviso del bot pegado sin ninguna orden

Es un encargo, no «para tu información»: se deduce el trabajo y se hace entero (L45).
1. **Reproducir el hecho contra los datos reales**: `moderation_log`, `seen_users` y `docker logs`, sobre la base viva.
2. **Distinguir**: el bot no lo detectó (falta cobertura) o lo detectó y se rompió (bug, más urgente; un `Traceback` con la hora del mensaje).
3. **Arreglar la causa raíz y la clase entera** (buscar el patrón en todo `src/` y dejar un meta-test).
4. **Comprobar qué habría pasado sin el fallo**: si ya puntuaba para ban, no se tocan las listas.
5. **Cerrar el ciclo**: tests con el caso real, docs, `docker compose restart`, commit y push.
6. **Contar qué se hizo y qué no se pudo saber**, y añadir la traza que falte.

Un ban manual de otro admin en el aviso es una pista de que el bot falló: averiguar por qué.

## Flujo de trabajo típico

```bash
.venv/bin/python -m pytest tests/ -q          # suite completa
.venv/bin/ruff check src/ tests/
sudo -n docker compose restart                # up -d si cambia .env; up -d --build si cambia requirements
sudo -n docker logs cazaspam-bot --tail 5     # verificar "Bot ... listo"
git add -A && git commit -m "..." && git push
```

**`restart` recarga el código (src/ montado por volumen) pero no el `.env`**: para eso hace falta `up -d`, y para las dependencias, `up -d --build` (se instalan al construir la imagen).

## Docs detalladas

`docs/ARCHITECTURE.md`, `docs/ECOSYSTEM.md`, `docs/ROADMAP.md`, `docs/LEARNING.md`. `docs/lecciones.md` (el relato de cada regla, `Ln`). `CHANGELOG.md` (hitos por fecha, lo más reciente arriba). `src/locales/README.md` (traductores) · `config/blacklist/README.md` (listas) · `config/welcomes/README.md`.

## Tráfico del repo (visitas y clones)

GitHub guarda solo 14 días: `scripts/traffic_log.py` los acumula en `traffic/history.json` (gitignored) y hay que pasarlo un par de veces al mes. Receta, permisos del token y `GH_TOKEN`: skill `trafico-repo`.

## Dónde va lo que se aprende

Lo nuevo va en su apartado temático de este fichero como invariante de 1-3 líneas (qué no hacer, el número medido, el test que lo fija), nunca al final por fecha. El relato (el caso, la medida, lo que se probó) va a `docs/lecciones.md` como lección nueva, con su línea en el índice, y aquí se cita con `(Ln)`. Un procedimiento de varios pasos que se usa a veces, a una skill en `.claude/skills/`. Las preferencias del admin y el estado del trabajo, a la memoria.

*Actualizado: 2026-10-26 — 25 detectores, 1759 tests, 1.185 claves por idioma.*
