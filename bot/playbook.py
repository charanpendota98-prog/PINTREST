"""Content playbook — HOW the top affiliate channels post, encoded.

Built from 2026 platform research (data, not opinion):

YouTube Shorts
  * viewers decide in the first 1.5-3s -> hook + product visible immediately
  * Problem-Agitate-Solve (PAS) framing converts ~3-4x better than pretty
    product shots ("I kept losing my keys until I found this ₹199 tracker")
  * MAX 3 products per Short — more than 3 tanks conversion
  * 15-30s sweet spot; 60% watch muted -> on-screen text carries the message
  * PINNED COMMENT with product context adds ~10-15% conversion
  * 3-5 relevant hashtags (broad + niche + branded)
  * India: Hinglish list hooks ("Top 3 gadgets that fix ... in 30s")

Instagram
  * Carousels = highest engagement (0.50-0.55%) and ~3x the saves of Reels;
    slide 1 carries ~80% of the engagement -> it must be a hook, not a logo
  * 8-10 slides is the sweet spot (engagement dips after slide 3, returns 8+)
  * 1080x1350 (4:5) portrait fills the most feed space
  * Reels = reach (33% reach rate, ~4.7x non-follower reach) -> discovery
  * a sensible mix: ~40% Reels, ~30% carousels, ~20% stories, ~10% feed
  * saves/shares are weighted ~3x -> always ask for the save
  * affiliate reality: link in bio + story link stickers + DM replies

Pinterest
  * keyword-first titles/descriptions, 5-15 pins/day, 1000x1500
  * list/roundup pins ("Top 5 under ₹499") earn the saves that compound

Everything here is deterministic and offline — captions/hooks never depend on
a network call, so posting can never fail because a caption could not load.
"""
from __future__ import annotations

import random
import re

# --------------------------------------------------------------- limits
YOUTUBE_MAX_PRODUCTS = 3          # >3 tanks conversion (platform research)
IG_CAROUSEL_SLIDES = (8, 10)      # sweet spot
PINTEREST_PIN_DAYS = (5, 15)      # pins/day band for a healthy account
HASHTAG_COUNT = (3, 5)            # YouTube: 3-5 relevant tags

# Best-practice posting windows (local time, IST for this repo). Scheduler
# already has PEAK windows; these are the per-platform refinements.
BEST_TIMES = {
    "pinterest": [(20, 23), (6, 8)],        # evening scroll + early morning
    "instagram": [(11, 13), (19, 22)],      # lunch + prime evening
    "youtube": [(17, 21), (7, 9)],          # after-school/work + commute
    "facebook": [(12, 14), (20, 22)],
}

# Hooks by archetype. {kw} = product keyword, {price} = price label.
PAS_HOOKS = [
    "{kw} valla daily thala noppi? Ee {price} fix chusuko.",
    "Every time you {pain}, you lose time you never get back. This {price} one ends it.",
    "{kw} ni inka adjust chestunnara? Chusandi idi — {price}.",
    "You do not need a bigger house, you need this {price} {kw}.",
    "3 years ga ilaage undi… {price} tho idi oke roju lo fix.",
]

LIST_HOOKS = [
    "Top {n} {kw} under {price} — evaru chusina 'idi kavali' antaru.",
    "{n} {kw} that actually work (not the useless ones).",
    "Stop scrolling — {n} best {kw} in {price} range, tested.",
    "{n} things you will use EVERY day (all under {price}).",
]

POV_HOOKS = [
    "POV: nee intlo space chala takkuva… idi chudu.",
    "POV: nuvvu {kw} konali anukuntunnav kani price bhayam? {price}.",
    "POV: guest vastunnaru, 5 minutes lo intlo set ayipovali.",
]

SAVE_CTA = ("💾 Save this — you'll need it when the price drops again. "
            "Share it with the one friend who needs it.")
BIO_CTA = "🔗 Full list + live prices in bio (updated daily)"
YT_PINNED = ("Products in this Short (live prices + full list):\n"
             "{lines}\n\n"
             "Save this comment — deals change daily.")

