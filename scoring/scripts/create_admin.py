"""Create or rotate the admin worker.

Usage:
    python -m scripts.create_admin --handle admin --name "Ada Admin"
    python -m scripts.create_admin --handle admin --name "Ada" --password "..."   (not recommended; shell history)

If --password is omitted, getpass prompts twice (hidden input).
If the worker already exists, this rotates their password and marks them admin.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from shared import auth
from shared.bootstrap import init
from shared.db import new_id, transaction


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handle", required=True, help="login handle, e.g. 'admin'")
    ap.add_argument("--name",   required=True, help="display name")
    ap.add_argument("--password", help="(omit to be prompted)")
    args = ap.parse_args()

    init(seed=True)  # make sure schema exists

    pw = args.password
    if not pw:
        pw = getpass.getpass("password: ")
        again = getpass.getpass("again:    ")
        if pw != again:
            print("passwords do not match", file=sys.stderr)
            return 2
    if len(pw) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 2

    pw_hash = auth.hash_password(pw)
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, name FROM team_workers WHERE handle=?", (args.handle,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE team_workers SET name=?, password_hash=?, is_admin=1 WHERE id=?",
                (args.name, pw_hash, row["id"]),
            )
            # rotate: kill old sessions
            conn.execute("DELETE FROM team_sessions WHERE worker_id=?", (row["id"],))
            print(f"rotated admin: {args.name} @{args.handle}  id={row['id']}")
        else:
            wid = new_id()
            conn.execute(
                """INSERT INTO team_workers
                       (id, name, type, handle, password_hash, is_admin)
                   VALUES (?, ?, 'human', ?, ?, 1)""",
                (wid, args.name, args.handle, pw_hash),
            )
            print(f"created admin: {args.name} @{args.handle}  id={wid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
