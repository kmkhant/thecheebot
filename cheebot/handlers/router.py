"""Route incoming locations and free text to whichever flow is active."""

from __future__ import annotations

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import keyboards
from ..deps import user_data, user_language
from ..i18n import t
from ..locations import parse_point
from . import manage, nearby, share


def _point_of(message: Message | None) -> tuple[float, float] | None:
    """The point carried by a location or a forwarded venue message."""
    if message is None:
        return None
    if message.location is not None:
        return message.location.latitude, message.location.longitude
    if message.venue is not None:
        return message.venue.location.latitude, message.venue.location.longitude
    return None


async def on_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    point = _point_of(update.effective_message)
    if point is None:
        return
    if user_data(context).get("draft") is not None:
        await share.point_received(update, context, *point)
    else:
        await nearby.point_received(update, context, *point)


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
        point = parse_point(text)
        if point is not None:
            await share.point_received(update, context, *point)
            return
        await message.reply_text(
            t(language, "send_location_instead"),
            reply_markup=keyboards.location_keyboard(language, "share_button_label"),
        )
        return

    if data.get("flow") == "nearest":
        point = parse_point(text)
        if point is not None:
            await nearby.point_received(update, context, *point)
            return
        await message.reply_text(
            t(language, "send_location_instead"),
            reply_markup=keyboards.location_keyboard(language, "nearest_button_label"),
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