# Problem keywords → the real-life pain we name in PAS hooks.
PAIN_MAP = {
    "organizer": "hunt for the same thing every morning",
    "storage": "run out of shelf space while cooking",
    "rack": "run out of counter space in the kitchen",
    "holder": "dig through a messy drawer",
    "clean": "scrub the same stains every weekend",
    "kitchen": "fight the mess every time you cook",
    "makeup": "dig for one lipstick for ten minutes",
    "bag": "carry three bags to carry one thing",
    "kurta": "iron everything before every function",
    "saree": "struggle with pleats every single time",
    "jewel": "untangle your chains and rings",
    "serum": "try everything and still see dull skin",
    "hair": "fight frizz every single morning",
    "shoe": "get foot pain after two hours standing",
    "bottle": "buy water bottles every month",
    "charger": "stand next to a plug all evening",
    "bedsheet": "refold the same crumpled bedsheet",
    "curtain": "stare at the same boring curtains",
    "toy": "step on the same toys every night",
    "lunch": "waste money eating outside every day",
    "cable": "untangle a cable nest before charging",
}


def _kw(title: str) -> str:
    """Short human keyword from a product title (for hook lines)."""
    words = re.sub(r"[^A-Za-z0-9 ]", " ", (title or "").lower()).split()
    stop = {"for", "with", "and", "the", "set", "of", "pack", "pcs", "new",
            "women", "men", "girls", "boys", "buy", "best", "1", "2", "3"}
    keep = [w for w in words if w not in stop and len(w) > 2]
    return " ".join(keep[:3]) or (words[0] if words else "deal")


def pain_for(title: str) -> str:
    """The relatable pain line used by PAS hooks ('' when unknown)."""
    low = (title or "").lower()
    for key, pain in PAIN_MAP.items():
        if key in low:
            return pain
    return ""


def hook_line(title: str, price: str = "", archetype: str = "",
              seed: int | None = None) -> str:
    """One scroll-stopping first line. Deterministic when `seed` is given.

    `archetype`: pas | list | pov | auto (default). Falls back gracefully so a
    caption can never crash on an odd title.
    """
    rng = random.Random(seed) if seed is not None else random
    kw = _kw(title)
    pain = pain_for(title)
    price = (price or "").strip() or "₹299"
    if archetype in ("", "auto"):
        archetype = "pas" if pain else "list"
    if archetype == "pas" and pain:
        line = rng.choice(PAS_HOOKS)
        line = line.replace("{pain}", pain)
    elif archetype == "pov":
        line = rng.choice(POV_HOOKS)
    else:
        line = rng.choice(LIST_HOOKS).replace("{n}", str(rng.choice([3, 5, 7])))
    return line.replace("{kw}", kw).replace("{price}", price).strip()


def onscreen_text(title: str, price: str, seed: int | None = None) -> list[str]:
    """Text overlays for a muted-first Short (60% watch without sound).

    Research rule: 3-5 words per card, big and readable on a phone. Frame 0
    carries the promise; later cards carry the payoff and the price.
    """
    kw = _kw(title)
    priced = (price or "").strip() or "₹299"
    words = kw.split()
    short_kw = " ".join(words[:3]).title() if len(" ".join(words[:3])) <= 22 \
        else " ".join(words[:2]).title()
    short_kw = short_kw or "This find"
    pain = pain_for(title)
    # 2-3 word pain label (overlay text, not a sentence)
    pains = {
        "hunt": "No more hunting",
        "run out": "No more clutter",
        "dig": "Stop digging",
        "scrub": "Half the cleaning",
        "fight the mess": "Mess-free cooking",
        "struggle": "2-minute fix",
        "iron": "No ironing",
        "untangle": "Zero tangles",
        "dull skin": "Glow daily",
        "frizz": "Frizz-free hair",
        "foot pain": "All-day comfort",
        "buy water": "Buy once",
        "stand next to a plug": "Charge anywhere",
        "waste money": "Save ₹2000/mo",
        "step on": "Tidy in seconds",
        "refold": "Stays perfect",
        "stare at": "Instant upgrade",
        "carry three bags": "One bag",
        "dig through": "Never lose it",
    }
    pain_card = "Solves it"
    best_pos = -1
    for key, label in pains.items():
        pos = (pain or "").find(key)
        if pos >= 0 and pos >= best_pos:
            best_pos, pain_card = pos, label
    cards = [short_kw, f"under {priced}", pain_card, "Daily use"]
    kept = [c for c in cards if len(c) <= 26]
    if not kept:
        kept = ["Best find"]
    return kept[:5]


