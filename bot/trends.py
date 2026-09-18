"""Winner-clone intelligence — post what TOP channels post, FIRST.

Distilled from 2026 data on the highest-view Pinterest/Instagram affiliate
creators (see README "Winner Cloning"): the winning niches, in priority
order, with the exact search queries used to HUNT products in each niche
and a "winner score" that sorts your queue so the proven earners post first.

We clone the WINNING CATEGORIES & PRODUCT TYPES (data, not creative):
our pins/reels stay 100% original — copying someone's images/content gets
accounts banned; cloning the niche strategy is what pros actually do.
"""
from __future__ import annotations

import re

# priority 1 = what the biggest channels push hardest right now
WINNER_NICHES: list[dict] = [
    {
        "name": "Women's Fashion",
        "priority": 1,
        "kw": ("kurta", "saree", "dress", "fashion", "women", "ethnic", "suit",
               "dupatta", "leggings", "gown"),
        "queries": {
            "meesho": "women kurta set",
            "amazon": "women kurti",
            "flipkart": "women kurta",
        },
        "sweet_price": (199, 799),   # impulse-buy zone
    },
    {
        "name": "Home Decor & Organization",
        "priority": 2,
        "kw": ("decor", "organizer", "storage", "lamp", "led", "curtain",
               "bedsheet", "wall", "kitchen rack", "showpiece"),
        "queries": {
            "amazon": "home decor items",
            "meesho": "home decor",
            "flipkart": "home decor",
        },
        "sweet_price": (199, 999),
    },
    {
        "name": "Beauty & Skincare",
        "priority": 3,
        "kw": ("serum", "sunscreen", "cream", "facewash", "makeup", "lipstick",
               "skincare", "beauty", "hair oil", "shampoo"),
        "queries": {
            "amazon": "face serum",
            "flipkart": "sunscreen",
            "meesho": "makeup",
        },
        "sweet_price": (149, 699),
    },
    {
        "name": "Tech Gadgets & Accessories",
        "priority": 4,
        "kw": ("earbuds", "smart watch", "headphone", "speaker", "charger",
               "mobile holder", "smartwatch", "trimmer", "gadget"),
        "queries": {
            "amazon": "wireless earbuds under 1000",
            "flipkart": "smart watch",
        },
        "sweet_price": (499, 1499),
    },
    {
        "name": "Kitchen Tools",
        "priority": 5,
        "kw": ("kitchen", "chopper", "bottle", "lunch box", "cookware",
               "vegetable cutter", "flask", "container"),
        "queries": {
            "amazon": "kitchen gadgets",
            "meesho": "kitchen accessories",
            "flipkart": "kitchen tools",
        },
        "sweet_price": (149, 899),
    },
    {
        "name": "Jewellery & Accessories",
        "priority": 6,
        "kw": ("jewellery", "earrings", "necklace", "bracelet", "bag", "watch",
               "sunglasses", "wallet"),
        "queries": {
            "meesho": "earrings",
            "amazon": "artificial jewellery",
            "flipkart": "handbag",
        },
        "sweet_price": (99, 599),
    },
    {
        "name": "Kids & Baby",
        "priority": 7,
        "kw": ("kids", "baby", "toy", "school bag", "children"),
        "queries": {
            "amazon": "toys for kids",
            "meesho": "kids dress",
            "flipkart": "toys",
        },
        "sweet_price": (199, 999),
    },
    {
        "name": "Fitness & Wellness",
        "priority": 8,
        "kw": ("yoga", "gym", "fitness", "protein", "massage", "bottle gym"),
        "queries": {
            "amazon": "yoga mat",
            "flipkart": "gym accessories",
        },
        "sweet_price": (199, 1299),
    },
]

HOOKY_WORDS = ("viral", "trending", "new", "best", "combo", "pack of")

# Deep-level money thinking: expected commission % per network (typical).
# Higher rate = posts earlier = more money per click. (Meesho lifestyle pays
# the most in India — so Meesho products jump the queue automatically.)
COMMISSION_EST = {
    "meesho": 10,   # 3–15%, lifestyle/fashion sweet spot
    "amazon": 7,    # 1–10% by category, strong on gadgets/home
    "flipkart": 5,
    "earncaro": 4,  # multi-store aggregator
    "cuelinks": 4,
}


def niche_for(title: str) -> dict | None:
    low = title.lower()
    for n in WINNER_NICHES:
        if any(k in low for k in n["kw"]):
            return n
    return None


def score_product(title: str, price: str, source: str) -> int:
    """Winner score — higher posts first.

      niche priority (top channels' niches)   0-8
      price in impulse sweet-spot             +3
      hooky words in title                    +2
      store strength (meesho fashion etc.)    +1
    """
    s = 0
    n = niche_for(title)
    if n:
        s += (len(WINNER_NICHES) - n["priority"] + 1)  # 8..1
        lo, hi = n["sweet_price"]
        try:
            val = float(re.sub(r"[^\d.]", "", price.replace(",", "")) or 0)
            if val and lo <= val <= hi:
                s += 3
        except ValueError:
            pass
    if any(w in title.lower() for w in HOOKY_WORDS):
        s += 2
    if source in ("meesho", "amazon"):
        s += 1
    # 💰 money-first: highest-paying network posts first
    s += COMMISSION_EST.get(source, 2)
    return s


def sourcing_plan(per_niche: int = 2) -> list[tuple[str, str, str]]:
    """Hunt order for autopilot: (store, query, niche_name) best niches first."""
    plan: list[tuple[str, str, str]] = []
    for n in sorted(WINNER_NICHES, key=lambda x: x["priority"]):
        for store, q in n["queries"].items():
            plan.append((store, q, n["name"]))
            if len([p for p in plan if p[2] == n["name"]]) >= per_niche:
                break
    return plan


def describe() -> str:
    lines = ["🏆 WINNER NICHES (what top channels push — priority order):"]
    for n in sorted(WINNER_NICHES, key=lambda x: x["priority"]):
        lo, hi = n["sweet_price"]
        lines.append(
            f"  {n['priority']}. {n['name']:<28} sweet price ₹{lo}-₹{hi}"
        )
    return "\n".join(lines)
