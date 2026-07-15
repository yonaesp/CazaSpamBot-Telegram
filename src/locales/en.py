"""ENGLISH language pack. Key -> text (with {x} placeholders for .format()).

Quality translation of es.py. Any key missing here falls back to the Spanish string.
"""
STRINGS = {
    # --- common ---
    "only_admin": "Only the bot admin can change this.",
    "on": "✅ ON",
    "off": "❌ OFF",

    # --- /idioma (language) command ---
    "lang.current": "🌍 Bot language: <b>{lang}</b>\n"
                    "Change it with <code>/idioma en</code> or <code>/idioma es</code>.",
    "lang.set": "🌍 Language changed to <b>{lang}</b>. The bot's text will now be in that language.",
    "lang.invalid": "Unsupported language. Available: <code>es</code>, <code>en</code>.",

    # --- suspicious-user review notification ---
    "review.title": "🔍 <b>Suspicious user (review)</b>",
    "review.chat": "📍 Chat: {title}",
    "review.user": "👤 <a href=\"tg://user?id={uid}\">{label}</a> (<code>{uid}</code>)",
    "review.reason": "🚩 Reason: {reasons}",
    "review.reason_default": "dubious profile",
    "review.footer": "<i>They are already INSIDE the group (allowed by default). "
                     "Check their profile and decide.</i>",
    "review.allowed": "\n\n✅ <b>Allowed by the admin.</b>",
    "review.banned": "\n\n🔨 <b>Banned by the admin</b> ({n} group/s).",

    # --- notification buttons ---
    "btn.allow": "✅ Allow",
    "btn.ban": "🔨 Ban",
    "btn.gear": "⚙️ Group settings",
    "btn.verif": "🛡️ Human verification: {state}",
    "btn.alerts": "🔔 Suspicious alerts: {state}",
    "btn.reminders": "⏰ Verification reminders: {state}",
    "btn.times": "⏱️ Timings: {sk}min · {rh}h · +{kh}h ▸",
    "btn.hide": "⬅️ Hide settings",
    "btn.back": "⬅️ Back",

    # --- toasts (ephemeral button responses) ---
    "toast.allowed": "✅ Allowed.",
    "toast.banned": "🔨 Banned ({n} group/s).",
    "toast.verif": "Human verification",
    "toast.alerts": "Suspicious alerts",
    "toast.reminders": "Verification reminders",
}
