<div align="center">

# 🛡️ CazaSpamBot: Telegram anti-spam bot

### Checks who is posting, not just what they post.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/PTB-22.8-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-1.44-blueviolet)](https://docs.telethon.dev/)
[![Languages](https://img.shields.io/badge/languages-es%20%7C%20en%20%7C%20add%20yours-orange)](src/locales/README.md)
[![Tests](https://img.shields.io/badge/tests-1710%20passing-success)](#tests)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

🌍 **English** · [**Español**](README.es.md)

**[What makes it different](#different)** · **[Install in 5 minutes](#install)** · **[FAQ](#faq)**

</div>

---

**CazaSpamBot** is an anti-spam bot for people who run Telegram groups: free, open source, and you run it on your own server. A regular bot only sees the message. CazaSpamBot can also look at the sender's profile, the text inside images and the content of shared stories, so it catches spam that looks clean when all you read is the message.

- **Sees what a regular bot can't.** With an optional secondary Telegram account that you authorize, it reads the bio, personal channel, profile photos and stories of whoever is posting.
- **Reads the text in images.** It extracts the text from posters and screenshots with OCR, on your server and without a GPU, and judges it as if it had been typed.
- **Learns from your group.** From your decisions and, on its own, from safe bans and everyday conversation. All local, no external AI.
- **Careful and quiet.** Doubtful cases reach you in private, with buttons, instead of ending in a ban, and it doesn't flood the group with notices. You can start in test mode, banning no one.
- **Easy to get running.** You install it by copying and pasting a handful of commands, and manage it from Telegram with the `/config` panel.

> [!NOTE]
> **In production.** Reference install: 4 groups, May to October 2026.
> - It removed **over 1,300 suspicious or spam accounts** on its own, **nearly 9 in 10 before they wrote a single word**.
> - Bans the admins had to make by hand dropped from **41 in May to 4 or 5 a month**: every spam that slips through teaches it to catch the next one.
> - Spam keeps coming, but it's stopped at the door and the group barely notices.

---

<a id="different"></a>

## 👁️ Why it catches more spam than a regular bot

A Telegram bot only sees **the message**. Most anti-spam bots, including the most popular ones, stop there, because that's all the Bot API gives them.

CazaSpamBot can also use **a regular Telegram account that you authorize**, just like logging in on another device (over **MTProto**, the protocol the official apps use). With it, the bot also sees **who wrote the message**:

| What it checks | A regular bot | CazaSpamBot with a secondary account |
|:---|:---:|:---:|
| The message text | ✅ | ✅ |
| The profile **bio** | ❌ | ✅ |
| The profile's **personal channel** and what it posts | ❌ | ✅ |
| **When** each profile photo was uploaded (accounts built in an afternoon) | ❌ | ✅ |
| What a **story** shared in the group says | ❌ arrives empty | ✅ |
| **Reporting** spam to Telegram officially | ❌ | ✅ |

On the reference install, **165 spammers were given away by their profile alone** (bio, channel or photos): no other rule fired on them.

The account **doesn't give itself away**: reading a story or a channel doesn't count as a view and never joins anything. It's optional: without it, the bot works the same with everything else.

---

## ✨ What makes it different

🖼️ **Reads the text inside images (OCR).** A poster saying "Windows, Office, Photoshop, AutoCAD… message me privately" carries not one typed letter, so to a regular bot it's an empty message. CazaSpamBot reads it with Tesseract and judges it as if it were text. Same with a screenshot of a fake Elon Musk crypto giveaway. No GPU: 0.6 seconds per image.

🎭 **Sees through the disguise.** The trick of the moment is joining with a normal name and switching to the real one right before posting. The bot watches every newcomer's name **for 7 days** and checks their whole profile again on their first message.

💸 **Understands the scam, not just the words.** It recognizes how scams are built: the "I gave her 500 and got 5,000 back" testimonial, the fake customer replying to the bait with no figures or links ("Saw your post and honestly thought it was a scam, but the money actually came through", a real case), the "extra money, DM me", and the crypto giveaway that sends you to another site to redeem a code.

🧠 **Learns on its own, with no external AI.** It learns from your `/spam` and `/legal`, and, without you lifting a finger, from safe bans and from how your veterans talk. Everything stays on your server.

📖 **Reads shared stories.** Telegram hands them to bots with no text and no link, and that's how ads slipped through. The bot fetches the real content and analyzes it.

🧹 **Cleans up after the spammer.** Banning on Telegram doesn't delete their messages. CazaSpamBot deletes the recent ones in every group where it bans them, along with its own notices about them.

🔗 **Banned in one, banned in all your groups.** It also checks the worldwide spammer lists [CAS](https://cas.chat) and lols.bot, and can report clear spam to Telegram if you want.

🤝 **Respects normal people.** Every member has a trust level from 1 to 10 based on their history in the group. Doubtful cases reach you **in private, with buttons** (✅ Legit / ❌ Spam), and you can start in **test mode**, banning no one, to see what it would do.

🌍 **For any community.** Ships in Spanish and English, and another language is one JSON file. You choose which alphabets are normal in your group.

<details>
<summary><b>🔍 See the 25 detectors</b></summary>

<br>

🔑 = needs the secondary account.

| Detector | What it catches |
|---|---|
| `unicode_script` | Text in an alphabet your group doesn't use (`/config` ▸ Allowed alphabets) |
| `external_mention` | Mentions and links to other groups or channels |
| `url_blocklist` | Link shorteners typical of spam |
| `tg_deeplink` | Phishing `tg://` links |
| `link_target` | The link leads to a chat that advertises itself as spam |
| `commercial_ad` | Ads: salaries, "work from home", pirated software, "DM me" |
| `investment_scam` | "I gave X and got Y back", the fake happy customer, and fake crypto giveaways |
| `offplatform_contact` | "Here's my number on another app, write me there" |
| `contact_spam` | A contact card whose name is the ad |
| `external_reply` | Promoting someone else's channel by quoting one of its messages |
| `cross_post` | The same message at once in several of your groups |
| `forward_first_msg` | First message forwarded from a channel or a bot |
| `first_msg_media` | First message that's only a photo, video or sticker |
| `inline_buttons` | A person (not a bot) sending buttons |
| `emoji_only` | First message that's a string of emojis |
| `jfm_delta` | Posting a few seconds after joining |
| `premium_new_link` | Brand-new Premium account that joins with a link |
| `dormant_bot_mention` | Account dormant for over a year that comes back citing a bot (hijacked) |
| `reaction_farming` | Accounts that only hand out reactions and never write |
| `story_share` | Sharing another channel's story right after joining (no secondary account needed) |
| `bio_spam` 🔑 | Bio promoting porn, commercial or hacking services |
| `personal_channel` 🔑 | The profile's channel used as a spam shopfront |
| `photos_batch` 🔑 | Several profile photos uploaded within minutes: a built account |
| `cas` · `lols_bot` | Spammers flagged on the worldwide lists |

Plus: obvious spam profiles (a full name in another alphabet, letters disguised with homoglyphs), what it learned from your `/spam`, the text inside images and stories, and per-user antiflood.

</details>

---

<a id="install"></a>

## 🚀 Install in 5 minutes

You need a Linux machine that stays on (a cheap VPS, a mini PC or a home server). The bot uses less than 100 MB of RAM.

### Step 0 · Get Telegram ready (2 minutes)

1. Open [@BotFather](https://t.me/BotFather), send `/newbot` and give it a name. You'll get the **token**: keep it.
2. In @BotFather, `/setprivacy` → your bot → **Disable**, so it sees every message and not just commands.
3. Message [@userinfobot](https://t.me/userinfobot): it tells you your **user_id** (a number).
4. *(Recommended)* For the secondary account: with **another** Telegram number, log in to [my.telegram.org](https://my.telegram.org) → **API development tools**, create an app, and note down the **api_id** and **api_hash**.

### Step 1 · Install Docker and get the bot

```bash
sudo apt update && sudo apt install -y git curl python3
curl -fsSL https://get.docker.com | sudo sh
git clone https://github.com/yonaesp/CazaSpamBot-Telegram.git
cd CazaSpamBot-Telegram
```

### Step 2 · Configure it

It asks a few questions: paste the token, your user_id and, if you want, the secondary account's details. For everything else, press Enter.

```bash
python3 scripts/setup.py
```

### Step 3 · Start it

```bash
sudo install -d -o 10112 -g 10112 data config/blacklist/custom
sudo docker compose up -d --build
sudo docker compose logs -f
```

Once you see `Bot @YourBot … listo`, it's alive (Ctrl+C leaves the log; the bot keeps running).

### Step 4 · Add it to your groups

1. In each group: *Administrators* → *Add administrator* → your bot, with **Delete messages** and **Ban users**.
2. Open your bot in Telegram and press **Start**. Without it, Telegram won't let the bot send you alerts.
3. Once it's in all your groups, close the door so nobody adds it to theirs: @BotFather → `/mybots` → your bot → **Bot Settings** → **Allow Groups?** → **Turn groups off**.

### Step 5 · Connect the secondary account *(if you set one up)*

Make it an administrator of your groups too, with the same permissions. Then:

```bash
sudo docker compose exec antispam-bot python -m scripts.telethon_login request
```

Telegram sends a code to that account. Put it in place of `12345` (if it has two-step verification, add the password after it):

```bash
sudo docker compose exec antispam-bot python -m scripts.telethon_login confirm 12345
sudo docker compose restart
```

The log will show `Telethon=conectado`.

### Step 6 · From test to live

It starts in **test mode**: it watches everything and logs what it would do, banning no one. Once you've checked the log for a few days and trust it:

```bash
sed -i 's/^MODE=.*/MODE=active/' .env && sudo docker compose up -d
```

> [!NOTE]
> Official reports to Telegram ship **off**. Turn them on with `REPORT_BEFORE_BAN=true` in `.env` once you trust the detectors: reporting legitimate people can get the secondary account limited.

<details>
<summary><b>Day to day: update, check the log, stop</b></summary>

<br>

| I want to… | Command |
|---|---|
| See what it's doing | `sudo docker compose logs -f` |
| Update to the latest version | `git pull && sudo docker compose up -d --build` |
| Apply a change to `.env` | `sudo docker compose up -d` (`restart` doesn't reload `.env`) |
| Restart it | `sudo docker compose restart` |
| Stop it | `sudo docker compose down` (everything in `data/` is kept) |

**Updating loses nothing**: your `.env`, the database (`data/`) and the words you added from Telegram (`config/blacklist/custom/`) live outside git, and anything new in the database is created on startup. If you hand-edited a versioned list in `config/blacklist/` and git reports a conflict: `git stash && git pull && git stash pop`.

**Back up** the `data/` folder and your `.env`: that's all you need to bring it back on another machine. The bot already keeps a daily database backup in `data/backups/` (7 days).

If your user is in the `docker` group, you can drop the `sudo` from every command.

</details>

<details>
<summary><b>With Podman instead of Docker</b></summary>

<br>

Same steps, replacing `docker compose` with `podman compose`:

```bash
sudo apt install -y podman podman-compose     # Fedora: sudo dnf install -y podman podman-compose
mkdir -p data config/blacklist/custom
podman unshare chown -R 10112:10112 data config/blacklist/custom
podman compose up -d --build
```

- **Folders go through `podman unshare`**: rootless Podman maps the container's uid 10112 to a different one on your machine, so step 3's `sudo install` doesn't apply here.
- **To start again after a server reboot**, once: `systemctl --user enable --now podman-restart.service` and `loginctl enable-linger $USER`.
- **Fedora, RHEL and derivatives (SELinux)**: if it can't read `config/` or write to `data/`, add `Z` to each volume in `docker-compose.yml`, e.g. `./data:/app/data:Z` and `./config:/app/config:ro,Z`.

</details>

<details>
<summary><b>Configure by hand, without the wizard</b></summary>

<br>

```bash
cp .env.example .env && chmod 600 .env
nano .env
```

Only two values are mandatory. The ones below are **made up**, just to show the format:

```ini
TELEGRAM_BOT_TOKEN=8123456789:AAF-ThisTokenIsFakeReplaceItWithYours00
ADMIN_USER_ID=123456789
```

For the secondary account, `TG_API_ID`, `TG_API_HASH` and `TG_PHONE` (with country code, `+34600111222`). `.env.example` explains every variable with a sample. Never commit your `.env` (it's already in `.gitignore`).

</details>

<details>
<summary><b>What <code>docker-compose.yml</code> mounts</b></summary>

<br>

You don't need to touch it. In case you want to know what it does:

| Line | What it's for |
|---|---|
| `build: .` | The image is built on your machine from the `Dockerfile`: nothing is pulled from a registry |
| `user: "10112:10112"` | Runs without root, as a uid nobody owns on your machine. Different uid: `APP_UID`/`APP_GID` in `.env` |
| `env_file: .env` | Your configuration |
| `./data:/app/data` | Database, secondary account session and daily backups |
| `./config:/app/config:ro` | Blocklists and welcomes, read-only |
| `./config/blacklist/custom` | The only part of `config/` it writes to: the words you add from Telegram |
| `./src` and `./scripts` (`:ro`) | The code, mounted so an update applies without rebuilding |
| `restart: unless-stopped` | Starts again on its own after a crash or a server reboot |
| `healthcheck` | Marks it `unhealthy` if it stops showing signs of life for 5 minutes |
| `logging` | The log rotates over 3 files of 10 MB, so it never fills the disk |

</details>

---

## ⚙️ Run it from Telegram

Type **`/config`** in the group or in the bot's private chat and you get a panel with buttons. No commands to remember:

- 🛡️ **Verification** with an "I'm human" button, 👋 **welcome** and 📜 **rules**, each one separately
- 👁️ **Private alerts about suspicious profiles**, with three strictness levels
- 🔤 **Allowed alphabets**: shows which ones are actually written in your group
- 🛡️ **Work and money strictness**: normal, soft or off
- 🚫 **Blocked words**: before saving, it tells you how many real messages from your group would have matched
- ⚠️ **Warns**: limit, penalty, and who can give them
- 🔗 **Sync**: one change applies to all your groups (on by default)

By default the group stays **clean and quiet**: no welcomes, no verification, and moderation working all the same.

> [!WARNING]
> **If your community doesn't write in the Latin alphabet, adjust this first.** Out of the box the bot only treats the Latin alphabet as normal, so in an Arabic, Russian, Greek or Hindi group it would flag your own members. Two taps fix it: `/config` ▸ 🔤 **Allowed alphabets**, and switch yours on.

<details>
<summary><b>🎛️ <code>.env</code> settings and editable files</b></summary>

<br>

| What | Where |
|---|---|
| Groups to moderate | `MODERATED_CHAT_IDS` (empty = every group where it's an admin allowed to ban) |
| Where your alerts go | `ADMIN_NOTIFY_CHAT_ID` (empty = your private chat; or a moderation group's `chat_id`) |
| CAS strictness | `CAS_AUTOBAN_MIN`: `2` bans when confirmed in 2+ groups and asks you about the rest (recommended); `1`, on any signal |
| Word list languages | `BLACKLIST_LANGS` (defaults to the bot's language + English, spam's lingua franca) |
| Languages the OCR reads | `OCR_LANGS` (defaults to the bot's languages) |
| Blocked shorteners | `URL_BLOCKLIST` |
| Ban, kick and mute thresholds | The `*_SCORE` variables in `.env.example` |
| Word and phrase lists | `config/blacklist/` (one pattern per line; [guide](config/blacklist/README.md)) |
| Group-flavoured welcomes | `config/welcomes/` ([guide](config/welcomes/README.md)) |

Whatever you change from `/config` is stored in the database and survives updates.

</details>

<details>
<summary><b>💬 All commands</b></summary>

<br>

Only the **bot admin** (`ADMIN_USER_ID`) can change things. **Each group's admins** can look things up and give warns. Everyone else is ignored.

| Command | What it does |
|---|---|
| `/config` (`/ajustes`, `/panel`) | Settings panel with buttons |
| `/ban @user reason` · `/unban @user` | Ban or unban across all your groups at once (reply, @username or id) |
| `/warn` `/warns` `/rmwarn` `/resetwarns` `/warnlimit` `/warnaction` | Progressive warnings |
| `/spam` · `/legal` | Teach the bot (replying to a message) |
| `/scan` (`/analizar`) | Would it catch this message? (replying to it) |
| `/notspam <id>` · `/forget <id>` | Undo a false positive · delete a learned sample |
| `/whitelist @user` | Mark someone as untouchable |
| `/stats` `/recent` `/top` `/topweekly` | Stats and rankings |
| `/verificacion` (`/verification`) | Human verification per group |
| `/setwelcome` `/setrules` `/welcome` `/rules` | Welcome and rules |
| `/cleanservice` · `/limpieza` (`/cleanup`) | Delete service messages · hide and delete commands in the group |
| `/alertas` (`/alerts`) | Which alerts reach you in private |
| `/sync on\|off` | Same settings in every group |
| `/idioma <code>` (`/language`) | Bot language |
| `/shadow on\|off` | Test mode |
| `/help` · `/comandos` (`/commands`) | The full guide, inside Telegram |

With **`/ban` and a reason**, the bot posts the reason in the group and that notice stays; with no reason, the ban is silent. Members can alert you by replying to a message with **`@admin`**.

</details>

---

<a id="faq"></a>

## ❓ FAQ

**Can I just add @CazaSpamBot to my group?**
No: that copy is private and only moderates its owner's groups. The code is free, so you run your own bot with your own token, and it's fully yours. It takes [5 minutes](#install).

**What's this secondary account? Is it safe?**
It's a regular Telegram account, with another number, that the bot uses the way you would from another device. **Don't use your personal account**: if Telegram ever limited the secondary one for automated activity, yours would be unaffected. The session lives in `data/telethon.session` and must be treated like a password. It's optional.

**Will it ban legitimate members?**
That's what it tries hardest to avoid. Members with history in the group are protected by their trust level, doubtful cases reach you with buttons instead of ending in a ban, and you can start in test mode to see what it would do before letting it act.

**How is it different from a captcha bot?**
A captcha only stops dumb bots at the door. Here verification is optional and ships off, because today's spam gets past it and then posts at leisure. What matters is looking at who they are and what they post, days later too.

**Does my data leave my server?**
No. Learning and OCR run locally. Outside Telegram, the only things that go out are lookups to the CAS and lols.bot lists (with the user's id) and, if you turn them on, reports to Telegram.

**Is it free? Does it work in other languages?**
Yes, free and open source (GPL-3.0). Detection doesn't depend on the group's language, the interface ships in Spanish and English, and adding a language is one JSON file ([translator guide](src/locales/README.md)).

**Where can I get help?**
Open an [issue on GitHub](https://github.com/yonaesp/CazaSpamBot-Telegram/issues). Support is free.

---

## 🔒 Security

- Runs **without root**, as a uid nobody owns on your machine, with the code and configuration **read-only**.
- Secrets live only in `.env` (permissions `600`, outside git). The secondary account's session is never committed.
- The secondary account reports under strict criteria (specific rules, high score and an hourly limit) to protect its reputation on Telegram.

<a id="tests"></a>

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 1710 tests
```

Every detector has tests for what it must catch **and what it must not**, built from real cases. A false positive is worse than a false negative.

<details>
<summary><b>📁 Code layout and docs</b></summary>

<br>

```
src/
├── main.py              # startup, handlers and scheduled jobs
├── handlers.py          # every message and every join
├── detectors/           # one module per detector
├── verification.py      # "I'm human" verification and obvious profiles
├── federation.py        # ban in all your groups and message cleanup
├── learning.py          # Naive Bayes + cosine
├── autoaprendizaje.py   # what it learns on its own
├── ocr.py               # text inside images
├── story_reader.py      # story content (MTProto)
├── channel_reader.py    # profile's personal channel (MTProto)
├── reporter.py          # official reports to Telegram (MTProto)
├── config_panel.py      # /config panel
├── locales/             # languages (es.json, en.json and yours)
└── db.py                # SQLite + migrations
config/
├── welcomes/            # editable welcomes
└── blacklist/           # editable word lists
```

In depth: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/LEARNING.md`](docs/LEARNING.md), [`config/blacklist/README.md`](config/blacklist/README.md) and [`CHANGELOG.md`](CHANGELOG.md).

</details>

## 📄 License

[GPL-3.0](LICENSE): use it, modify it and share it freely; forks and derivatives must stay open source.

---

<div align="center">
<sub>Built with care (and a lot of coffee) to keep communities clean. · <a href="README.es.md">🇪🇸 Versión en español</a></sub>
</div>
