"""Application wiring: handlers, error handling, storage bootstrap."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from . import keyboards
from .config import Settings
from .db import Database
from .deps import user_language
from .handlers import (
    inline,
    language,
    manage,
    menu,
    nearby,
    rating,
    report,
    router,
    share,
)
from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, t

logger = logging.getLogger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]

CONFLICT_HELP = (
    "Another instance is polling this bot token.\n"
    "  Telegram allows one getUpdates consumer per token, so run either the local\n"
    "  copy or the deployed one — not both. For local development use a separate\n"
    "  bot from @BotFather (see 'Local development' in the README)."
)


def stop_reason(app: Application) -> str | None:
    return app.bot_data.get("stop_reason")


def _language_of(update: object, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Best-effort language for error copy; must never raise."""
    if not isinstance(update, Update):
        return DEFAULT_LANGUAGE
    try:
        return user_language(update, context)
    except Exception:
        return DEFAULT_LANGUAGE


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error

    # Polling errors reach this handler too, with update=None. A Conflict means
    # another process holds the token; retrying forever would only spam
    # tracebacks, so stop cleanly and let the entry point explain why.
    if isinstance(error, Conflict):
        logger.error("Stopping: another instance is polling this bot token")
        context.application.bot_data["stop_reason"] = "conflict"
        context.application.stop_running()
        return

    logger.error("Unhandled error while processing an update", exc_info=error)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                t(_language_of(update, context), "error")
            )
        except Exception:
            logger.warning("Could not deliver the error message", exc_info=True)


def _button(*keys: str) -> filters.BaseFilter:
    """Match a persistent-keyboard label in any language.

    Labels are translated but the handlers are not, so a tap has to reach the
    same place whichever language the keyboard was drawn in.
    """
    labels = [label for key in keys for label in keyboards.labels(key)]
    pattern = "|".join(re.escape(label) for label in labels)
    return filters.Regex(f"^(?:{pattern})$")


def _register_handlers(app: Application) -> None:
    # Commands
    app.add_handler(CommandHandler("start", menu.start))
    app.add_handler(CommandHandler("help", menu.help_command))
    app.add_handler(CommandHandler("about", menu.about))
    app.add_handler(CommandHandler("cancel", menu.cancel))
    app.add_handler(CommandHandler("nearest", nearby.prompt_nearest))
    app.add_handler(CommandHandler("share", share.prompt_share))
    app.add_handler(CommandHandler("find", nearby.find_command))
    app.add_handler(CommandHandler("skip", share.skip_name))
    app.add_handler(CommandHandler("language", language.prompt))
    app.add_handler(CommandHandler("mine", manage.prompt_mine))

    # A point can arrive as a shared location, a forwarded place, or typed
    # coordinates (handled in router.on_text). All take the same path.
    app.add_handler(
        MessageHandler(filters.LOCATION | filters.VENUE, router.on_location)
    )

    # Inline buttons on result cards
    app.add_handler(CallbackQueryHandler(share.duplicate_callback, pattern=r"^dup:"))
    app.add_handler(
        CallbackQueryHandler(report.report_callback, pattern=r"^report:\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(rating.rate_callback, pattern=r"^rate:\d+:[1-5]$")
    )
    app.add_handler(
        CallbackQueryHandler(
            language.chosen,
            pattern="^lang:(?:" + "|".join(SUPPORTED_LANGUAGES) + ")$",
        )
    )
    app.add_handler(CallbackQueryHandler(manage.delete_prompt, pattern=r"^del:\d+$"))
    app.add_handler(
        CallbackQueryHandler(manage.delete_confirmed, pattern=r"^del:ok:\d+$")
    )
    app.add_handler(
        CallbackQueryHandler(manage.delete_cancelled, pattern=r"^del:no:\d+$")
    )
    app.add_handler(CallbackQueryHandler(manage.rename_prompt, pattern=r"^ren:\d+$"))

    # Inline mode
    app.add_handler(InlineQueryHandler(inline.inline_query))

    # Persistent reply keyboard. The nearest button is absent on purpose: it
    # asks Telegram for a location, so it arrives as a location message.
    buttons: dict[str, Handler] = {
        "menu_share": share.prompt_share,
        "menu_find": nearby.prompt_find,
        "menu_mine": manage.prompt_mine,
        "menu_about": menu.about,
        "menu_language": language.prompt,
        "menu_cancel": menu.cancel,
        "menu_skip": share.skip_name,
    }
    for key, handler in buttons.items():
        app.add_handler(MessageHandler(_button(key), handler))

    # Fallbacks
    app.add_handler(MessageHandler(filters.COMMAND, menu.unknown_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router.on_text))
    app.add_error_handler(_on_error)


def build_application(config: Settings) -> Application:
    database = Database(config.db_path)
    database.init_schema()

    app = (
        Application.builder()
        .token(config.bot_token)
        # One update at a time: the share flow keeps state in user_data, and a
        # small bot has no throughput problem worth trading predictability for.
        .concurrent_updates(False)
        .build()
    )
    app.bot_data["settings"] = config
    app.bot_data["db"] = database

    _register_handlers(app)
    return app
