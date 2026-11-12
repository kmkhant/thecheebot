# Contributing to cheebot

Thanks for helping. cheebot is a free, ad-free map of public toilets that runs on a single Python
process and a SQLite file — the kind of project where one person can make a real difference. Bug
reports, translations, new cities and code are all welcome.

This document covers how to set up, how the code is arranged, and the few invariants a change must
not break. For what the bot does and how it is deployed, see the [README](README.md).

## Ways to help

| Contribution              | Where                                                                 |
| ------------------------- | --------------------------------------------------------------------- |
| Report a bug              | Open an issue with what you sent, what happened, and what you expected |
| Suggest a feature         | Open an issue first for anything larger than a small fix              |
| Add a city                | One line in `cheebot/seeds.py` — see [Add a city](#add-a-city)         |
| Improve a translation     | `cheebot/i18n.py` — see [Add a language](#add-a-language)              |
| Improve the docs          | `README.md`, `CONTRIBUTING.md`                                         |
| Write code                | Pick up an issue, or propose one                                      |

## Ground rules

- **Be decent.** Assume good faith, keep criticism about the code.
- **Privacy is a feature, not a footnote.** The bot must never store a raw Telegram user id or the
  coordinates a user sends. Ids exist only as `sha256(salt + id)`; locations are used for one query
  and discarded. A change that logs, caches or persists either one will be rejected.
- **Attribution stays.** Map data comes from OpenStreetMap under the ODbL. Keep the attribution in
  `/about` and the README.
- **Everything merged is MIT.** By contributing you agree your work is released under the
  [LICENSE](LICENSE) in this repository.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Git. uv installs the interpreter pinned in
`.python-version` (3.12); the package itself supports 3.11+.

```sh
git clone https://github.com/kmkhant/thecheebot.git
cd thecheebot
uv sync                     # creates .venv from uv.lock — never pip install by hand
cp .env.example .env        # only needed for the live-bot loop below
```

`uv run <cmd>` executes inside that environment, so there is no activation step.

You do **not** need a bot token to run the tests or the simulator. If you do run a real bot, create
your own dev bot with [@BotFather](https://t.me/BotFather) and never commit its token.

## Project layout

```
cheebot/
├── cheebot/               # the importable package
│   ├── __main__.py        # entry point: logging, settings, polling
│   ├── app.py             # Application wiring: handlers, filters, button routing
│   ├── config.py          # environment → Settings, validated at startup
│   ├── db.py              # connections and append-only schema migrations
│   ├── repo.py            # every SQL statement lives here
│   ├── geo.py             # bounding box + haversine, antimeridian safe
│   ├── identity.py        # salted user hashes
│   ├── deps.py            # per-user language, context.user_data helpers
│   ├── i18n.py            # the three language catalogs and t()
│   ├── keyboards.py       # reply/inline keyboards, built per language
│   ├── texts.py           # assembling copy: escaping, truncation, venue cards
│   ├── seeds.py           # city and country bounding boxes
│   └── handlers/          # one module per flow (menu, nearby, share, manage, …)
├── scripts/               # import_osm.py, backup_db.py, dev_sim.py (also shipped in the image)
├── tests/                 # pytest; the network boundary is mocked
├── Dockerfile
└── pyproject.toml         # deps, ruff config, pytest config
```

Two rules keep this structure useful:

- **SQL only in `repo.py`.** Handlers ask the repository questions; they never build statements.
  This is also where ownership checks live (`… WHERE id = ? AND added_by = ?`), so a handler cannot
  forget one.
- **Copy only in `i18n.py`.** Handlers call `t(language, "key", **values)`; they do not embed
  user-facing strings. If you need a new string, add it to all three catalogs.

## Development loop

Cheapest first — the README has the long version under *Local development*.

```sh
uv run pytest                            # full suite, no token, no network, ~1 s
uv run pytest tests/test_flows.py -k dup # one area while iterating
uv run ruff check                        # lint (E, F, W, I, B, SIM, UP; 88 cols)
uv run python scripts/dev_sim.py --db dev.db   # drive the real dispatcher from a terminal
```

`scripts/dev_sim.py` uses the actual `Application` — same handlers, same filters, same routing — and
prints what the bot would send plus the callback data behind each button. It is the fastest way to
check a change to a conversation flow. It intentionally refuses to read a token from `.env`.

Only the third loop needs Telegram and a token: `uv run python -m cheebot` with
`CHEEBOT_DB_PATH=dev.db`. Use a separate dev bot — Telegram allows one polling process per token, so
a dev bot running the same token as production will fight it for updates.

## Making a change

1. Branch from `main`.
2. Make the smallest change that solves the problem.
3. Add or update tests that fail without your change.
4. `uv run pytest && uv run ruff check` — both must be clean.
5. If you touched dependencies, run `uv lock` and commit the updated `uv.lock`.
6. Open a pull request describing *what* changed and *why*.

### Code conventions

- Modern annotations (`from __future__ import annotations`, `X | None`, built-in generics).
- Handlers are `async def …(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None` and stay
  thin: validate, call `repo`, reply with `t(...)` and a keyboard.
- Keep comments for intent and non-obvious constraints, not for restating code.
- Errors the user can cause (bad input, missing location) get a translated reply, not an exception.
- Do not add a dependency for something the standard library does in a few lines.

### Tests

Tests run against real `Update` objects and a real temporary SQLite database; only the network
boundary is mocked. That makes them fast and keeps them honest about PTB's data shapes. When adding
a test:

- Put it in the file that matches the area (`test_repo.py`, `test_flows.py`, `test_i18n.py`, …).
- Prefer driving the handler over calling internals, so routing and filters are covered too.
- Use `tmp_path` for databases — never a file in the repo. `.gitignore` covers `*.db`, but a stray
  database should not be possible.
- For anything user-visible in more than one language, remember the i18n tests enforce that every
  catalog has the same keys and the same `{}` placeholders.

## Recipes

### Add a city

Cities are seeded one at a time from OpenStreetMap because the public Overpass API restricts bulk
use. A city is one line in `cheebot/seeds.py`:

```python
CITIES: dict[str, City] = {
    …
    "dawei": City("Dawei", "Myanmar", (13.90, 98.15, 14.15, 98.30)),
}
```

The key is the CLI name (`--city dawei`); the box is `(south, west, north, east)` in decimal degrees
and only needs to cover the built-up area. Then verify locally:

```sh
uv run python scripts/import_osm.py --city dawei --db dev.db
uv run python scripts/dev_sim.py --db dev.db   # then: /find <something in Dawei>
```

Re-running an import is safe — rows match on `osm_id` and update in place. If the public instance is
at capacity, pass `--endpoint` with a mirror. Add a test box only if the box is non-obvious (e.g. it
must exclude a neighbouring city); `tests/test_seeds.py` is the place.

### Add a language

Everything a new language needs is in `cheebot/i18n.py`. Using Khmer (`km`) as an example:

1. Add the code to `SUPPORTED_LANGUAGES` (order is the picker order; keep the default first).
2. Add its own name to `LANGUAGE_NAMES` (`"km": "ខ្មែរ"`) — the picker shows each language in itself.
3. Add aliases to `_ALIASES` (`"km": "km"`, plus `"khm"`), so Telegram locale tags resolve.
4. Copy a catalog (`_MY` is the reference) to `_KM` and translate every value.
5. Register it in `MESSAGES`.

Then run the tests — `tests/test_i18n.py` fails if a key or a `{}` placeholder is missing, which
catches most incomplete translations. Button routing needs no extra work: `keyboards.labels()` reads
the label in every supported language, so a keyboard drawn before a language switch still works.

Translate the prose, not the placeholders. `{radius}`, `{count}` and friends are substituted at
runtime. Numbers and distances are formatted on the way in, so leave the formatting of `{…}` alone.

### Change the schema

Migrations are **append-only**. `PRAGMA user_version` records what has run, and production databases
are migrated in place at startup — there is no dump/restore step, and no way to edit history.

- Add a new script constant and append `(SCHEMA_VERSION + 1, _YOUR_SCRIPT)` to `MIGRATIONS`.
- Bump `SCHEMA_VERSION`.
- Never edit an existing migration: databases that already ran it will not re-run it.
- Keep it additive where possible (`CREATE TABLE`, `ALTER TABLE … ADD COLUMN`). SQLite cannot drop
  or retype columns without a table rebuild, which is a much riskier migration.
- Add a test that opens a database at the previous version, migrates, and asserts the old rows
  survive. `tests/test_repo.py` has the pattern.

State this in the PR: existing installations migrate automatically, and a backup is recommended
before deploying. Users' data must survive.

### Add or change a flow

Handlers live in `cheebot/handlers/`, one module per flow, and are registered in
`cheebot/app.py::_register_handlers`. Two things to respect:

- **Conversation state goes in `context.user_data`, not the database.** A draft that is abandoned
  must leave no rows behind.
- **Validate callback data.** Inline buttons carry ids, but ids are never proof of ownership —
  mutations re-check `added_by` in SQL.

Add the new copy to all catalogs, add a `_button` entry if the flow gets a persistent-keyboard label,
and cover it in `tests/test_flows.py` by feeding `Update` objects through the handler.

## Pull requests

- One logical change per PR. Small PRs get reviewed quickly.
- Subject line in the imperative mood, under ~72 characters
  (`Add Dawei to the seed cities`, not `added dawei`).
- Describe behaviour changes and any migration or configuration impact.
- Update the README when you change something it documents (commands, env vars, setup).
- CI runs the tests and the linter; keep both green.

## Security and secrets

This repository is public and the bot holds a token that controls it. Before you push:

- **Never commit** `TELEGRAM_BOT_TOKEN`, `CHEEBOT_USER_HASH_SALT`, `.env`, `*.db` files, hostnames,
  IP addresses, registry URLs or deployment scripts. `.gitignore` covers the common cases, but it is
  not a guarantee — read `git status` and `git diff --cached` before every commit.
- **Never print secrets.** Startup logs the bot's username, never the token; keep it that way.
- **Do not weaken the hash.** `CHEEBOT_USER_HASH_SALT` must stay long and random, and the shipped
  placeholder is rejected at startup on purpose.
- Report a vulnerability privately through GitHub Security Advisories rather than a public issue.

## License

cheebot is MIT licensed — see [LICENSE](LICENSE). Map data is © OpenStreetMap contributors, under
the [ODbL](https://www.openstreetmap.org/copyright), and is not covered by the MIT licence.
