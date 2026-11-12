"""Accessors for the per-application and per-user state PTB hands us."""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from . import repo
from .config import Settings
from .db import Database
from .i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize_language
from .identity import hash_user_id


def settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.application.bot_data["db"]


def user_data(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    """The per-user scratch dict used by the multi-step flows.

    PTB types ``context.user_data`` as optional because an application can be
    built without one, but ours always has it. Narrowing here keeps every
    handler free of redundant ``is None`` checks.
    """
    data = context.user_data
    if data is None:  # pragma: no cover - only possible in a broken setup
        raise RuntimeError("context.user_data is missing; check the application setup")
    return data


def user_hash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """The salted hash that stands in for this user's id everywhere."""
    conf = settings(context)
    user = update.effective_user
    return hash_user_id(conf.user_hash_salt, user.id if user else None)


def user_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Which language to answer this user in.

    Order: their saved choice, then their Telegram client's language, then the
    deployment default (Burmese). The result is cached in ``user_data`` so only
    the first update of a session touches the database.
    """
    cache = context.user_data
    if cache is not None:
        cached = cache.get("language")
        if cached in SUPPORTED_LANGUAGES:
            return cached

    with db(context).connect() as conn:
        stored = repo.get_user_language(conn, user_hash(update, context))

    language = stored if stored in SUPPORTED_LANGUAGES else None
    if language is None:
        client_code = getattr(update.effective_user, "language_code", None)
        language = normalize_language(client_code)
    if language is None:
        conf = settings(context)
        language = (
            conf.default_language
            if conf.default_language in SUPPORTED_LANGUAGES
            else DEFAULT_LANGUAGE
        )

    if cache is not None:
        cache["language"] = language
    return language


def store_language(
    update: Update, context: ContextTypes.DEFAULT_TYPE, language: str
) -> None:
    """Persist a language choice so it survives restarts."""
    with db(context).connect() as conn:
        repo.set_user_language(conn, user_hash(update, context), language)
    if context.user_data is not None:
        context.user_data["language"] = language
