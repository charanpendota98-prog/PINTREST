"""Readiness — the honest answer to "naaku em cheyyali migilindi?".

Splits work into exactly two buckets:

* **YOU (one time)** — the handful of things that physically cannot be
  automated because they need *your* login/identity/OTP: create the Pinterest
  app, click ALLOW, paste affiliate IDs, and (optional) IG/FB/YouTube tokens.
* **BOT (forever)** — everything else, listed explicitly so the owner can see
  what runs unattended.

Every check reads real state (config/env/token files/permissions), never a
guess, and each unfinished item carries the exact command or URL to fix it.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import health

# ------------------------------------------------------------------ checks
def _item(key: str, label: str, done: bool, how: str = "", optional: bool = False,
          minutes: int = 3, recommended: bool = False) -> dict:
    return {"key": key, "label": label, "done": bool(done), "how": how,
            "optional": bool(optional), "minutes": int(minutes),
            "recommended": bool(recommended)}


def checks(cfg) -> list[dict]:
    """Every one-time item, with real completion state. Never raises."""
    import os
    try:
        return _checks(cfg, os)
    except Exception:  # noqa: BLE001 — a broken config must not break readiness
        return [_item("config", "Config readable (config.yaml)", False,
                      "check config.yaml (python -m bot doctor)", minutes=2)]


def _checks(cfg, os) -> list[dict]:

    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    items: list[dict] = []

    items.append(_item(
        "env", ".env file created (one click)",
        env_path.exists(),
        "python -m bot setup   (creates it for you)", minutes=1))
    items.append(_item(
        "pinterest_app", "Pinterest app ID + secret",
        bool(cfg.pinterest_app_id and cfg.pinterest_app_secret),
        "1) Business account lo 'Describe your business' → pick 'Content creator'\n"
        "   Goals: Increase online sales + Drive traffic to your site + "
        "Create content | Brand focus: Home\n"
        "2) developers.pinterest.com/apps → create app → copy into .env "
        "(or: python -m bot setup)", minutes=4))
    items.append(_item(
        "pinterest_token", "Pinterest account connected (click ALLOW once)",
        cfg.token_path.exists(),
        "python -m bot auth-url  →  paste code:\n"
        "python -m bot auth --code <CODE>", minutes=3))

    money_any = bool(cfg.amazon_tag or cfg.get("affiliate.meesho_affid")
                     or cfg.get("affiliate.earnkaro_prefix")
                     or cfg.get("affiliate.cuelinks_template")
                     or cfg.get("affiliate.meesho_template_link"))
    items.append(_item(
        "money", "At least ONE affiliate ID (this is the money link)",
        money_any,
        "Amazon tag / Meesho affid / EarnKaro / Cuelinks → .env "
        "(python -m bot setup walks you through it)", minutes=4))
    items.append(_item(
        "meesho_direct", "Meesho af_invite link (recommended: direct commission)",
        bool(os.getenv("MEESHO_TEMPLATE_LINK")
             or cfg.get("affiliate.meesho_template_link")),
        "affiliate.meesho.com → create ONE af_invite link → "
        ".env MEESHO_TEMPLATE_LINK (used verbatim, never rewritten)",
        minutes=3, optional=True, recommended=True))
    items.append(_item(
        "amazon_tag", "Amazon Associates tag (for Amazon pins)",
        bool(cfg.amazon_tag), "affiliate-program.amazon.in → your tag → .env",
        minutes=2, optional=True, recommended=True))

    try:
        from . import claim as _claim
        claimed = bool(_claim.token_of(cfg))
    except Exception:  # noqa: BLE001
        claimed = False
    items.append(_item(
        "website_claim", "Claim your Pinterest website (Rich Pins + attribution)",
        claimed,
        "after deploy, with a domain: Pinterest → Settings → Claimed accounts → "
        "Claim website → copy the token → python -m bot claim <token>",
        optional=True, recommended=True, minutes=3))

    items.append(_item(
        "instagram", "Instagram Business token (optional)",
        bool(os.getenv("INSTAGRAM_ACCESS_TOKEN") and os.getenv("IG_USER_ID")),
        "README → Instagram Automation (Meta app + token)", optional=True,
        minutes=8))
    items.append(_item(
        "facebook", "Facebook Page token (optional)",
        bool(os.getenv("FACEBOOK_ACCESS_TOKEN") and os.getenv("FACEBOOK_PAGE_ID")),
        "README → Facebook Page setup", optional=True, minutes=6))
    items.append(_item(
        "youtube", "YouTube Shorts upload (optional)",
        bool(os.getenv("YT_CLIENT_ID") and os.getenv("YT_CLIENT_SECRET")),
        "python -m bot yt-auth-url  (then yt-auth --code)", optional=True,
        minutes=6))

    # free wins — these are already done by the bot, shown for completeness
    pw = (root / "data" / "dashboard_password.txt").exists()
    items.append(_item(
        "panel_password", "Panel password (auto-created by the bot)", pw,
        "python -m bot dashboard-pass", minutes=0))

    try:
        secrets = health.audit_secrets(cfg)
        bad = [s for s in secrets if s.get("exists") and not s.get("ok")]
        items.append(_item(
            "secrets", "Credential files private (chmod 600)",
            not bad, "chmod 600 .env data/*.txt", minutes=1))
    except Exception:  # noqa: BLE001 — readiness must never crash
        pass

    try:
        data_dir = Path(cfg.db_path).parent
        write_ok = (data_dir.exists()
                    and shutil.disk_usage(str(data_dir)).free > 1 << 20)
    except Exception:  # noqa: BLE001 — readiness must never raise
        data_dir, write_ok = Path("data"), False
    items.append(_item(
        "storage", "Data folder writable + disk free",
        write_ok, "check permissions on data/", minutes=1))
    return items


def summary(cfg) -> dict:
    """Percent + honest to-do list + time estimate."""
    items = checks(cfg)
    you = [i for i in items if not i["done"] and not i["optional"]]
    optional = [i for i in items if not i["done"] and i["optional"]]
    recommended = [i for i in optional if i.get("recommended")]
    optional = [i for i in optional if not i.get("recommended")]
    required = [i for i in items if not i["optional"]]
    done_required = [i for i in required if i["done"]]
    pct = int(round(100 * len(done_required) / max(1, len(required))))
    ready = not you
    return {
        "items": items,
        "you_must_do": you,
        "recommended_left": recommended,
        "optional_left": optional,
        "percent": pct,
        "ready": ready,
        "minutes_left": sum(i["minutes"] for i in you),
        "automatic": automatic_lines(),
    }


def automatic_lines() -> list[str]:
    """What the bot does with zero human involvement (the actual product)."""
    return [
        "hunts top products by itself (radar: score 0-100, queue-low → auto-hunt)",
        "writes keyword-rich pins + reels + IG carousels + YouTube Shorts",
        "inserts YOUR affiliate link on every pin/post/description/comment",
        "QA gate before every post (media, link, title, description, #ad, dupes)",
        "posts on a human-like schedule inside your proven hours",
        "tracks clicks per pin/hour/day/pin-template and re-posts winners",
        "learns the winning hook style and posts more of what works",
        "keeps the feed varied (no 3 same-topic posts in a row)",
        "circuit breaker: pauses itself on token/rate-limit problems",
        "daily cap + quiet hours so it never looks like spam",
        "auto-replies on Instagram with the exact product + buy link",
        "daily self-audit: link health, secrets, breaker, queue — in the log",
        "weekly report (bot report --telegram) ready to send to your phone",
    ]


def lines(cfg) -> list[str]:
    """CLI rendering — answer the question in one screen."""
    s = summary(cfg)
    out = [f"🎯 READINESS: {s['percent']}% ready"
           + ("  — 🎉 EVERYTHING NEEDED IS SET" if s["ready"] else ""),
           "",
           "YOU DO (one time only):"]
    if not s["you_must_do"]:
        out.append("   ✅ nothing left — you are done, forever")
    for i in s["you_must_do"]:
        out.append(f"   ❌ {i['label']}  (~{i['minutes']} min)")
        for line in str(i["how"]).splitlines():
            out.append(f"        → {line}")
    if s["recommended_left"]:
        out.append("")
        out.append("RECOMMENDED (money-optimizing, not required to run):")
        for i in s["recommended_left"]:
            out.append(f"   ⭐ {i['label']}  (~{i['minutes']} min)")
            for line in str(i["how"]).splitlines():
                out.append(f"        → {line}")
    if s["optional_left"]:
        out.append("")
        out.append("OPTIONAL (skip if you don't want that platform):")
        for i in s["optional_left"]:
            out.append(f"   ○ {i['label']}  → {str(i['how']).splitlines()[0]}")
    out.append("")
    out.append(f"BOT DOES (forever, no humans — {len(s['automatic'])} items):")
    out.extend(f"   🤖 {line}" for line in s["automatic"])
    out.append("")
    if s["ready"]:
        out.append("▶️  Next: sudo ./deploy.sh   (24×7)  — malli nuvvu em cheyyalsina "
                   "pani ledu")
    else:
        out.append(f"⏱  ~{s['minutes_left']} minutes of YOUR time, one time. "
                   f"Tarvata: sudo ./deploy.sh")
    return out
