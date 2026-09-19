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
    # R56: the researched final answer — coined + ownable beats descriptive
    # (NestKart / NestBazaar / Aangan / Nestora / Grihika are all in use).
    "🏆 FINAL PICK (coined, ownable)": [
        "Gharvana | Home & Kitchen",
        "Gharvana | Home Decor Finds",
        "Gharvana | Kitchen & Home",
    ],
    "all-round (safe default)": [
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
    source = getattr(cfg, "source_path", None)
    target = (Path(path) if path
              else Path(source) if source
              else Path(__file__).resolve().parent.parent / "config.yaml")
    try:
        target.write_text(_patch_yaml_text(target.read_text(), strip, name, bio))
        import yaml
        yaml.safe_load(target.read_text())      # the file must still parse
        wrote = True
    except Exception:  # noqa: BLE001 — saving must never crash the CLI
        wrote = False
    return {"saved": wrote, "strip": strip, "name": name, "bio": bio, **check}


BLOCKED_WEBSITE_HOSTS = (
    "t.me", "telegram.me", "telegram.dog", "wa.me", "whatsapp.com",
    "chat.whatsapp.com", "linktr.ee", "bit.ly", "tinyurl.com", "rb.gy",
    "cutt.ly", "shorturl.at", "is.gd", "cuelinks.com", "earnkaro.com",
    "amzn.to", "fkrt.it",
)


def website_advice(url: str) -> tuple[str, str]:
    """Pinterest profile 'Website' field — (verdict, reason).

    The field is NOT decoration: it is what Pinterest lets you claim, and an
    unclaimable link is both useless (no Rich Pins / attribution) and a spam
    signal. So answer honestly instead of letting the owner paste anything.
    """
    url = (url or "").strip()
    if not url:
        return ("empty",
                "Ippudu blank ga vadileyyandi. Deploy ayyaka mana landing "
                "domain (link.public_base) pettandi — appudu claim cheyyochu "
                "(Rich Pins + attribution free reach).")
    if "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0].lower()
    else:
        host = url.split("/", 1)[0].lower()
    host = host.split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    for bad in BLOCKED_WEBSITE_HOSTS:
        if host == bad or host.endswith("." + bad):
            return ("warn",
                    f"'{host}' ni profile website ga pettakandi: Pinterest idi "
                    "claim cheyyanivvadu (Rich Pins + content attribution "
                    "pothayi) and loot-deal shortlinks ni spam pattern ga "
                    "chustundi — reach padipothundi. Telegram channel ni bot "
                    "broadcast/Deals-of-the-Day lo promote cheyyandi.")
    return ("ok",
            f"'{host}' nee own domain — deploy ayyaka Settings → Claimed "
            "accounts → Claim website lo ide URL tho claim cheyyandi.")


def profile_form(cfg, name: str = "") -> list[str]:
    """Field-by-field values for Pinterest's 'Edit profile' form."""
    display = name
    try:
        display = display or str(cfg.get("brand.display_name", "") or "")
    except Exception:  # noqa: BLE001 — the form must always print
        pass
    display = display or "PinDrop Deals | Home & Kitchen"
    bio = bio_for(display.split("|")[0].strip() or "PinDrop Deals")
    try:
        bio = str(cfg.get("brand.bio", "") or "") or bio
    except Exception:  # noqa: BLE001
        pass
    site = ""
    try:
        site = str(cfg.get("link.public_base", "") or "")
    except Exception:  # noqa: BLE001
        pass
    verdict, reason = website_advice(site)
    mark = {"empty": "⏸ ", "warn": "⛔", "ok": "✅"}.get(verdict, "•")
    handle = pin_strip(display).lower().replace(" ", "")
    saved_handle = ""
    try:
        saved_handle = str(cfg.get("brand.handle", "") or "")
    except Exception:  # noqa: BLE001
        pass
    if saved_handle:
        handle = saved_handle
    return [
        "📝 PINTEREST 'EDIT PROFILE' FORM — field by field:",
        f"   Name       → {display}",
        "                (idi KEYWORD field — search lo ide kanipistundi)",
        f"   Username   → {handle}"
        "                  (@handle; Name lo handle pettakandi"
        + ("" if saved_handle else " — taken aa? python -m bot handle") + ")",
        f"   About      → {bio}",
        "   Pronouns   → (blank — brand account ki avasaram ledu)",
        f"   Website    → {site or '(blank until deploy)'}",
        f"   {mark} {reason}",
        "",
    ]


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
    out += [""] + profile_form(cfg, name)
    out.append('   🏷️  Naming engine: python -m bot name "<Brand>" [--live] — '
               "score + collision memory + live check")
    out += ["📋 READY-TO-PASTE PROFILE FIELDS:",
            f"   Display name: {name or '(pick one above)'}",
            f"   Bio ({BIO_MAX} max): {bio_for(name or 'PinDrop Deals')}"]
    out.append("   Boards to create:")
    for b in board_plan()[:6]:
        out.append(f"     • {b['title']} ({len(b['title'])} chars)")
    out += ["",
            "⚙️  Save your choice:  python -m bot brand \"Gharvana | Home & Kitchen\"",
            "   (writes the pin strip + display name into config.yaml)"]
    return out
