"""API circuit breaker — protection against bans and pointless hammering.

Real 2026 risk: when a Pinterest token expires (401) or the account gets rate
limited (429), a naive 24x7 loop keeps calling the API every few minutes
forever. That is exactly how accounts get flagged — and it wastes the day.

This module turns the API error text into a cooldown:

* auth errors  -> long pause (6h) with a one-line fix hint; retrying cannot
  help until the owner re-auths, so hammering is pure ban risk.
* rate limits  -> escalating cooldown 15m -> 1h -> 4h -> 12h, reset by success.
* anything else -> short 5 min breather.

The state is persisted in the DB (`state` table) so a restart cannot forget a
cooldown, and is pure/testable — no clock or network of its own.
"""
from __future__ import annotations

import json
from typing import Any

STATE_KEY = "api_breaker"

AUTH_COOLDOWN = 6 * 3600           # token problems cannot fix themselves
OTHER_COOLDOWN = 300               # transient errors: short breather
RATE_STEPS = (900, 3600, 14400, 43200)   # 15m, 1h, 4h, 12h


def classify(message: str) -> str:
    """'auth' | 'rate' | 'other' from an API error message."""
    m = (message or "").lower()
    if any(s in m for s in ("401", "403", "invalid_grant", "unauthorized",
                            "token exchange failed", "invalid token",
                            "missing access token", "not configured")):
        return "auth"
    if any(s in m for s in ("429", "too many retries", "rate limit",
                            "retry-after")):
        return "rate"
    return "other"


def record_failure(prev: dict[str, Any] | None, message: str,
                   now: float) -> dict[str, Any]:
    """Return the next breaker state after a failure."""
    kind = classify(message)
    prev = prev or {}
    was = str(prev.get("kind", ""))
    fails = int(prev.get("fails", 0) or 0)
    rate_n = int(prev.get("rate_n", 0) or 0)

    if kind == "auth":
        cooldown, rate_n = AUTH_COOLDOWN, 0
        hint = "token problem — fix: python -m bot auth (posting paused)"
    elif kind == "rate":
        # escalate only when the previous failure was also a rate limit
        rate_n = rate_n + 1 if was == "rate" else 1
        cooldown = RATE_STEPS[min(rate_n - 1, len(RATE_STEPS) - 1)]
        hint = "Pinterest rate limit — backing off (escalating)"
    else:
        cooldown, rate_n = OTHER_COOLDOWN, 0
        hint = "API error — short breather"

    return {
        "kind": kind,
        "fails": fails + 1,
        "rate_n": rate_n,
        "until": float(now) + cooldown,
        "cooldown": cooldown,
        "reason": (message or "")[:200],
        "hint": hint,
    }


def record_success() -> dict[str, Any]:
    """A successful API call clears the breaker."""
    return {"kind": "", "fails": 0, "rate_n": 0, "until": 0.0,
            "cooldown": 0, "reason": "", "hint": ""}


def is_open(state: dict[str, Any] | None, now: float) -> bool:
    return bool(state) and float(state.get("until", 0) or 0) > float(now)


def remaining(state: dict[str, Any] | None, now: float) -> float:
    if not state:
        return 0.0
    return max(0.0, float(state.get("until", 0) or 0) - float(now))


def human(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def load(raw: str) -> dict[str, Any]:
    """Parse the persisted JSON; never raises."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def dump(state: dict[str, Any]) -> str:
    try:
        return json.dumps(state)
    except (TypeError, ValueError):
        return "{}"


def safe_state(state: dict[str, Any] | None) -> str:
    """One-line summary for the panel/API."""
    if not is_open(state, __import__("time").time()):
        return "ok"
    return f"paused {human(remaining(state, __import__('time').time()))} — " \
           f"{(state or {}).get('hint', '')}"
