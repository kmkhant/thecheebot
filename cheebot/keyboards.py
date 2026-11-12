"""Reply and inline keyboards, built in the user's language."""

from __future__ import annotations

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, t

# Persistent-keyboard buttons that arrive back as plain text messages.
BUTTON_KEYS = (
    "menu_share",
    "menu_find",
    "menu_mine",
    "menu_about",
    "menu_language",
    "menu_cancel",
    "menu_skip",
)


def labels(key: str) -> list[str]:
    """The label for ``key`` in every language.

    Incoming button taps carry translated text, so routing has to accept all
    of them — switching language must not leave an old keyboard unusable.
    """
    return [t(language, key) for language in SUPPORTED_LANGUAGES]


def directions_url(lat: float, lon: float) -> str:
    """Google Maps directions link; works without an API key on every platform."""
    return f"https://www.google.com/maps/dir/?api=1&destination={lat:.6f},{lon:.6f}"


def main_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(language, "menu_nearest"), request_location=True)],
            [
                KeyboardButton(t(language, "menu_share")),
                KeyboardButton(t(language, "menu_find")),
            ],
            [KeyboardButton(t(language, "menu_mine"))],
            [
                KeyboardButton(t(language, "menu_about")),
                KeyboardButton(t(language, "menu_language")),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def location_keyboard(
    language: str, label_key: str = "nearest_button_label"
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(language, label_key), request_location=True)],
            [KeyboardButton(t(language, "menu_cancel"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def name_keyboard(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(language, "menu_skip"))],
            [KeyboardButton(t(language, "menu_cancel"))],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def toilet_actions(
    language: str, toilet_id: int, lat: float, lon: float
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "btn_directions"), url=directions_url(lat, lon)
                )
            ],
            [
                InlineKeyboardButton(
                    t(language, "btn_share"), switch_inline_query=f"t_{toilet_id}"
                ),
                InlineKeyboardButton(
                    t(language, "btn_report"), callback_data=f"report:{toilet_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{score}⭐", callback_data=f"rate:{toilet_id}:{score}"
                )
                for score in range(1, 6)
            ],
        ]
    )


def duplicate_actions(language: str, toilet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "btn_same_place"),
                    callback_data=f"dup:same:{toilet_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    t(language, "btn_different_place"), callback_data="dup:new"
                )
            ],
        ]
    )


def manage_actions(language: str, toilet_id: int) -> InlineKeyboardMarkup:
    """Buttons on a place the user added themselves."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "btn_rename"), callback_data=f"ren:{toilet_id}"
                ),
                InlineKeyboardButton(
                    t(language, "btn_delete"), callback_data=f"del:{toilet_id}"
                ),
            ]
        ]
    )


def delete_confirm(language: str, toilet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t(language, "btn_delete_yes"),
                    callback_data=f"del:ok:{toilet_id}",
                ),
                InlineKeyboardButton(
                    t(language, "btn_delete_no"),
                    callback_data=f"del:no:{toilet_id}",
                ),
            ]
        ]
    )


def cancel_keyboard(language: str) -> ReplyKeyboardMarkup:
    """For prompts where the only escape is cancelling."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t(language, "menu_cancel"))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def language_menu(language: str) -> InlineKeyboardMarkup:
    """One button per language, with the current one ticked."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    ("✓ " if code == language else "") + LANGUAGE_NAMES[code],
                    callback_data=f"lang:{code}",
                )
            ]
            for code in SUPPORTED_LANGUAGES
        ]
    )
