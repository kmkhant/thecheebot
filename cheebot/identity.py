"""Pseudo-anonymous user identifiers.

We never store a Telegram user id. Rate limits and duplicate-report detection
only need a stable, non-reversible key, so we hash the id with a secret salt.
"""

from __future__ import annotations

import hashlib


def hash_user_id(salt: str, user_id: int | None) -> str:
    if user_id is None:
        # Keep anonymous/admin paths in a distinct bucket.
        return "anonymous"
    digest = hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()
    return digest[:32]
