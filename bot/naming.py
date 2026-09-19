"""R56: brand-naming engine — stop guessing, score and verify.

Why this exists: the owner kept cycling through descriptive names
(PinDrop Deals → pindropdeals_home → "inka bestga emaina cheppu"). Research
showed why that loop never ends — every comfortable descriptive name in this
niche is already in use:

    NestKart      → nestkart.in, a live India store, same categories
    NestBazaar    → pinterest.com/nestbazaar1 — an ACTIVE home & kitchen
                    affiliate account in the exact niche
    Aangan        → aanganofindia.com (ethnic home decor, US)
    Nestora       → nestora88.com, nestorahome.us, nestora.pk cookware
    Grihika       → girikaflair.com (Bengali grocery brand)

So the ranking is: coined-and-ownable > descriptive-and-crowded. The engine
scores a candidate the way a brand strategist would — length, pronounceability,
spam-coding, numbers, distinctiveness, meaning — and then lets the live probes
answer the only question that actually blocks: is the handle free?
"""
from __future__ import annotations

import re

MAX_BRAND = 16            # pin strip must stay readable on artwork
SPAM_WORDS = ("loot", "free", "cheap", "sale", "offer", "discount", "dealz",
              "sasta", "bumper", "mega", "cash", "win", "prize")
# "deal(s)" is not banned outright — the owner's model IS deals — but it is a
# weak, heavily-used word, so it costs points instead of failing outright.
WEAK_WORDS = ("deal", "deals", "store", "shop", "mart", "mall", "buy", "cart")
HOME_ROOTS = ("ghar", "griha", "gruha", "nest", "home", "aangan", "angan",
              "nivaas", "nivas", "kutir")
# Evidence-backed collisions (checked in this round, see module docstring).
KNOWN_USED = {
    "nestkart": "nestkart.in — live India store, same categories (home & kitchen)",
    "nestbazaar": "pinterest.com/nestbazaar1 — ACTIVE home & kitchen affiliate, "
                  "exact same model",
    "nestor": "nestorahome.us + nestora.pk + nestora88.com — home/cookware brands",
    "nestora": "nestorahome.us + nestora.pk + nestora88.com — home/cookware brands",
    "aangan": "aanganofindia.com — ethnic home decor",
    "aanganfinds": "aanganofindia.com — ethnic home decor",
    "grihika": "girikaflair.com — Bengali grocery brand",
    "pindrop": "Pindrop (US) is a known voice-security company + pindropdeals "
               "handle already taken",
    "pindropdeals": "Pinterest handle already taken",
    "pindropdealshome": "Pinterest handle already taken",
    "gharfinds": "descriptive — expect close variants in the same niche",
    "homefinds": "descriptive — heavily used across Pinterest/IG",
}

# Meaningful blends: home root + an aspirational/behavioural root.
ROOTS = ("ghar", "griha", "nest", "kona")
TAILS = {
    "vana": "nirvana → 'home bliss'",
    "ora": "aura → 'home aura'",
    "ika": "diminutive 'little home'",
    "iya": "warm suffix, brand-like",
    "ya": "short brand ending",
    "aa": "Indian brand ending (Nykaa-style)",
}


def _syllables(word: str) -> int:
    return max(1, len(re.findall(r"[aeiouy]+", word)))


def _clusters(word: str) -> int:
    return len(re.findall(r"[bcdfghjklmnpqrstvwxz]{3,}", word))


def score(name: str) -> dict:
    """0-100 with the reasons — same rules I would use reviewing a brand."""
    raw = str(name or "").strip()
    plain = re.sub(r"[^a-z0-9]", "", raw.lower())
    reasons: list[str] = []
    risks: list[str] = []
    pts = 0

    if not plain:
        return {"name": raw, "score": 0, "grade": "❌", "reasons": [],
                "risks": ["Name khali undi."]}

    # 1. brevity (20)
    n = len(plain)
    if n <= 10:
        pts += 20
        reasons.append(f"Short ({n}) — pin artwork, handle, chat lo easy.")
    elif n <= MAX_BRAND:
        pts += 14
        reasons.append(f"OK length ({n}).")
    else:
        pts += 5
        risks.append(f"Podugu ({n}) — artwork lo chinna ga kanipistundi.")

    # 2. pronounceable (15)
    syll, clus = _syllables(plain), _clusters(plain)
    if syll <= 3 and clus == 0:
        pts += 15
        reasons.append(f"Easy ga palukutaru ({syll} syllables, no hard clusters).")
    elif clus == 0:
        pts += 8
        reasons.append(f"{syll} syllables — ok, kani konchem long.")
    else:
        risks.append("Consonant cluster undi — spelling mistakes ekkuva.")

    # 3. trust / spam coding (20)
    spam = [w for w in SPAM_WORDS if w in plain]
    if spam:
        risks.append(f"⛔ Spam-coding word: {', '.join(spam)} — Pinterest "
                     "distribution padipothundi, trust thakkuva.")
    else:
        pts += 20
        reasons.append("Spam word ledu (loot/free/cheap/sale ledu) → "
                       "trust build avutundi.")

    # 4. numbers (10)
    if any(c.isdigit() for c in plain):
        risks.append("Numbers unnai — fan/duplicate account la kanipistundi.")
    else:
        pts += 10
        reasons.append("Numbers ledu.")

    # 5. meaning (15): home root OR a clear English home word
    root = next((r for r in HOME_ROOTS if r in plain), "")
    if root:
        pts += 15
        reasons.append(f"Home root '{root}' undi → niche clear (home decor/kitchen).")
    else:
        pts += 7
        reasons.append("Home root ledu — niche ni NAME field tho cheppali "
                       "(adi ranking field, problem ledu).")

    # 6. distinctiveness (20)
    weak = [w for w in WEAK_WORDS if w in plain]
    if plain in KNOWN_USED:
        risks.append(f"⚠️ Already in use: {KNOWN_USED[plain]}")
    elif weak:
        pts += 8
        reasons.append(f"'{weak[0]}' word undi — common, distinctiveness thakkuva.")
    else:
        pts += 20
        reasons.append("Distinctive — ee name tho already unna accounts thakkuva "
                       "(thokkalo, brand build avutundi).")

    total = max(0, min(100, pts))
    grade = ("🏆 FINAL pick" if total >= 85 else
             "✅ strong" if total >= 70 else
             "⚠️ usable" if total >= 55 else "❌ vaddu")
    return {"name": raw, "plain": plain, "score": total, "grade": grade,
            "reasons": reasons, "risks": risks, "syllables": syll}


