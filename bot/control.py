"""Owner control plane — pause, daily cap, quiet hours.

Real channels always have a hand on the brake: a bad batch, a platform
warning, a family emergency, or simply "today I don't want 20 pins". This
module gives the owner that brake in ONE command / ONE panel click, plus two
guardrails that run by themselves:

* **kill switch**  — `python -m bot pause "reason"` stops the scheduler at the
  next cycle boundary (never mid-API-call), `bot resume` starts it again.
  Persisted in the DB, so restarts cannot forget it.
* **daily cap**    — never post more than `posting.max_per_day` in a day even
  if the window math says otherwise (anti-spam).
* **quiet hours**  — `posting.quiet_hours: "0-6"` = no posting while the
  owner sleeps (bad-hour posts also tank engagement).

Pure logic + DB state, so everything is unit-testable.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

PAUSE_KEY = "posting.pause"


def _load(raw: str) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def pause(db, reason: str = "owner", until_ts: float | None = None) -> dict:
    """Stop the scheduler (optional auto-resume time). Returns the state."""
    state = {"paused": True, "reason": (reason or "owner")[:200],
             "since": time.time(), "until": float(until_ts or 0)}
    db.set_state(PAUSE_KEY, json.dumps(state))
    db.log("WARN", f"⏸ Posting paused by owner — {state['reason']}")
    return state


def resume(db) -> bool:
    """Clear the pause. Returns True when something was actually paused."""
    was = is_paused(db)
    db.del_state(PAUSE_KEY)
    if was:
        db.log("INFO", "▶️ Posting resumed by owner")
    return bool(was)


def is_paused(db, now: float | None = None) -> dict:
    """Pause state when the scheduler must hold off ({} when free)."""
    try:
        raw = db.get_state(PAUSE_KEY)
    except Exception:  # noqa: BLE001 — a DB hiccup must not stop posting logic
        return {}
    state = _load(raw)
    if not state.get("paused"):
        return {}
    until = float(state.get("until", 0) or 0)
    if until and float(now if now is not None else time.time()) >= until:
        try:
            db.del_state(PAUSE_KEY)      # auto-resume elapsed
        except Exception:  # noqa: BLE001
            pass
        return {}
    return state


def human_pause(state: dict, now: float | None = None) -> str:
    if not state:
        return ""
    until = float(state.get("until", 0) or 0)
    if until:
        left = max(0, int(until - (now if now is not None else time.time())))
        return f"{state.get('reason', '')} (auto-resume in {left // 60}m)"
    return str(state.get("reason", ""))


def parse_quiet_hours(raw: str) -> tuple[int, int]:
    """'0-6' → (0, 6). Junk/empty → (0, 0) = disabled."""
    try:
        a, b = str(raw or "").split("-", 1)
        start, end = int(a) % 24, int(b) % 24
        if start == end:
            return 0, 0
        return start, end
    except (TypeError, ValueError):
        return 0, 0


def in_quiet_hours(cfg, hour: int) -> bool:
    start, end = parse_quiet_hours(cfg.get("posting.quiet_hours", "0-6"))
    if not start and not end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end       # wraps midnight (e.g. 23-7)


def posts_today(db, tz=None) -> int:
    """How many pins actually went out today (local day)."""
    day = datetime.now(tz or timezone.utc).date().isoformat()
    try:
        return int(db.count_posts_since(day + "T00:00:00"))
    except Exception:  # noqa: BLE001 — a counting failure must not stop posting
        try:
            return sum(1 for p in db.recent_posts(limit=200)
                       if str(p.get("created_at") or "").startswith(day))
        except Exception:  # noqa: BLE001
            return 0


def cap_reached(db, cfg, tz=None) -> tuple[bool, int, int]:
    """(capped?, posted_today, cap). cap<=0 disables the guard."""
    cap = cfg.get_int("posting.max_per_day", 25)
    if cap <= 0:
        return False, 0, 0
    posted = posts_today(db, tz)
    return posted >= cap, posted, cap


def gate(db, cfg, hour: int, tz=None) -> str:
    """Why posting must wait right now ('' when clear to post).

    Contract: NEVER raises — the scheduler calls it every cycle and a bad DB
    handle or config must not be able to kill the 24x7 loop.
    """
    try:
        state = is_paused(db)
        if state:
            return f"paused by owner — {human_pause(state)}"
    except Exception:  # noqa: BLE001
        pass
    try:
        if in_quiet_hours(cfg, hour):
            s, e = parse_quiet_hours(cfg.get("posting.quiet_hours", "0-6"))
            return f"quiet hours ({s}:00-{e}:00)"
    except Exception:  # noqa: BLE001
        pass
    try:
        capped, posted, cap = cap_reached(db, cfg, tz)
        if capped:
            return f"daily cap reached ({posted}/{cap})"
    except Exception:  # noqa: BLE001
        pass
    return ""
