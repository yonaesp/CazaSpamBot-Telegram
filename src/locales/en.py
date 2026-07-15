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

    # --- Telegram command menu (shown when typing "/") ---
    "cmd.help": "Guide and command list",
    "cmd.comandos": "Command list",
    "cmd.stats": "Group metrics",
    "cmd.chats": "Groups I operate in",
    "cmd.recent": "Latest anti-spam actions",
    "cmd.ban": "Ban (reply or @user) across all groups",
    "cmd.unban": "Remove a user's ban",
    "cmd.whitelist": "Mark a user as immune",
    "cmd.notspam": "Revert a false positive (id from /recent)",
    "cmd.warn": "Warn a user",
    "cmd.warns": "See a user's warnings",
    "cmd.warnlimit": "Warnings limit before sanction",
    "cmd.warnaction": "Action when the limit is reached (ban/kick/mute)",
    "cmd.spam": "Learn: mark message as spam + ban",
    "cmd.legal": "Learn: mark message as legitimate",
    "cmd.samples": "View learned samples",
    "cmd.forget": "Forget a learned sample",
    "cmd.scan": "Analyze a message: would it be detected? (reply to it)",
    "cmd.config": "Visual group settings panel",
    "cmd.sync": "Sync identical settings across all groups (on/off)",
    "cmd.limpieza": "Hide/auto-delete the bot's commands in groups",
    "cmd.idioma": "Change the bot's language (es/en)",
    "cmd.verificacion": "Adjust the group's human verification",
    "cmd.welcome": "View the welcome message",
    "cmd.setwelcome": "Change the welcome message",
    "cmd.rules": "View the rules",
    "cmd.setrules": "Change the rules",
    "cmd.cleanservice": "Delete 'X joined the group' messages",
    "cmd.alertas": "Enable or silence informational alerts",
    "cmd.shadow": "View or change shadow mode",
    "cmd.top": "Message ranking",
    "cmd.topweekly": "Weekly ranking",
}