def blends(limit: int = 12) -> list[dict]:
    """Coined home-brand names, filtered the same way (easy to say, no clusters)."""
    out: list[dict] = []
    for root in ROOTS:
        for tail, meaning in TAILS.items():
            word = f"{root}{tail}"
            if len(word) > 12 or _clusters(word):
                continue
            res = score(word)
            if res["score"] < 70 or res["risks"]:
                continue
            if word in KNOWN_USED:
                continue
            out.append({"name": word.capitalize(), "handle": word,
                        "score": res["score"], "meaning": meaning})
    out.sort(key=lambda c: -c["score"])
    return out[:limit]


def probe_domain(host: str, timeout: float = 6.0) -> tuple[str, str]:
    """Is a domain serving something? ('serving' | 'not-serving' | 'unknown').

    Honest by design: a non-resolving domain is NOT proof of availability (it can
    be registered without a site), so the wording says "not serving" — never
    "free".
    """
    host = str(host or "").strip().lower().lstrip("https://").lstrip("http://")
    host = host.split("/", 1)[0].split(":", 1)[0]
    if not host or "." not in host:
        return "unknown", "bad host"
    try:
        import requests
        r = requests.get(f"http://{host}/", timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        if r.status_code < 400:
            return "serving", f"http {r.status_code}"
        return "not-serving", f"http {r.status_code}"
    except Exception as exc:  # noqa: BLE001 — offline/DNS is normal in sandbox
        name = type(exc).__name__
        if "NameResolution" in name or "ConnectionError" in name or \
                "SSLError" in name or "Timeout" in name:
            return "not-serving", name
        return "unknown", name


def report(name: str, cfg=None, live: bool = False) -> list[str]:
    """Everything needed to make ONE final call on a brand name."""
    res = score(name)
    plain = res.get("plain", "")
    out = [
        "═" * 66,
        f"🏷️  BRAND DECISION — '{res['name']}' → {res['score']}/100  {res['grade']}",
        "═" * 66,
    ]
    for r in res["reasons"]:
        out.append(f"   ✅ {r}")
    for r in res["risks"]:
        out.append(f"   ⚠️ {r}")

    if plain:
        handle = plain[:20]
        out += [
            "",
            f"   Handle candidate: @{handle}",
            f"   NAME field (unique kaadu, ranking ikkada): "
            f"{res['name']} | Home & Kitchen Finds",
            "",
        ]
        if live:
            from . import handles as _h
            out.append("🔎 LIVE CHECK")
            out += _h.check_lines([handle], limit=1)
            for tld in (".com", ".in"):
                state, detail = probe_domain(f"{plain}{tld}")
                icon = {"serving": "❌ in use", "not-serving": "✅ not serving",
                        "unknown": "❔ unknown"}[state]
                out.append(f"   {icon:<14} {plain}{tld}  ({detail})")
            out.append("   ℹ️ 'not serving' = site ledu, kani registered aa leda "
                       "ani proof kaadu — registrar lo final confirm cheyyandi.")
        else:
            out.append("   ℹ️ Live ga verify cheyyadaniki: "
                       f"python -m bot name {plain} --live")
        out += [
            "",
            "📌 Apply cheyyi (rendu commands):",
            f'   python -m bot brand "{res["name"]} | Home & Kitchen Finds"',
            f"   python -m bot handle {plain}",
        ]

    out += [
        "",
        "⚠️  Ee names already in use (avoid):",
    ]
    for key, why in list(KNOWN_USED.items())[:6]:
        out.append(f"   • {key}: {why}")
    out += [
        "",
        "💡 Coined (ownable) options — meaning tho:",
    ]
    for cand in blends(6):
        out.append(f"   • {cand['name']} ({cand['handle']}) — "
                   f"{cand['meaning']} [{cand['score']}/100]")
    out += [
        "",
        "🎯 Rule: descriptive names anni crowded. Coined name + NAME field lo "
        "keywords = ownable brand + full keyword reach.",
    ]
    return out
