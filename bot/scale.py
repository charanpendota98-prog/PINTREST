"""Scale engine — the honest arithmetic behind a revenue target.

"Lakhs ravali" is a target, not a feature: it needs a number of clicks, which
needs a number of posts, which takes a number of months. This module turns the
target into those concrete numbers using the SAME funnel the earnings module
uses, then measures how far the account actually is.

Everything is computed from real DB numbers (clicks, posts, days active) plus
the configurable assumptions in `money.*` and `target.*`. Nothing here is a
promise: `plan()` prints the levers and the gap, and `recommend_posts_per_day()`
only suggests volume that the safety rails allow.

Config:
    target.monthly_commission: 100000   # ₹ per month
    target.months: 6                    # by when
    target.auto_scale: false            # let the bot raise volume itself
    target.ceiling_per_day: 30          # hard safety ceiling for auto-scale
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import earnings

STATE_KEY = "scale.posts_per_day"


def funnel(cfg, target_monthly: float | None = None) -> dict:
    """Target → orders → clicks → posts/day. Pure arithmetic, all visible.

    NOTE: the target is a STEADY-STATE monthly figure (₹/month), so needs are
    per month — dividing by the ramp months would understate them (real bug
    caught in self-review: it made ₹1L/month look 6x easier than it is).
    `months` is the ramp runway, not a divisor.
    """
    a = earnings.assumptions(cfg)
    rate_blend = blend_rate(cfg)
    if target_monthly is None:
        target_monthly = cfg.get_float("target.monthly_commission", 100000.0)
    months = max(1, cfg.get_int("target.months", 6))
    commission_per_order = a["aov"] * rate_blend / 100.0
    orders = target_monthly / max(0.01, commission_per_order)
    clicks = orders / max(0.0001, a["click_to_order"])
    return {
        "target_monthly": round(target_monthly, 2),
        "ramp_months": months,
        "blend_rate": round(rate_blend, 2),
        "commission_per_order": round(commission_per_order, 2),
        "orders_per_month": round(orders, 1),
        "clicks_per_month": round(clicks, 0),
        "clicks_per_day": round(clicks / 30.0, 1),
        "orders_per_day": round(orders / 30.0, 1),
        "assumptions": a,
    }


def blend_rate(cfg) -> float:
    """Weighted commission rate across the networks we actually post to."""
    r = earnings.rates(cfg)
    mix = {"meesho": 0.6, "amazon": 0.3, "flipkart": 0.1}
    total_w = 0.0
    acc = 0.0
    for net, w in mix.items():
        acc += r.get(net, 5.0) * w
        total_w += w
    return acc / max(0.0001, total_w)


def run_rate(db, cfg, days: int = 30) -> dict:
    """What the account is ACTUALLY doing right now (measured, not guessed)."""
    days = max(1, int(days))
    rows = earnings.click_rows_since(db, days=days)
    clicks = sum(int((p or {}).get("clicks", 0) or 0) for p in rows)
    posts = len(rows)
    est = earnings.estimate(cfg, rows)
    per_day_clicks = clicks / days
    per_day_posts = posts / days
    cpp = (clicks / posts) if posts else 0.0          # clicks per post
    monthly_clicks = per_day_clicks * 30.0
    return {
        "days": days,
        "posts": posts,
        "clicks": clicks,
        "posts_per_day": round(per_day_posts, 2),
        "clicks_per_day": round(per_day_clicks, 2),
        "clicks_per_post": round(cpp, 3),
        "monthly_commission": est["commission"],       # from the window
        "monthly_projection": round(est["commission"] / days * 30.0, 2),
    }


def gap(cfg, db, days: int = 30) -> dict:
    """Target vs reality: the gap, and how many posts/day would close it."""
    f = funnel(cfg)
    rr = run_rate(db, cfg, days=days)
    projected = rr["monthly_projection"]
    pct = (projected / f["target_monthly"] * 100.0) if f["target_monthly"] else 0.0
    cpp = rr["clicks_per_post"]
    needed_clicks_day = f["clicks_per_day"]
    posts_needed = (needed_clicks_day / cpp) if cpp > 0 else 0.0
    return {
        "target_monthly": f["target_monthly"],
        "projected_monthly": projected,
        "gap": round(max(0.0, f["target_monthly"] - projected), 2),
        "percent": round(min(999.0, pct), 1),
        "posts_per_day_now": rr["posts_per_day"],
        "posts_per_day_needed": round(posts_needed, 1),
        "clicks_per_post": cpp,
        "days_active": days_active(db),
        "funnel": f,
    }


def eta_months(cfg, db) -> float | None:
    """At the CURRENT growth rate, how many months to the target?

    Needs at least two weeks of data: clicks in the last 7 days vs the 7
    before. Returns None when it cannot be measured honestly (too little data
    or not growing).
    """
    try:
        recent = earnings.click_rows_since(db, days=7)
        prev_all = earnings.click_rows_since(db, days=14)
        prev_ids = {id(r) for r in recent}
        prev = [r for r in prev_all if id(r) not in prev_ids]
        c_now = sum(int((r or {}).get("clicks", 0) or 0) for r in recent)
        c_prev = sum(int((r or {}).get("clicks", 0) or 0) for r in prev)
    except Exception:  # noqa: BLE001
        return None
    if c_prev <= 0 or c_now <= c_prev:
        return None
    growth = c_now / c_prev                     # per week
    target_clicks = funnel(cfg)["clicks_per_day"] * 7.0
    if c_now >= target_clicks:
        return 0.0
    import math
    weeks = math.log(target_clicks / c_now) / math.log(growth)
    return round(weeks / 4.345, 1)


def days_active(db) -> int:
    try:
        oldest = db.oldest_activity()
        if not oldest:
            return 0
        return max(0, (datetime.now(timezone.utc) - oldest).days)
    except Exception:  # noqa: BLE001 — analytics must never crash
        return 0


def scenarios(cfg, targets: tuple[float, ...] = (25000, 50000, 100000),
              cvrs: tuple[float, ...] = (0.01, 0.02, 0.05)) -> list[dict]:
    """What-if table: target × conversion rate → clicks/day needed.

    Honest by construction: it shows that raising the conversion (better
    product match, bridge page) matters as much as raising the volume.
    """
    a = earnings.assumptions(cfg)
    rate = blend_rate(cfg) / 100.0
    out = []
    for target in targets:
        row = {"target": float(target), "clicks_per_day": {}}
        for cvr in cvrs:
            orders = float(target) / max(0.01, a["aov"] * rate)
            clicks = orders / max(0.0001, cvr)
            row["clicks_per_day"][f"{cvr * 100:.0f}%"] = round(clicks / 30.0, 1)
        out.append(row)
    return out


def recommend_posts_per_day(cfg, db, base: float | None = None) -> dict:
    """Safe suggested volume, never above the safety ceiling.

    Logic: once we know how many clicks one post earns (`clicks_per_post`), the
    required volume is just needed_clicks / cpp. We never suggest more than
    `target.ceiling_per_day` or `posting.max_per_day`, and we always keep at
    least today's volume (never scale DOWN automatically — that is the owner's
    call via the kill switch).
    """
    g = gap(cfg, db)
    ceiling = min(cfg.get_int("target.ceiling_per_day", 30),
                  max(1, cfg.get_int("posting.max_per_day", 25)))
    configured = base if base else cfg.get_int("posting.pins_per_day", 8)
    now = max(float(configured), float(g["posts_per_day_now"]))
    need = float(g["posts_per_day_needed"] or 0)
    if need <= 0:                      # no measured clicks yet — can't scale
        return {"suggested": int(min(ceiling, now)), "ceiling": ceiling,
                "reason": "no click data yet — keeping your configured volume"}
    if need <= now:
        return {"suggested": int(now), "ceiling": ceiling,
                "reason": "on track — current volume is enough"}
    suggested = min(ceiling, max(now, need))
    return {"suggested": int(round(suggested)), "ceiling": ceiling,
            "reason": f"need {need:.1f}/day for the target (ceiling {ceiling})"}


def apply_autoscale(db, cfg) -> int:
    """Persist a suggested volume when `target.auto_scale` is on. Returns it."""
    if not cfg.get_bool("target.auto_scale", False):
        return 0
    try:
        rec = recommend_posts_per_day(cfg, db)
        db.set_state(STATE_KEY, str(int(rec["suggested"])))
        return int(rec["suggested"])
    except Exception:  # noqa: BLE001 — scaling must never break a run
        return 0


def effective_per_day(db, cfg, base: int) -> int:
    """What the scheduler should actually use today (auto-scale aware)."""
    if not cfg.get_bool("target.auto_scale", False):
        return base
    try:
        scaled = int(db.get_state(STATE_KEY) or 0)
    except Exception:  # noqa: BLE001
        scaled = 0
    if scaled <= 0:
        return base
    ceiling = min(cfg.get_int("target.ceiling_per_day", 30),
                  max(1, cfg.get_int("posting.max_per_day", 25)))
    return max(1, min(ceiling, max(base, scaled)))


# ------------------------------------------------------------------ store mix
def mix_ok(store: str, queued_stores: list[str], max_share: float = 0.7,
           min_others: int = 1) -> bool:
    """Avoid a one-store queue: too much Meesho = payout + platform risk."""
    store = str(store or "").lower()
    if not store:
        return True
    counts: dict[str, int] = {}
    for s in queued_stores or []:
        counts[str(s).lower()] = counts.get(str(s).lower(), 0) + 1
    total = sum(counts.values())
    if total < 3:
        return True                      # too small a queue to matter
    share = counts.get(store, 0) / total
    if share < max_share:
        return True
    others = [k for k, v in counts.items() if k != store and v >= min_others]
    return not others                    # if we have other stores, prefer them


def mix_report(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows or []:
        s = str((r or {}).get("source") or "other").lower()
        counts[s] = counts.get(s, 0) + 1
    total = sum(counts.values()) or 1
    return {"counts": counts,
            "share": {k: round(v / total, 3) for k, v in counts.items()}}


def lines(cfg, db, days: int = 30) -> list[str]:
    """One-screen honest answer: where am I, what is missing, what to do."""
    g = gap(cfg, db, days=days)
    f = g["funnel"]
    rr = run_rate(db, cfg, days=days)
    rec = recommend_posts_per_day(cfg, db)
    a = f["assumptions"]
    eta = eta_months(cfg, db)
    out = [
        f"🎯 TARGET: ₹{f['target_monthly']:,.0f}/month "
        f"(ramp runway {f['ramp_months']} months)",
        f"   that needs ~{f['clicks_per_day']:.0f} clicks/day "
        f"(~{f['clicks_per_month']:,.0f}/month) at {a['click_to_order'] * 100:.1f}% "
        f"clicks→orders, ₹{a['aov']:.0f} avg order, {f['blend_rate']}% blended rate",
        f"   ≈ {f['orders_per_month']:.0f} orders/month, "
        f"≈ ₹{f['commission_per_order']:.0f} commission per order",
        "",
        f"📈 NOW (last {rr['days']}d): {rr['posts']} posts · {rr['clicks']} clicks "
        f"· {rr['clicks_per_post']} clicks/post · {rr['posts_per_day']}/day",
        f"   projected: ₹{rr['monthly_projection']:,.0f}/month "
        f"({g['percent']}% of target) · account age {g['days_active']}d",
        f"   gap: ₹{g['gap']:,.0f}/month",
    ]
    if eta is not None:
        out.append(f"   📈 at the CURRENT growth rate: ~{eta} months to target "
                   f"(if growth continues)" if eta > 0 else
                   "   📈 already at the target's click level!")
    else:
        out.append("   📈 growth ETA: not measurable yet (needs ~2 weeks of "
                   "click data)")
    if g["days_active"] < 45:
        out.append("   ⏳ month 1-2 = Pinterest indexing; low numbers now is "
                   "NORMAL, not a bug (honest expectation)")
    out.append("")
    out.append(f"🔧 LEVERS: posts/day now {g['posts_per_day_now']} → "
               f"needed {g['posts_per_day_needed']} (ceiling {rec['ceiling']})")
    out.append(f"   recommendation: {rec['suggested']}/day — {rec['reason']}")
    if not cfg.get_bool("target.auto_scale", False):
        out.append("   (turn on auto-scale: target.auto_scale: true — the bot "
                   "then raises volume itself as data comes in)")
    out.append("   what-if (clicks/day needed):")
    for row in scenarios(cfg):
        parts = " · ".join(f"{k}→{v:,.0f}" for k, v in
                           row["clicks_per_day"].items())
        out.append(f"     ₹{row['target']:,.0f}/mo: {parts}   "
                   f"(conversion %)")
    out.append("   • more IG/Story surfaces (list posts, reels, stories)")
    out.append("   • winners re-posted + price-drop re-announce (compounding)")
    out.append("   • variety guard keeps reach healthy at higher volume")
    out.append("")
    out.append("⚠️  These are arithmetic, not promises: sales depend on real "
               "buyers. Volume + time are the only honest levers.")
    return out
