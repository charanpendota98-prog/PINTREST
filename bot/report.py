"""Period report — the owner's one-screen answer to "ela nadustundi?".

Pulls only real numbers out of the DB (posts, clicks, subscribers, queue,
breaker state) and pairs them with the honest earnings estimate. Works as a
CLI (`bot report --days 7`) and can push the same text to Telegram
(`bot report --telegram`) so the owner never has to open the panel.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import control, earnings


def build(cfg, db, days: int = 7, tz=None) -> dict:
    days = max(1, int(days))
    tz = tz or timezone.utc
    since = datetime.now(timezone.utc) - timedelta(days=days)
    iso = since.isoformat(timespec="seconds")

    all_posts = db.recent_posts(limit=1000) or []
    recent = [p for p in all_posts
              if str(p.get("posted_at") or p.get("scheduled_for") or "") >= iso]
    clicks_all = sum(int(p.get("clicks", 0) or 0) for p in all_posts)
    clicks_recent = sum(int(p.get("clicks", 0) or 0) for p in recent)

    by_store: dict[str, int] = {}
    for p in recent:
        s = str(p.get("source") or "other").lower()
        by_store[s] = by_store.get(s, 0) + 1

    top = sorted(all_posts, key=lambda p: int(p.get("clicks", 0) or 0),
                 reverse=True)[:5]
    hours = db.click_hours() or {}
    days_map = db.click_days() or {}
    # only claim a "best hour" when clicks actually exist — never invent one
    best_hour = (max(hours, key=lambda h: hours[h])
                 if hours and sum(hours.values()) > 0 else None)
    best_day = (max(days_map, key=lambda d: days_map[d])
                if days_map and sum(days_map.values()) > 0 else None)

    stats = db.stats() or {}
    est = earnings.estimate(cfg, recent or all_posts)
    return {
        "days": days,
        "since": since.date().isoformat(),
        "posts": len(recent),
        "posts_total": int(stats.get("posted", 0) or 0),
        "clicks": clicks_recent,
        "clicks_total": clicks_all,
        "subscribers": db.subscriber_count(),
        "queue": int(stats.get("queued", 0) or 0),
        "failed": int(stats.get("failed", 0) or 0),
        "by_store": by_store,
        "top_pins": [{"title": (p.get("title") or "")[:60],
                      "clicks": int(p.get("clicks", 0) or 0),
                      "source": p.get("source", "")} for p in top],
        "best_hour_utc": best_hour,
        "best_weekday": best_day,
        "earnings": est,
        "paused": bool(control.is_paused(db)),
    }


def lines(cfg, db, days: int = 7, tz=None) -> list[str]:
    r = build(cfg, db, days=days, tz=tz)
    out = [f"📊 LAST {r['days']} DAYS ({r['since']} → today)",
           f"   pins posted: {r['posts']} (all time {r['posts_total']}) · "
           f"queue: {r['queue']} · failed: {r['failed']}",
           f"   clicks: {r['clicks']} (all time {r['clicks_total']}) · "
           f"subscribers: {r['subscribers']}"]
    if r["by_store"]:
        mix = ", ".join(f"{k} {v}" for k, v in sorted(r["by_store"].items(),
                                                      key=lambda kv: -kv[1]))
        out.append(f"   store mix: {mix}")
    if r["best_hour_utc"] is not None:
        out.append(f"   best hour (UTC {r['best_hour_utc']}:00) · "
                   f"best weekday: {r['best_weekday']}")
    if r["top_pins"]:
        out.append("   🏆 top pins:")
        for p in r["top_pins"]:
            out.append(f"      {p['clicks']:>4} · {p['title']}")
    if r["paused"]:
        out.append("   ⏸ posting is PAUSED (bot resume to start again)")
    out.extend(earnings.report_lines(cfg, r["earnings"]))
    return out


def send_telegram(cfg, text: str) -> bool:
    """Push the report to the owner's Telegram (optional, never raises)."""
    try:
        from .notify import Notifier
        return bool(Notifier().send(text[:4000]))
    except Exception:  # noqa: BLE001
        return False
