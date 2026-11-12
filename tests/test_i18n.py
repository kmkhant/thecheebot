"""Multilingual copy: catalog integrity, detection, and the /language flow."""

from __future__ import annotations

import asyncio
import sqlite3
import string
from pathlib import Path

import pytest
from _loader import load_script

import cheebot.db as db_module
from cheebot import i18n, keyboards, repo, texts
from cheebot.app import build_application
from cheebot.config import ConfigError, Settings, load_settings
from cheebot.identity import hash_user_id

dev_sim = load_script("dev_sim")


@pytest.fixture
def conn(tmp_path: Path):
    database = db_module.Database(tmp_path / "test.db")
    database.init_schema()
    with database.connect() as connection:
        yield connection


def make_settings(db_path: Path, **overrides) -> Settings:
    values = {
        "bot_token": "123456:TEST-TOKEN-NOT-REAL",
        "db_path": db_path,
        "default_radius_m": 1_000,
        "max_radius_m": 25_000,
        "results_limit": 5,
        "dedupe_radius_m": 30,
        "report_hide_threshold": 3,
        "daily_share_limit": 10,
        "user_hash_salt": "test-salt",
        "default_language": "my",
    }
    values.update(overrides)
    return Settings(**values)


# --------------------------------------------------------------------------- #
# Catalog integrity
# --------------------------------------------------------------------------- #


def _placeholders(template: str) -> set[str]:
    return {
        name for _, name, _, _ in string.Formatter().parse(template) if name is not None
    }


def first_line(language: str, key: str) -> str:
    """A message's opening line, as the simulator prints it (markup stripped)."""
    return dev_sim.plain(i18n.t(language, key).splitlines()[0])


def last_line(language: str, key: str) -> str:
    """A message's final line, as the simulator prints it (markup stripped)."""
    return dev_sim.plain(i18n.t(language, key).splitlines()[-1])


def test_every_language_defines_the_same_keys() -> None:
    expected = set(i18n.MESSAGES[i18n.DEFAULT_LANGUAGE])

    for language, catalog in i18n.MESSAGES.items():
        assert set(catalog) == expected, f"{language} is missing or has extra keys"


def test_placeholders_match_across_languages() -> None:
    """A translation that drops {radius} breaks that language at runtime."""
    default = i18n.MESSAGES[i18n.DEFAULT_LANGUAGE]

    for key, template in default.items():
        expected = _placeholders(template)
        for language, catalog in i18n.MESSAGES.items():
            assert _placeholders(catalog[key]) == expected, (language, key)


def test_every_supported_language_has_a_catalog_and_a_name() -> None:
    assert set(i18n.MESSAGES) == set(i18n.SUPPORTED_LANGUAGES)
    assert set(i18n.LANGUAGE_NAMES) == set(i18n.SUPPORTED_LANGUAGES)
    assert i18n.SUPPORTED_LANGUAGES[0] == i18n.DEFAULT_LANGUAGE == "my"


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("my", "my"),
        ("my-MM", "my"),
        ("en", "en"),
        ("en-US", "en"),
        ("EN_gb", "en"),
        ("zh", "zh"),
        ("zh-Hans", "zh"),
        ("zh_CN", "zh"),
        ("fr", None),
        ("", None),
        (None, None),
    ],
)
def test_client_locales_map_to_supported_languages(
    code: str | None, expected: str | None
) -> None:
    assert i18n.normalize_language(code) == expected


def test_translation_falls_back_to_burmese() -> None:
    assert i18n.t("nope", "not_found") == i18n.t("my", "not_found")


def test_translation_fills_placeholders() -> None:
    assert "★4" in i18n.t("zh", "rating_thanks", score=4)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN-NOT-REAL")
    monkeypatch.setenv("CHEEBOT_USER_HASH_SALT", "test-salt")
    monkeypatch.delenv("CHEEBOT_DEFAULT_LANGUAGE", raising=False)
    return monkeypatch


def test_default_language_is_burmese(env) -> None:
    assert load_settings().default_language == "my"


def test_default_language_accepts_a_locale_tag(env) -> None:
    env.setenv("CHEEBOT_DEFAULT_LANGUAGE", "zh-Hans")

    assert load_settings().default_language == "zh"


