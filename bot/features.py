"""Feature inventory — "em features vunnayi, em add cheyochu" in one table.

Prints every capability of the machine with its live status (ON / OFF /
NOT-CONFIGURED) and how to enable it. When a platform ships a new feature
(e.g. Meesho opens an API, Pinterest adds carousel pins), add ONE entry to
FEATURES + the code — the inventory, doctor and README stay in sync.
"""
from __future__ import annotations

import os

FEATURES = [
    # (name, category, what it does, enablement check, how to enable)
    ("Pinterest posting", "posting", "official API pins + video pins + boards",
     lambda cfg: bool(os.getenv("PINTEREST_ACCESS_TOKEN", "")),
     "PINTEREST_ACCESS_TOKEN in .env"),
    ("Instagram posting", "posting", "reels/carousel via official Graph API",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "instagram.enabled=true + INSTAGRAM_ACCESS_TOKEN, IG_USER_ID"),
    ("Facebook Page posting", "posting", "photo/link posts on your FB Page",
     lambda cfg: bool(os.getenv("FACEBOOK_ACCESS_TOKEN", "")),
     "facebook.enabled=true + FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID"),
    ("Telegram alerts", "reach", "posted/daily reports to your chat",
     lambda cfg: bool(os.getenv("TELEGRAM_TOKEN", "")),
     "TELEGRAM_TOKEN + TELEGRAM_CHAT_ID (optional)"),
    ("Auto-reels + voiceover", "content", "video from photos + TTS (en/hi/te)",
     lambda cfg: bool(cfg.get("video.auto_reel", True)),
     "video.auto_reel (default on)"),
    ("Your videos / your audio", "content", "your uploads beat auto-generated",
     lambda cfg: True,
     "dashboard 🎬/🎵 uploads → data/videos, data/music"),
    ("Original BGM composer", "content", "copyright-free music auto-generated",
     lambda cfg: bool(cfg.get("video.auto_music", True)),
     "video.auto_music (default on)"),
    ("Winner-clone sourcing", "sourcing", "top-channel niches auto-hunted",
     lambda cfg: bool(cfg.get("autopilot.auto_source", True)),
     "autopilot.auto_source (default on)"),
    ("Cross-store media enrichment", "sourcing", "same product media from other stores",
     lambda cfg: True, "automatic"),
    ("Commission-priority queue", "money", "highest-paying network posts first",
     lambda cfg: True, "automatic (COMMISSION_EST)"),
    ("Bridge landing pages", "money", "/go/<id> → landing → affiliate link",
     lambda cfg: bool(cfg.get("link.bridge", False)),
     "link.bridge=true + link.public_base=https://yourdomain"),
    ("Email capture", "money", "buyer list on every landing page",
     lambda cfg: bool(cfg.get("link.landing", True)),
     "automatic with landing pages"),
    ("Pin-by-Pin QA gate", "safety", "broken content never posts",
     lambda cfg: True, "automatic"),
    ("Warm-up ramp + jitter", "safety", "anti-flag volume ramping",
     lambda cfg: True, "automatic"),
    ("IG 'link' auto-replies", "engagement", "answers link? comments (capped+delayed)",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "with Instagram + instagram_manage_comments scope"),
    ("IG ManyChat-grade auto-DM", "engagement", "keyword DMs → product + buy link",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "instagram_manage_messages scope; instagram.auto_dm"),
    ("Meesho DIRECT af_invite", "money", "bot builds links with your IDs",
     lambda cfg: bool(os.getenv("MEESHO_TEMPLATE_LINK", "") or
                      cfg.get("affiliate.meesho_template_link", "")),
     "paste one af_invite link → MEESHO_TEMPLATE_LINK"),
    ("Deals-of-the-Day roundups", "growth", "daily list pins + /deals/today page",
     lambda cfg: bool(cfg.get("roundup.enabled", True)), "roundup.enabled"),
    ("Winners rotation", "growth", "proven pins re-posted as fresh designs",
     lambda cfg: True, "automatic (reshare.*)"),
    ("CTR hour learning", "growth", "dense posting in proven hours",
     lambda cfg: True, "automatic after ≥10 clicks"),
]


def report(cfg) -> list[dict]:
    rows = []
    for name, cat, what, check, how in FEATURES:
        try:
            on = bool(check(cfg))
        except Exception:  # noqa: BLE001
            on = False
        rows.append({"name": name, "category": cat, "what": what,
                     "status": "ON" if on else "OFF", "how": how})
    return rows


def print_report(cfg) -> None:
    print("\n🔎 FEATURE INVENTORY — every capability + its live status\n")
    cats: dict[str, list[dict]] = {}
    for r in report(cfg):
        cats.setdefault(r["category"], []).append(r)
    for cat, rows in cats.items():
        print(f"  ── {cat.upper()} " + "─" * max(0, 40 - len(cat)))
        for r in rows:
            mark = "✅" if r["status"] == "ON" else "⚪"
            print(f"  {mark} {r['name']:<32} {r['what']}")
            if r["status"] == "OFF":
                print(f"      ↳ enable: {r['how']}")
    n_on = sum(1 for r in report(cfg) if r["status"] == "ON")
    print(f"\n  {n_on}/{len(FEATURES)} features active. New platform feature "
          "releases → one entry in bot/features.py + code → inventory updates.\n")
