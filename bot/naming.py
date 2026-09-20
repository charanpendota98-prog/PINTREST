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
WEAK_WORDS = ("deal", "deals", "store", "shop", "mart", "mall", "buy", "cart",
              "super", "mega", "hot", "best", "top", "big", "daily")
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
    "superdeals": "Super Deals India (FB), Superdeals.in (FB), Online SUPER DEALS "
                  "(Chandigarh) — plus the same name on every platform: generic "
                  "promo phrase, not a brand",
    "superdeal": "same clutter as 'superdeals' — every deals page uses it",
    "dropvana": "dropvana.org — live store (clothing/sports accessories)",
    "pickora": "pickora.com + @pickora on IG/TikTok — the name is taken "
               "platform-wide",
    "haulvana": "haulvana.com — waste-management SaaS (unrelated, still taken)",
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
    already_used = plain in KNOWN_USED
    if already_used:
        risks.append(f"⚠️ Already in use: {KNOWN_USED[plain]}")
    elif weak:
        pts += 8
        reasons.append(f"'{weak[0]}' word undi — common, distinctiveness thakkuva.")
    else:
        pts += 20
        reasons.append("Distinctive — ee name tho already unna accounts thakkuva "
                       "(thokkalo, brand build avutundi).")

    total = max(0, min(100, pts))
    if already_used:
        # Honest ceiling: a name that is already out there cannot be "strong",
        # however tidy it looks on paper.
        total = min(total, 60)
        grade = "⛔ already in use — vaddu"
    else:
        grade = ("🏆 FINAL pick" if total >= 85 else
                 "✅ strong" if total >= 70 else
                 "⚠️ usable" if total >= 55 else "❌ vaddu")
    return {"name": raw, "plain": plain, "score": total, "grade": grade,
            "reasons": reasons, "risks": risks, "syllables": syll}


NAME_FIELD_MAX = 30       # Pinterest truncates longer names on mobile


def name_field_options(brand: str) -> list[str]:
    """Keyword-rich NAME fields for a brand word (≤30 chars so nothing truncates).

    This is where "deals" belongs: the NAME field is the ranked, visible field,
    while the brand word stays short so it can be owned and remembered.
    """
    plain = re.sub(r"[^A-Za-z0-9 ]", "", str(brand or "")).strip()
    if not plain:
        return []
    tails = ("Home Deals & Finds", "Deals & Home Finds", "Home, Kitchen & Deals",
             "Deals & Finds", "Home & Kitchen")
    out: list[str] = []
    for tail in tails:
        cand = f"{plain} | {tail}"
        if len(cand) <= NAME_FIELD_MAX:
            out.append(cand)
    return out


def spelling_variants(base: str) -> list[dict]:
    """Coined respellings of a brand word — same sound, still ownable.

    Used when the exact word is taken: a doubled vowel or a different ending
    keeps the name recognisable AND gives a fresh, claimable handle.
    """
    plain = re.sub(r"[^a-z]", "", str(base or "").lower())
    if not plain:
        return []
    out: list[dict] = []
    stem = plain[:-1] if plain.endswith(("a", "i", "o", "u")) else plain
    ideas = [
        (stem + "aa", "double vowel — same sound, Indian-style spelling"),
        (stem + "ah", "'ah' ending — same pronunciation, different spelling"),
        (stem + "ika", "'-ika' suffix — brand-like, easy to say"),
        (stem + "ora", "'-ora' suffix — modern brand feel"),
        (stem + "iya", "'-iya' suffix — warm, brandable"),
        (stem + "aya", "'-aya' ending — keeps the rhythm, easy to type"),
    ]
    for word, why in ideas:
        if word == plain or len(word) > 14 or _clusters(word):
            continue
        res = score(word)
        if res["score"] < 70 or any("already in use" in r.lower()
                                   for r in res["risks"]):
            continue
        out.append({"name": word.capitalize(), "handle": word, "why": why,
                    "score": res["score"]})
    return out


