"""Product radar — continuously find the products people ACTUALLY need.

Owner's brief: "top lo unnadi mana link tho konāli… top products, most useful
products eppudu vethukutū undāli". So this module answers two questions:

  1. WHICH products are genuinely useful (worth posting at all)?
  2. WHICH of them should go out FIRST while demand is hot?

Usefulness score (0-100, deterministic, offline):

  demand category     0-22   kitchen/home-organizers/beauty problem-solvers
                             are bought on impulse AND repeat-purchased.
                             (Pinterest's best niches: home decor,
                             organisation, women's fashion, beauty, wedding)
  problem solver      0-18   does the title name a problem it kills?
                             (organizer/rack/storage/clean/… → conversion gold)
  evergreen           0-14   useful all year vs. single-festival gimmicks
  price sweet spot    0-14   ₹299-₹999 converts on impulse in India
  repeat purchase     0-12   consumables (beauty, refills) come back monthly
  gift / wedding      0-10   high-intent, high-value Indian occasions
  review trust        0-10   rating/review count when the source exposes it

Everything is capped at 100 and every part is explainable, so `bot radar`
can print WHY a product is ranked where it is — no black box.
"""
from __future__ import annotations

import re

# ------------------------------------------------ demand categories (0-22)
# Highest = bought on impulse and/or bought again. Order reflects 2026
# Pinterest/IG data: home organisation + women's fashion + beauty lead.
DEMAND_TIERS = [
    (22, ("organizer", "organiser", "storage", "rack", "holder", "hanger",
          "kitchen", "spice", "container")),
    (20, ("kurta", "kurti", "saree", "lehenga", "dupatta", "dress", "top",
          "jeans", "co-ord", "nighty")),
    (19, ("serum", "cream", "sunscreen", "lipstick", "kajal", "makeup",
          "hair", "shampoo", "oil")),
    (17, ("bedsheet", "curtain", "cushion", "lamp", "decor", "wall", "mat",
          "towel", "pillow", "diya", "rangoli", "pooja", "fairy light",
          "string light")),
    (15, ("bottle", "flask", "tiffin", "lunch", "cookware", "pan", "mixer")),
    (14, ("watch", "wallet", "bag", "sling", "shoe", "sandal", "heel")),
    (13, ("toy", "puzzle", "kids", "baby", "school")),
    (12, ("gadget", "charger", "cable", "earphone", "headphone", "light",
          "trimmer", "fan")),
    (10, ("book", "stationery", "pen", "diary")),
]

# ------------------------------------------------ problem solvers (0-18)
PROBLEM_WORDS = ("organizer", "organiser", "storage", "rack", "holder",
                 "stackable", "foldable", "portable", "self adhesive",
                 "waterproof", "rechargeable", "adjustable", "multipurpose",
                 "space saving", "non stick", "leak proof", "anti slip")

# ------------------------------------------------ evergreen vs gimmick (0-14)
EVERGREEN = ("daily", "regular", "basic", "essential", "combo", "pack of",
             "set of", "cotton", "steel", "reusable", "washable", "premium")
FESTIVAL_ONLY = ("diwali special", "christmas", "new year", "holi", "rakhi",
                 "birthday return gift", "festival combo")

# ------------------------------------------------ repeat purchase (0-12)
REPEAT = ("serum", "cream", "shampoo", "refill", "cartridge", "replacement",
          "filter", "wipe", "tissue", "diaper", "pads", "soap", "oil")

GIFT_WORDS = ("gift", "combo", "hamper", "wedding", "bridal", "anniversary",
              "return gift")

IMPULSE_BAND = (299, 999)          # India impulse sweet spot
STRETCH_BAND = (150, 1999)         # still fine, slightly less


