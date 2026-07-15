"""Paquete de idioma ESPAÑOL. Clave -> texto (con placeholders {x} para .format()).

El español es el idioma de referencia (fallback). Al añadir una clave aquí, añádela
también en en.py con su traducción de calidad.
"""
STRINGS = {
    # --- comunes ---
    "only_admin": "Solo el admin del bot puede configurar.",
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
}
