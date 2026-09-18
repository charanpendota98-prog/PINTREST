"""Topic buckets + feed variety — stop the bot from looking like a spam feed.

Marketer reality: five "kitchen storage organizer" pins back-to-back reads as
spam to both Pinterest's ranking and to humans scrolling your profile. Real
channels rotate categories. This module keeps that promise:

* `bucket(title)` -> coarse topic (kitchen, beauty, fashion, festive, ...)
* `order_for_variety(rows, recent_titles)` -> prefers a product from a
  DIFFERENT bucket when the last `max_run` posts were all the same topic.
* `allows_more(...)` -> hunt-time guard so a single hunt cannot queue the
  queue full of one topic.

Pure functions, no I/O — easy to test.
"""
from __future__ import annotations

BUCKETS: dict[str, tuple[str, ...]] = {
    "kitchen": ("kitchen", "storage", "organizer", "organiser", "container",
                "spice", "cookware", "bottle", "chopper", "peeler", "gadget",
                "utensil", "lunch", "tiffin", "mug", "flask", "sink"),
    "home_decor": ("decor", "wall", "light", "lamp", "curtain", "cushion",
                   "rug", "clock", "frame", "vase", "mat", "bedsheet",
                   "pillow", "mirror", "shelf", "planter"),
    "beauty": ("serum", "cream", "sunscreen", "lipstick", "makeup", "hair",
               "oil", "perfume", "skin", "face", "kajal", "eyeliner",
               "shampoo", "scrub", "body"),
    "fashion": ("kurta", "saree", "dress", "jeans", "shirt", "lehenga",
                "ethnic", "kurti", "top", "palazzo", "dupatta", "suit",
                "hoodie", "tshirt", "t-shirt"),
    "jewellery": ("earring", "necklace", "bangle", "ring", "jewellery",
                  "jewelry", "watch", "anklet", "chain", "pendant"),
    "kids": ("toy", "kids", "baby", "school", "puzzle", "doll", "game",
             "newborn"),
    "electronics": ("earbud", "earphone", "headphone", "charger", "cable",
                    "powerbank", "speaker", "smartwatch", "buds", "trimmer",
                    "mouse", "keyboard"),
    "festive": ("diya", "rangoli", "pooja", "puja", "christmas", "gift",
                "rakhi", "holi", "gulal", "fairy", "string light", "toran"),
    "bags": ("bag", "wallet", "backpack", "purse", "sling", "luggage"),
}

GENERAL = "general"


def bucket(title: str) -> str:
    """Coarse topic of a product title (never raises, never empty)."""
    t = str(title or "").lower()
    for name, words in BUCKETS.items():
        if any(w in t for w in words):
            return name
    return GENERAL


def order_for_variety(rows: list[dict], recent_titles: list[str] | None = None,
                      max_run: int = 2) -> list[dict]:
    """Stable-reorder so we don't post `max_run`+ items of one topic in a row.

    Only the *head* of the list changes: everything else keeps its score order.
    """
    rows = list(rows or [])
    if len(rows) < 2:
        return rows
    recents = [bucket(t) for t in (recent_titles or [])][-max_run:]
    if (len(recents) < max_run or len(set(recents)) != 1
            or recents[0] == GENERAL):
        return rows                       # run broken already / unknown topic
    blocked = recents[0]
    fresh = [r for r in rows if bucket(r.get("title", "")) != blocked]
    stale = [r for r in rows if bucket(r.get("title", "")) == blocked]
    if not fresh:
        return rows                       # nothing else queued — post anyway
    return fresh + stale


def allows_more(bucket_name: str, queued_buckets: list[str],
                existing_queue: list[str] | None = None,
                max_per_bucket: int = 3) -> bool:
    """Hunt-time guard: at most `max_per_bucket` of one topic in the queue."""
    if bucket_name == GENERAL:
        return True
    have = [(existing_queue or []).count(bucket_name),
            (queued_buckets or []).count(bucket_name)]
    return max(have) < max_per_bucket


def bucket_counts(titles: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in titles or []:
        b = bucket(t)
        out[b] = out.get(b, 0) + 1
    return out