def test_unknown_default_language_is_rejected(env) -> None:
    env.setenv("CHEEBOT_DEFAULT_LANGUAGE", "fr")

    with pytest.raises(ConfigError):
        load_settings()


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


def test_user_language_round_trip(conn: sqlite3.Connection) -> None:
    assert repo.get_user_language(conn, "user-a") is None

    repo.set_user_language(conn, "user-a", "zh")
    assert repo.get_user_language(conn, "user-a") == "zh"

    # Choosing again replaces, it does not add a row.
    repo.set_user_language(conn, "user-a", "en")
    assert repo.get_user_language(conn, "user-a") == "en"
    count = conn.execute("SELECT COUNT(*) AS n FROM user_languages").fetchone()["n"]
    assert count == 1


def test_language_preferences_survive_a_v2_migration(tmp_path: Path) -> None:
    path = tmp_path / "v2.db"
    legacy = sqlite3.connect(path)
    legacy.row_factory = sqlite3.Row
    legacy.executescript(db_module._INITIAL)
    legacy.executescript(db_module._RATINGS)
    legacy.execute("PRAGMA user_version = 2")
    legacy.execute(
        "INSERT INTO toilets (name, lat, lon, created_at)"
        " VALUES ('Old WC', 16.775, 96.158, '2024-01-01T00:00:00+00:00')"
    )
    legacy.execute(
        "INSERT INTO ratings (toilet_id, user_hash, score, created_at, updated_at)"
        " VALUES (1, 'user-a', 5, 'now', 'now')"
    )
    legacy.commit()
    legacy.close()

    database = db_module.Database(path)
    database.init_schema()

    with database.connect() as conn:
        assert (
            conn.execute("PRAGMA user_version").fetchone()[0]
            == db_module.SCHEMA_VERSION
        )
        assert repo.count_toilets(conn) == 1
        assert repo.rating_summary(conn, 1) == (5.0, 1)
        repo.set_user_language(conn, "user-a", "zh")
        assert repo.get_user_language(conn, "user-a") == "zh"


# --------------------------------------------------------------------------- #
# Copy and keyboards
# --------------------------------------------------------------------------- #


def test_describe_speaks_the_requested_language(conn: sqlite3.Connection) -> None:
    toilet_id = repo.insert_toilet(
        conn, name="WC", lat=0.0, lon=0.0, is_free=True, is_accessible=True
    )
    toilet = repo.get_toilet(conn, toilet_id)

    assert texts.describe("en", toilet) == "free · wheelchair accessible"
    assert texts.describe("my", toilet) == "အခမဲ့ · ဘီးတပ်ကုလားထိုင်ဖြင့် ဝင်နိုင်"
    assert texts.describe("zh", toilet) == "免费 · 无障碍"


def test_unaddressed_toilet_uses_a_localised_default(conn: sqlite3.Connection) -> None:
    toilet = repo.get_toilet(conn, repo.insert_toilet(conn, name="WC", lat=0, lon=0))

    assert texts.describe("en", toilet) == "Public toilet"
    assert texts.describe("zh", toilet) == "公共厕所"


def test_skipped_name_is_stored_in_the_users_language() -> None:
    assert texts.clean_name("zh", None) == "公共厕所"
    assert texts.clean_name("my", "  ") == "အများပြည်သူ့ အိမ်သာ"
    assert texts.clean_name("en", "Market WC") == "Market WC"


def test_main_menu_is_translated() -> None:
    labels = [
        button.text for row in keyboards.main_menu("zh").keyboard for button in row
    ]

    assert labels == [
        "📍 最近",
        "➕ 添加",
        "🔍 搜索",
        "📋 我的地点",
        "ℹ️ 关于",
        "🌐 语言",
    ]


def test_button_labels_cover_every_language() -> None:
    """Routing must accept keyboards drawn in any language, not just the current one."""
    for key in keyboards.BUTTON_KEYS:
        labels = keyboards.labels(key)
        assert len(labels) == len(i18n.SUPPORTED_LANGUAGES)
        assert len(set(labels)) == len(labels), key


