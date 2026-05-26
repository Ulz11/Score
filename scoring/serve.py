"""Boot scoring.db and launch the 4 services + static frontend.

Usage:
    python serve.py                    # localhost-only (default)
    python serve.py --reset            # wipe and re-seed the DB first
    HOST=0.0.0.0 python serve.py       # bind on all interfaces (LAN)

Environment:
    HOST          interface to bind (default 127.0.0.1)
    CORS_ORIGIN   origin allowed by CORS (default http://127.0.0.1:8010)
"""
from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import threading
from functools import partial
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE.parent / "public"

HOST = os.environ.get("HOST", "127.0.0.1")

PORTS = {
    "team":      8011,
    "netdef":    8012,
    "money":     8013,
    "judge":     8014,
    "container": 8015,
    "web":       8010,
}


class _HardenedHandler(http.server.SimpleHTTPRequestHandler):
    """Static server with a small set of production-leaning headers."""
    def end_headers(self) -> None:  # type: ignore[override]
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # quieter than default; keep one line per request
        print(f"[web] {self.address_string()} {fmt % args}")


def _serve_uvicorn(app_path: str, port: int) -> None:
    try:
        uvicorn.run(app_path, host=HOST, port=port, log_level="warning",
                    access_log=False, server_header=False)
    except Exception as exc:
        print(f"[boot] FATAL: {app_path} on port {port} crashed: {exc}", flush=True)
    else:
        print(f"[boot] WARN:  {app_path} on port {port} exited unexpectedly", flush=True)


def _serve_static(port: int, directory: Path) -> None:
    handler = partial(_HardenedHandler, directory=str(directory))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((HOST, port), handler) as httpd:
        httpd.serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate scoring.db")
    args = ap.parse_args()

    from shared.bootstrap import init, reset
    if args.reset:
        reset()
    init(seed=True)
    print(f"[boot] scoring.db ready at {HERE / 'scoring.db'}")
    if HOST != "127.0.0.1":
        print(f"[boot] WARNING: binding on {HOST} — anyone on the network can reach this.")
        print(f"[boot]          Ensure CORS_ORIGIN, HTTPS, and admin password are set.")

    services = [
        ("services.team.main:app",      PORTS["team"]),
        ("services.netdef.main:app",    PORTS["netdef"]),
        ("services.money.main:app",     PORTS["money"]),
        ("services.judge.main:app",     PORTS["judge"]),
        ("services.container.main:app", PORTS["container"]),
    ]
    threads: list[tuple[str, int, threading.Thread]] = []
    for app_path, port in services:
        t = threading.Thread(target=_serve_uvicorn, args=(app_path, port), daemon=True)
        t.start()
        threads.append((app_path, port, t))
        print(f"[boot] {app_path:30s} -> http://{HOST}:{port}")

    print(f"[boot] frontend                       -> http://{HOST}:{PORTS['web']}/web/")
    print("[boot] Ctrl+C to stop.")

    # Give services a moment to bind, then report any that failed.
    import time, socket
    time.sleep(2)
    for app_path, port, t in threads:
        s = socket.socket()
        ok = s.connect_ex((HOST, port)) == 0
        s.close()
        if not ok:
            print(f"[boot] ERROR: {app_path} did NOT bind port {port} — check above for errors")
    try:
        _serve_static(PORTS["web"], STATIC_DIR)
    except KeyboardInterrupt:
        print("\n[boot] bye.")


if __name__ == "__main__":
    main()
