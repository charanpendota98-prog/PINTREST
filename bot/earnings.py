"""Honest earnings estimator — what the traffic is actually worth.

No fake dashboards: this multiplies real click numbers by ASSUMPTIONS the
owner can see and change in config. The output always prints the assumptions,
because an estimate without its assumptions is a lie.

Config (all optional, sensible Indian defaults):
    money.click_to_order: 0.02     # 2% of clicks become orders
    money.aov: 599                 # average order value, ₹
    money.rates: {meesho: 8, amazon: 3, flipkart: 5, cuelinks: 6, earnkaro: 6}
    money.confirm_days: 45         # payout confirmation cycle (cash timing)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEFAULT_RATES = {"meesho": 8.0, "amazon": 3.0, "flipkart": 5.0,
                 "cuelinks": 6.0, "earnkaro": 6.0, "ajio": 6.0, "myntra": 6.0}


def rates(cfg) -> dict[str, float]:
    out = dict(DEFAULT_RATES)
    raw = cfg.get("money.rates")
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k).lower()] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def assumptions(cfg) -> dict:
    return {
        "click_to_order": cfg.get_float("money.click_to_order", 0.02),
        "aov": cfg.get_float("money.aov", 599.0),
        "confirm_days": cfg.get_int("money.confirm_days", 45),
    }


def estimate(cfg, rows: list[dict]) -> dict:
    """rows = posts with 'clicks' and 'source'. Returns per-network numbers."""
    a = assumptions(cfg)
    r = rates(cfg)
    per: dict[str, dict] = {}
    total_orders = total_gross = 0.0
    for row in rows or []:
        src = str((row or {}).get("source") or "other").lower()
        clicks = int((row or {}).get("clicks", 0) or 0)
        if clicks <= 0:
            per.setdefault(src, {"clicks": 0, "orders": 0.0, "gross": 0.0,
                                 "rate": r.get(src, 5.0)})
            per[src]["clicks"] += clicks
            continue
        orders = clicks * a["click_to_order"]
        gross = orders * a["aov"]
        rate = r.get(src, 5.0)
        bucket = per.setdefault(src, {"clicks": 0, "orders": 0.0, "gross": 0.0,
                                      "rate": rate})
        bucket["clicks"] += clicks
        bucket["orders"] += orders
        bucket["gross"] += gross
        total_orders += orders
        total_gross += gross
    commission = 0.0
    for src, b in per.items():
        b["commission"] = round(b["gross"] * b["rate"] / 100.0, 2)
        b["orders"] = round(b["orders"], 2)
        b["gross"] = round(b["gross"], 2)
        commission += b["commission"]
    confirm = datetime.now(timezone.utc) + timedelta(days=a["confirm_days"])
    return {
        "clicks": sum(b["clicks"] for b in per.values()),
        "orders": round(total_orders, 2),
        "gross": round(total_gross, 2),
        "commission": round(commission, 2),
        "per_network": per,
        "assumptions": a,
        "expected_payout_on": confirm.date().isoformat(),
        "disclaimer": ("Estimate only — based on the click numbers in your DB "
                       "and the assumptions above, not platform-reported sales."),
    }


def click_rows_since(db, days: int = 30) -> list[dict]:
    """Posted products with clicks, within the window (best-effort)."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))
                  ).date().isoformat()
        # the posts table has posted_at (not created_at) — and a pending post
        # still counts for the window via its scheduled_for
        rows = [p for p in db.recent_posts(limit=1000)
                if str(p.get("posted_at") or p.get("scheduled_for") or "")[:10]
                >= cutoff]
    except Exception:  # noqa: BLE001 — analytics must never break a run
        return []
    return rows


def report_lines(cfg, est: dict) -> list[str]:
    a = est["assumptions"]
    lines = [f"💰 ESTIMATE — {est['clicks']} clicks → "
             f"~{est['orders']:.1f} orders → ~₹{est['commission']:.0f} commission",
             f"   assumptions: {a['click_to_order'] * 100:.1f}% clicks→orders, "
             f"₹{a['aov']:.0f} avg order, payout ~{a['confirm_days']} days "
             f"(≈{est['expected_payout_on']})"]
    for src, b in sorted(est["per_network"].items(),
                         key=lambda kv: -kv[1]["commission"]):
        lines.append(f"   • {src:<9} {b['clicks']:>5} clicks · rate {b['rate']}% "
                     f"· ~₹{b['commission']:.0f}")
    lines.append(f"   ⚠️  {est['disclaimer']}")
    return lines
