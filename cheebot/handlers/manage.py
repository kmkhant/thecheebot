"""Managing your own contributions: list, rename, delete."""

from __future__ import annotations

import sqlite3

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import keyboards, repo, texts
from ..deps import db, user_data, user_hash, user_language
from ..i18n import t

# How many of a user's places /mine lists. Manageable in a burst of messages
# without pagination machinery.
MINE_LIMIT = 20


def _place_text(language: str, toilet: sqlite3.Row) -> str:
    return (
        f"<b>{texts.escape(toilet['name'])}</b>\n"
        f"{texts.escape(texts.describe(language, toilet))}"
    )


async def prompt_mine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List the places this user added, each with rename/delete buttons."""
    message = update.effective_message
    if message is None:
        return

    language = user_language(update, context)
    with db(context).connect() as conn:
        toilets = repo.toilets_added_by(conn, user_hash(update, context), MINE_LIMIT)

    if not toilets:
        await message.reply_text(
            t(language, "mine_empty"), reply_markup=keyboards.main_menu(language)
        )
        return

    await message.reply_text(
        t(language, "mine_header"),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(language),
    )
    for toilet in toilets:
        await message.reply_text(
            _place_text(language, toilet),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.manage_actions(language, toilet["id"]),
        )


async def delete_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask before deleting — the row is gone for good."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    language = user_language(update, context)
    toilet_id = int(query.data.split(":", 1)[1])
    with db(context).connect() as conn:
        toilet = repo.get_owned_toilet(conn, toilet_id, user_hash(update, context))

    if toilet is None:
        await query.answer(t(language, "not_yours"))
        return

    await query.answer()
    await query.edit_message_text(
        t(language, "delete_confirm", name=texts.escape(toilet["name"])),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.delete_confirm(language, toilet_id),
    )


async def delete_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    language = user_language(update, context)
    toilet_id = int(query.data.rsplit(":", 1)[1])
    with db(context).connect() as conn:
        deleted = repo.delete_toilet(conn, toilet_id, user_hash(update, context))
        exists = repo.get_toilet(conn, toilet_id) is not None

    if deleted:
        body = t(language, "deleted")
    elif exists:
        body = t(language, "not_yours")
    else:
        body = t(language, "not_found")
    await query.answer(body)
    await query.edit_message_text(body)


async def delete_cancelled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Put the card back the way it was."""
    query = update.callback_query
    if query is None or query.data is None:
        return

    language = user_language(update, context)
    toilet_id = int(query.data.rsplit(":", 1)[1])
    with db(context).connect() as conn:
        toilet = repo.get_owned_toilet(conn, toilet_id, user_hash(update, context))

    await query.answer()
    if toilet is None:
        await query.edit_message_text(t(language, "not_found"))
        return
    await query.edit_message_text(
        _place_text(language, toilet),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.manage_actions(language, toilet_id),
    )


async def rename_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    language = user_language(update, context)
    toilet_id = int(query.data.split(":", 1)[1])
    with db(context).connect() as conn:
        toilet = repo.get_owned_toilet(conn, toilet_id, user_hash(update, context))

    if toilet is None:
        await query.answer(t(language, "not_yours"))
        return

    # Reuse the draft slot: the next text message becomes the new name.
    data = user_data(context)
    data["draft"] = {"stage": "rename", "id": toilet_id}
    data["flow"] = "rename"

    await query.answer()
    if isinstance(query.message, Message):
        await query.message.reply_text(
            t(language, "ask_new_name"),
            reply_markup=keyboards.cancel_keyboard(language),
        )


async def rename_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE, raw_name: str
) -> bool:
    """Apply a pending rename. Returns False if no rename was pending."""
    data = user_data(context)
    draft = data.get("draft")
    if not draft or draft.get("stage") != "rename":
        return False

    language = user_language(update, context)
    message = update.effective_message
    name = texts.clean_name(language, raw_name)
    with db(context).connect() as conn:
        renamed = repo.rename_toilet(
            conn, draft.get("id"), name, user_hash(update, context)
        )

    data.pop("draft", None)
    data.pop("flow", None)

    if message is not None:
        if renamed:
            await message.reply_text(
                t(language, "renamed", name=texts.escape(name)),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.main_menu(language),
            )
        else:
            await message.reply_text(
                t(language, "not_found"), reply_markup=keyboards.main_menu(language)
            )
    return True
