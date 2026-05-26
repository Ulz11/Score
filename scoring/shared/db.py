from __future__ import annotations

import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("SCORING_DB", Path(__file__).resolve().parent.parent / "scoring.db"))


def _uuid7_fallback() -> uuid.UUID:
    """RFC 9562 UUIDv7 — 48-bit big-endian ms timestamp + 74 random bits + version/variant."""
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)               # 12 bits
    rand_b = secrets.randbits(62)               # 62 bits (after variant)
    # Assemble 128 bits
    n = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=n)


_uuid7 = getattr(uuid, "uuid7", _uuid7_fallback)


def new_id() -> str:
    """Return a fresh UUID7 string. UUID7 is time-ordered, so the natural
    lexicographic order of these ids equals creation order — convenient
    for cursors, witness log ordering, and feed pagination."""
    return str(_uuid7())


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
