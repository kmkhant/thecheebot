"""Route incoming locations and free text to whichever flow is active."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import keyboards
from ..deps import user_data, user_language
from ..i18n import t
from . import manage, nearby, share


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if user_data(context).get("draft") is not None:
        await share.location_received(update, context)
    else:
        await nearby.location_received(update, context)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return

    text = message.text.strip()
    data = user_data(context)
    draft = data.get("draft") or {}

    if draft.get("stage") == "name" and await share.name_received(
        update, context, text
    ):
        return

    if draft.get("stage") == "rename" and await manage.rename_received(
        update, context, text
    ):
        return

    language = user_language(update, context)

    if draft.get("stage") == "location":
        await message.reply_text(
            t(language, "send_location_instead"),
            reply_markup=keyboards.location_keyboard(language, "share_button_label"),
        )
        return

    if data.get("flow") == "find":
        data.pop("flow", None)
        await nearby.text_search(update, context, text)
        return

    await message.reply_text(
        t(language, "unknown_message"),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(language),
    )