def taken_plan(brand: str, niche: str = "Home") -> list[str]:
    """'Handle taken' ki full plan: handle variants + spelling variants + fresh names."""
    base = re.sub(r"[^a-z0-9]", "", str(brand or "").lower()) or "yourbrand"
    title = str(brand or "").split("|")[0].strip().title() or base.title()
    niche_word = re.sub(r"[^a-z]", "", niche.lower()) or "home"
    handle_opts = [
        (base + niche_word, f"brand + niche ('{niche_word}') — SEO-friendly, "
                            "first thing to try"),
        (base + "deals", "brand + 'deals' — matches the positioning"),
        (base + "finds", "brand + 'finds' — matches the NAME field wording"),
        ("the" + base, "'the' prefix — reads like the official account"),
        (base + "india", "market keyword — India audience signal"),
        ("get" + base, "'get' prefix — action word, voice-search friendly"),
        (base + "hq", "'hq' — short, modern, brand-studio feel"),
        (base + "_" + niche_word, "intentional separator (never a trailing "
                                  "underscore)"),
    ]
    out = [
        "═" * 66,
        f"🚨 '{base}' HANDLE TAKEN — plan (brand ni marchalsina avasaram ledu)",
        "═" * 66,
        "   Try order (Pinterest lo paste → free aa? → Instagram lo kuda same",
        "   handle check cheyyi → dorikindi save cheyyi):",
        "",
        "1️⃣ Same brand + suffix/prefix (4-6 chars extra, brand gurthu pettukuntaru)",
    ]
    for i, (h, why) in enumerate(handle_opts, 1):
        h = clean_handle(h)[:HANDLE_MAX] if "clean_handle" in globals() else h[:30]
        out.append(f"   {i}. @{h}  — {why}")

    out += ["", "2️⃣ Same sound, different spelling (brand word kuda fresh + claimable)"]
    variants = spelling_variants(base)
    if variants:
        for v in variants:
            out.append(f"   • {v['name']}  (@{v['handle']}) — {v['why']} "
                       f"[{v['score']}/100]")
        out.append("   ℹ️ Spelling maarithe NAME field kuda maarchali "
                   f"(ex: '{variants[0]['name']} | Home Deals & Finds') — "
                   "appudu brand + handle rendu nee vi avutayi.")
    else:
        out.append("   (variants generate avvaledu — base already variant-la undi)")

    out += ["", "3️⃣ Kotha coined name (brand word marudam ante)"]
    fresh = [c for c in blends(8) if c["handle"] != base][:6]
    for cand in fresh:
        out.append(f"   • {cand['name']}  (@{cand['handle']}) — "
                   f"{cand['meaning']} [{cand['score']}/100]")

    out += [
        "",
        "⚙️  ANNI okkasari check + save (VPS lo):",
        f"   python -m bot handle check --pick {' '.join(h for h, _ in handle_opts[:5])}",
        "   → Pinterest + Instagram rendu chotla free unna MODATI handle ni",
        "     automatic ga save chestundi (adhigam lo print chestundi).",
        "",
        "⚙️  Manual ga okati ishtam ante:",
        "   python -m bot handle gharvanahome",
    ]
    return out


def deals_formula(brand: str) -> list[str]:
    """The honest answer to 'shall we just call it SuperDeals?'."""
    plain = re.sub(r"[^A-Za-z0-9]", "", str(brand or "")).lower() or "yourbrand"
    return [
        "🎯 DEALS POSITIONING — formula (why 'SuperDeals' is not the move)",
        "",
        "   ⛔ 'SuperDeals' problem: it is a PROMO PHRASE, not a brand.",
        "      • Already in use: Super Deals India (FB), Superdeals.in (FB),",
        "        Online SUPER DEALS (Chandigarh) — plus every deals page ever.",
        "      • Generic = no recall: evaru gurthu pettukoru, and Pinterest",
        "        'super/hot/daily' promo words ni spam-la chustundi (reach down).",
        "      • Trademark/claim cheyyalem — evadaina vaadagaladu.",
        "",
        "   ✅ Correct formula: OWNED brand word + 'Deals' keyword in the NAME field",
        f"      Name field  : {plain.title()} | Home Deals & Finds   (ranked, visible)",
        f"      Pin strip   : {plain.title()}   (short artwork word)",
        f"      Handle      : @{plain}",
        "      Bio/boards  : 'deals' word + categories (home, kitchen, fashion…)",
        "",
        "   💡 Enduku ila: Pinterest lo NAME field = keyword ranking,",
        "      brand word = recall + ownability. Rendu kalipithe 2x labham.",
    ]


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
        # When the candidate is already taken, show the formula with the
        # configured brand word instead of the rejected one.
        suggest = res["name"]
        if plain in KNOWN_USED and cfg is not None:
            try:
                configured = str(cfg.get("design.brand_name", "") or "").strip()
                suggest = configured or suggest
            except Exception:  # noqa: BLE001
                pass
        out += deals_formula(suggest) + [""]
        handle = plain[:20]
        out += [
            "",
            f"   Handle candidate: @{handle}",
            f"   NAME field (unique kaadu, ranking ikkada): "
            f"{(name_field_options(res['name']) or [res['name']])[0]}",
            "",
        ]
        if live:
            from . import handles as _h
            out.append("🔎 LIVE CHECK")
            lines = _h.check_lines([handle], limit=1)
            out += lines
            if any("taken" in line for line in lines):
                out += [""] + taken_plan(res["name"])
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
