"""Password hashing + session helpers.

Hash format: scrypt$N$r$p$salt_hex$dk_hex  (stdlib `hashlib.scrypt`).
Sessions are server-side rows in team_sessions; clients receive an HttpOnly
cookie named 'sid' with the UUID7 token. Per-request cost is one indexed
SQLite lookup.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.db import new_id

SESSION_COOKIE = "sid"
SESSION_TTL_DAYS = 7

SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 64
MAXMEM = 64 * 1024 * 1024


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        pw.encode("utf-8"), salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
        dklen=DKLEN, maxmem=MAXMEM,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, n_s, r_s, p_s, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.scrypt(
            pw.encode("utf-8"), salt=salt,
            n=n, r=r, p=p, dklen=len(expected), maxmem=MAXMEM,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    user_agent: str | None = None,
    ttl_days: int = SESSION_TTL_DAYS,
) -> tuple[str, str]:
    """Insert a new session row. Returns (token, expires_at_iso)."""
    token = secrets.token_urlsafe(32)  # 256 bits of entropy
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    conn.execute(
        """INSERT INTO team_sessions (token, worker_id, expires_at, user_agent)
           VALUES (?, ?, ?, ?)""",
        (token, worker_id, expires_at, user_agent),
    )
    return token, expires_at


def get_session(conn: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    """Return {worker_id, name, handle, is_admin, expires_at} for a valid live
    session, or None if missing / expired / unknown."""
    if not token:
        return None
    row = conn.execute(
        """SELECT s.token, s.worker_id, s.expires_at,
                  w.name, w.handle, w.is_admin
           FROM team_sessions s
           JOIN team_workers w ON w.id = s.worker_id
           WHERE s.token = ?""",
        (token,),
    ).fetchone()
    if not row:
        return None
    if row["expires_at"] < datetime.now(timezone.utc).isoformat():
        conn.execute("DELETE FROM team_sessions WHERE token=?", (token,))
        return None
    return dict(row)


def delete_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM team_sessions WHERE token=?", (token,))