def title_line(title: str, price: str = "", source: str = "",
               max_len: int = 92) -> str:
    """Keyword-rich, search-friendly title (YouTube titles are discovery levers).

    Kept under `max_len` so the uploader can always append " #Shorts" — a
    title that overflows YouTube's 100-char limit fails the upload with 400.
    """
    kw = _kw(title)
    priced = (price or "").strip()
    parts = [kw.title() if kw else (title or "Deal").strip()]
    if priced:
        parts.append(f"under {priced}")
    option = ""
    src = (source or "").lower()
    if "amazon" in src:
        option = "Amazon Find"
    elif "meesho" in src:
        option = "Meesho Find"
    elif "flipkart" in src:
        option = "Flipkart Deal"
    if option:
        parts.append(option)
    out = " | ".join(parts)
    if len(out) > max_len:
        out = out[:max_len].rsplit(" ", 1)[0].rstrip(" |,-")
    return out


def shorts_script(products: list[dict], seed: int | None = None) -> dict:
    """YouTube Shorts plan for up to 3 products (research: >3 kills conversion).

    Returns {"hook", "beats", "onscreen", "cta", "hashtags", "pinned_comment"}.
    """
    rng = random.Random(seed) if seed is not None else random
    items = [p for p in (products or []) if p and p.get("title")][:YOUTUBE_MAX_PRODUCTS]
    if not items:
        return {"hook": "", "beats": [], "onscreen": [], "cta": "",
                "hashtags": [], "pinned_comment": ""}
    first = items[0]
    price = str(first.get("price_label") or first.get("price") or "")
    hook = hook_line(first["title"], price, seed=seed)
    beats = []
    for p in items:
        label = str(p.get("price_label") or p.get("price") or "")
        beats.append(f"{_kw(p['title'])} — {label} ({'problem solved' if pain_for(p['title']) else 'daily use'})")
    tags = ["#Shorts", "#Deals", "#India"]
    src = (first.get("source") or "").strip()
    if src:
        tags.append("#" + re.sub(r"[^A-Za-z]", "", src.title()))
    cat = _kw(first["title"]).split()[0] if _kw(first["title"]) else ""
    if cat:
        tags.append("#" + cat.title())
    tags = tags[:HASHTAG_COUNT[1]]
    lines = []
    for i, p in enumerate(items, 1):
        label = str(p.get("price_label") or p.get("price") or "")
        lines.append(f"{i}. {p['title'][:60]} — {label}")
    return {
        "hook": hook,
        "beats": beats,
        "onscreen": onscreen_text(first["title"], price, seed=seed),
        "cta": "Full list link pinned in the comment 👇 (updated daily)",
        "title": title_line(first["title"], price, first.get("source", "")),
        "hashtags": tags,
        "pinned_comment": YT_PINNED.format(lines="\n".join(lines)),
        "max_products": YOUTUBE_MAX_PRODUCTS,
    }


