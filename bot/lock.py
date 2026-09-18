"""Single-instance guard — two autopilots must NEVER run on the same machine.

Why this exists (real money + ban risk):
  * two schedulers = the same product posted twice = duplicate pins, spam
    signals, wasted API quota — and Pinterest/IG do not forgive that;
  * two dashboards = "Address already in use" restart loops and a panel that
    silently is not the one you are watching.

How it decides (no guessing about command lines):
  A lock file under `data/locks/<name>.lock` records the holder pid + token.
  The holder **heartbeats** (touches the file) every 30s.

    pid alive + file fresh  (< stale_after)  -> a real twin  -> refuse to start
    pid alive + file stale                    -> frozen/zombie/PID reused -> take over
    pid dead                                  -> crashed     -> take over
    unreadable/absent                         -> take over

  So a crashed or killed bot never bricks the machine, and a live one can
  never be silently doubled.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

LOCK_DIR_NAME = "locks"
DEFAULT_STALE_AFTER = 120.0        # seconds without heartbeat = not really alive
HEARTBEAT_EVERY = 30.0


class AlreadyRunning(RuntimeError):
    """Raised when another live instance holds the lock."""

    def __init__(self, pid: int, cmd: str = "", since: str = "") -> None:
        self.pid, self.cmd, self.since = pid, cmd, since
        detail = f"pid {pid}"
        if cmd:
            detail += f" ({cmd[:70]})"
        if since:
            detail += f" since {since}"
        super().__init__(f"another instance is already running: {detail}")


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:          # exists, owned by someone else
        return True
    except OSError:
        return False
    return True


def holder_cmd(pid: int) -> str:
    """Best-effort cmdline of a live pid (Linux; '' elsewhere) — reporting only."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode("utf-8", "ignore").strip()
    except OSError:
        return ""


def lock_path(cfg, name: str) -> Path:
    return Path(cfg.db_path).parent / LOCK_DIR_NAME / f"{name}.lock"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text() or "{}")
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _age(path: Path) -> float:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return 1e9


def touch(path: Path, token: str) -> bool:
    """Refresh the heartbeat — only if the lock is still ours."""
    if _read(path).get("token") != token:
        sys.stderr.write(
            "⚠️  Another instance took over the lock file — this process is no "
            "longer the single owner (check for duplicates!).\n")
        return False
    try:
        path.touch()
    except OSError:
        return False
    return True


def _start_heartbeat(path: Path, token: str) -> threading.Event:
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(HEARTBEAT_EVERY):
            if not path.exists():
                # someone removed our lock (manual cleanup / takeover): re-claim
                try:
                    path.write_text(json.dumps({
                        "pid": os.getpid(), "token": token,
                        "cmd": " ".join(sys.argv)[:160],
                        "since": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
                except OSError:
                    stop.set()
                continue
            touch(path, token)

    threading.Thread(target=_beat, name="pin-lock-heartbeat", daemon=True).start()
    return stop


def acquire(cfg, name: str, wait: float = 0.0,
            stale_after: float = DEFAULT_STALE_AFTER,
            heartbeat: bool = True) -> Path:
    """Take the lock for `name` ('scheduler' / 'dashboard').

    Returns the lock path. Raises AlreadyRunning if a live twin holds it.
    """
    path = lock_path(cfg, name)
    deadline = time.time() + max(0.0, wait)
    me = os.getpid()
    while True:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            info = _read(path)
            holder = int(info.get("pid") or 0)
            fresh = _age(path) < stale_after
            if holder != me and _alive(holder) and fresh:
                if time.time() < deadline:
                    time.sleep(0.5)
                    continue
                raise AlreadyRunning(holder,
                                     str(info.get("cmd") or holder_cmd(holder)),
                                     str(info.get("since", "")))
            try:                       # crashed / frozen / foreign: take over
                path.unlink()
            except OSError:
                pass
        token = secrets.token_hex(8)
        try:
            path.write_text(json.dumps({
                "pid": me, "token": token, "name": name,
                "cmd": " ".join(sys.argv)[:160],
                "since": time.strftime("%Y-%m-%d %H:%M:%S"),
            }) + "\n")
        except OSError:
            return path               # read-only storage: never block the bot
        time.sleep(0.05)
        if _read(path).get("token") == token:
            if heartbeat:
                _start_heartbeat(path, token)
            return path
        if time.time() >= deadline:
            info = _read(path)
            raise AlreadyRunning(int(info.get("pid") or 0),
                                 str(info.get("cmd", "")),
                                 str(info.get("since", "")))


def release(path: Path) -> None:
    """Drop the lock, but only if it is still ours."""
    if _read(path).get("pid") == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass
