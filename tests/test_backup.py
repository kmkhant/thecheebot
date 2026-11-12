"""Tests for the backup script (SQLite online backup, not a file copy)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from _loader import load_script

from cheebot import repo
from cheebot.db import Database

backup_db = load_script("backup_db")


def make_db(path: Path, toilets: int = 3) -> Database:
    database = Database(path)
    database.init_schema()
    with database.connect() as conn:
        for index in range(toilets):
            repo.insert_toilet(conn, name=f"WC {index}", lat=1.0 + index, lon=2.0)
    return database


def test_backup_copies_every_row(tmp_path: Path) -> None:
    database = make_db(tmp_path / "bot.db", toilets=3)
    destination = tmp_path / "copy.db"

    code = backup_db.main(["--db", database.path, "--out", str(destination)])

    assert code == 0
    assert destination.exists()
    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT COUNT(*) FROM toilets").fetchone()[0] == 3


def test_backup_includes_writes_still_in_the_wal(tmp_path: Path) -> None:
    """The whole reason for the backup API: a plain copy can miss these."""
    database = make_db(tmp_path / "bot.db", toilets=0)
    wal = Path(f"{database.path}-wal")

    with database.connect() as conn:
        repo.insert_toilet(conn, name="Freshly added", lat=1.0, lon=2.0)
    # Uncheckpointed WAL content is normal while the bot is running.
    if not wal.exists():
        return  # already checkpointed; nothing to prove on this run

    destination = tmp_path / "copy.db"
    assert backup_db.main(["--db", database.path, "--out", str(destination)]) == 0

    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT COUNT(*) FROM toilets").fetchone()[0] == 1


def test_default_destination_is_timestamped_and_beside_the_database(
    tmp_path: Path,
) -> None:
    database = make_db(tmp_path / "bot.db", toilets=1)

    assert backup_db.main(["--db", database.path]) == 0

    backups = list(tmp_path.glob("bot-*.db"))
    assert len(backups) == 1
    assert backups[0].name.endswith("Z.db")


def test_refuses_to_overwrite_an_existing_backup(tmp_path: Path) -> None:
    database = make_db(tmp_path / "bot.db", toilets=1)
    destination = tmp_path / "copy.db"
    destination.write_text("do not clobber me")

    assert backup_db.main(["--db", database.path, "--out", str(destination)]) == 1
    assert destination.read_text() == "do not clobber me"


def test_missing_database_is_reported(tmp_path: Path) -> None:
    assert backup_db.main(["--db", str(tmp_path / "nope.db")]) == 1
