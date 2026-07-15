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
}
