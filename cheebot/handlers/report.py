"""Reporting an inaccurate or removed toilet."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from .. import repo
from ..deps import db, settings, user_hash, user_language
from ..i18n import t


async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    try:
        toilet_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    language = user_language(update, context)
    conf = settings(context)
    hashed = user_hash(update, context)

    with db(context).connect() as conn:
        # A button can outlive its record, e.g. in an old chat.
        if repo.get_toilet(conn, toilet_id) is None:
            missing = True
            counted = hidden_now = False
        else:
            missing = False
            counted, hidden_now, _ = repo.report_toilet(
                conn,
                toilet_id,
                hashed,
                hide_threshold=conf.report_hide_threshold,
            )

    if missing:
        await query.answer(t(language, "not_found"))
    elif not counted:
        await query.answer(t(language, "report_already"))
    elif hidden_now:
        await query.answer(t(language, "report_hidden"), show_alert=True)
    else:
        await query.answer(t(language, "report_thanks"))
