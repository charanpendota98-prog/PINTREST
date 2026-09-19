"""Brand & profile SEO — the name that actually earns Pinterest reach.

Pinterest is a search engine: the **profile display name is a ranked field**
(format that works in 2026: `Brand | Primary Niche Keyword`, ideally ≤30
characters so it never truncates on mobile), while the **pin strip**
(`design.brand_name`) is visual and must stay SHORT.

So one name is not enough — the bot keeps the two roles apart:

* `design.brand_name`   → 2-4 words, printed on every pin (readable at a glance)
* `brand.display_name`  → `Brand | keyword niche`, used in profile/landing copy
* `brand.bio`           → ≤160 chars, 2-3 keywords + call to action
* board titles          → keyword-rich (50-char limit), from the real niches

`bot brand` prints ready-to-paste text, validates lengths, and saves the choice.
"""
from __future__ import annotations

from pathlib import Path

NAME_RECOMMENDED = 30       # renders fully even on small phones
NAME_TRUNCATE_AT = 40       # above this the name starts truncating in feeds
NAME_HARD_MAX = 65          # Pinterest's own field limit
BIO_MAX = 160               # description field
BOARD_MAX = 50
SPAM_WORDS = ("cheap", "free", "clickbait", "loot", "offer offer")

# keyword-forward names, grouped by the niches the bot actually hunts
NAME_IDEAS: dict[str, list[str]] = {
    "all-round (safe default)": [
        "PinDrop Deals | Home & Kitchen",
        "Deal Drops | Home & Kitchen Finds",
        "Smart Finds India | Kitchen",
    ],
    "home & kitchen": [
        "Ghar Finds | Home & Kitchen",
        "Tidy Home India | Storage Ideas",
        "Home Hacks India | Kitchen",
    ],
    "ladies / fashion": [
        "Style Drops | Kurta & Saree",
        "Ethnic Picks | Kurta Sets",
        "Wardrobe Wins | Women Style",
    ],
    "beauty": [
        "Glow Picks | Skincare Finds",
        "Beauty Finds | Serum & Makeup",
    ],
    "mixed: home + ladies (recommended)": [
        "Deal Drops | Home & Style",
        "PinDrop Deals | Home Finds",
        "Ghar & Style | Daily Deals",
    ],
}

# industry truth: Pinterest's strongest 2026 niches for this model
TOP_NICHES = ("home decor & organization", "kitchen gadgets",
              "women's fashion (kurta/saree)", "beauty & skincare",
              "festive & wedding", "kids & toys")


def validate(name: str) -> dict:
    """Length / spam / structure check for a display name."""
    name = str(name or "").strip()
    out: dict = {"name": name, "ok": True, "errors": [], "warnings": [],
                 "notes": []}
    if not name:
        out["ok"] = False
        out["errors"].append("empty name")
        return out
    if len(name) > NAME_HARD_MAX:
        out["ok"] = False
        out["errors"].append(f"{len(name)} chars — Pinterest allows "
                             f"{NAME_HARD_MAX} max")
    elif len(name) > NAME_TRUNCATE_AT:
        out["warnings"].append(f"{len(name)} chars — may truncate in feeds "
                               f"(aim ≤{NAME_TRUNCATE_AT})")
    elif len(name) > NAME_RECOMMENDED:
        out["notes"] = out.get("notes", []) + [
            f"{len(name)} chars — fine on desktop, tiny truncation on small "
            f"phones (≤{NAME_RECOMMENDED} is ideal)"]
    low = name.lower()
    for word in SPAM_WORDS:
        if word in low:
            out["warnings"].append(f"'{word}' reads as spam to Pinterest")
    if "|" not in name:
        tip = "add a keyword niche: 'Brand | Niche Keyword'"
        if len(name) > 18:
            out["warnings"].append(tip)
        else:
            out["notes"].append(tip)      # short brand-only names: gentle tip
    if name.count("|") > 1:
        out["warnings"].append("one '|' is enough — keep it readable")
    return out


def pin_strip(name: str) -> str:
    """The SHORT version for the pin artwork (before the '|' when present)."""
    short = str(name or "").split("|")[0].strip()
    return short[:28]


def display_suggestions(brand: str = "") -> dict[str, list[str]]:
    """Name sets per niche; if a brand is given, its variations come first."""
    brand = str(brand or "").strip()
    out: dict[str, list[str]] = {}
    for group, ideas in NAME_IDEAS.items():
        out[group] = list(ideas)
    if brand:
        strip = pin_strip(brand)
        out = {f"your brand: {brand}": [
            f"{strip} | Home & Kitchen",
            f"{strip} | Home Finds",
            f"{strip} | Home & Style",
        ], **out}
    return out


def bio_for(brand: str, niches: tuple[str, ...] = TOP_NICHES) -> str:
    """≤160-char profile description: what + who + CTA, keywords early."""
    b = pin_strip(brand) or "We"
    text = (f"{b} shares easy home, kitchen & style finds under ₹999 — "
            f"organizers, gadgets, kurtas and beauty picks. New deals daily. "
            f"Tap the pin to shop.")
    if len(text) > BIO_MAX:
        text = (f"{b} shares home & kitchen finds under ₹999 + kurta and "
                f"beauty picks. New deals daily — tap the pin to shop.")
    return text[:BIO_MAX]


