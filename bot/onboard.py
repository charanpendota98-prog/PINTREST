"""R53: one sheet that answers EVERY Pinterest onboarding screen.

Rationale: onboarding is a set of optional shortcut screens, not a gate. The
owner kept asking the same question per screen ("edi select cheyali?"), so the
whole click-path lives here, in one place, printable at any time.

Nothing here is required to run the bot — that is the point. Each row says what
to pick, why, and whether skipping costs anything.
"""
from __future__ import annotations

# (screen, what to select, why / consequences, mandatory?)
SCREENS: list[tuple[str, str, str, str]] = [
    (
        "Create business account",
        "business.pinterest.com → email + password → business account",
        "Business account is required for commercial/affiliate activity "
        "(Pinterest ToS) and it unlocks analytics. Never use a personal one.",
        "REQUIRED",
    ),
    (
        "Describe your business",
        "Content creator",
        "Affiliate/brand-curation kuda 'Content creator' kinda vasthundi. "
        "'Online merchant' ki own shop website kavali, and the Verified Merchant "
        "Program (the sales-y one) is closed to pure affiliates.",
        "pick this",
    ),
    (
        'A few more details (business goals)',
        "Increase online sales + Drive traffic to your site + "
        "Create content on Pinterest to grow an audience",
        "Outbound clicks = mana money metric, so 'Drive traffic' must be ON; "
        "it is also a ranking signal Pinterest uses to decide distribution.",
        "pick these 3",
    ),
    (
        'A few more details (brand focus dropdown)',
        "Home",
        "2026 lo #1 money niche on Pinterest (home decor), and it matches what "
        "the radar already hunts. If it is already selected: keep it.",
        "keep Home",
    ),
    (
        "Shortcut cards: Share ideas / Claim your website / Showcase your brand",
        "Select nothing — just next/skip",
        "Ee moodu optional shortcuts; account already usable. "
        "'Claim your website' only works once a domain is live.",
        "OPTIONAL",
    ),
    (
        'On the "Share ideas" card → "Create a Pin"',
        "Skip it. If the screen has no Skip/Next: open pinterest.com directly "
        "(or close the X / refresh) — the overlay does not gate the account.",
        "Bot ne story pins vestundi (real product media + affiliate links), "
        "so manual pin avasaram ledu. 'Create a Pin' click chesina: builder "
        "open avutundi, X tho close chesthe chalu — emi post avvadu.",
        "SKIP",
    ),
    (
        "Profile: name + username + bio + picture",
        "python -m bot brand  (recommended name/bio/boards ikkada ready)",
        "Profile itself is a ranked entity; name = 'Brand | Niche Keyword'. "
        "Username lo keywords pettakandi — brand name chalu.",
        "do it (2 min)",
    ),
    (
        "Connected accounts (Instagram / YouTube / Etsy)",
        "Instagram claim cheyyandi (bot already IG API tho post chestundi)",
        "Claimed account = ne pins meeda ne peru + analytics. "
        "YouTube/Etsy ledu kabatti skip.",
        "optional",
    ),
    (
        "Settings → Claimed accounts → Claim website",
        "python -m bot claim <token>   (deploy ayyaka, domain unte)",
        "Attribution + analytics + Rich Pins size. DNS avasaram ledu: bot meta "
        "tag ni pages lo inject chestundi + /pinterest-<token>.html serve "
        "chestundi.",
        "do after deploy",
    ),
    (
        "developers.pinterest.com → Create app",
        "App ID + App secret, redirect http://localhost:8888/callback",
        "Ee OAuth tokens tho bot publish chestundi. "
        "Scopes: pins:write, boards:write, user_accounts:read (+ read scopes).",
        "REQUIRED",
    ),
]

FOOTER = [
    "",
    "🎯 Nijam: ee onboarding screens lo REQUIRE avsarinavi 2 matrame —",
    "   business account + developer app. Migilinavi anni optional shortcuts.",
    "   Skip chesina account ki emi avvadu; bot anni screens tarvata cheyyagaladu.",
    "   Ready state eppudu: python -m bot ready",
]


def lines(cfg=None) -> list[str]:
    """Full onboarding sheet, personalised with the configured brand."""
    brand = "PinDrop Deals | Home & Kitchen"
    bio = ""
    site = ""
    if cfg is not None:
        try:
            brand = cfg.get("design.brand_name", brand)
            display = cfg.get("brand.display_name", "")
            if display:
                brand = display
            bio = cfg.get("brand.bio", "") or ""
            site = cfg.get("link.public_base", "") or ""
        except Exception:  # noqa: BLE001 — sheet must always print
            pass

    out = [
        "═" * 66,
        "📋 PINTEREST ONBOARDING — SCREEN BY SCREEN (nuvvu em select cheyyali)",
        "═" * 66,
        f"Suggested profile: {brand}   (@pindropdeals)",
    ]
    if bio:
        out.append(f"Bio (paste as-is): {bio}")
    if site:
        out.append(f"Website: {site}")
    out.append("-" * 66)

    for i, (screen, pick, why, tag) in enumerate(SCREENS, 1):
        out.append(f"\n{i}. {screen}   [{tag}]")
        out.append(f"   → SELECT: {pick}")
        for line in _wrap(why, 62):
            out.append(f"     {line}")

    out.extend(FOOTER)
    return out


def _wrap(text: str, width: int) -> list[str]:
    words, cur, lines = text.split(), "", []
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
