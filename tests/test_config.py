"""Configuration guards: a published salt is worse than no salt."""

from __future__ import annotations

import pytest

from cheebot.config import INSECURE_SALT, ConfigError, load_settings


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN-NOT-REAL")
    monkeypatch.delenv("CHEEBOT_DEFAULT_LANGUAGE", raising=False)
    return monkeypatch


def test_example_salt_is_rejected(env) -> None:
    """Copying .env.example verbatim must fail loudly, not silently ship."""
    env.setenv("CHEEBOT_USER_HASH_SALT", INSECURE_SALT)

    with pytest.raises(ConfigError) as excinfo:
        load_settings()

    assert "example value" in str(excinfo.value)
    assert "token_urlsafe" in str(excinfo.value)


def test_missing_salt_is_rejected(env) -> None:
    env.delenv("CHEEBOT_USER_HASH_SALT", raising=False)

    with pytest.raises(ConfigError):
        load_settings()


def test_a_real_salt_is_accepted(env) -> None:
    env.setenv("CHEEBOT_USER_HASH_SALT", "Qh2vWd8yUOt4m9Kxk0Jc3gJ9u3t1V0dR2bXf")

    assert load_settings().user_hash_salt.startswith("Qh2vWd8y")