def board_plan() -> list[dict]:
    """Keyword-rich board titles (the heaviest-ranking field after pins)."""
    try:
        from .growth import BOARD_RULES
        names = [b for _, b in BOARD_RULES]
    except Exception:  # noqa: BLE001
        names = ["Home & Kitchen Ideas", "Fashion Finds", "Beauty Picks"]
    out = []
    for n in names + ["Deals Under ₹499", "Festive & Gifts"]:
        title = n if len(n) <= BOARD_MAX else n[:BOARD_MAX]
        out.append({"title": title, "desc": (
            f"{title} — easy, affordable ideas you can actually use. "
            f"Organizers, kitchen gadgets, decor and everyday finds under "
            f"₹999. Save your favourites and tap to shop.")})
    return out


def _patch_yaml_text(text: str, strip: str, name: str, bio: str) -> str:
    """Comment-preserving config edit.

    `yaml.safe_dump` wipes every comment in config.yaml (real regression caught
    in review — 85 comment lines → 4). We therefore edit lines surgically:
    keep the file byte-for-byte except the two values we own.
    """
    lines = text.splitlines()
    out: list[str] = []
    in_brand = False
    wrote_brand = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("brand_name:"):
            comment = line.split("#", 1)[1] if "#" in line else ""
            out.append(f"  brand_name: {strip}"
                       + (f"  # {comment.strip()}" if comment else ""))
            continue
        if stripped == "brand:":
            in_brand = True
            out.append(line)
            out.append(f'  display_name: "{name}"')
            out.append(f'  bio: "{bio}"')
            wrote_brand = True
            continue
        if in_brand and line and not line.startswith((" ", "\t")):
            in_brand = False
        if in_brand and stripped.startswith(("display_name:", "bio:")):
            continue                      # replaced above
        out.append(line)
    if not wrote_brand:
        out.append("")
        out.append("brand:")
        out.append(f'  display_name: "{name}"')
        out.append(f'  bio: "{bio}"')
    return "\n".join(out) + "\n"


def save(cfg, name: str, path: str | Path | None = None) -> dict:
    """Persist the chosen brand: short strip on pins + full display name."""
    name = str(name or "").strip()
    check = validate(name)
    if not check["ok"]:
        return {"saved": False, **check}
    strip, bio = pin_strip(name), bio_for(name)
    cfg.raw.setdefault("design", {})["brand_name"] = strip
    cfg.raw.setdefault("brand", {})["display_name"] = name
    cfg.raw["brand"]["bio"] = bio
    target = (Path(path) if path
              else Path(__file__).resolve().parent.parent / "config.yaml")
    try:
        target.write_text(_patch_yaml_text(target.read_text(), strip, name, bio))
        import yaml
        yaml.safe_load(target.read_text())      # the file must still parse
        wrote = True
    except Exception:  # noqa: BLE001 — saving must never crash the CLI
        wrote = False
    return {"saved": wrote, "strip": strip, "name": name, "bio": bio, **check}


def lines(cfg, name: str = "") -> list[str]:
    """CLI output: the rules, the ideas, and ready-to-paste fields."""
    current_strip = str(cfg.get("design.brand_name", "") or "")
    current_display = str(cfg.get("brand.display_name", "") or "")
    out = [
        "🏷️  BRAND & PROFILE SEO (Pinterest is a search engine)",
        "   • Display name = ranked field → format: Brand | Niche Keyword "
        f"(≤{NAME_RECOMMENDED} chars so mobile shows it fully)",
        "   • Pin strip (design.brand_name) = visual → keep it SHORT "
        "(2-4 words, readable on the artwork)",
        "   • Boards = keyword titles (≤50 chars), 15-20 pins each before they rank",
        "   • Bio = ≤160 chars, keywords early + call to action",
        "",
        f"   current pin strip : {current_strip or '(not set)'}",
        f"   current display   : {current_display or '(not set)'}",
        "",
        "💡 STRONGEST 2026 NICHES for this model: " + ", ".join(TOP_NICHES),
        "",
        "📛 NAME IDEAS (copy-paste):",
    ]
    for group, ideas in display_suggestions(name).items():
        out.append(f"   {group}:")
        for idea in ideas:
            check = validate(idea)
            mark = "✅" if not check["errors"] else "⛔"
            extra = ""
            if check["warnings"]:
                extra = f"  ⚠️ {check['warnings'][0]}"
            elif check["notes"]:
                extra = f"  ({len(idea)} chars)"
            else:
                extra = f"  ({len(idea)} chars ✨)"
            out.append(f"     {mark} {idea}{extra}")
    if name:
        check = validate(name)
        out += ["", f"🔍 YOUR NAME: {name} ({len(name)} chars)",
                f"   pin strip would be: «{pin_strip(name)}»"]
        for w in check["warnings"]:
            out.append(f"   ⚠️ {w}")
        for e in check["errors"]:
            out.append(f"   ⛔ {e}")
    out += ["", "📋 READY-TO-PASTE PROFILE FIELDS:",
            f"   Display name: {name or '(pick one above)'}",
            f"   Bio ({BIO_MAX} max): {bio_for(name or 'PinDrop Deals')}"]
    out.append("   Boards to create:")
    for b in board_plan()[:6]:
        out.append(f"     • {b['title']} ({len(b['title'])} chars)")
    out += ["",
            "⚙️  Save your choice:  python -m bot brand \"PinDrop Deals | Home & Kitchen Finds\"",
            "   (writes the pin strip + display name into config.yaml)"]
    return out
