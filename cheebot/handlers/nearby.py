"""Nearest-toilet lookup, toilet detail cards, and text search."""

from __future__ import annotations

import sqlite3

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import keyboards, repo, texts
from ..deps import db, settings, user_data, user_language
from ..geo import format_distance
from ..i18n import t


def _search(
    conn: sqlite3.Connection,
    lat: float,
    lon: float,
    default_radius: int,
    max_radius: int,
    limit: int,
) -> tuple[int, list[tuple[sqlite3.Row, float]], int | None]:
    """Nearest toilets, widening the radius until something turns up.

    Returns (radius_used, results, radius_we_widened_from_or_None).
    """
    radius = default_radius
    widened_from: int | None = None
    while True:
        results = repo.nearest_toilets(conn, lat, lon, radius, limit=limit)
        if results or radius >= max_radius:
            return radius, results, widened_from
        widened_from = radius if widened_from is None else widened_from
        radius = min(radius * 5, max_radius)


async def prompt_nearest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    user_data(context)["flow"] = "nearest"
    await message.reply_text(
        t(language, "ask_location_nearest"),
        reply_markup=keyboards.location_keyboard(language, "nearest_button_label"),
    )


async def location_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a shared point for a nearby search.

    The location is used for this query only and never written to the database.
    """
    message = update.effective_message
    if message is None or message.location is None:
        return

    language = user_language(update, context)
    conf = settings(context)
    with db(context).connect() as conn:
        radius, results, widened_from = _search(
            conn,
            message.location.latitude,
            message.location.longitude,
            conf.default_radius_m,
            conf.max_radius_m,
            conf.results_limit,
        )
        ratings = repo.ratings_for(conn, [toilet["id"] for toilet, _ in results])

    if not results:
        await message.reply_text(
            t(language, "no_results", radius=format_distance(radius)),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.main_menu(language),
        )
        return

    await message.reply_text(
        texts.nearest_header(language, radius, widened_from),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(language),
    )
    for toilet, distance in results:
        await _send_venue_card(
            update,
            context,
            toilet,
            language,
            distance,
            ratings.get(toilet["id"]),
        )


async def _send_venue_card(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    toilet: sqlite3.Row,
    language: str,
    distance: float | None = None,
    rating: tuple[float, int] | None = None,
) -> None:
    if update.effective_chat is None:
        return
    await context.bot.send_venue(
        chat_id=update.effective_chat.id,
        latitude=toilet["lat"],
        longitude=toilet["lon"],
        title=texts.truncate(toilet["name"]),
        address=texts.describe(language, toilet, distance, rating),
        reply_markup=keyboards.toilet_actions(
            language, toilet["id"], toilet["lat"], toilet["lon"]
        ),
    )


async def send_toilet(
    update: Update, context: ContextTypes.DEFAULT_TYPE, raw_id: str
) -> None:
    """Show one toilet by id (deep links, inline results)."""
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    try:
        toilet_id = int(raw_id)
    except (TypeError, ValueError):
        await message.reply_text(
            t(language, "not_found"), reply_markup=keyboards.main_menu(language)
        )
        return

    with db(context).connect() as conn:
        toilet = repo.get_active_toilet(conn, toilet_id)
        rating = repo.rating_summary(conn, toilet_id) if toilet is not None else None

    if toilet is None:
        await message.reply_text(
            t(language, "not_found"), reply_markup=keyboards.main_menu(language)
        )
        return
    await _send_venue_card(update, context, toilet, language, rating=rating)


async def prompt_find(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    language = user_language(update, context)
    user_data(context)["flow"] = "find"
    await message.reply_text(
        t(language, "ask_search"), reply_markup=keyboards.main_menu(language)
    )


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    query = " ".join(context.args or []).strip()
    if not query:
        await prompt_find(update, context)
        return
    await text_search(update, context, query)


async def text_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
) -> None:
    message = update.effective_message
    if message is None:
        return

    language = user_language(update, context)
    conf = settings(context)
    with db(context).connect() as conn:
        results = repo.search_by_text(conn, query, limit=conf.results_limit)
        ratings = repo.ratings_for(conn, [row["id"] for row in results])

    if not results:
        await message.reply_text(
            t(language, "search_no_results", query=texts.escape(query)),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.main_menu(language),
        )
        return

    await message.reply_text(
        t(language, "search_header", query=texts.escape(query)),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu(language),
    )
    for toilet in results:
        await _send_venue_card(
            update, context, toilet, language, rating=ratings.get(toilet["id"])
        )