def ig_carousel_plan(products: list[dict], seed: int | None = None) -> dict:
    """Instagram carousel plan: slide 1 = hook (80% of engagement lives there).

    Slide 1 hook, slides 2..n-1 = one product each, last slide = CTA + list.
    Target 8-10 slides when enough products exist.
    """
    items = [p for p in (products or []) if p and p.get("title")]
    lo, hi = IG_CAROUSEL_SLIDES
    items = items[:hi]
    if not items:
        return {"slides": [], "caption": "", "hashtags": [], "slide1": ""}
    first = items[0]
    price = str(first.get("price_label") or first.get("price") or "")
    slide1 = hook_line(first["title"], price, archetype="list", seed=seed)
    slides = [slide1]
    for p in items:
        label = str(p.get("price_label") or p.get("price") or "")
        slides.append(f"{p['title'][:52]} — {label}")
    slides.append(f"All {len(items)} here 👉 link in bio")
    # pad toward the 8-slide sweet spot with the strongest benefit line
    while len(slides) < lo and len(items) > 0:
        slides.insert(len(slides) - 1, "Everything under ₹999 — daily use items")
    caption = (f"{slide1}\n\n" + "\n".join(
        f"{i}. {p['title'][:60]}" for i, p in enumerate(items, 1)) +
        f"\n\n{SAVE_CTA}\n{BIO_CTA}\n#ad")
    return {"slides": slides[:hi + 1], "slide1": slide1, "caption": caption,
            "hashtags": ["#deals", "#india", "#homehacks", "#under999"],
            "slide_count": len(slides[:hi + 1])}


ARCHETYPES = ("pas", "list", "pov")


def pick_archetype(performance: dict | None = None,
                   rng: random.Random | None = None) -> str:
    """Choose a hook archetype, biased by what actually earned clicks.

    `performance` = db.hook_performance() output. Untested archetypes always
    keep a share of the traffic (exploration), so the bot cannot lock itself
    into an early lucky winner — the classic explore/exploit balance.
    """
    r = rng or random
    perf = performance or {}
    weights: list[tuple[str, float]] = []
    for name in ARCHETYPES:
        stats = perf.get(name)
        if not stats:
            weights.append((name, 1.0))            # unexplored: full chance
        else:
            cpc = float(stats.get("cpc", 0) or 0)
            weights.append((name, 0.35 + cpc))     # explored: proportional
    total = sum(w for _, w in weights) or 1.0
    roll = r.random() * total
    upto = 0.0
    for name, w in weights:
        upto += w
        if roll <= upto:
            return name
    return ARCHETYPES[0]


def best_time_blocks(platform: str) -> list[tuple[int, int]]:
    """Posting windows for a platform (falls back to a sane default)."""
    return BEST_TIMES.get((platform or "").lower(), [(9, 22)])


def in_best_window(platform: str, hour: int) -> bool:
    """True when `hour` sits in one of the platform's strong windows."""
    for start, end in best_time_blocks(platform):
        if start <= end and start <= hour < end:
            return True
        if start > end and (hour >= start or hour < end):   # wraps midnight
            return True
    return False


def report() -> str:
    """Human-readable summary (used by `bot playbook`)."""
    return """📚 CONTENT PLAYBOOK (2026 data — what top affiliate channels do)

YOUTUBE SHORTS
  • Hook + product visible in the first 1.5-3 seconds (viewers decide there)
  • Problem→Agitate→Solve framing converts 3-4x better than aesthetic shots
  • MAX 3 products per Short (4+ tanks conversion)
  • 15-30s long; 60% watch muted → bold on-screen text carries the message
  • PIN the product comment (+10-15% conversion)
  • 3-5 hashtags (broad + niche + brand)
  • India: Hinglish list hooks ("Top 3 gadgets that fix … in 30s")

INSTAGRAM
  • Carousels = highest engagement (0.50-0.55%) + ~3x saves vs Reels
  • Slide 1 carries ~80% of engagement → hook first, never a logo
  • 8-10 slides (dips after slide 3, returns at 8+); 1080x1350 (4:5)
  • Reels = reach (33% reach rate) → use them for discovery
  • Ask for the save/share (weighted ~3x)
  • Link in bio + story link stickers close the sale

PINTEREST
  • Keyword-first titles/descriptions; 5-15 pins/day
  • List/roundup pins ("Top 5 under ₹499") earn compounding saves

WHAT THE BOT DOES WITH THIS AUTOMATICALLY
  • Shorts description: PAS hook line + max 3 products + hashtags + pinned comment
  • IG carousel: hook slide 1, one product per slide, save-CTA + bio link
  • Posting windows per platform (IN_BEST_WINDOW) guide the scheduler
  • `bot radar` ranks products by real usefulness before they enter the queue
"""
