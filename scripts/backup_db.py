#!/usr/bin/env python3
"""Copy a live cheebot database to a backup file.

    python scripts/backup_db.py
    python scripts/backup_db.py --out /data/backups/cheebot-2026-11-12.db

Uses SQLite's online backup API, which is safe while the bot is running. A plain
file copy is *not*: in WAL mode the newest writes can still be sitting in the
``-wal`` sidecar and would be missed.

Restoring is copying the file back while the bot is stopped.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB = "cheebot.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=os.getenv("CHEEBOT_DB_PATH") or DEFAULT_DB,
        help="database to back up (default: CHEEBOT_DB_PATH or cheebot.db)",
    )
    parser.add_argument(
        "--out",
        "-o",
        help="destination file (default: <name>-<timestamp>.db beside the db)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    source = Path(args.db)
    if not source.exists():
        print(f"No database at {source}", file=sys.stderr)
        return 1

    if args.out:
        destination = Path(args.out)
    else:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = source.with_name(f"{source.stem}-{stamp}.db")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f"Refusing to overwrite {destination}", file=sys.stderr)
        return 1

    try:
        with (
            closing(sqlite3.connect(source)) as src,
            closing(sqlite3.connect(destination)) as dst,
        ):
            src.backup(dst)
        with closing(sqlite3.connect(destination)) as check:
            toilets = check.execute("SELECT COUNT(*) FROM toilets").fetchone()[0]
    except sqlite3.Error as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        destination.unlink(missing_ok=True)
        return 1

    size_kib = destination.stat().st_size / 1024
    print(f"Backed up {source} → {destination} ({toilets} toilets, {size_kib:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