def test_no_two_buttons_share_a_label() -> None:
    """A duplicate label in one language would route taps to the wrong handler."""
    for language in i18n.SUPPORTED_LANGUAGES:
        seen: dict[str, str] = {}
        for key in keyboards.BUTTON_KEYS:
            label = i18n.t(language, key)
            assert label not in seen, (language, label, seen.get(label), key)
            seen[label] = key


def test_language_picker_marks_the_current_language() -> None:
    buttons = keyboards.language_menu("zh").inline_keyboard

    assert [row[0].callback_data for row in buttons] == [
        f"lang:{code}" for code in i18n.SUPPORTED_LANGUAGES
    ]
    assert buttons[2][0].text.startswith("✓ ")
    assert not buttons[0][0].text.startswith("✓ ")


# --------------------------------------------------------------------------- #
# Flow, through the real dispatcher
# --------------------------------------------------------------------------- #


@pytest.fixture
def app(tmp_path: Path):
    return build_application(make_settings(tmp_path / "dev.db"))


def add_toilet(app, name: str = "Riverside WC") -> int:
    with app.bot_data["db"].connect() as conn:
        return repo.insert_toilet(conn, name=name, lat=16.775, lon=96.158)


def session(app, lines: list[str], capsys, language_code: str | None = None) -> str:
    simulator = dev_sim.Simulator(app, language_code=language_code)

    async def _inner() -> None:
        await simulator.start()
        try:
            for line in lines:
                item = dev_sim.parse_line(line)
                assert item is not None, line
                await simulator.handle(item)
        finally:
            await simulator.stop()

    asyncio.run(_inner())
    return capsys.readouterr().out


def test_default_language_is_burmese_for_unknown_clients(app, capsys) -> None:
    output = session(app, ["/start"], capsys, language_code="fr")

    assert first_line("my", "welcome") in output


def test_english_client_gets_english(app, capsys) -> None:
    output = session(app, ["/start"], capsys, language_code="en-US")

    assert "Welcome to cheebot" in output


def test_chinese_client_gets_chinese(app, capsys) -> None:
    output = session(app, ["/start"], capsys, language_code="zh-Hans")

    assert "欢迎使用 cheebot" in output


def test_language_button_taps_route_in_burmese(app, capsys) -> None:
    output = session(app, [i18n.t("my", "menu_about")], capsys, language_code="my")

    assert first_line("my", "about") in output


def test_language_button_taps_route_in_chinese(app, capsys) -> None:
    output = session(app, [i18n.t("zh", "menu_cancel")], capsys, language_code="zh")

    assert last_line("zh", "cancelled") in output


def test_switching_language_changes_later_replies(app, capsys) -> None:
    output = session(app, ["/language", "cb lang:zh", "/start"], capsys)

    assert last_line("my", "choose_language") in output
    assert first_line("zh", "welcome") in output


def test_a_switch_survives_a_restart(app, capsys, tmp_path: Path) -> None:
    session(app, ["cb lang:zh"], capsys)

    db_path = app.bot_data["settings"].db_path
    restarted = build_application(make_settings(db_path))
    output = session(restarted, ["/start"], capsys)

    assert first_line("zh", "welcome") in output


def test_the_choice_is_stored_hashed(app, capsys) -> None:
    session(app, ["cb lang:en"], capsys)

    user_hash = hash_user_id("test-salt", 4242)
    with app.bot_data["db"].connect() as conn:
        assert repo.get_user_language(conn, user_hash) == "en"


def test_an_old_keyboard_keeps_working_after_a_switch(app, capsys) -> None:
    """The reply keyboard is drawn once; switching language must not kill it."""
    session(app, ["cb lang:zh"], capsys)

    output = session(app, [i18n.t("en", "menu_share")], capsys)

    assert last_line("zh", "share_intro") in output


def test_inline_results_use_the_users_language(app, capsys) -> None:
    add_toilet(app)

    output = session(app, ["inline riverside"], capsys, language_code="zh")

    assert "公共厕所" in output


def test_rating_toasts_are_translated(app, capsys) -> None:
    toilet_id = add_toilet(app)

    output = session(app, [f"cb rate:{toilet_id}:5"], capsys, language_code="zh")

    assert i18n.t("zh", "rating_thanks", score=5) in output
