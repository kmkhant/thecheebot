#!/usr/bin/env python3
"""Drive the bot from a terminal, without Telegram or a bot token.

    python scripts/dev_sim.py --db cheebot.db

It runs the *real* application — same handlers, same filters, same routing —
and prints what the bot would send. Only the Telegram API calls are replaced,
so flows behave exactly as they do in production.

Commands:
    /start /nearest /share /find <x> /help /about /cancel /skip
                                   send a command exactly as typed
    <any other text>               send a text message
    loc <lat> <lon>                share a location
    cb <callback_data>             press an inline button (e.g. cb report:3, cb lang:zh)
    inline <query>                 run an inline query
    count                          show how many toilets are stored
    quit                           leave (Ctrl-D works too)
"""

from __future__ import annotations

import argparse
import asyncio
import html
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# Make the project importable when this file is run directly from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from telegram import (
    Bot,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
    User,
)
from telegram.ext import Application

from cheebot import repo
from cheebot.app import build_application
from cheebot.config import ConfigError, Settings, load_settings

DATE = 1_700_000_000
DEV_TOKEN = "0:dev-token"
_TAG = re.compile(r"</?(?:b|i|u|s|code|pre|a)(?:\s[^>]*)?>")


# --------------------------------------------------------------------------- #
# Input parsing (kept free of Telegram types so it can be tested)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Input:
    kind: str  # "message" | "location" | "callback" | "inline" | "quit"
    text: str = ""
    lat: float = 0.0
    lon: float = 0.0
    data: str = ""


def parse_line(line: str) -> Input | None:
    """Turn one line of terminal input into an update description."""
    raw = line.strip()
    if not raw:
        return None

    lowered = raw.lower()
    if lowered in {"quit", "exit", "q"}:
        return Input("quit")

    if lowered == "loc" or lowered.startswith("loc "):
        parts = raw.split()
        if len(parts) != 3:
            raise ValueError("usage: loc <lat> <lon>")
        try:
            lat, lon = float(parts[1]), float(parts[2])
        except ValueError as exc:
            raise ValueError("lat and lon must be numbers") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("lat must be ±90 and lon ±180")
        return Input("location", lat=lat, lon=lon)

    if lowered == "cb" or lowered.startswith("cb "):
        data = raw[2:].strip()
        if not data:
            raise ValueError("usage: cb <callback_data>")
        return Input("callback", data=data)

    if lowered.startswith("inline "):
        return Input("inline", text=raw[7:].strip())

    return Input("message", text=raw)


# --------------------------------------------------------------------------- #
# Output formatting
# --------------------------------------------------------------------------- #


def plain(text: str) -> str:
    """Strip the small set of HTML tags our copy uses, for readable output."""
    return html.unescape(_TAG.sub("", text))


def describe_buttons(markup: Any) -> list[str]:
    """Render a keyboard so you can see which callback data to type."""
    if isinstance(markup, InlineKeyboardMarkup):
        lines = []
        for row in markup.inline_keyboard:
            parts = []
            for button in row:
                if button.callback_data:
                    parts.append(f"[{button.text} → cb {button.callback_data}]")
                elif button.switch_inline_query is not None:
                    parts.append(f"[{button.text} → inline]")
                elif button.url:
                    parts.append(f"[{button.text} → {button.url}]")
                else:
                    parts.append(f"[{button.text}]")
            lines.append("     " + "  ".join(parts))
        return lines
    if isinstance(markup, ReplyKeyboardMarkup):
        rows = [" / ".join(button.text for button in row) for row in markup.keyboard]
        return ["     keyboard: " + " | ".join(rows)]
    return []


# --------------------------------------------------------------------------- #
# Simulator
# --------------------------------------------------------------------------- #


