# Security

## Reporting a vulnerability

Please don't open a public issue. Report it privately from the repository's **Security** tab → **Report a vulnerability**. Only the maintainer sees it, and you'll get a reply there.

Include what an attacker could do, the steps to reproduce it and the version you tested (`./update.sh --check` shows it). If you leave out tokens, ids and real usernames, even better.

## Supported versions

| Version | Security fixes |
|---|---|
| Latest release | ✅ |
| `main` branch | ✅ |
| Older releases | ❌ Update with `./update.sh` |

The published image is rebuilt every week with the base system's security fixes.

## What's in scope

The bot's code, `update.sh`, the `Dockerfile` and the compose files. Vulnerabilities in Telegram, python-telegram-bot or Telethon belong to their own projects, but tell us if the bot uses them in an unsafe way.

## How the bot protects you

- It runs without root, as a uid nobody owns on your machine.
- Secrets live only in `.env` (permissions `600`, outside git), and the secondary account's session is never committed.
- Nothing about your groups leaves your server except the spammer list lookups (CAS and lols.bot), the reports to Telegram if you turn them on, an anonymous daily check for new versions on GitHub (`UPDATE_CHECK=false` turns it off) and, only if you set it up, what goes to the optional AI second opinion (`LLM_VETO`, off by default).
