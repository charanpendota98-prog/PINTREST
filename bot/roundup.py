"""Deals-of-the-Day roundups — the list-post strategy top channels use.

Single pin = many products ("Top 5 Kitchen Finds Under ₹499", "Ladies
Special Deals Today"). Pinterest LOVES list pins; buyers save them, the
pin links to a full deals page where every item carries its affiliate link.

Segments mirror the audience that dominates Pinterest (women-first:
fashion, beauty, home, kitchen, kids) — exactly what top pages push.
"""
from __future__ import annotations

import random
from datetime import datetime

SEGMENTS = {
    "ladies": {
        "label": "Ladies Special ✨",
        "kw": ("kurta", "saree", "dress", "gown", "makeup", "beauty", "lipstick",
               "jewellery", "earring", "handbag", "kurti", "women", "ladies",
               "dupatta", "heels", "nail"),
        "title": "Top {n} Deals for Ladies Today ✨",
    },
    "home": {
        "label": "Home & Kitchen 🏠",
        "kw": ("kitchen", "decor", "organizer", "storage", "home", "curtain",
               "wall", "lamp", "container", "rack", "cookware", "dinner set"),
        "title": "{n} Home & Kitchen Finds Everyone's Saving 🏠",
    },
    "kids": {
        "label": "Kids Corner 🧸",
        "kw": ("kids", "baby", "toys", "children", "infant", "school bag"),
        "title": "{n} Cute & Useful Kids Picks 🧸",
    },
    "gadgets": {
        "label": "Gadget Deals 📱",
        "kw": ("earbuds", "smartwatch", "charger", "speaker", "phone", "headphone",
               "trimmer", "powerbank", "gadget"),
        "title": "{n} Gadgets Under Budget Right Now 📱",
    },
}

# seasonal pulse — what's hot this time of year (deep-level trend thinking)
SEASONAL = {
    (9, 10): ("festive", "Festive picks"),
    (11, 12): ("winter+gifting", "Gifting picks"),
    (1, 2): ("new year", "New-year picks"),
    (3, 4): ("summer", "Summer essentials"),
    (5, 6): ("summer", "Summer picks"),
    (7, 8): ("monsoon", "Monsoon picks"),
}


def segment_for(title: str) -> str:
    low = title.lower()
    for seg, info in SEGMENTS.items():
        if any(k in low for k in info["kw"]):
            return seg
    return "ladies" if any(w in low for w in ("floral", "printed", "fashion")) else "home"


def trending_tag(now: datetime) -> str:
    """Season-aware hook line for roundup pins/posts."""
    for months, (_, tag) in SEASONAL.items():
        if now.month in months:
            return tag
    return "🔥 Trending today"


def roundup_title(segment: str, n: int, now: datetime) -> str:
    info = SEGMENTS.get(segment, SEGMENTS["home"])
    base = info["title"].format(n=n)
    return f"{base} · {trending_tag(now)}"


def pick_roundup(products: list[dict], segment: str | None, n: int = 5) -> list[dict]:
    """Best-N products for a list pin: segment match first, then score."""
    def key(p: dict):
        seg_ok = 0 if (segment and segment_for(p.get("title", "")) == segment) else 1
        return (seg_ok, -int(p.get("score", 0) or 0))
    pool = [p for p in products if p.get("pin_image") or p.get("image_path")]
    random.shuffle(pool)          # tie-break variety → fresh list pins daily
    pool.sort(key=key)
    return pool[:n]
