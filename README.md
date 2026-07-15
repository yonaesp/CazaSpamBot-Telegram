<div align="center">

# 🛡️ CazaSpamBot

### Self-hosted anti-spam & moderation bot for Telegram — synchronized cross-group bans, active learning, and near-zero false positives

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-21.6-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.36-blueviolet)](https://docs.telethon.dev/)
[![Tests](https://img.shields.io/badge/tests-360%20passing-success)](#-tests)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

🌍 **English** · [**Español**](README.es.md)

*Moderate as many groups as you want, 24/7. Built so the average member never notices it exists… until a spammer walks in.*

</div>

---

## ✨ What it does

CazaSpamBot watches your Telegram groups and removes spam **before it becomes a nuisance**, with one obsession: **never ban a legitimate user**. It would rather let a borderline spam slip through than kick a real person.

- 🔗 **Synchronized bans** — a ban in one group = a ban across **all** your groups (what other bots call *federation*). No native primitive: it iterates over every chat where it's an admin.
- 🧠 **19 detectors** combined with a graduated trust system.
- 🤫 **Silent moderation** — automatic bans don't clutter the chat.
- 📚 **Active learning** — learns from your `/spam` and `/legal` calls (Naive Bayes + cosine similarity).
- 🛰️ **Official reports** to Telegram (Native Antispam) over MTProto.
- ⚙️ **Configure without touching code** — welcomes, blocklists, and allowed alphabets live in text files, `.env`, and visual `/config` panels.

Works with **any number of groups** (auto-discovers the ones where it's an admin, or restrict it with `MODERATED_CHAT_IDS`). The bot's own text is currently in Spanish (an English/i18n layer is in progress), but detection is **language-agnostic**: you decide which alphabets are normal for your community.

---

## 🛡️ How it protects

### When someone new joins

```
Already banned by the bot in another of YOUR groups?  ──► re-ban
Clearly a spam profile?      ──► direct, silent ban
   · name in unusual alphabets (≥2 fields)
   · bio with porn/promo invite link + emojis + keywords
   · profile photos all uploaded at once (stolen identity)
On global lists (CAS / lols.bot)?  ──► ban (configurable threshold)
A bot added to the group?          ──► kick + notify the admin
Very legit profile? (photo + >1 year + normal name)  ──► walks straight in
Everyone else  ──► clean mode by default (see below)
```

> **Synchronized bans ≠ global lists.** Synchronization (the "federation" of Rose and similar bots) is *internal*: your own bans replicated across your groups. **CAS** ([cas.chat](https://cas.chat), by Combot) and **lols.bot** are *worldwide* crowd-sourced databases of spammers already caught across thousands of groups. With CAS you tune strictness via `CAS_AUTOBAN_MIN`: `2` (default) only bans when confirmed in 2+ groups and sends single-hit cases to your review; `1` bans on any signal (more aggressive, more false positives). High-trust users are never list-banned without passing through your review first.

### On every message

| Detector | Catches |
|---|---|
| `non_allowed_script` | Text in disallowed alphabets (configurable via `ALLOWED_SCRIPTS`) |
| `external_mention` | Mentions/links to other groups |
| `url_blocklist` · `tg_deeplink` | URL shorteners and phishing deep-links |
| `commercial_ad` | Ads (salaries, "work from home", crypto, illegal services) |
| `contact_spam` | Shared contact card whose name is the ad itself (foreign alphabet or with links) |
| `external_reply` | Promoting an external channel via a cross-chat quote (the "quote" that leads off-site) |
| `bio_spam` | Profile bio with porn/commercial/hacking promo |
| `forward_first_msg` | Channel forward as the very first message |
| `first_msg_media` · `inline_buttons` | Suspicious photo/buttons right out of the gate |
| `photos_batch_upload` | 3+ profile photos uploaded within seconds |
| `obvious_spam_profile` | Profile with multiple bot signals |
| `reaction_farming` | Accounts that only drop likes without ever writing |
| `dormant_bot_mention` | Account dormant >1 year that reappears citing a bot (hijacked) |
| `emoji_only` | First message that's just a string of emojis, no text |
| `jfm_delta` | First message suspiciously fast after joining (<90s = bot) |
| `premium_new_link` | Brand-new Premium account that joins posting links |
| `cas` · `lols_bot` | Spammers flagged on the global CAS and lols.bot lists |
| `learned_similarity` | Whatever it learned from your `/spam` calls |
| `antiflood` | Per-user message flooding |

It also bans **spam posted "on behalf of a channel"** (`sender_chat` → `banChatSenderChat`) in comment groups when a strong rule fires. With **`/scan`** (reply to a forwarded message) you can check in advance whether the bot would detect any given message, and what structure it has.

### Trust levels (anti-false-positive)

Every user has a **trust level from 1 to 10** (rises with messages and time in the group, drops with warnings; whitelist = instant 10):

- **Level 7-10** (veterans) → practically untouchable.
- **Level 4-6** + something suspicious → the bot **asks you privately** with ✅ Legit / ❌ Spam buttons, and **learns** from your answer.
- **Level 1-3** (newcomers) → normal moderation.

Every alert also includes a **spam level from 1 to 10** for the message, so it's understandable at a glance.

Reinforcements: **NFKC + [confusable_homoglyphs](https://github.com/vhf/confusable_homoglyphs) (UTS#39)** so decorative names (Cherokee, mathematical, mixed scripts) aren't mistaken for spam. Bypass for old accounts with a photo.

---

## 🎨 Configuration without touching code

Everything is adjustable **from Telegram itself** with visual button panels, or from files/`.env` — whichever you prefer.

### Visual settings panel (`/config`)

The **recommended** way to configure each group without memorizing subcommands. Type `/config` (aliases `/ajustes`, `/panel`) in the group, or **in the bot's DM** to pick a group with buttons. A panel appears and updates instantly on tap:

- 🔗 **Sync all groups** on/off · 🛡️ **Verification** · 👁️ **Review suspicious privately** · 🔔 **Reminders**
- 🚪 **On failed verification**: Kick / Mute · ⏱️ **Timings** (submenu with presets)
- 👋 **Welcome** on/off · ✏️ **Edit welcome** · 📜 **Edit rules** (on edit you pick **All groups** or **just one**, with an example to type the text directly)
- 🧹 **Clean service messages** on/off · 🔔 **Informational alerts**

**Clean mode by default:** verification and welcome start **OFF** (the group stays silent), while **private review of suspicious profiles is ON** — when a clearly dubious profile joins, you get a **private** alert (in your DM or the `ADMIN_NOTIFY_CHAT_ID` chat) with **✅ Allow** / **🔨 Ban** buttons; the user enters allowed by default. That alert also carries a **⚙️ gear** that expands quick toggles (verification, alerts, reminders, timings) editing the notification in place. Message moderation stays fully active regardless.

**Welcome is independent of verification:** you can greet newcomers *without* the SOY HUMANO gate, run verification only, or both.

### Sync settings across groups (`/sync`)

**On by default.** When sync is ON, any setting change applies **to all groups at once** (they stay identical), the welcome text is shared (use `{chat}` for the group name and `{name}` for the user), and `/config` doesn't ask which group. Turn it **OFF** to configure each group separately.

### Keep groups clean (`/limpieza`)

Hide the bot's commands in groups (they don't show up when typing `/`) and auto-delete command messages written in the chat, so nothing clutters the group and users don't tap them. Both **on by default**.

### Files & environment

| What | Where | How |
|---|---|---|
| Welcome greetings | `config/welcomes/` | One phrase per line, `{name}` for the name. `generic.txt` for all groups, `<chat_id>.txt` for group-specific lines. |
| Blocklist words/phrases | `config/blacklist/` | One pattern per line (word or regex). Delete a file and defaults kick in. |
| Allowed alphabets | `.env` → `ALLOWED_SCRIPTS` | CSV: `latin`, `cyrillic`, `arabic`, `han`, … per your community's language. |
| CAS strictness | `.env` → `CAS_AUTOBAN_MIN` | `2` = ban only if confirmed in 2+ groups (recommended); `1` = ban on any signal. |
| Blocked shorteners | `.env` → `URL_BLOCKLIST` | CSV of domains. |
| Thresholds & actions | `.env` | Ban/kick/mute scores, first-suspicious-message action, etc. |

Each folder has its own `README.md` explaining the format.

---

## 🧰 Stack

| Component | Technology |
|---|---|
| Bot API (async polling) | `python-telegram-bot[ext]` 21.6 |
| MTProto (bio, photos, official reports) | `Telethon` 1.36 |
| Database | SQLite (WAL) |
| Classifier | Naive Bayes + cosine (stdlib, no sklearn) |
| Homoglyphs | `confusable-homoglyphs` (UTS#39) |
| Deployment | Docker Compose |

> **Telethon is optional** (but recommended): it needs a secondary user account. Without it, or with `TELETHON_ENABLED=false`, the bot runs on the Bot API alone — the features that depend on it (reading bios, profile photos, official reports) simply don't activate, and everything else works the same.

---

## 🚀 Getting started

Set up your credentials one of two ways:

**Option A — Interactive wizard** (recommended for first-timers). It walks you through every value and tells you where to get it. Needs nothing installed but Python 3, and it won't nag if already configured:

```bash
python3 scripts/setup.py          # creates .env by answering a few questions
# (to redo it on purpose:  python3 scripts/setup.py --force)
```

**Option B — By hand**:

```bash
cp .env.example .env
nano .env    # replace TELEGRAM_BOT_TOKEN and ADMIN_USER_ID; the rest has defaults
```

Only those two values are mandatory. The ones below are **made up**, just to show the format:

```ini
# Token @BotFather gives you when you create the bot (/newbot):
TELEGRAM_BOT_TOKEN=8123456789:AAF-ThisTokenIsFakeReplaceItWithYours00
# Your numeric Telegram user_id (@userinfobot tells you):
ADMIN_USER_ID=123456789
```

Then bring it up and verify:

```bash
docker compose up -d --build
docker compose logs -f            # "Bot @... listo. Modo=shadow"
```

The `.env.example` is commented step by step, and every variable ships a **fake example** of the format. Never commit your `.env` (it's already in `.gitignore`).

**Bot requirements on Telegram**: admin of the groups with *delete messages* and *ban users* permissions, and **Privacy Mode disabled** (BotFather → `/setprivacy` → Disable) so it sees every message.

**Where do alerts go?** Two options (`ADMIN_NOTIFY_CHAT_ID` in `.env`): your **private DM** (leave it empty) or a **moderation group** (set its `chat_id`). If you pick the DM, **open your bot and press START once** — Telegram won't let a bot message you first.

**Tip**: start in `MODE=shadow` (only logs what it *would* do, without acting), watch the log for a few days, then switch to `MODE=active`.

---

## 💬 Main commands

Only the **bot admin** (`ADMIN_USER_ID`) can run actions; **group admins** can query info; everyone else is silently ignored.

| Command | What it does |
|---|---|
| `/help` · `/comandos` | Full guide to how the bot works |
| `/ban @user reason` · `/unban @user` | Ban/unban across all your groups at once (reply, @username, or id) |
| `/warn` `/warns` `/rmwarn` `/warnlimit` | Progressive warning system |
| `/spam` · `/legal` | Teach the classifier (reply to a message) |
| `/whitelist @user` | Mark a user as immune |
| `/stats` `/recent` `/top` `/topweekly` | Metrics and rankings |
| `/config` (aliases `/ajustes` `/panel`) | Visual settings panel (verification, welcome, rules, timings…) |
| `/sync on\|off` (alias `/sincronizar`) | Sync identical settings across all groups (ON by default) |
| `/limpieza` | Hide bot commands in groups and auto-delete command messages (both ON by default) |
| `/setwelcome` `/setrules` `/welcome` `/rules` `/cleanservice` | Configure welcome, rules, and service-message cleanup |
| `/scan` (alias `/analizar`) | Analyze a message (reply to it): would it be detected? and what structure does it have? |
| `/alertas` | Enable or silence informational alerts (deletions, other admins' bans…) |
| `/notspam <id>` | Revert a false positive (undo the ban and learn) |
| `/forget <id>` | Delete a classifier sample |
| `/shadow on/off` | Test mode (log only) / active |

Group members can report with **`@admin`** (reply to a message); the bot notifies the admin and, if it acts, thanks the reporter.

---

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 360 tests
```

Every detector has **positive and negative** test cases (emphasis on anti-false-positives). Philosophy: *a false positive is worse than a false negative.*

---

## 📁 Layout

```
src/
├── main.py              # entry point, handlers, jobs
├── handlers.py          # on_message, on_chat_member, _apply_action
├── verification.py      # welcome + SOY HUMANO button + 3 tiers
├── federation.py        # cross-group federated ban
├── detectors/           # one module per detector
├── config_panel.py      # /config visual settings panel
├── settings_sync.py     # cross-group settings sync
├── group_clean.py       # hide/auto-delete commands in groups
├── trust.py             # 1-10 trust and spam levels
├── learning.py          # Naive Bayes + cosine
├── reporter.py          # official reports (Telethon)
└── db.py                # SQLite + migrations
config/
├── welcomes/            # editable greetings (generic + per group)
└── blacklist/           # editable anti-spam words/regex
tests/                   # 360 tests
```

---

## 🔒 Security

- Secrets and identifiers live only in `.env` (gitignored). `.env.example` ships empty values.
- The Telethon session (`*.session`) is never committed. Use a **secondary account**, not your personal one.
- The secondary account reports under strict criteria (rule allowlist + rate limit) to protect its Telegram reputation.

---

## 📄 License

[GPL-3.0](LICENSE) — use it, modify it, and share it freely; forks and derivatives must remain open source.

---

<div align="center">
<sub>Built with care (and a lot of coffee) to keep communities clean. · <a href="README.es.md">🇪🇸 Versión en español</a></sub>
</div>
