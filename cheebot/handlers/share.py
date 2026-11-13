"""Adding a toilet: location → duplicate check → name → save."""

from __future__ import annotations

from telegram import CallbackQuery, Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import keyboards, repo, texts
from ..deps import db, settings, user_data, user_hash, user_language
from ..geo import format_distance
from ..i18n import t


async def prompt_share(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    language = user_language(update, context)
    conf = settings(context)
    with db(context).connect() as conn:
        used = repo.count_submissions_since(
            conn, user_hash(update, context), repo.hours_ago(24)
        )

    if used >= conf.daily_share_limit:
        await message.reply_text(
            t(language, "share_limit_reached", limit=conf.daily_share_limit),
            reply_markup=keyboards.main_menu(language),
        )
        return

    data = user_data(context)
    data["draft"] = {"stage": "location"}
    data["flow"] = "share"
    await message.reply_text(
        t(language, "share_intro"),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.location_keyboard(language, "share_button_label"),
    )


async def point_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float
) -> None:
    """Check a point for duplicates, however the user supplied it.

    Called for a shared location, a forwarded venue and typed coordinates, so
    the flow behaves the same whichever way the pin was chosen.
    """
    message = update.effective_message
    draft = user_data(context).get("draft")
    if message is None or draft is None:
        return

    language = user_language(update, context)
    draft.update({"lat": lat, "lon": lon, "stage": "duplicate"})

    conf = settings(context)
    with db(context).connect() as conn:
        match = repo.find_within(conn, lat, lon, conf.dedupe_radius_m)

    if match is not None:
        toilet, distance = match
        await message.reply_text(
            t(
                language,
                "share_duplicate",
                distance=format_distance(distance),
                name=texts.escape(toilet["name"]),
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.duplicate_actions(language, toilet["id"]),
        )
        return

    await _ask_for_name(update, context, language)


async def _ask_for_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE, language: str
) -> None:
    draft = user_data(context).get("draft")
    message = update.effective_message
    if draft is None or message is None:
        return
    draft["stage"] = "name"
    await message.reply_text(
        t(language, "ask_name"), reply_markup=keyboards.name_keyboard(language)
    )


async def name_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE, raw_name: str
) -> bool:
    """Save the draft using the typed name. Returns False if nothing was pending."""
    draft = user_data(context).get("draft")
    if not draft or draft.get("stage") != "name":
        return False
    language = user_language(update, context)
    await _save(update, context, texts.clean_name(language, raw_name), language)
    return True


async def skip_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    draft = user_data(context).get("draft")
    language = user_language(update, context)
    if not draft or draft.get("stage") != "name":
        message = update.effective_message
        if message is not None:
            await message.reply_text(
                t(language, "nothing_to_skip"),
                reply_markup=keyboards.main_menu(language),
            )
        return
    await _save(update, context, t(language, "default_toilet_name"), language)


async def _save(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    name: str,
    language: str,
) -> None:
    message = update.effective_message
    data = user_data(context)
    draft = data.get("draft") or {}
    lat, lon = draft.get("lat"), draft.get("lon")
    if message is None or lat is None or lon is None:
        return

    user_hash_value = user_hash(update, context)
    with db(context).connect() as conn:
        toilet_id = repo.insert_toilet(
            conn, name=name, lat=lat, lon=lon, added_by=user_hash_value
        )
        repo.log_submission(conn, user_hash_value, toilet_id)
        toilet = repo.get_toilet(conn, toilet_id)

    data.pop("draft", None)
    data.pop("flow", None)

    link = f"https://t.me/{context.bot.username}?start=t_{toilet_id}"
    await message.reply_text(
        texts.share_confirmed(language, link),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(language),
        disable_web_page_preview=True,
    )
    if toilet is not None and update.effective_chat is not None:
        await context.bot.send_venue(
            chat_id=update.effective_chat.id,
            latitude=toilet["lat"],
            longitude=toilet["lon"],
            title=texts.truncate(toilet["name"]),
            address=texts.describe(language, toilet),
            reply_markup=keyboards.toilet_actions(
                language, toilet["id"], toilet["lat"], toilet["lon"]
            ),
        )


async def _replace_prompt(query: CallbackQuery, text: str, language: str) -> None:
    """Dismiss a prompt and deliver the outcome with the main menu restored.

    ``edit_message_text`` only accepts inline keyboards, so the persistent
    reply keyboard has to come back on a fresh message.
    """
    await query.edit_message_text(t(language, "prompt_dismissed"))
    # CallbackQuery.message can be an InaccessibleMessage in odd chat states.
    if isinstance(query.message, Message):
        await query.message.reply_text(text, reply_markup=keyboards.main_menu(language))


async def duplicate_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle the 'same place / different place' buttons."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    language = user_language(update, context)
    data = user_data(context)
    draft = data.get("draft")
    if not draft or draft.get("stage") != "duplicate":
        await _replace_prompt(query, t(language, "draft_expired"), language)
        return

    if query.data == "dup:new":
        await _ask_for_name(update, context, language)
        return

    # "Same place" — count it as a confirmation and drop the draft.
    try:
        toilet_id = int(query.data.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return

    with db(context).connect() as conn:
        repo.confirm_toilet(conn, toilet_id)
    data.pop("draft", None)
    data.pop("flow", None)
    await _replace_prompt(query, t(language, "share_duplicate_confirmed"), language)
