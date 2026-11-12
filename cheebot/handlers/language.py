"""Choosing the language: /language, the 🌐 button and the picker buttons."""

from __future__ import annotations

from telegram import Message, Update
from telegram.ext import ContextTypes

from .. import keyboards
from ..deps import store_language, user_language
from ..i18n import SUPPORTED_LANGUAGES, language_name, t


async def prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    await message.reply_text(
        t(language, "choose_language"),
        reply_markup=keyboards.language_menu(language),
    )


async def chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    language = query.data.split(":", 1)[1]
    if language not in SUPPORTED_LANGUAGES:
        await query.answer()
        return

    # Saved before answering: the confirmation is already in the new language.
    store_language(update, context, language)
    name = language_name(language)
    await query.answer(t(language, "language_changed", language=name))

    # The persistent keyboard is a client-side object, so it has to be sent again
    # for the new labels to appear.
    body = t(language, "language_saved", language=name)
    markup = keyboards.main_menu(language)
    target = query.message if isinstance(query.message, Message) else None
    if target is not None:
        await target.reply_text(body, reply_markup=markup)
    elif update.effective_message is not None:
        await update.effective_message.reply_text(body, reply_markup=markup)
