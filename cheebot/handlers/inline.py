"""Inline mode: share a toilet into any chat with @bot <query>."""

from __future__ import annotations

import sqlite3

from telegram import InlineQueryResultsButton, InlineQueryResultVenue, Update
from telegram.ext import ContextTypes

from .. import repo, texts
from ..deps import db, settings, user_language
from ..i18n import t


def _to_results(
    rows: list[sqlite3.Row],
    ratings: dict[int, tuple[float, int]],
    language: str,
) -> list[InlineQueryResultVenue]:
    return [
        InlineQueryResultVenue(
            id=str(row["id"]),
            latitude=row["lat"],
            longitude=row["lon"],
            title=texts.truncate(row["name"], 60),
            address=texts.describe(language, row, rating=ratings.get(row["id"])),
        )
        for row in rows
    ]


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query
    if query is None:
        return

    language = user_language(update, context)
    conf = settings(context)
    text = (query.query or "").strip()

    rows: list[sqlite3.Row] = []
    ratings: dict[int, tuple[float, int]] = {}
    with db(context).connect() as conn:
        if text.startswith("t_") and text[2:].isdigit():
            # Exact reference, used by the Share button on a result card.
            toilet = repo.get_active_toilet(conn, int(text[2:]))
            rows = [toilet] if toilet is not None else []
        elif text:
            rows = repo.search_by_text(conn, text, limit=conf.results_limit)
        elif query.location is not None:
            rows = [
                row
                for row, _ in repo.nearest_toilets(
                    conn,
                    query.location.latitude,
                    query.location.longitude,
                    conf.default_radius_m,
                    limit=conf.results_limit,
                )
            ]
        ratings = repo.ratings_for(conn, [row["id"] for row in rows])

    results = _to_results(rows, ratings, language)
    button = None
    if not results:
        button = InlineQueryResultsButton(
            text=t(language, "inline_add_button"), start_parameter="share"
        )

    await query.answer(
        results=results,
        cache_time=30,
        button=button,
        is_personal=query.location is not None,
    )
