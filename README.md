<div align="center">

# 🛡️ CazaSpamBot

### Self-hosted, open source anti-spam and moderation bot for Telegram: synchronized cross-group bans, multilingual, active learning, and near-zero false positives

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-22.8-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.44-blueviolet)](https://docs.telethon.dev/)
[![Languages](https://img.shields.io/badge/languages-es%20%7C%20en%20%7C%20add%20yours-orange)](src/locales/README.md)
[![Tests](https://img.shields.io/badge/tests-1339%20passing-success)](#-tests)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

🌍 **English** · [**Español**](README.es.md)

*Moderate as many groups as you want, 24/7. Built so the average member never notices it exists… until a spammer walks in.*

</div>

---

## ✨ What it does

CazaSpamBot watches your Telegram groups and removes spam **before it becomes a nuisance**, with one obsession: **never ban a legitimate user**. It would rather let a borderline spam slip through than kick a real person.

- 🔗 **Synchronized bans** — a ban in one group = a ban across **all** your groups (what other bots call *federation*). No native primitive: it iterates over every chat where it's an admin.
- 🧠 **25 detectors** combined with a graduated trust system.
- 🤫 **Silent moderation** — automatic bans don't clutter the chat.
- 📚 **Active learning** — learns from your `/spam` and `/legal` calls (Naive Bayes + cosine similarity).
- 🛰️ **Official reports** to Telegram (Native Antispam) over MTProto.
- 🌍 **Multilingual**: ships in Spanish and English, and a new language is one JSON file away (no code changes).
- ⚙️ **Configure without touching code** — welcomes, blocklists, and allowed alphabets live in text files, `.env`, and visual `/config` panels.

Works with **any number of groups** (auto-discovers the ones where it's an admin, or restrict it with `MODERATED_CHAT_IDS`). Detection itself is **language-agnostic**: you decide which alphabets are normal for your community.

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
| `investment_scam` | "I gave her X and got Y back" testimonials praising a money-maker, even without an @mention |
| `contact_spam` | Shared contact card whose name is the ad itself (foreign alphabet or with links) |
| `external_reply` | Promoting an external channel via a cross-chat quote (the "quote" that leads off-site) |
| `bio_spam` | Profile bio with porn/commercial/hacking promo |
| `personal_channel_spam` | Channel linked on the profile used as a spam shopfront |
| `forward_first_msg` | Channel forward as the very first message |
| `first_msg_media` · `inline_buttons` | Suspicious photo/buttons right out of the gate |
| `story_share` | **A story from another channel** shared right after joining, or by someone who barely posts and whose source channel has a spammy name. **No Telethon needed** |
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

> **The channel linked on a profile is a separate field from the bio** (Telegram added it in 2024), and it's a blind spot: an account with an empty bio, no photo and no @username can still be pointing at an entire spam channel. `personal_channel_spam` reads that title over Telethon. **Having a personal channel is perfectly legitimate** and never triggers anything on its own: what counts is the mismatch, a name written in the alphabet your group uses next to a channel titled in another one, plus spam vocabulary in the title (editable in `config/blacklist/personal_channel_keywords.txt`) or a profile with nothing else public to look at. No single signal reaches the threshold; at least two must line up.

It also bans **spam posted "on behalf of a channel"** (`sender_chat` → `banChatSenderChat`) in comment groups when a strong rule fires. With **`/scan`** (reply to a forwarded message) you can check in advance whether the bot would detect any given message, and what structure it has.

### Trust levels (anti-false-positive)

Every user has a **trust level from 1 to 10** (rises with messages and time in the group, drops with warnings; whitelist = instant 10):

- **Level 7-10** (veterans) → practically untouchable. The bot takes no action, but **no longer stays
  silent**: if a rule fires on a veteran you get a **private** notice (never in the group) with
  **Nothing / Warn / Ban** buttons and you decide. A trusted account can be stolen, or its owner may
  have shared something without looking. Mute it from `/alerts`.
- **Level 4-6** + something suspicious → the bot **asks you privately** with ✅ Legit / ❌ Spam buttons, and **learns** from your answer.
- **Level 1-3** (newcomers) → normal moderation.

Every alert also includes a **spam level from 1 to 10** for the message, so it's understandable at a glance.

Reinforcements: **NFKC + [confusable_homoglyphs](https://github.com/vhf/confusable_homoglyphs) (UTS#39)** so decorative names (Cherokee, mathematical, mixed scripts) aren't mistaken for spam. Bypass for old accounts with a photo.

---

### 📖 Stories: the format bots cannot read

Telegram hands a shared story to bots with **only two fields**: `chat` and `id`. No text, no image,
no entities, **not even a forward marker**, so `forward_first_msg` does not fire either. To the bot
it is an empty message, and that is how crypto ads slipped through with their invite link in plain
sight for every human in the group.

The bot covers it in **two layers**, and the first one works with no secondary account:

| Layer | Needs Telethon | What it does |
|---|---|---|
| **Structure** (`story_share`) | No | Sharing ANOTHER channel's story right after joining, or coming from a spammy-named channel while barely posting |
| **Content** (`story_reader.py`) | Yes | Fetches the real text over MTProto and runs the usual detectors on it, same thresholds |

Two things worth knowing:

- **It does not expose your account.** Reading a story with `stories.getStoriesByID` **does not count
  as a view** (that is `incrementStoryViews`), so you never show up in the viewer list the poster sees.
- **Stories expire in 24h** (6 to 48 depending on the account). Plenty for live moderation, since spam
  arrives while the story is fresh. For after-the-fact analysis there is nothing left to read, and
  `/scan` says so instead of faking a verdict.

No single signal decides on its own: structure alone stays below the action threshold, and the channel
name only counts if the user also barely participates. The name list
(`config/blacklist/story_source.txt`) holds **pairs** ("crypto signals", "pump and dump"), never single
words: plain "insider" matched "Windows Insider Program".

## 🎨 Configuration without touching code

Everything is adjustable **from Telegram itself** with visual button panels, or from files/`.env` — whichever you prefer.

### Visual settings panel (`/config`)

The **recommended** way to configure each group without memorizing subcommands. Type `/config` (aliases `/ajustes`, `/panel`) in the group, or **in the bot's DM** to pick a group with buttons. A panel appears and updates instantly on tap:

- 🔗 **Sync all groups** on/off · 🛡️ **Verification** · 👁️ **Review suspicious privately** · 🔔 **Reminders**
- 🚪 **On failed verification**: Kick / Mute · ⏱️ **Timings** (submenu with presets)
- 👋 **Welcome** on/off · ✏️ **Edit welcome** · 📜 **Edit rules** (on edit you pick **All groups** or **just one**, with an example to type the text directly)
- 🧹 **Clean service messages** on/off · 🔔 **Informational alerts**
- 🔤 **Allowed alphabets** (submenu, see below)
- 🛡️ **Work/money strictness** (submenu, see below) · 🚫 **Blocked words** (see below)

> ### ⚠️ If your community doesn't write in the Latin alphabet, read this first
>
> Out of the box the bot treats only the **Latin alphabet** as normal, and flags a first message written in anything else. That's right for a Spanish or English group, but it means **in an Arabic, Russian, Greek or Hindi group the bot would flag your own members**.
>
> Two taps to fix: `/config` ▸ 🔤 **Allowed alphabets**, and switch yours on. That screen shows you **which alphabets are actually being written in your group** and warns which ones would cause false positives, so you don't have to guess. You can also set it once for every install with `ALLOWED_SCRIPTS` in `.env`.

**Tune how strict it is with work and money messages:** the 🛡️ **Work/money strictness** button controls the two detectors that flag job ads and investment testimonials (the "I gave her X and got Y back" scam), especially in a first message. Three modes: **Normal** (default, catches clear and borderline cases), **Soft** (only very obvious cases; borderline work/money messages get through), and **Off** (those two detectors stand down, the rest keep working). Handy if your community legitimately talks money a lot and you want fewer borderline bans.

**Block words without server access:** the 🚫 **Blocked words** button adds and removes terms from the blocklists straight from Telegram. Whatever you type is treated as **literal text**, never as a regex, so a stray `.*` can't turn into a wildcard that bans your neighbours. Before saving, the bot tells you **how many recent real messages in your group that term would have matched**, with examples: the difference between adding "offer" blindly and seeing it would sweep up 14 normal conversations. Your terms are stored separately, in `config/blacklist/custom/`, so **they survive an update**.

**Clean mode by default:** verification and welcome start **OFF** (the group stays silent), while **private review of suspicious profiles is ON** — when a clearly dubious profile joins, you get a **private** alert (in your DM or the `ADMIN_NOTIFY_CHAT_ID` chat) with **✅ Allow** / **🔨 Ban** buttons; the user enters allowed by default. That alert also carries a **⚙️ gear** that expands quick toggles (verification, alerts, reminders, timings) editing the notification in place. Message moderation stays fully active regardless.

**Welcome is independent of verification:** you can greet newcomers *without* the SOY HUMANO gate, run verification only, or both.

### Sync settings across groups (`/sync`)

**On by default.** When sync is ON, any setting change applies **to all groups at once** (they stay identical), the welcome text is shared (use `{chat}` for the group name and `{name}` for the user), and `/config` doesn't ask which group. Turn it **OFF** to configure each group separately.

### Bot language (`/idioma`)

Every user-facing string lives in `src/locales/<code>.json`, one flat JSON per language. **Spanish and English ship in the box**, and adding a third takes no code at all: drop a `fr.json` next to them, restart, and the bot offers it. Anything you leave untranslated falls back to Spanish key by key, so a language at 40% is already usable, and a malformed file is skipped with a log warning instead of taking the bot down.

Switch with `/idioma en` (alias `/language`, admin only, persists across restarts). On a fresh install the language is picked up from the environment (`BOT_LANG`, or the usual `LC_ALL` / `LC_MESSAGES` / `LANG` / `LANGUAGE`), defaulting to Spanish.

> 📖 **Translators:** [`src/locales/README.md`](src/locales/README.md) has the full guide: the rules that matter (never touch keys or `{placeholders}`, always close HTML tags) and how to check your work with `pytest tests/test_locales.py`, which validates JSON, placeholders, and balanced HTML for every language.

### Keep groups clean (`/limpieza`)

Hide the bot's commands in groups (they don't show up when typing `/`) and auto-delete command messages written in the chat, so nothing clutters the group and users don't tap them. Both **on by default**.

### Human verification (`/verificacion`)

Per group, from Telegram itself (bot admin only). Run `/verificacion` with no arguments to see the current state and the options:

| Subcommand | What it does |
|---|---|
| `/verificacion on\|off` | Turns verification (SOY HUMANO button + mute on join) **and** the welcome message on or off at once. **OFF by default**, so newcomers walk straight in. |
| `/verificacion revisar on\|off` | **Review mode** (**ON by default**). Instead of gating the group, a dubious profile triggers a **private** alert (your DM or the configured chat) with **✅ Allow** / **🔨 Ban** buttons. The user is **allowed by default**: do nothing and they stay. It only fires on real signals (name in another alphabet, no photo, brand-new account), not on every user without a @username. The alert carries a **⚙️ Group settings** button that expands quick toggles in place. |
| `/verificacion avisos on\|off` | Whether to remind normal users before kicking them. |
| `/verificacion accion kick\|mute` | What happens to a normal user who never verifies: **kick**, or **mute** (stays muted indefinitely, can verify whenever they want). |
| `/verificacion tiempos <susp_min> <reminder_h> <kick_h>` | Timings: suspicious profiles are kicked after `susp_min` minutes; normal users get a reminder at `reminder_h` hours and are kicked `kick_h` hours later. E.g. `/verificacion tiempos 30 3 6`. |

> Users with a **suspicious profile** are always kicked once their timer runs out (that's the safety layer); `avisos` and `accion` apply to **normal** users. Message moderation is independent and stays active even with verification off.

### Files & environment

| What | Where | How |
|---|---|---|
| Welcome greetings | `config/welcomes/` | One phrase per line, `{name}` for the name. `generic.txt` for all groups, `<chat_id>.txt` for group-specific lines. Turn them off with `FRIENDLY_WELCOMES_ENABLED=false`. |
| Bot language | `.env` → `BOT_LANG` | `es`, `en`, or any language file you add. Empty = detect from the system. |
| Blocklist words/phrases | `config/blacklist/` | One pattern per line (word or regex). Delete a file and defaults kick in. |
| Blocklist languages | `.env` → `BLACKLIST_LANGS` | CSV of language codes. By default the bot loads the generic lists plus `config/blacklist/<lang>/` for its **active language and English** (spam's lingua franca on Telegram). Set it (e.g. `es,en,pt`) to replace that choice in a multilingual community. |
| Allowed alphabets | `.env` → `ALLOWED_SCRIPTS` | CSV: `latin`, `cyrillic`, `arabic`, `han`, … per your community's language. |
| CAS strictness | `.env` → `CAS_AUTOBAN_MIN` | `2` = ban only if confirmed in 2+ groups (recommended); `1` = ban on any signal. |
| Blocked shorteners | `.env` → `URL_BLOCKLIST` | CSV of domains. |
| Thresholds & actions | `.env` | Ban/kick/mute scores, first-suspicious-message action, etc. |

Each folder has its own `README.md` explaining the format.

---

## 🧰 Stack

| Component | Technology |
|---|---|
| Bot API (async polling) | `python-telegram-bot[ext]` 22.8 |
| MTProto (bio, photos, personal channel, official reports) | `Telethon` 1.44 |
| Database | SQLite (WAL) |
| Classifier | Naive Bayes + cosine (stdlib, no sklearn) |
| Homoglyphs | `confusable-homoglyphs` (UTS#39) |
| Deployment | Docker Compose |

> **Telethon is optional** (but recommended): it needs a secondary user account. Without it, or with `TELETHON_ENABLED=false`, the bot runs on the Bot API alone — the features that depend on it (reading bios, profile photos, **the channel linked on a profile**, official reports) simply don't activate, and everything else works the same.

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

**No folders to create by hand.** `data/` (database, session, heartbeat) is created on first run, and `config/` (welcomes and blocklists) already ships with sensible defaults. `data/` is the only writable volume.

*(Optional, only if you enable Telethon)* the session is generated **inside the container**, once:

```bash
# 1) Telegram sends a code to the secondary account's app:
docker compose exec antispam-bot python -m scripts.telethon_login request
# 2) Confirm it with the code you received (append your 2FA password if you have one):
docker compose exec antispam-bot python -m scripts.telethon_login confirm 12345
```

**Bot requirements on Telegram**: admin of the groups with *delete messages* and *ban users* permissions, and **Privacy Mode disabled** (BotFather → `/setprivacy` → Disable) so it sees every message.

**Where do alerts go?** Two options (`ADMIN_NOTIFY_CHAT_ID` in `.env`): your **private DM** (leave it empty) or a **moderation group** (set its `chat_id`). If you pick the DM, **open your bot and press START once** — Telegram won't let a bot message you first.

**Tip**: start in `MODE=shadow` (only logs what it *would* do, without acting), watch the log for a few days, then switch to `MODE=active`.

---

## 🔄 Updating an existing install

```bash
git pull
docker compose restart
```

That's it. `docker-compose.yml` mounts `./src`, `./config` and `./data` as volumes, so new code, language packs and blocklists are picked up **without rebuilding the image**. `docker compose pull` does nothing here: the image is built locally (`build:`), never downloaded. You only need `docker compose up -d --build` when `requirements.txt` or the `Dockerfile` change.

**Nothing you configured is lost.** Your `.env`, the database (`data/`: chosen language, each group's settings, bans, learned samples) and your own welcomes all live outside version control, and any new database columns are created on startup.

Two things worth knowing before you pull:

- If you hand-edited `src/locales/es.py` or `en.py`, those edits are gone: those files no longer exist. Languages are now `es.json` / `en.json`.
- If you hand-edited a versioned blocklist such as `config/blacklist/classifier_excluded_tokens.txt`, git may report a conflict. Resolve it with `git stash` → `git pull` → `git stash pop`. Terms you added from the `/config` panel are safe: they live in `config/blacklist/custom/`, outside the repo.

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
| `/idioma <code>` (alias `/language`) | Bot language (`es`, `en`, or any language file you drop in). Persists. |
| `/verificacion` | Human verification per group (see above) |
| `/limpieza` | Hide bot commands in groups and auto-delete command messages (both ON by default) |
| `/setwelcome` `/setrules` `/welcome` `/rules` `/cleanservice` | Configure welcome, rules, and service-message cleanup |
| `/scan` (alias `/analizar`) | Analyze a message (reply to it): would it be detected? and what structure does it have? |
| `/alertas` | Enable or silence informational alerts (deletions, other admins' bans…) |
| `/notspam <id>` | Revert a false positive (undo the ban and learn) |
| `/forget <id>` | Delete a classifier sample |
| `/shadow on/off` | Test mode (log only) / active |

> **Heads-up about `/ban` and the reason.** When replying to a message, the bot **deletes that message
> too**. And the **reason acts as consent**: with no reason the ban stays silent, like the automatic
> ones; if you write one, the bot posts it in the group and **that notice stays permanently**, because
> a hand-written reason is a moderation record, not a joke that expires. To auto-delete it, set the
> seconds in `BAN_NOTICE_DELETE_AFTER_S` (default `0` = permanent).

**English aliases:** the commands with Spanish names also answer to `/verification`, `/language`, `/alerts`, `/cleanup` and `/commands`. Telegram's `/` menu shows whichever name matches the active language, and the Spanish names keep working either way, so nothing breaks if you switch languages mid-flight.

Group members can report with **`@admin`** (reply to a message); the bot notifies the admin and, if it acts, thanks the reporter.

---

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 1339 tests
```

Every detector has **positive and negative** test cases (emphasis on anti-false-positives). Philosophy: *a false positive is worse than a false negative.*

Language packs get their own safety net (`tests/test_locales.py`): valid JSON, placeholders matching the Spanish reference, balanced HTML, and full parity between the two official languages. Incomplete coverage doesn't fail the suite, it just reports the percentage.

---

## 📁 Layout

```
src/
├── main.py              # entry point, handlers, jobs
├── handlers.py          # on_message, on_chat_member, _apply_action
├── verification.py      # welcome + SOY HUMANO button + 3 tiers
├── federation.py        # cross-group federated ban
├── detectors/           # one module per detector
├── locales/             # language packs (es.json, en.json, + yours)
├── i18n.py              # t() lookup with per-key fallback
├── config_panel.py      # /config visual settings panel
├── settings_sync.py     # cross-group settings sync
├── group_clean.py       # hide/auto-delete commands in groups
├── wordlists.py         # loads the editable blocklists
├── trust.py             # 1-10 trust and spam levels
├── ban_announce.py      # merges burst quips into one message
├── learning.py          # Naive Bayes + cosine
├── reporter.py          # official reports (Telethon)
└── db.py                # SQLite + migrations
config/
├── welcomes/            # editable greetings (generic + per group)
└── blacklist/           # editable anti-spam words/regex
docs/                    # ARCHITECTURE, ROADMAP, ...
tests/                   # 1339 tests
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