class Simulator:
    """Runs the real Application with the Telegram API replaced by printers."""

    def __init__(
        self,
        app: Application,
        chat_id: int = 4242,
        language_code: str | None = None,
    ) -> None:
        self.app = app
        self.chat_id = chat_id
        self.user_id = chat_id
        # Mirrors Telegram's User.language_code, which the bot uses to pick a
        # language when the user has not chosen one yet.
        self.language_code = language_code
        self._update_id = 0
        self._mocks: list[Any] = []

    def _user(self) -> dict[str, Any]:
        user: dict[str, Any] = {
            "id": self.user_id,
            "is_bot": False,
            "first_name": "Dev",
        }
        if self.language_code:
            user["language_code"] = self.language_code
        return user

    # -- Telegram API stand-ins ------------------------------------------- #

    async def _on_send_message(self, *args: Any, **kwargs: Any) -> None:
        for line in plain(kwargs.get("text", "")).splitlines():
            print(f"  bot │ {line}")
        for line in describe_buttons(kwargs.get("reply_markup")):
            print(line)
        print()

    async def _on_send_venue(self, *args: Any, **kwargs: Any) -> None:
        print(f"  bot │ 📍 {kwargs.get('title')}")
        print(f"      │    {kwargs.get('address')}")
        print(f"      │    {kwargs.get('latitude'):.5f}, {kwargs.get('longitude'):.5f}")
        for line in describe_buttons(kwargs.get("reply_markup")):
            print(line)
        print()

    async def _on_edit_message_text(self, *args: Any, **kwargs: Any) -> None:
        print(f"  bot │ (edited) {plain(kwargs.get('text', ''))}")
        print()

    async def _on_answer_callback(self, *args: Any, **kwargs: Any) -> None:
        text = kwargs.get("text")
        if text:
            alert = " (alert)" if kwargs.get("show_alert") else ""
            print(f"  bot │ ↳ toast{alert}: {text}")
            print()

    async def _on_answer_inline(self, *args: Any, **kwargs: Any) -> None:
        results = kwargs.get("results") or []
        if not results:
            button = kwargs.get("button")
            hint = f" (button: {button.text})" if button else ""
            print(f"  bot │ inline: no results{hint}")
        else:
            print(f"  bot │ inline: {len(results)} result(s)")
            for result in results:
                print(f"      │    {result.title} — {result.address}")
        print()

    # -- Update construction ----------------------------------------------- #

    def _next_update_id(self) -> int:
        self._update_id += 1
        return self._update_id

    def _message(self, **extra: Any) -> dict[str, Any]:
        return {
            "message_id": self._update_id,
            "date": DATE,
            "chat": {"id": self.chat_id, "type": "private"},
            "from": self._user(),
            **extra,
        }

    @staticmethod
    def _telegram_entities(text: str) -> list[dict[str, Any]]:
        """Reproduce the entity Telegram attaches to a /command message.

        Without it CommandHandler does not match, because PTB 21+ reads the
        command out of ``entities[0]`` rather than the leading slash.
        """
        if not text.startswith("/"):
            return []
        return [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]

    def build(self, item: Input) -> Update:
        self._next_update_id()
        if item.kind == "location":
            payload = {
                "message": self._message(
                    location={"latitude": item.lat, "longitude": item.lon}
                )
            }
        elif item.kind == "callback":
            payload = {
                "callback_query": {
                    "id": f"cb-{self._update_id}",
                    "from": self._user(),
                    "chat_instance": "sim",
                    "data": item.data,
                    "message": {
                        "message_id": self._update_id,
                        "date": DATE,
                        "chat": {"id": self.chat_id, "type": "private"},
                        "from": {"id": 1, "is_bot": True, "first_name": "cheebot"},
                        "text": "(earlier message)",
                    },
                }
            }
        elif item.kind == "inline":
            payload = {
                "inline_query": {
                    "id": f"iq-{self._update_id}",
                    "from": self._user(),
                    "query": item.text,
                    "offset": "",
                }
            }
        else:
            payload = {
                "message": self._message(
                    text=item.text, entities=self._telegram_entities(item.text)
                )
            }

        return Update.de_json({"update_id": self._update_id, **payload}, self.app.bot)

    # -- Session ------------------------------------------------------------ #

    def _toilet_count(self) -> int:
        with self.app.bot_data["db"].connect() as conn:
            return repo.count_toilets(conn)

    async def start(self) -> None:
        self._mocks = [
            patch.object(
                Bot, "send_message", AsyncMock(side_effect=self._on_send_message)
            ),
            patch.object(Bot, "send_venue", AsyncMock(side_effect=self._on_send_venue)),
            patch.object(
                Bot,
                "edit_message_text",
                AsyncMock(side_effect=self._on_edit_message_text),
            ),
            patch.object(
                Bot,
                "answer_callback_query",
                AsyncMock(side_effect=self._on_answer_callback),
            ),
            patch.object(
                Bot,
                "answer_inline_query",
                AsyncMock(side_effect=self._on_answer_inline),
            ),
        ]
        for mock in self._mocks:
            mock.start()

        fake_me = User(id=1, is_bot=True, first_name="cheebot", username="cheebot_dev")
        with patch.object(Bot, "get_me", AsyncMock(return_value=fake_me)):
            await self.app.initialize()
        # Telegram's get_me() result is cached here; assigning it directly is how
        # PTB's own test suite fakes an initialized bot offline.
        self.app.bot._bot_user = fake_me

    async def stop(self) -> None:
        for mock in self._mocks:
            mock.stop()
        self._mocks = []
        await self.app.shutdown()

    async def handle(self, item: Input) -> None:
        if item.kind == "message" and item.text.strip().lower() == "count":
            print(f"  db  │ {self._toilet_count()} toilets\n")
            return
        await self.app.process_update(self.build(item))

    async def run(self) -> int:
        await self.start()
        try:
            db_path = self.app.bot_data["settings"].db_path
            count = self._toilet_count()
            print(f"cheebot dev simulator — {db_path} ({count} toilets)")
            if count == 0:
                print(
                    "  The database is empty. Seed it first, e.g.\n"
                    "    uv run python scripts/import_osm.py "
                    f"--city yangon --db {db_path}\n"
                )
            print("  Commands: /start /nearest /share /find <x>, loc <lat> <lon>,")
            print("            cb <data>, inline <query>, count, quit")
            print("  Language: follows your Telegram client; here, try 'cb lang:zh'.")
            print()

            while True:
                try:
                    line = await asyncio.to_thread(input, "you │ ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 0

                try:
                    item = parse_line(line)
                except ValueError as exc:
                    print(f"  !   │ {exc}\n")
                    continue
                if item is None:
                    continue
                if item.kind == "quit":
                    return 0

                await self.handle(item)
        finally:
            await self.stop()


def dev_settings(db_path: Path) -> Settings:
    """Settings for the simulator.

    Deliberately never carries a real bot token: the simulator talks to nothing,
    and an inherited token could otherwise leak into logs or tracebacks.
    """
    try:
        return replace(load_settings(), db_path=db_path, bot_token=DEV_TOKEN)
    except ConfigError:
        return Settings(
            bot_token=DEV_TOKEN,
            db_path=db_path,
            default_radius_m=1_000,
            max_radius_m=25_000,
            results_limit=5,
            dedupe_radius_m=30,
            report_hide_threshold=3,
            daily_share_limit=10,
            user_hash_salt="dev-salt",
        )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=os.getenv("CHEEBOT_DB_PATH") or "dev.db",
        help="database to use (default: CHEEBOT_DB_PATH or dev.db)",
    )
    args = parser.parse_args(argv)

    app = build_application(dev_settings(Path(args.db)))
    return asyncio.run(Simulator(app).run())


if __name__ == "__main__":
    raise SystemExit(main())
