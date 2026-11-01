# Contributing to CazaSpamBot

Thanks for wanting to help. You don't need to write code: telling us about a mistake the bot made is just as useful.

## Questions and ideas

Ask in [Discussions](https://github.com/yonaesp/CazaSpamBot-Telegram/discussions), in English or Spanish. Issues are for things that are wrong.

## The bot banned someone who wasn't a spammer

This is the most valuable report, because a false positive is worse than a missed spam. Open an issue with:

- the rule the bot named in its private notice (for example `investment_scam`) and the version (`./update.sh --check` shows it);
- the message that triggered it, with names, @usernames, phone numbers and links removed;
- whether the person had written in the group before.

Never post someone's id, @username or profile in an issue: describe them instead ("a member with two years in the group").

## Spam got through

Same as above: the message without personal data and what gave it away to you. If several accounts are posting the same thing, say so; that's often the clue.

## Translations

Every text lives in `src/locales/<code>.json`. Copy `en.json`, translate the values and open a pull request: a file that's 40% done already works, and whatever is missing falls back to Spanish. The guide is in [`src/locales/README.md`](src/locales/README.md).

## Code

```bash
git clone https://github.com/yonaesp/CazaSpamBot-Telegram.git
cd CazaSpamBot-Telegram
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src/ tests/
```

A few rules the project keeps:

- **False positives first.** Every change to a detector comes with tests for what it must catch and, above all, what it must not. If in doubt, leave the pattern out.
- **No single weak signal bans anyone.** New signals add points; they don't decide alone.
- **Every visible text in both `es.json` and `en.json`**, with balanced HTML. A test checks it.
- **A new detector gets a scene in `scripts/simular.py`**: a whole conversation, with spam and with a normal person.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`…), in English or Spanish.

Word lists live in `config/blacklist/`, one Python regex per line; [`config/blacklist/README.md`](config/blacklist/README.md) explains the layers and how to test a pattern before adding it.

By contributing, you agree that your work is published under the [GPL-3.0](LICENSE) license, like the rest of the project.