def _num(value) -> float:
    """'₹1,299.00' -> 1299.0 ; junk/negative -> 0.0  (never raises).

    A negative or absurd price must never earn the impulse-price bonus —
    stripping the sign used to turn '-500' into a valid-looking 500.
    """
    raw = str(value or "").replace(",", "").strip()
    if raw.startswith("-") or "-" in raw.split(".")[0][:1]:
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.]", "", raw)
        if not cleaned or cleaned.count(".") > 1:
            return 0.0
        val = float(cleaned)
        return val if 0 < val <= 1_000_000 else 0.0     # sanity ceiling
    except (TypeError, ValueError):
        return 0.0


def _season_ahead(text: str, days: int = 45) -> bool:
    """Is a festival (matching the product or any) coming within `days`?

    Uses the same FESTIVALS calendar the scheduler boosts pins with, so the
    radar and the posting multiplier always agree.
    """
    try:
        from datetime import datetime
        from .growth import FESTIVALS
    except Exception:  # noqa: BLE001
        return False
    now = datetime.now()
    for m, d, name, kw in FESTIVALS:
        try:
            fest = datetime(now.year, m, d)
        except ValueError:
            continue
        delta = (fest - now).days
        if delta < 0:
            fest = datetime(now.year + 1, m, d)
            delta = (fest - now).days
        if 0 <= delta <= days:
            needle = (kw or name or "").lower()
            if not needle or needle in text or "festival" in text \
                    or "special" in text or "diya" in text or "gift" in text:
                return True
    return False


def _text(product: dict) -> str:
    return f"{product.get('title', '')} {product.get('seo_text', '')}".lower()


def usefulness(product: dict, *, rating: float = 0.0,
               reviews: int = 0) -> tuple[int, list[str]]:
    """Score 0-100 + human-readable reasons (exactly what `bot radar` prints)."""
    if not product or not str(product.get("title", "")).strip():
        return 0, ["no title"]
    text = _text(product)
    reasons: list[str] = []
    score = 0

    # 1) demand category
    for points, words in DEMAND_TIERS:
        hit = next((w for w in words if w in text), "")
        if hit:
            score += points
            reasons.append(f"demand: '{hit}' (+{points})")
            break
    else:
        if any(w in text for w in ("cover", "case", "stand")):
            score += 8
            reasons.append("demand: accessory (+8)")

    # 2) problem solver
    hits = [w for w in PROBLEM_WORDS if w in text]
    if hits:
        pts = min(18, 9 * len(hits))
        score += pts
        reasons.append(f"problem-solver: {hits[0]} (+{pts})")

    # 3) evergreen vs festival-only — but TIMELY festive stock is gold, so a
    # festive product within 45 days of its festival scores like evergreen.
    low = text
    festive = any(w in low for w in FESTIVAL_ONLY)
    if festive:
        if _season_ahead(low, 45):
            score += 14
            reasons.append("festive + season is near (+14, timely)")
        else:
            reasons.append("festival-only, off-season (+0)")
    else:
        ev = 14 if any(w in text for w in EVERGREEN) else 8
        score += ev
        reasons.append(f"evergreen (+{ev})")

    # 4) price sweet spot
    price = _num(product.get("price"))
    if price:
        lo, hi = IMPULSE_BAND
        slo, shi = STRETCH_BAND
        if lo <= price <= hi:
            score += 14
            reasons.append(f"impulse price ₹{price:.0f} (+14)")
        elif slo <= price <= shi:
            score += 7
            reasons.append(f"stretch price ₹{price:.0f} (+7)")
        else:
            reasons.append(f"price ₹{price:.0f} outside band (+0)")

    # 5) repeat purchase
    rep = next((w for w in REPEAT if w in text), "")
    if rep:
        score += 12
        reasons.append(f"repeat purchase: {rep} (+12)")

    # 6) gifting / wedding intent
    gift = next((w for w in GIFT_WORDS if w in text), "")
    if gift:
        score += 10
        reasons.append(f"high-intent occasion: {gift} (+10)")

    # 7) social proof when the source exposes it
    try:
        r = float(rating or 0)
        n = int(reviews or 0)
    except (TypeError, ValueError):
        r, n = 0.0, 0
    if r >= 4.0 and n >= 100:
        score += 10
        reasons.append(f"social proof {r:.1f}★ ×{n} (+10)")
    elif r >= 4.0:
        score += 5
        reasons.append(f"good rating {r:.1f}★ (+5)")
    # 7b) pure VOLUME — thousands of ratings = it is trending RIGHT NOW
    if r >= 4.0 and n >= 1000:
        score += 6
        reasons.append(f"🔥 trending volume: {n:,} ratings (+6)")

    return min(100, score), reasons


