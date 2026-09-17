"""Growth / viral-tricks engine.

Everything here is distilled from what top affiliate creators actually do in
2026 (see README "Viral Tricks Playbook"):

  * curiosity HOOKS in titles/captions ("Wait for the price 👀")
  * keyword-stuffed SEO titles (Pinterest is a SEARCH engine)
  * tiered hashtag mix (huge + medium + niche)
  * posting in PEAK windows (IST)
  * roundup / "3 finds under ₹X" value pins (convert better than raw product pins)
  * fresh variations — never the same pin twice
"""
from __future__ import annotations

import random
from datetime import datetime

YEAR = datetime.now().year

# ------------------------------------------------------------- hooks (IG/reels)
HOOKS = [
    "Wait for the price 👀",
    "This looks WAY more expensive than it is 😳",
    "Amazon didn't want you to find this 🤫",
    "POV: you found the perfect {kw} 🛍️",
    "I was today years old when I found this 😭",
    "Rating viral finds until I go broke — day {n}",
    "The {kw} upgrade your desk/home needed ✨",
    "Under {price}?! Take my money 💸",
    "3 reasons this {kw} is worth it ⬇️",
    "Don't buy a {kw} until you see this 🚫",
]

# ------------------------------------------------- keyword bank (Pinterest SEO)
POWER_KEYWORDS = [
    "viral find", "budget pick", "amazon find", "must have", "deal alert",
    "aesthetic", "trending", "gift idea", "home upgrade", "student budget",
]
PRICE_KEYWORDS = ["under 500", "under 999", "under 1500", "low price", "best price"]
SOURCE_KEYWORDS = {
    "amazon": ["amazon finds", "amazon deals", "amazon india"],
    "meesho": ["meesho finds", "meesho haul", "meesho fashion"],
    "flipkart": ["flipkart deals", "flipkart sale"],
    "other": ["online shopping deals", "best deals india"],
}


def seo_title(title: str, price_label: str, source: str, phrase: str = "") -> str:
    """Keyword-rich Pinterest title, ≤100 chars.

    Pattern:  <clean product name> | <LIVE search phrase or source kw> | price kw
    """
    clean = " ".join(title.split())[:52]
    kw = (phrase or "").strip() or random.choice(
        SOURCE_KEYWORDS.get(source, SOURCE_KEYWORDS["other"]))
    price_kw = random.choice(PRICE_KEYWORDS) if price_label else random.choice(POWER_KEYWORDS)
    cand = f"{clean} | {kw} | {price_kw} {YEAR}"
    return cand[:100]


def hook_for(price_label: str, title: str, day: int) -> str:
    kw = " ".join(title.split()[:2]).lower() or "find"
    h = random.choice(HOOKS)
    return h.format(kw=kw, price=price_label.replace("₹", "₹") or "₹499", n=day)


def hashtag_mix(title: str, source: str, max_tags: int = 8) -> str:
    """Tiered mix: 2 huge + 3 medium + niche words from the title."""
    huge = ["#viral", "#trending", "#deals"]
    medium = SOURCE_KEYWORDS.get(source, ["#onlineshopping"]) + ["#budgetfinds", "#musthaves"]
    niche = [f"#{w}" for w in dict.fromkeys(
        x.lower() for x in title.split() if len(x) > 4 and x.isalpha())][:4]
    pool = []
    for group in (huge, medium, niche):
        random.shuffle(group)
    def norm(t: str) -> str:
        t = t.replace(" ", "")
        return t if t.startswith("#") else "#" + t
    pool += [norm(t) for t in huge[:2]]
    pool += [norm(t) for t in medium[:3]]
    pool += [norm(t) for t in niche[:3]]
    seen, out = set(), []
    for t in pool:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return " ".join(out[:max_tags])


# ------------------------------------------------------------- peak windows
def peak_window(now: datetime) -> tuple[int, int]:
    """Best IST posting window for the given day (weekend mornings run longer)."""
    if now.weekday() >= 5:           # Sat/Sun
        return (10, 13) if now.hour < 15 else (18, 22)
    return (12, 14) if now.hour < 16 else (19, 22)


# ------------------------------------------------------------- roundups
ROUNDUP_TITLES = [
    "3 Viral Finds Under {price} You Need 😍",
    "Top 3 Budget {kw} Picks This Week 🔥",
    "I Tested 3 Viral {kw} Deals — #2 Shocked Me",
    "{kw} Haul: 3 Deals Under {price} 🛒",
]


def roundup_title(price_label: str, kw: str) -> str:
    return random.choice(ROUNDUP_TITLES).format(
        price=price_label or "₹999", kw=kw or "Amazon"
    ).strip()


# ------------------------------------------------- India shopping festivals
# (month, day, name, keyword) — pin volume & keywords boost in the 7 days
# before each: India's shopping spikes are festival-driven.
FESTIVALS = [
    (1, 1, "New Year Sale", "new year sale"),
    (1, 14, "Makar Sankranti", "sankranti shopping"),
    (3, 3, "Holi Sale", "holi sale"),
    (8, 15, "Independence Day Sale", "independence day sale"),
    (8, 29, "Raksha Bandhan", "rakhi gift"),
    (9, 7, "Ganesh Chaturthi", "ganesh chaturthi"),
    (10, 2, "Navratri", "navratri fashion"),
    (10, 20, "Dussehra Sale", "dussehra sale"),
    (11, 8, "Diwali", "diwali deals"),
    (11, 14, "Children's Day", "kids gift"),
    (12, 25, "Christmas Sale", "christmas gifts"),
]


def festival_boost(now: datetime) -> tuple[str, str, float]:
    """Returns (festival_name, keyword, volume_multiplier).

    Within 7 days before a festival (or on it): 1.5× pins + festival keyword.
    Days 1-3 of any month (payday/salary week): 1.25× — India buys on salary.
    """
    for m, d, name, kw in FESTIVALS:
        fest = datetime(now.year, m, d)
        delta = (fest - now.replace(tzinfo=None)).days if now.tzinfo else (fest - now).days
        if 0 <= delta <= 7:
            return name, kw, 1.5
    if now.day <= 3:
        return "Payday", "salary sale", 1.25
    return "", "", 1.0
BOARD_RULES = [
    (("kurta", "saree", "dress", "fashion", "women", "jewel", "footwear", "bag"),
     "Fashion Finds"),
    (("earbud", "watch", "phone", "gadget", "headphone", "speaker", "smart", "charger"),
     "Tech Deals"),
    (("home", "kitchen", "decor", "bedsheet", "lamp", "organizer", "storage"),
     "Home & Kitchen Ideas"),
    (("serum", "cream", "beauty", "makeup", "hair", "skincare"),
     "Beauty Picks"),
    (("kids", "baby", "toy", "school"), "Kids & Toys"),
]


def pick_board(title: str, source: str, default: str) -> str:
    """Niche board per product — boards rank in search too, so several
    keyword-named niche boards = many more surfaces than one big board."""
    low = title.lower()
    for words, board in BOARD_RULES:
        if any(w in low for w in words):
            return board
    return default
