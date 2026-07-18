"""Paquete de idioma ESPAÑOL. Clave -> texto (con placeholders {x} para .format()).

El español es el idioma de referencia (fallback). Al añadir una clave aquí, añádela
también en en.py con su traducción de calidad.
"""
STRINGS = {
    # --- comunes ---
    "on": "✅ ON",
    "off": "❌ OFF",

    # --- comando /idioma ---
    "lang.current": "🌍 Idioma del bot: <b>{lang}</b>\n"
                    "Cámbialo con <code>/idioma es</code> o <code>/idioma en</code>.",
    "lang.set": "🌍 Idioma cambiado a <b>{lang}</b>. Los textos del bot saldrán en ese idioma.",
    "lang.invalid": "Idioma no soportado. Disponibles: <code>es</code>, <code>en</code>.",

    # --- aviso de revisión de sospechoso ---
    "review.title": "🔍 <b>Usuario sospechoso (revisar)</b>",
    "review.chat": "📍 Chat: {title}",
    "review.user": "👤 <a href=\"tg://user?id={uid}\">{label}</a> (<code>{uid}</code>)",
    "review.reason": "🚩 Motivo: {reasons}",
    "review.reason_default": "perfil dudoso",
    "review.footer": "<i>Ya está DENTRO del grupo (permitido por defecto). "
                     "Revisa su perfil y decide.</i>",
    "review.allowed": "\n\n✅ <b>Permitido por el admin.</b>",
    "review.banned": "\n\n🔨 <b>Baneado por el admin</b> ({n} grupo/s).",

    # --- botones del aviso ---
    "btn.allow": "✅ Permitir",
    "btn.ban": "🔨 Banear",
    "btn.gear": "⚙️ Ajustes del grupo",
    "btn.verif": "🛡️ Verificación humana: {state}",
    "btn.alerts": "🔔 Avisos de sospechosos: {state}",
    "btn.reminders": "⏰ Recordatorios de verificación: {state}",
    "btn.times": "⏱️ Tiempos: {sk}min · {rh}h · +{kh}h ▸",
    "btn.hide": "⬅️ Ocultar ajustes",
    "btn.back": "⬅️ Volver",

    # --- toasts (respuestas efímeras a los botones) ---
    "toast.allowed": "✅ Permitido.",
    "toast.banned": "🔨 Baneado ({n} grupo/s).",
    "toast.verif": "Verificación humana",
    "toast.alerts": "Avisos de sospechosos",
    "toast.reminders": "Recordatorios de verificación",

    # --- confirmaciones de comandos de moderación ---
    "shadow.usage": "Uso: /shadow on|off",
    "shadow.changed": "Modo cambiado a <b>{mode}</b>",
    "whitelist.usage": "Uso: /whitelist <user_id>",
    "whitelist.done": "Usuario <code>{uid}</code> whitelisted en este chat.",
    "notspam.usage": "Uso: /notspam <action_id>",
    "notspam.notfound": "action_id no encontrado.",
    "notspam.done": "Acción {aid} marcada como falso positivo. Ban revocado y regla suprimida 7 días.",
    "alerts.panel": (
        "🔔 <b>Avisos informativos</b>\n"
        "Pulsa un botón para activarlo o silenciarlo. No afecta a los avisos de "
        "acciones antispam (esos son el núcleo del bot)."
    ),

    # --- panel /config y /sync ---
    "cfg.header": "⚙️ <b>Ajustes · {title}</b>\nPulsa para cambiar. Los cambios se guardan al instante.",
    "cfg.title_all": "Todos los grupos (sincronizado)",
    "cfg.kick": "Expulsar",
    "cfg.mute": "Silenciar",
    "cfg.b.sync": "🔗 Sincronizar todos los grupos: {state}",
    "cfg.b.verif": "🛡️ Verificación: {state}",
    "cfg.b.review": "👁️ Revisar sospechosos en privado: {state}",
    "cfg.b.reminders": "🔔 Recordatorios: {state}",
    "cfg.b.action": "🚪 Al no verificar: {action}",
    "cfg.b.times": "⏱️ Tiempos: {sk}min · {rh}h · +{kh}h ▸",
    "cfg.b.welcome": "👋 Bienvenida: {state}",
    "cfg.b.edit_welcome": "✏️ Editar texto de bienvenida ▸",
    "cfg.b.edit_rules": "📜 Editar reglas ▸",
    "cfg.b.cleanservice": "🧹 Limpiar mensajes de servicio: {state}",
    "cfg.b.alerts": "🔔 Avisos informativos ▸",
    "cfg.b.close": "✖️ Cerrar",
    "cfg.b.back": "⬅️ Volver",
    "cfg.b.all_groups": "🌐 Todos los grupos",
    "cfg.b.cancel": "✖️ Cancelar",
    "cfg.scope_n": "en {n} grupos",
    "cfg.scope_one": "en {title}",
    "cfg.times_text": (
        "⏱️ <b>Tiempos de verificación · {title}</b>\n\n"
        "1ª fila · <b>sospechoso</b>: minutos hasta expulsar si no verifica.\n"
        "2ª fila · <b>recordatorio</b>: horas hasta avisar al que no verifica.\n"
        "3ª fila · <b>expulsión</b>: horas tras el recordatorio para expulsar.\n\n"
        "Actual: <b>{sk}min · {rh}h · +{kh}h</b>"
    ),
    "cfg.no_admin": "No estoy de admin en ningún grupo todavía.",
    "cfg.pick_group": "⚙️ <b>Ajustes</b> — ¿qué grupo quieres configurar?\n<i>(La sincronización está OFF: cada grupo por separado.)</i>",
    "cfg.only_admin": "Solo el admin del bot puede configurar.",
    "cfg.invalid_chat": "Chat inválido.",
    "cfg.invalid_opt": "Opción inválida.",
    "cfg.invalid_val": "Valor inválido.",
    "cfg.val_range": "Valor fuera de rango.",
    "cfg.closed_toast": "Cerrado.",
    "cfg.closed_msg": "⚙️ Panel cerrado. Escribe /config para volver a abrirlo.",
    "cfg.act_on": "✅ Activado",
    "cfg.act_off": "❌ Desactivado",
    "cfg.in_n": " en {n} grupos",
    "cfg.dot_n": " · {n} grupos",
    "cfg.sync_on": "🔗 Sincronización ON",
    "cfg.sync_off": "Sincronización OFF",
    "cfg.sync_off_msg": "🔗 <b>Sincronización desactivada.</b>\nAhora cada grupo se configura por separado: escribe /config para elegir grupo.",
    "cfg.which_welcome": "la bienvenida",
    "cfg.which_rules": "las reglas",
    "cfg.edit_which": "✏️ ¿En qué grupo(s) quieres cambiar <b>{what}</b>?\n<i>Elige «Todos» o un grupo concreto.</i>",
    "cfg.dest_all": "todos los grupos",
    "cfg.prompt_welcome": (
        "✏️ <b>Nueva bienvenida para {dest}.</b> Envíamela ahora.\n\n"
        "Ejemplo (cópialo y edítalo):\n"
        "<code>¡Hola {{name}}! 👋 Bienvenido/a a {{chat}}. Échale un ojo al "
        "mensaje anclado con las normas.</code>\n\n"
        "Placeholders: <code>{{name}}</code> (usuario) · <code>{{chat}}</code> "
        "(nombre del grupo). HTML: &lt;b&gt; &lt;i&gt; &lt;code&gt;. "
        "Botones: <code>[Texto](buttonurl://https://url.com)</code>."
    ),
    "cfg.prompt_rules": (
        "📜 <b>Nuevas reglas para {dest}.</b> Envíamelas ahora.\n\n"
        "Ejemplo:\n"
        "<code>1) Respeto. 2) Nada de spam ni enlaces. 3) Solo temas del grupo.</code>\n\n"
        "HTML permitido (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;)."
    ),
    "cfg.alerts_short": "🔔 <b>Avisos informativos</b>\nPulsa para activar o silenciar.",
    "cfg.empty_text": "El texto está vacío. Cancelado. Abre /config para reintentar.",
    "cfg.welcome_updated": "✅ Bienvenida actualizada{extra} {scope}. Escribe /config para seguir ajustando.",
    "cfg.rules_updated": "✅ Reglas actualizadas {scope}. Escribe /config para seguir ajustando.",
    "cfg.btn_extra": " + {n} botón(es)",
    "cfg.sync_status": "🔗 <b>Sincronización de ajustes: {state}</b>\n{detail}\nCambia con <code>/sync on</code> o <code>/sync off</code> (o desde /config).",
    "cfg.sync_detail_on": "Cada cambio de ajuste se aplica a los <b>{n} grupos</b> a la vez y el panel /config no pide elegir grupo.",
    "cfg.sync_detail_off": "Cada grupo se configura por separado; /config te deja elegir grupo.",

    # --- bienvenidas y verificación (lo que ve el usuario del grupo) ---
    # OJO: welcome.* son PLANTILLAS: su {name}/{chat} lo formatea después quien las
    # envía (con guard). t() las devuelve sin formatear a propósito.
    "welcome.default": (
        "👋 Hola {name}, bienvenido/a a <b>{chat}</b>.\n\n"
        "Para evitar spam, los nuevos miembros entran muteados. "
        "<b>Pulsa el botón de abajo para verificar que eres humano</b> y poder escribir."
    ),
    "welcome.clean_default": "👋 ¡Bienvenido/a {name} a {chat}! Echa un vistazo a las normas del grupo.",
    "welcome.friendly1": "👋 Bienvenido/a {name}. Echa un vistazo al grupo.",
    "welcome.friendly2": "🤝 ¡Hola {name}! Bienvenido/a.",
    "welcome.footer_fixed": "Las normas y el mensaje anclado, lo tienen todo.",
    "verif.ok_header": "✅ <b>Verificación correcta.</b>\n\n",
    "verif.btn_human": "✅ SOY HUMANO (PULSA PARA ENTRAR)",
    "verif.not_for_you": "Este botón no es para ti.",
    "verif.done": "✅ Verificado, ya puedes escribir.",
    "verif.footer_susp": "\n\n⏰ <i>Cuenta sospechosa ({reasons}): verifica en <b>{mins} min</b> o serás expulsado.</i>",
    "verif.footer_kick": "\n\n⏰ <i>Si no verificas, serás expulsado en unas <b>{hours}h</b>.</i>",
    "verif.footer_mute": "\n\n⏰ <i>Hasta que no verifiques no podrás escribir (sin límite de tiempo).</i>",
    "verif.reminder": (
        "⏰ <b>Recordatorio para {name}</b>\n\n"
        "Llevas {hours}h en <b>{chat}</b> y aún no has verificado que eres humano. "
        "Te quedan <b>{remaining_hours}h</b> para pulsar el botón o serás "
        "<b>expulsado</b> por considerarte posible bot.\n\n"
        "👇 Pulsa el botón para poder escribir."
    ),

    # --- motivos de sospecha (códigos → texto; la lógica usa los códigos) ---
    "reason.no_username": "sin username",
    "reason.no_firstname": "sin nombre",
    "reason.non_latin_name": "nombre en otro alfabeto",
    "reason.non_latin_username": "username en otro alfabeto",
    "reason.no_photo": "sin foto",
    "reason.recent_account": "cuenta reciente ({days}d)",
    "reason.decorative": "{label} decorativo (mezcla de alfabetos, ignorado)",
    "reason.non_latin_field": "{label} {ratio} no latino ({dominant})",
    "reason.bypass_old_photo": "excepción: cuenta antigua con foto",
    "reason.han_dominant": "nombre dominado por ideogramas chinos (Han)",
    "reason.no_photo_new": "sin foto + cuenta de {days}d",
    "alert.obvious_spam": "Perfil evidentemente spammer: ",

    # --- aviso de acción (lo que recibes cada vez que el bot actúa) ---
    "alert.no_username": "(sin username)",
    "alert.fed": "\n🌐 <b>Federación:</b> {ok} ok · {shadow} shadow · {err} err ({total} chats)",
    "alert.body": (
        "{emoji} <b>{action}</b> · {mode}\n"
        "📍 <b>Chat:</b> {chat} (<code>{chat_id}</code>)\n"
        "👤 <b>User:</b> {user_link} (<code>{user_id}</code>)\n"
        "📏 <b>Nivel de spam:</b> {spam} <i>(score interno {score})</i>\n"
        "🚨 <b>Regla:</b> <code>{rule}</code>\n"
        "💬 <b>Razón:</b> {reason}{signals}{fed}\n"
        "\n📝 <b>Mensaje:</b>\n<pre>{preview}</pre>"
    ),
    "alert.btn_notspam": "❌ No era spam",
    "alert.btn_confirm": "✅ Confirmar",
    "alert.btn_whitelist": "🛡️ Whitelist user",

    # --- warns ---
    "warn.usage": "Uso: <code>/warn [razón]</code> respondiendo a un mensaje, o <code>/warn @username [razón]</code>, o <code>/warn user_id [razón]</code>.",
    "warn.is_admin": "⚠️ No puedo warnear a un admin del chat. Si necesitas hacerlo, hazlo manualmente.",
    "warn.counter": "⚠️ {mention} — Warn <b>{n}/{limit}</b>",
    "warn.last_reason": "\n💬 Último motivo: {reason}",
    "warn.limit_ban": "🔨 {mention} ha alcanzado el límite de warns (<b>{n}/{limit}</b>).\n<b>Ban federado</b> en {ok} chats.",
    "warn.limit_kick": "👢 {mention} ha alcanzado el límite (<b>{n}/{limit}</b>). <b>Kick</b>.",
    "warn.limit_kick_fail": "⚠️ {mention} ha alcanzado el límite (<b>{n}/{limit}</b>), pero <b>no he podido expulsarle</b> (¿me faltan permisos?). Los warns se mantienen.",
    "warn.limit_mute": "🤐 {mention} ha alcanzado el límite (<b>{n}/{limit}</b>). <b>Mute 24h</b>.",
    "warn.limit_mute_fail": "⚠️ {mention} ha alcanzado el límite (<b>{n}/{limit}</b>), pero <b>no he podido silenciarle</b> (¿me faltan permisos?). Los warns se mantienen.",
    "warns.reply_needed": "Responde al mensaje del usuario con /warns.",
    "warns.none": "Sin warns activos para {name}.",
    "rmwarn.reply_needed": "Responde al mensaje del usuario con /rmwarn.",
    "rmwarn.done": "✅ Último warn eliminado.",
    "rmwarn.none": "Sin warns para eliminar.",
    "resetwarns.reply_needed": "Responde al mensaje del usuario con /resetwarns.",
    "resetwarns.done": "✅ {n} warn(s) eliminados.",
    "warnlimit.current": "Límite actual: <b>{limit}</b>",
    "warnlimit.usage": "Uso: /warnlimit <N>",
    "warnlimit.set": "✅ Límite warns = {n}",
    "warnaction.current": "Acción actual: <b>{action}</b>",
    "warnaction.usage": "Uso: /warnaction ban|kick|mute",
    "warnaction.set": "✅ Acción warns = {action}",

    # --- panel /limpieza ---
    "clean.panel": "🧹 <b>Limpieza en grupos</b>\nPara mantener los grupos limpios: que los comandos del bot no salgan al teclear «/» y que no queden escritos en el chat.",
    "clean.b.hide": "🙈 Ocultar comandos en grupos: {state}",
    "clean.b.autodel": "🧽 Auto-borrar comandos en grupos: {state}",
    "clean.hidden": "Comandos en grupos: ocultos",
    "clean.visible": "Comandos en grupos: visibles",
    "clean.autodel_on": "Auto-borrado: ON",
    "clean.autodel_off": "Auto-borrado: OFF",

    # --- menú de comandos de Telegram (el que sale al teclear "/") ---
    "cmd.help": "Guía y lista de comandos",
    "cmd.comandos": "Lista de comandos",
    "cmd.stats": "Métricas del grupo",
    "cmd.chats": "Grupos donde opero",
    "cmd.recent": "Últimas acciones antispam",
    "cmd.ban": "Banear (reply o @usuario) en todos los grupos",
    "cmd.unban": "Quitar el ban a un usuario",
    "cmd.whitelist": "Marcar un usuario como inmune",
    "cmd.notspam": "Revertir un falso positivo (id de /recent)",
    "cmd.warn": "Avisar a un usuario (warn)",
    "cmd.warns": "Ver los warns de un usuario",
    "cmd.warnlimit": "Límite de warns antes de sancionar",
    "cmd.warnaction": "Acción al llegar al límite (ban/kick/mute)",
    "cmd.spam": "Aprender: marcar mensaje como spam + banear",
    "cmd.legal": "Aprender: marcar mensaje como legítimo",
    "cmd.samples": "Ver muestras aprendidas",
    "cmd.forget": "Olvidar una muestra aprendida",
    "cmd.scan": "Analizar un mensaje: ¿lo detectaría? (responde al mensaje)",
    "cmd.config": "Panel de ajustes del grupo con botones",
    "cmd.sync": "Sincronizar ajustes iguales en todos los grupos (on/off)",
    "cmd.limpieza": "Ocultar/auto-borrar comandos del bot en grupos",
    "cmd.idioma": "Cambiar el idioma del bot (es/en)",
    "cmd.verificacion": "Ajustar verificación humana del grupo",
    "cmd.welcome": "Ver la bienvenida",
    "cmd.setwelcome": "Cambiar la bienvenida",
    "cmd.rules": "Ver las reglas",
    "cmd.setrules": "Cambiar las reglas",
    "cmd.cleanservice": "Borrar mensajes de 'X se ha unido'",
    "cmd.alertas": "Activar o silenciar avisos informativos",
    "cmd.shadow": "Ver o cambiar el modo shadow",
    "cmd.top": "Ranking de mensajes",
    "cmd.topweekly": "Ranking semanal",

    # --- /help (guía completa, 2 mensajes) ---
    "help.msg1": (
        "<b>🤖 CazaSpamBot — cómo funciona</b>\n\n"
        "Soy un bot antispam que protege todos los grupos donde soy "
        "admin. <b>Un ban en uno = ban en todos.</b>\n\n"
        "<b>🛡️ Capas de protección (en orden)</b>\n\n"
        "<b>1. Al entrar alguien nuevo</b>\n"
        "  • Si ya lo baneé antes en cualquiera de tus grupos → re-ban (bans sincronizados).\n"
        "  • Reviso su perfil (vía cuenta secundaria): nombre, foto, bio, antigüedad.\n"
        "  • Si el perfil es <b>claramente spam</b> (nombre en otro alfabeto, bio con enlaces porno/promo, fotos subidas todas de golpe = identidad robada) → <b>ban directo, sin avisar</b>.\n"
        "  • Si aparece en listas anti-spam globales (CAS, lols.bot) → ban.\n"
        "  • Si es un <b>bot</b> añadido al grupo → lo expulso y te aviso.\n"
        "  • Si el perfil es muy legítimo (foto + cuenta antigua + nombre normal) → entra directo, sin verificación.\n"
        "  • El resto → mensaje de bienvenida con botón <b>SOY HUMANO</b> (muteado hasta pulsarlo). Sospechosos: kick a los 30 min. Normales: recordatorio a las 3h.\n\n"
        "<b>2. En cada mensaje</b>\n"
        "  Detecto: texto en otro alfabeto, menciones/enlaces a otros grupos, acortadores, deep-links, anuncios comerciales (sueldos, ofertas), forwards de canales en el primer mensaje, mensajes con botones (típico de bots spam), inundación de mensajes (antiflood), y patrones que he aprendido de tus <code>/spam</code>.\n\n"
        "<b>3. Casos especiales que ya cubro</b>\n"
        "  • Bots posteando spam (botones porno) → ban.\n"
        "  • Cuentas dormidas >1 año que reaparecen citando un bot → ban (cuenta hackeada/vendida).\n"
        "  • Mensajes posteados vía bots inline → borro + te aviso.\n\n"
        "<b>⚖️ Niveles de confianza (anti-falsos-positivos)</b>\n"
        "  Cada usuario tiene un <b>nivel de confianza del 1 al 10</b> (10 = veterano de fiar, 1 = recién llegado). Lo calculo así:\n"
        "  • <b>Sube</b> con: mensajes escritos en el grupo, antigüedad de la cuenta en el grupo, y que yo le viera entrar (trayectoria limpia).\n"
        "  • <b>Baja</b> con: warns activos. Y si lo pones en whitelist, va directo a 10.\n"
        "  Según el nivel actúo distinto:\n"
        "  • <b>Nivel 7-10</b> (confianza alta) → casi nunca les actúo.\n"
        "  • <b>Nivel 4-6</b> (media) + algo sospechoso → <b>te pregunto a ti por privado</b> con botones ✅Legítimo / ❌Spam, y aprendo de tu respuesta.\n"
        "  • <b>Nivel 1-3</b> (nuevo/sin historial) → trato normal según las reglas.\n"
        "  En cada mensaje sospechoso verás también un <b>nivel de spam 1-10</b> (10 = clarísimamente spam).\n"
        "  • <i>Mi filosofía: mejor dejar pasar un spam que banear a alguien legítimo.</i>\n\n"
        "<b>🔕 Mensajes en el grupo</b>\n"
        "  Los bans automáticos son <b>silenciosos</b> (no ensucian el chat). Solo tus bans manuales publican un mensajito gracioso, que se borra a las 3h.\n\n"
        "<i>👇 Te paso la lista de comandos en el siguiente mensaje.</i>"
    ),
    "help.note": (
        "\n\n<i>🔒 Eres admin de uno de los grupos pero no el bot admin principal. "
        "Puedes ver toda la información (lectura). Los comandos que modifican "
        "(ban/setwelcome/warn/etc.) los ejecuta solo el bot admin.</i>"
    ),
    "help.msg2": (
        "<b>🛠️ Comandos del bot — referencia</b>\n\n"
        "<b>📊 Ver información</b>\n"
        "  /start — estado del bot y stats rápidas\n"
        "  /stats — métricas (en DM te pregunta de qué grupo)\n"
        "  /chats — lista de grupos donde el bot opera\n"
        "  /recent — últimas 10 acciones. Ejemplo: <code>/recent 30</code> para ver las últimas 30\n"
        "  /comandos — esta misma guía\n  /alertas — activar o silenciar avisos informativos (borrados, bans de otros admins...)\n\n"
        "<b>🔧 Moderación</b> (reply al mensaje o usando @usuario)\n"
        "  <code>/ban @usuario razón</code> — banea en todos tus grupos a la vez\n"
        "  <code>/unban @usuario</code> — quita el ban\n"
        "  <code>/whitelist @usuario</code> — marca como inmune en el chat actual\n"
        "  <code>/notspam 42</code> — revierte falso positivo (el número es el id que ves en /recent)\n\n"
        "<b>⚠️ Warns</b> (avisos progresivos: por defecto 3 = ban)\n"
        "  <code>/warn @usuario razón</code> o reply al mensaje\n"
        "  /warns (reply al user) — ver sus warns activos\n"
        "  /rmwarn (reply) — quita el último warn\n"
        "  /resetwarns (reply) — borra todos los warns\n"
        "  <code>/warnlimit 3</code> — cambia el límite (sin número solo lo muestra)\n"
        "  <code>/warnaction ban</code> — qué hacer al llegar al límite: <code>ban</code>, <code>kick</code> o <code>mute</code>\n\n"
        "<b>📚 Entrenar el clasificador</b> (responde a un mensaje)\n"
        "  /spam — banea al autor (en todos los grupos) + reporta el mensaje + lo añade al clasificador.\n"
        "  /legal — marca el mensaje como LEGÍTIMO (anti-falsos positivos, solo aprende).\n"
        "  El bot borra tu comando del grupo y te confirma por DM.\n"
        "  /samples — cuántas muestras hay. Ejemplo: <code>/samples spam 30</code> lista 30 spam\n"
        "  <code>/forget 5</code> — borra la muestra número 5 (id que ves en /samples)\n"
        "  /scan — <b>¿esto lo pillaría?</b> Responde a un mensaje (reenviado al DM vale) y te digo "
        "qué reglas dispararía y qué estructura tiene (texto, contacto, botones, forward)\n\n"
        "<b>🌹 Welcome, reglas y servicios</b>\n"
        "  /config — <b>panel visual con botones</b>: verificación, avisos, tiempos, bienvenida, "
        "reglas y limpieza, todo de un vistazo. (alias /ajustes /panel)\n"
        "  /sync on|off — <b>sincronizar ajustes en TODOS los grupos</b> (ON por defecto): "
        "cada cambio se aplica a todos a la vez y /config no pide grupo. OFF = cada grupo por separado.\n"
        "  /limpieza — <b>mantener los grupos limpios</b>: ocultar los comandos del bot al teclear «/» "
        "en grupos y auto-borrar los comandos escritos en el chat (ambos ON por defecto).\n"
        "  /idioma es|en — idioma del bot (por defecto se detecta del sistema; español si no).\n"
        "  <i>La bienvenida (👋) es independiente de la verificación: puedes saludar sin verificar.</i>\n"
        "  /welcome — ver el mensaje de bienvenida del grupo actual\n"
        "  <code>/setwelcome texto</code> — cambia el welcome (acepta sintaxis Rose con botones)\n"
        "  /resetwelcome — vuelve al welcome por defecto\n"
        "  /rules — ver reglas | <code>/setrules texto</code> — cambiarlas\n"
        "  /cleanservice on / off — borrar mensajes 'X se ha unido' automáticamente\n"
        "  /verificacion — verificación humana + bienvenida. <b>Por defecto: OFF</b> (grupo "
        "limpio) + <b>revisar ON</b> (aviso privado de sospechosos). Sin nada = ver estado y opciones:\n"
        "     · on|off (desactiva verificación Y welcome) · avisos on|off (recordatorio)\n"
        "     · accion kick|mute (al no verificar: expulsar o quedar muteado) · tiempos N N N\n"
        "     · revisar on|off (sin verificar en grupo: aviso privado de sospechosos con botones)\n"
        "  /testwelcome — vista previa del welcome (te lo enseña como si fueras nuevo)\n\n"
        "<b>🔘 Botones del welcome</b>\n"
        "  /welcomebuttons — lista los botones configurados\n"
        "  <code>/setwelcomebutton Texto | https://url</code> — añade botón\n"
        "  <code>/setwelcomebutton Texto | https://url same</code> — botón en la misma fila\n"
        "  <code>/rmwelcomebutton 3</code> — quita el botón con id 3 (lo ves en /welcomebuttons)\n"
        "  /clearwelcomebuttons — quita todos\n\n"
        "<b>🏆 Top semanal de actividad</b>\n"
        "  /top — muestra el top 5 de los últimos 7 días (en DM te pregunta de qué grupo)\n"
        "  /topweekly on / off — activar o desactivar el anuncio automático (domingo 20:00)\n"
        "  Filtros: texto ≥10 chars o mensajes con media (foto/video/sticker/audio), sin saludos repetidos, cooldown 10s.\n\n"
        "<b>🫡 Greeters (reacciones a saludos)</b>\n"
        "  /listgreeters — usuarios marcados como amables\n"
        "  <code>/setgreeter @usuario 🫡 🤝</code> — añade greeter con reacciones (ej.)\n"
        "  <code>/rmgreeter @usuario</code> — quítalo\n\n"
        "<b>👥 Reportes con @admin</b> (lo usan los miembros del grupo)\n"
        "  Cualquier user responde a un mensaje con <code>@admin</code>; el bot le confirma. "
        "Si tú actúas (warn/ban/borrar), el bot borra también el reporte original y publica un agradecimiento al reporter. Sin warns para el que reporta.\n\n"
        "<b>⚙️ Modo de operación</b>\n"
        "  /shadow on — solo loggea, no actúa (modo prueba)\n"
        "  /shadow off — modo ACTIVO (ban/kick/delete reales)\n"
        "  El cambio es inmediato pero no persiste al reiniciar el bot; "
        "para que sea permanente edita MODE en el .env del servidor.\n\n"
        "<b>ℹ️ Tips útiles</b>\n"
        "  · Los <i>números id</i> (de muestra, acción, botón, etc.) los ves siempre en el listado correspondiente: /recent, /samples, /welcomebuttons...\n"
        "  · Los <i>user_id numéricos</i> los obtienes en las notificaciones que te llegan al DM, o usando @userinfobot.\n"
        "  · En DM al bot, los comandos de consulta (/stats /welcome /rules) muestran botones para elegir grupo si estás en varios."
    ),
}
