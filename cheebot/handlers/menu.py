"""Message handlers: /start, /help, /about, /cancel and the main menu."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import texts
from ..deps import user_data, user_language
from ..i18n import t
from ..keyboards import main_menu
from .nearby import send_toilet
from .share import prompt_share


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    # Deep link: t.me/<bot>?start=t_<id> opens a specific toilet.
    args = context.args or []
    if args and args[0].startswith("t_"):
        await send_toilet(update, context, args[0][2:])
        return
    if args and args[0] == "share":
        # Inline mode sends people here when it has nothing to offer yet.
        await prompt_share(update, context)
        return

    language = user_language(update, context)
    await message.reply_text(
        texts.welcome(language, context.bot.username),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(language),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    await message.reply_text(
        texts.help_text(language, context.bot.username),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(language),
        disable_web_page_preview=True,
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    await message.reply_text(
        texts.about(language),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu(language),
        disable_web_page_preview=True,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    data = user_data(context)
    data.pop("draft", None)
    data.pop("flow", None)
    await message.reply_text(t(language, "cancelled"), reply_markup=main_menu(language))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    await message.reply_text(
        t(language, "unknown_message"),
        reply_markup=main_menu(language),
        parse_mode=ParseMode.HTML,
    )
