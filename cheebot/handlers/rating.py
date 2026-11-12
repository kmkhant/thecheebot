"""1-5 star ratings on a toilet card."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from .. import repo
from ..deps import db, user_hash, user_language
from ..i18n import t


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    try:
        _, raw_id, raw_score = query.data.split(":")
        toilet_id, score = int(raw_id), int(raw_score)
    except ValueError:
        await query.answer()
        return

    language = user_language(update, context)
    hashed = user_hash(update, context)

    with db(context).connect() as conn:
        # A button can outlive its record, e.g. in an old chat.
        if repo.get_active_toilet(conn, toilet_id) is None:
            missing = True
            first_time = False
        else:
            missing = False
            first_time = repo.rate_toilet(conn, toilet_id, hashed, score)

    if missing:
        await query.answer(t(language, "not_found"))
    elif first_time:
        await query.answer(t(language, "rating_thanks", score=score))
    else:
        await query.answer(t(language, "rating_updated", score=score))
