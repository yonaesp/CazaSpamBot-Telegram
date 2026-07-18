"""ENGLISH language pack. Key -> text (with {x} placeholders for .format()).

Quality translation of es.py. Any key missing here falls back to the Spanish string.
"""
STRINGS = {
    # --- common ---
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

    # --- moderation command confirmations ---
    "shadow.usage": "Usage: /shadow on|off",
    "shadow.changed": "Mode changed to <b>{mode}</b>",
    "whitelist.usage": "Usage: /whitelist <user_id>",
    "whitelist.done": "User <code>{uid}</code> whitelisted in this chat.",
    "notspam.usage": "Usage: /notspam <action_id>",
    "notspam.notfound": "action_id not found.",
    "notspam.done": "Action {aid} marked as a false positive. Ban revoked and rule suppressed for 7 days.",
    "alerts.panel": (
        "🔔 <b>Informational alerts</b>\n"
        "Tap a button to enable or silence it. It doesn't affect anti-spam action "
        "alerts (those are the bot's core)."
    ),

    # --- /config and /sync panel ---
    "cfg.header": "⚙️ <b>Settings · {title}</b>\nTap to change. Changes are saved instantly.",
    "cfg.title_all": "All groups (synced)",
    "cfg.kick": "Kick",
    "cfg.mute": "Mute",
    "cfg.b.sync": "🔗 Sync all groups: {state}",
    "cfg.b.verif": "🛡️ Verification: {state}",
    "cfg.b.review": "👁️ Review suspicious privately: {state}",
    "cfg.b.reminders": "🔔 Reminders: {state}",
    "cfg.b.action": "🚪 On failed verification: {action}",
    "cfg.b.times": "⏱️ Timings: {sk}min · {rh}h · +{kh}h ▸",
    "cfg.b.welcome": "👋 Welcome: {state}",
    "cfg.b.edit_welcome": "✏️ Edit welcome text ▸",
    "cfg.b.edit_rules": "📜 Edit rules ▸",
    "cfg.b.cleanservice": "🧹 Delete service messages: {state}",
    "cfg.b.alerts": "🔔 Informational alerts ▸",
    "cfg.b.close": "✖️ Close",
    "cfg.b.back": "⬅️ Back",
    "cfg.b.all_groups": "🌐 All groups",
    "cfg.b.cancel": "✖️ Cancel",
    "cfg.scope_n": "in {n} groups",
    "cfg.scope_one": "in {title}",
    "cfg.times_text": (
        "⏱️ <b>Verification timings · {title}</b>\n\n"
        "1st row · <b>suspicious</b>: minutes until kick if they don't verify.\n"
        "2nd row · <b>reminder</b>: hours until reminding those who don't verify.\n"
        "3rd row · <b>kick</b>: hours after the reminder to kick.\n\n"
        "Current: <b>{sk}min · {rh}h · +{kh}h</b>"
    ),
    "cfg.no_admin": "I'm not an admin in any group yet.",
    "cfg.pick_group": "⚙️ <b>Settings</b> — which group do you want to configure?\n<i>(Sync is OFF: each group separately.)</i>",
    "cfg.only_admin": "Only the bot admin can configure this.",
    "cfg.invalid_chat": "Invalid chat.",
    "cfg.invalid_opt": "Invalid option.",
    "cfg.invalid_val": "Invalid value.",
    "cfg.val_range": "Value out of range.",
    "cfg.closed_toast": "Closed.",
    "cfg.closed_msg": "⚙️ Panel closed. Type /config to open it again.",
    "cfg.act_on": "✅ Enabled",
    "cfg.act_off": "❌ Disabled",
    "cfg.in_n": " in {n} groups",
    "cfg.dot_n": " · {n} groups",
    "cfg.sync_on": "🔗 Sync ON",
    "cfg.sync_off": "Sync OFF",
    "cfg.sync_off_msg": "🔗 <b>Sync disabled.</b>\nNow each group is configured separately: type /config to pick a group.",
    "cfg.which_welcome": "the welcome",
    "cfg.which_rules": "the rules",
    "cfg.edit_which": "✏️ Which group(s) do you want to change <b>{what}</b> for?\n<i>Pick «All» or a specific group.</i>",
    "cfg.dest_all": "all groups",
    "cfg.prompt_welcome": (
        "✏️ <b>New welcome for {dest}.</b> Send it now.\n\n"
        "Example (copy and edit it):\n"
        "<code>Hi {{name}}! 👋 Welcome to {{chat}}. Take a look at the "
        "pinned message with the rules.</code>\n\n"
        "Placeholders: <code>{{name}}</code> (user) · <code>{{chat}}</code> "
        "(group name). HTML: &lt;b&gt; &lt;i&gt; &lt;code&gt;. "
        "Buttons: <code>[Text](buttonurl://https://url.com)</code>."
    ),
    "cfg.prompt_rules": (
        "📜 <b>New rules for {dest}.</b> Send them now.\n\n"
        "Example:\n"
        "<code>1) Respect. 2) No spam or links. 3) On-topic only.</code>\n\n"
        "HTML allowed (&lt;b&gt;, &lt;i&gt;, &lt;code&gt;)."
    ),
    "cfg.alerts_short": "🔔 <b>Informational alerts</b>\nTap to enable or silence.",
    "cfg.empty_text": "The text is empty. Cancelled. Open /config to retry.",
    "cfg.welcome_updated": "✅ Welcome updated{extra} {scope}. Type /config to keep adjusting.",
    "cfg.rules_updated": "✅ Rules updated {scope}. Type /config to keep adjusting.",
    "cfg.btn_extra": " + {n} button(s)",
    "cfg.sync_status": "🔗 <b>Settings sync: {state}</b>\n{detail}\nChange it with <code>/sync on</code> or <code>/sync off</code> (or from /config).",
    "cfg.sync_detail_on": "Every setting change applies to all <b>{n} groups</b> at once and the /config panel doesn't ask which group.",
    "cfg.sync_detail_off": "Each group is configured separately; /config lets you pick a group.",

    # --- welcomes and verification (what group members see) ---
    # NOTE: welcome.* are TEMPLATES: their {name}/{chat} is formatted later by the
    # sender (with a guard). t() returns them unformatted on purpose.
    "welcome.default": (
        "👋 Hi {name}, welcome to <b>{chat}</b>.\n\n"
        "To keep spam out, new members join muted. "
        "<b>Tap the button below to verify you're human</b> and be able to write."
    ),
    "welcome.clean_default": "👋 Welcome {name} to {chat}! Take a look at the group rules.",
    "welcome.friendly1": "👋 Welcome {name}. Have a look around.",
    "welcome.friendly2": "🤝 Hi {name}! Welcome aboard.",
    "welcome.footer_fixed": "The rules and the pinned message have everything.",
    "verif.ok_header": "✅ <b>Verification successful.</b>\n\n",
    "verif.btn_human": "✅ I AM HUMAN (TAP TO JOIN IN)",
    "verif.not_for_you": "This button isn't for you.",
    "verif.done": "✅ Verified, you can write now.",
    "verif.footer_susp": "\n\n⏰ <i>Suspicious account ({reasons}): verify within <b>{mins} min</b> or you'll be removed.</i>",
    "verif.footer_kick": "\n\n⏰ <i>If you don't verify, you'll be removed in about <b>{hours}h</b>.</i>",
    "verif.footer_mute": "\n\n⏰ <i>Until you verify you won't be able to write (no time limit).</i>",
    "verif.reminder": (
        "⏰ <b>Reminder for {name}</b>\n\n"
        "You've been in <b>{chat}</b> for {hours}h and still haven't verified you're human. "
        "You have <b>{remaining_hours}h</b> left to tap the button or you'll be "
        "<b>removed</b> as a suspected bot.\n\n"
        "👇 Tap the button to be able to write."
    ),

    # --- suspicion reasons (codes → text; the logic uses the codes) ---
    "reason.no_username": "no username",
    "reason.no_firstname": "no first name",
    "reason.non_latin_name": "name in another alphabet",
    "reason.non_latin_username": "username in another alphabet",
    "reason.no_photo": "no profile photo",
    "reason.recent_account": "recent account ({days}d)",
    "reason.decorative": "{label} decorative (mixed alphabets, ignored)",
    "reason.non_latin_field": "{label} {ratio} non-latin ({dominant})",
    "reason.bypass_old_photo": "exception: old account with photo",
    "reason.han_dominant": "name dominated by Chinese ideographs (Han)",
    "reason.no_photo_new": "no photo + {days}d-old account",
    "alert.obvious_spam": "Clearly a spammer profile: ",

    # --- action alert (what you get every time the bot acts) ---
    "alert.no_username": "(no username)",
    "alert.fed": "\n🌐 <b>Federation:</b> {ok} ok · {shadow} shadow · {err} err ({total} chats)",
    "alert.body": (
        "{emoji} <b>{action}</b> · {mode}\n"
        "📍 <b>Chat:</b> {chat} (<code>{chat_id}</code>)\n"
        "👤 <b>User:</b> {user_link} (<code>{user_id}</code>)\n"
        "📏 <b>Spam level:</b> {spam} <i>(internal score {score})</i>\n"
        "🚨 <b>Rule:</b> <code>{rule}</code>\n"
        "💬 <b>Reason:</b> {reason}{signals}{fed}\n"
        "\n📝 <b>Message:</b>\n<pre>{preview}</pre>"
    ),
    "alert.btn_notspam": "❌ Not spam",
    "alert.btn_confirm": "✅ Confirm",
    "alert.btn_whitelist": "🛡️ Whitelist user",

    # --- warns ---
    "warn.usage": "Usage: <code>/warn [reason]</code> replying to a message, or <code>/warn @username [reason]</code>, or <code>/warn user_id [reason]</code>.",
    "warn.is_admin": "⚠️ I can't warn a chat admin. If you need to, do it manually.",
    "warn.counter": "⚠️ {mention} — Warn <b>{n}/{limit}</b>",
    "warn.last_reason": "\n💬 Last reason: {reason}",
    "warn.limit_ban": "🔨 {mention} reached the warning limit (<b>{n}/{limit}</b>).\n<b>Federated ban</b> in {ok} chats.",
    "warn.limit_kick": "👢 {mention} reached the limit (<b>{n}/{limit}</b>). <b>Kick</b>.",
    "warn.limit_kick_fail": "⚠️ {mention} reached the limit (<b>{n}/{limit}</b>), but I <b>couldn't remove them</b> (am I missing permissions?). The warnings are kept.",
    "warn.limit_mute": "🤐 {mention} reached the limit (<b>{n}/{limit}</b>). <b>Mute 24h</b>.",
    "warn.limit_mute_fail": "⚠️ {mention} reached the limit (<b>{n}/{limit}</b>), but I <b>couldn't mute them</b> (am I missing permissions?). The warnings are kept.",
    "warns.reply_needed": "Reply to the user's message with /warns.",
    "warns.none": "No active warnings for {name}.",
    "rmwarn.reply_needed": "Reply to the user's message with /rmwarn.",
    "rmwarn.done": "✅ Last warning removed.",
    "rmwarn.none": "No warnings to remove.",
    "resetwarns.reply_needed": "Reply to the user's message with /resetwarns.",
    "resetwarns.done": "✅ {n} warning(s) removed.",
    "warnlimit.current": "Current limit: <b>{limit}</b>",
    "warnlimit.usage": "Usage: /warnlimit <N>",
    "warnlimit.set": "✅ Warning limit = {n}",
    "warnaction.current": "Current action: <b>{action}</b>",
    "warnaction.usage": "Usage: /warnaction ban|kick|mute",
    "warnaction.set": "✅ Warning action = {action}",

    # --- /limpieza panel ---
    "clean.panel": "🧹 <b>Group cleanup</b>\nTo keep groups clean: the bot's commands don't show when typing «/» and don't stay written in the chat.",
    "clean.b.hide": "🙈 Hide commands in groups: {state}",
    "clean.b.autodel": "🧽 Auto-delete commands in groups: {state}",
    "clean.hidden": "Commands in groups: hidden",
    "clean.visible": "Commands in groups: visible",
    "clean.autodel_on": "Auto-delete: ON",
    "clean.autodel_off": "Auto-delete: OFF",

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

    # --- /help (full guide, 2 messages) ---
    "help.msg1": (
        "<b>🤖 CazaSpamBot — how it works</b>\n\n"
        "I'm an anti-spam bot that protects every group where I'm an "
        "admin. <b>A ban in one = a ban in all.</b>\n\n"
        "<b>🛡️ Protection layers (in order)</b>\n\n"
        "<b>1. When someone new joins</b>\n"
        "  • If I already banned them in any of your groups → re-ban (synchronized bans).\n"
        "  • I check their profile (via the secondary account): name, photo, bio, age.\n"
        "  • If the profile is <b>clearly spam</b> (name in another alphabet, bio with porn/promo links, photos all uploaded at once = stolen identity) → <b>direct ban, no warning</b>.\n"
        "  • If they appear on global anti-spam lists (CAS, lols.bot) → ban.\n"
        "  • If it's a <b>bot</b> added to the group → I kick it and notify you.\n"
        "  • If the profile is very legit (photo + old account + normal name) → walks straight in, no verification.\n"
        "  • Everyone else → welcome message with a <b>SOY HUMANO</b> (I'M HUMAN) button (muted until they tap it). Suspicious: kick after 30 min. Normal: reminder after 3h.\n\n"
        "<b>2. On every message</b>\n"
        "  I detect: text in another alphabet, mentions/links to other groups, URL shorteners, deep-links, commercial ads (salaries, offers), channel forwards as the first message, messages with buttons (typical of spam bots), message flooding (antiflood), and patterns I learned from your <code>/spam</code> calls.\n\n"
        "<b>3. Special cases I already cover</b>\n"
        "  • Bots posting spam (porn buttons) → ban.\n"
        "  • Accounts dormant >1 year that reappear citing a bot → ban (hijacked/sold account).\n"
        "  • Messages posted via inline bots → I delete + notify you.\n\n"
        "<b>⚖️ Trust levels (anti-false-positive)</b>\n"
        "  Every user has a <b>trust level from 1 to 10</b> (10 = trusted veteran, 1 = newcomer). I compute it like this:\n"
        "  • <b>Goes up</b> with: messages written in the group, account age in the group, and my having seen them join (clean track record).\n"
        "  • <b>Goes down</b> with: active warnings. And if you whitelist them, they jump straight to 10.\n"
        "  I act differently depending on the level:\n"
        "  • <b>Level 7-10</b> (high trust) → I almost never act on them.\n"
        "  • <b>Level 4-6</b> (medium) + something suspicious → <b>I ask you privately</b> with ✅Legit / ❌Spam buttons, and I learn from your answer.\n"
        "  • <b>Level 1-3</b> (new/no history) → normal treatment by the rules.\n"
        "  On every suspicious message you'll also see a <b>spam level 1-10</b> (10 = blatantly spam).\n"
        "  • <i>My philosophy: better to let a spam slip than to ban a legit user.</i>\n\n"
        "<b>🔕 Messages in the group</b>\n"
        "  Automatic bans are <b>silent</b> (they don't clutter the chat). Only your manual bans post a little witty message, which auto-deletes after 3h.\n\n"
        "<i>👇 I'll send you the command list in the next message.</i>"
    ),
    "help.note": (
        "\n\n<i>🔒 You're an admin of one of the groups but not the main bot admin. "
        "You can see all the information (read-only). The commands that modify things "
        "(ban/setwelcome/warn/etc.) can only be run by the bot admin.</i>"
    ),
    "help.msg2": (
        "<b>🛠️ Bot commands — reference</b>\n\n"
        "<b>📊 View information</b>\n"
        "  /start — bot status and quick stats\n"
        "  /stats — metrics (in DM it asks which group)\n"
        "  /chats — list of groups where the bot operates\n"
        "  /recent — last 10 actions. Example: <code>/recent 30</code> to see the last 30\n"
        "  /comandos — this same guide\n  /alertas — enable or silence informational alerts (deletions, other admins' bans...)\n\n"
        "<b>🔧 Moderation</b> (reply to the message or use @user)\n"
        "  <code>/ban @user reason</code> — bans across all your groups at once\n"
        "  <code>/unban @user</code> — removes the ban\n"
        "  <code>/whitelist @user</code> — marks as immune in the current chat\n"
        "  <code>/notspam 42</code> — reverts a false positive (the number is the id shown in /recent)\n\n"
        "<b>⚠️ Warns</b> (progressive warnings: default 3 = ban)\n"
        "  <code>/warn @user reason</code> or reply to the message\n"
        "  /warns (reply to the user) — see their active warnings\n"
        "  /rmwarn (reply) — removes the last warning\n"
        "  /resetwarns (reply) — clears all warnings\n"
        "  <code>/warnlimit 3</code> — change the limit (no number just shows it)\n"
        "  <code>/warnaction ban</code> — what to do at the limit: <code>ban</code>, <code>kick</code> or <code>mute</code>\n\n"
        "<b>📚 Train the classifier</b> (reply to a message)\n"
        "  /spam — bans the author (in all groups) + reports the message + adds it to the classifier.\n"
        "  /legal — marks the message as LEGITIMATE (anti-false-positive, only learns).\n"
        "  The bot deletes your command from the group and confirms by DM.\n"
        "  /samples — how many samples there are. Example: <code>/samples spam 30</code> lists 30 spam\n"
        "  <code>/forget 5</code> — deletes sample number 5 (id shown in /samples)\n"
        "  /scan — <b>would this be caught?</b> Reply to a message (forwarded to your DM works) and I'll tell you "
        "which rules would fire and what structure it has (text, contact, buttons, forward)\n\n"
        "<b>🌹 Welcome, rules and services</b>\n"
        "  /config — <b>visual panel with buttons</b>: verification, alerts, timings, welcome, "
        "rules and cleanup, all at a glance. (aliases /ajustes /panel)\n"
        "  /sync on|off — <b>sync settings across ALL groups</b> (ON by default): "
        "every change applies to all at once and /config doesn't ask which group. OFF = each group separately.\n"
        "  /limpieza — <b>keep groups clean</b>: hide the bot's commands when typing «/» "
        "in groups and auto-delete command messages written in the chat (both ON by default).\n"
        "  /idioma es|en — bot language (detected from the system by default; Spanish otherwise).\n"
        "  <i>The welcome (👋) is independent of verification: you can greet without verifying.</i>\n"
        "  /welcome — view the current group's welcome message\n"
        "  <code>/setwelcome text</code> — change the welcome (accepts Rose syntax with buttons)\n"
        "  /resetwelcome — back to the default welcome\n"
        "  /rules — view rules | <code>/setrules text</code> — change them\n"
        "  /cleanservice on / off — auto-delete 'X joined the group' messages\n"
        "  /verificacion — human verification + welcome. <b>Default: OFF</b> (clean "
        "group) + <b>review ON</b> (private suspicious alerts). With no args = view status and options:\n"
        "     · on|off (disables verification AND welcome) · avisos on|off (reminder)\n"
        "     · accion kick|mute (on failed verification: kick or stay muted) · tiempos N N N\n"
        "     · revisar on|off (without verifying in the group: private suspicious alert with buttons)\n"
        "  /testwelcome — welcome preview (shows it to you as if you were new)\n\n"
        "<b>🔘 Welcome buttons</b>\n"
        "  /welcomebuttons — lists the configured buttons\n"
        "  <code>/setwelcomebutton Text | https://url</code> — adds a button\n"
        "  <code>/setwelcomebutton Text | https://url same</code> — button on the same row\n"
        "  <code>/rmwelcomebutton 3</code> — removes button id 3 (shown in /welcomebuttons)\n"
        "  /clearwelcomebuttons — removes all\n\n"
        "<b>🏆 Weekly activity top</b>\n"
        "  /top — shows the top 5 of the last 7 days (in DM it asks which group)\n"
        "  /topweekly on / off — enable or disable the automatic announcement (Sunday 20:00)\n"
        "  Filters: text ≥10 chars or messages with media (photo/video/sticker/audio), no repeated greetings, 10s cooldown.\n\n"
        "<b>🫡 Greeters (reactions to greetings)</b>\n"
        "  /listgreeters — users marked as friendly\n"
        "  <code>/setgreeter @user 🫡 🤝</code> — adds a greeter with reactions (e.g.)\n"
        "  <code>/rmgreeter @user</code> — removes it\n\n"
        "<b>👥 Reports with @admin</b> (used by group members)\n"
        "  Any user replies to a message with <code>@admin</code>; the bot confirms it. "
        "If you act (warn/ban/delete), the bot also deletes the original report and posts a thank-you to the reporter. No warnings for whoever reports.\n\n"
        "<b>⚙️ Operation mode</b>\n"
        "  /shadow on — only logs, doesn't act (test mode)\n"
        "  /shadow off — ACTIVE mode (real ban/kick/delete)\n"
        "  The change is immediate but doesn't persist across restarts; "
        "to make it permanent edit MODE in the server's .env.\n\n"
        "<b>ℹ️ Useful tips</b>\n"
        "  · The <i>id numbers</i> (of sample, action, button, etc.) always appear in the matching list: /recent, /samples, /welcomebuttons...\n"
        "  · The <i>numeric user_ids</i> come from the notifications you get in your DM, or via @userinfobot.\n"
        "  · In the bot's DM, the query commands (/stats /welcome /rules) show buttons to pick a group if you're in several."
    ),
}