def rank(products: list[dict], limit: int = 20) -> list[dict]:
    """Rank products by usefulness. Returns copies + score/reasons (no mutation)."""
    scored = []
    for p in products or []:
        if not p or not str(p.get("title", "")).strip():
            continue
        s, why = usefulness(p, rating=p.get("rating", 0),
                            reviews=p.get("reviews", 0))
        row = dict(p)
        row["usefulness"] = s
        row["why"] = why
        scored.append(row)
    scored.sort(key=lambda r: (-r["usefulness"], -int(r.get("score", 0) or 0),
                               int(r.get("id", 0) or 0)))
    return scored[:max(1, limit)]


def top_picks(products: list[dict], n: int = 5,
              min_score: int = 40) -> list[dict]:
    """The products worth posting right now (usefulness >= min_score)."""
    return [p for p in rank(products, limit=200)
            if p["usefulness"] >= min_score][:max(1, n)]


def radar_view(cfg, db, n: int = 10) -> dict:
    """Live radar: what the queue holds, what is worth adding, what to fix.

    Never raises: every section degrades to empty rather than breaking a
    dashboard request or a CLI run.
    """
    out: dict = {"queued": [], "posted": [], "best": [], "notes": []}
    try:
        queued = [p for p in db.all_products(limit=400)
                  if p.get("status") == "queued"]
        posted = [p for p in db.all_products(limit=400)
                  if p.get("status") == "posted"]
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"db read failed: {exc}")
        return out
    out["queued"] = rank(queued, limit=n)
    out["posted"] = rank(posted, limit=n)
    out["best"] = top_picks(queued + posted, n=n,
                            min_score=int(cfg.get_int("radar.min_score", 40)))
    min_score = cfg.get_int("radar.min_score", 40)
    weak = [p for p in out["queued"] if p["usefulness"] < min_score]
    if weak:
        out["notes"].append(
            f"{len(weak)} queued product(s) score below {min_score} — they will "
            "still post, but the radar would hunt better ones first "
            "(`python -m bot radar --hunt`)")
    if not out["best"]:
        out["notes"].append("nothing scores high enough yet — run "
                            "`python -m bot radar --hunt` to source top products")
    return out


def radar_hunt(cfg, engine, n: int = 4, min_score: int = 40,
               per_niche: int = 2, budget_seconds: float | None = None) -> list[dict]:
    """Hunt the TOP useful products: discover -> scrape -> score -> queue best.

    Only the winners get ingested (media download + pin design are expensive),
    and the freshly scored products jump ahead of random fillers in the queue
    because `score` is what `pending_products()` orders by.

    Time-bounded on purpose: a slow/blocked network must never stall the run
    loop. Stops when (a) enough candidates collected, (b) the budget is spent,
    or (c) the network fails repeatedly — and says so instead of hanging.

    Returns the products that were actually added, with score + reasons.
    """
    import time as _time
    from .trends import sourcing_plan
    added: list[dict] = []
    candidates: list[tuple[dict, object]] = []      # (scored row, scraped prod)
    limit = max(2, int(cfg.get_int("autopilot.discover_limit", 4)))
    if budget_seconds is None:
        budget_seconds = float(cfg.get_int("radar.budget_seconds", 120))
    deadline = _time.monotonic() + max(5.0, float(budget_seconds))
    misses = 0                                      # consecutive discovery fails
    for store, query, niche in sourcing_plan(per_niche=per_niche):
        if _time.monotonic() > deadline:
            _log(engine, "WARN", f"radar: time budget ({int(budget_seconds)}s) "
                                 f"spent — using {len(candidates)} candidate(s)")
            break
        try:
            urls = engine.scraper.discover_products(store, limit=limit,
                                                    query=query) or []
        except Exception as exc:  # noqa: BLE001 — discovery is best-effort
            misses += 1
            _log(engine, "WARN", f"radar discovery {store}/{query} failed: {exc}")
            if misses >= 3:
                _log(engine, "WARN", "radar: stores unreachable 3x in a row — "
                                     "skipping this hunt (will retry next cycle)")
                break
            continue
        if not urls:
            # the scraper swallows network errors and returns [] — trust its
            # failure counter so a dead network ends the hunt in seconds
            misses += 1
            if getattr(engine.scraper, "net_down", False) or misses >= 3:
                _log(engine, "WARN", "radar: stores unreachable — skipping this "
                                     "hunt (will retry next cycle)")
                break
            continue
        misses = 0
        for url in urls:
            if _time.monotonic() > deadline:
                break
            if engine.db.url_exists(url):
                continue
            try:
                prod = engine.scraper.scrape(url)
            except Exception as exc:  # noqa: BLE001
                _log(engine, "WARN", f"radar scrape failed: {exc}")
                continue
            if not getattr(prod, "ok", False):
                continue
            row = {"title": getattr(prod, "title", "") or "",
                   "price": getattr(prod, "price", "") or "",
                   "url": url, "source": getattr(prod, "source", store),
                   "seo_text": getattr(prod, "seo_text", "") or "",
                   "rating": float(getattr(prod, "rating", 0.0) or 0.0),
                   "reviews": int(getattr(prod, "reviews", 0) or 0)}
            score, why = usefulness(row, rating=row["rating"],
                                    reviews=row["reviews"])
            candidates.append(({**row, "usefulness": score, "why": why}, prod))
            try:
                engine.scraper.polite_wait()
            except Exception:  # noqa: BLE001
                pass
        if len(candidates) >= max(n * 2, 6):
            break

    candidates.sort(key=lambda c: -c[0]["usefulness"])
    from . import topics as _topics
    try:
        queued_titles = [p.get("title", "") for p in
                         (engine.db.pending_products(limit=50) or [])]
    except Exception:  # noqa: BLE001
        queued_titles = []
    taken_buckets = [_topics.bucket(t) for t in queued_titles]
    try:
        taken_stores = [str(p.get("source") or "") for p in
                        (engine.db.pending_products(limit=50) or [])]
    except Exception:  # noqa: BLE001
        taken_stores = []
    for row, prod in candidates:
        if len(added) >= n:
            break
        if row["usefulness"] < min_score and added:
            continue                      # never pad with weak products
        b = _topics.bucket(row["title"])
        if not _topics.allows_more(b, taken_buckets, queued_titles):
            _log(engine, "INFO", f"radar: skipped '{row['title'][:40]}' — queue "
                                 f"already has 3+ {b} items (feed variety)")
            continue
        # store mix: don't let ONE store own the queue (payout + platform risk)
        from . import scale as _scale
        if not _scale.mix_ok(row.get("source", ""), taken_stores):
            _log(engine, "INFO", f"radar: skipped '{row['title'][:40]}' — queue "
                                 f"is already mostly {row.get('source')} "
                                 f"(store mix)")
            continue
        try:
            pid = engine.ingest_url(row["url"], prefetched=prod)
        except Exception as exc:  # noqa: BLE001
            _log(engine, "WARN", f"radar ingest failed {row['url'][:60]}: {exc}")
            continue
        if pid and pid > 0:
            try:
                engine.db.update_product(pid, score=row["usefulness"])
            except Exception:  # noqa: BLE001
                pass
            taken_buckets.append(b)
            taken_stores.append(str(row.get("source") or ""))
            added.append({**row, "product_id": pid})
    if added:
        _log(engine, "INFO", f"🧭 Radar queued {len(added)} top product(s) — "
                             f"best {added[0]['usefulness']}/100")
    return added


def _log(engine, level: str, message: str) -> None:
    try:
        engine.db.log(level, message)
    except Exception:  # noqa: BLE001
        pass
