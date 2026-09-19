"""R53c: Pinterest/IG handle — rules, ranked fallbacks when the first is taken, and saving.

`pindropdeals` is already taken on Pinterest, so the bot must be able to answer
"ippudu em pettali?" with a ranked list instead of a guess. Two constraints
shape the ranking (both verified rules, not opinions):

* Pinterest username = 3-30 chars, letters/digits/underscore only (no hyphen,
  no period, not all digits); Instagram allows the same set, so one candidate
  can be reused on both accounts — which is what keeps the brand consistent.
* The handle is a URL, not a ranked keyword field (the display NAME is the
  keyword field). So the fallback ladder prefers clean/readable variants before
  stuffing niche keywords into the handle.
"""
from __future__ import annotations

import re
from pathlib import Path

HANDLE_MIN, HANDLE_MAX = 3, 30
_ALLOWED = re.compile(r"^[a-z0-9_]+$")
_RESERVED = ("pinterest", "admin", "staff", "support", "official_")


def clean_handle(text: str) -> str:
    """Best-effort normalisation: lowercase, drop everything Pinterest rejects."""
    return re.sub(r"[^a-z0-9_]", "", str(text or "").strip().lower())


def validate_handle(handle: str) -> dict:
    """Pinterest rules (they also satisfy Instagram's letters/numbers/underscore)."""
    raw = str(handle or "").strip()
    h = raw.lower().lstrip("@")
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    if not h:
        errors.append("Handle khali undi.")
    else:
        if len(h) < HANDLE_MIN:
            errors.append(f"Chala podugu — minimum {HANDLE_MIN} characters.")
        if len(h) > HANDLE_MAX:
            errors.append(f"Chala podugu — maximum {HANDLE_MAX} characters "
                          f"({len(h)} undi).")
        bad = sorted({c for c in h if not re.match(r"[a-z0-9_]", c)})
        if bad:
            nice = " ".join(f"'{c}'" for c in bad)
            errors.append(f"{nice} allow cheyyaru — letters/numbers/underscore "
                          f"matrame (hyphen, dot, space ledu). "
                          f"Try: {clean_handle(h) or 'pindrop_deals'}")
        if h.isdigit():
            errors.append("Anni numbers unte Pinterest reject chestundi.")
        for word in _RESERVED:
            if word in h:
                warnings.append(f"'{word}' unte Pinterest impersonation ani "
                                "reject/limit cheyyochu — avoid.")
        if "__" in h or h.endswith("_"):
            warnings.append("Double underscore / last lo underscore = auto-"
                            "generated la kanipistundi, spam signal.")
        if len(h) > 20:
            notes.append("20+ chars: type cheyyadaniki kashtam, kani valid.")
        if h.endswith(("1", "2", "3", "01", "007")):
            warnings.append("Last lo number = duplicate/fan account la "
                            "kanipistundi — idi last option ga unchandi.")
        if "official" in h:
            notes.append("'official' ok, kani chala mandi vaadatharu — cluttered "
                         "ga kanipistundi.")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "notes": notes, "handle": h}


def handle_ideas(brand: str = "PinDrop Deals",
                 niche: str = "Home & Kitchen") -> list[dict]:
    """Ranked fallbacks. Order = try order (closest to brand first, numbers last)."""
    base = clean_handle(str(brand or "").split("|")[0]) or "pindropdeals"
    words = [w for w in re.split(r"[^a-z0-9]+", str(brand or "").lower())
             if w and w != "|"]
    underscore = "_".join(words) if len(words) > 1 else base
    niche_word = clean_handle(str(niche or "").split("&")[0]) or "home"
    drop = clean_handle(str(brand or "").split("|")[0].replace("deals", "deals"))

    ladder: list[tuple[str, str]] = [
        (underscore, "Closest to the brand — underscore exactly the space "
                     "(`PinDrop Deals` → `pindrop_deals`). Cleanest fallback."),
        (base + niche_word, f"Niche keyword add: search/suggest lo brand + "
                            f"'{niche_word}' kalisi kanipistundi."),
        (base + "india", "Market keyword: India audience ki direct ga signal "
                         "(and it reads as the official India account)."),
        ("the" + base, "'the' prefix — real-brand la kanipistundi, fan/"
                       "duplicate la kaadu."),
        ("get" + base, "'get' prefix — action word, tarvata 'Get PinDrop Deals' "
                       "la voice search ki baaguntundi."),
        (base + "hq", "'hq' suffix — short, modern, brand-studio feel."),
        (base + "co", "'co' suffix — company vibe, 30 chars lopu safe."),
        (base + "daily", "'daily' suffix — daily deals promise ki match "
                         "(bio lo kuda 'New deals daily' undi)."),
        (base + "shop", "'shop' suffix — shopping intent clear ga cheptundi."),
        (base + "official", "'official' suffix — ok, kani chala accounts "
                            "vaadatharu (last-resort tier)."),
        (base + "01", "Number suffix — LAST option: duplicate/fan account la "
                      "kanipistundi, trust thakkuva."),
    ]
    seen: set[str] = set()
    out: list[dict] = []
    for handle, why in ladder:
        h = clean_handle(handle)[:HANDLE_MAX]
        if len(h) < HANDLE_MIN or h in seen:
            continue
        seen.add(h)
        check = validate_handle(h)
        out.append({"handle": h, "why": why, "chars": len(h),
                    "ok": check["ok"], "warnings": check["warnings"]})
    return out


def plan_c(brand: str = "PinDrop Deals") -> list[str]:
    """If every PinDrop variant is gone: fresh, still-brandable families."""
    return ["dealdropsindia", "homedealsdrop", "smartfindsindia",
            "gharfinds", "dealfindsindia"]


def _patch_handle(text: str, handle: str) -> str:
    """Comment-preserving insert/replace of `brand.handle` (same rule as save()).

    Regression caught on the real config: the brand block was the LAST block in
    the file, so a naive "insert when the block ends" rule appended a second
    `brand:` block. Find the block bounds first, then edit inside them.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "brand:" and not line.startswith((" ", "\t")):
            start = i
            break
    if start is None:
        return "\n".join(lines + ["", "brand:", f"  handle: {handle}"]) + "\n"

    end = len(lines)                      # block runs to EOF unless dedented
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line.strip() and not line.startswith((" ", "\t")):
            end = j
            break

    block: list[str] = []
    wrote = False
    for line in lines[start + 1:end]:
        if line.strip().startswith("handle:"):
            block.append(f"  handle: {handle}")
            wrote = True
        else:
            block.append(line)
    if not wrote:
        block.insert(0, f"  handle: {handle}")
    return "\n".join(lines[:start + 1] + block + lines[end:]) + "\n"


def save_handle(cfg, handle: str, path: str | Path | None = None) -> dict:
    check = validate_handle(handle)
    if not check["ok"]:
        return {"saved": False, **check}
    cfg.raw.setdefault("brand", {})["handle"] = check["handle"]
    source = getattr(cfg, "source_path", None)
    target = (Path(path) if path
              else Path(source) if source
              else Path(__file__).resolve().parent.parent / "config.yaml")
    try:
        target.write_text(_patch_handle(target.read_text(), check["handle"]))
        import yaml
        yaml.safe_load(target.read_text())
        wrote = True
    except Exception:  # noqa: BLE001 — saving must never crash the CLI
        wrote = False
    return {"saved": wrote, **check}


def advice(cfg=None, handle: str = "") -> list[str]:
    """Everything the owner needs to end the 'username already taken' loop."""
    derived = "pindropdeals"
    try:
        derived = clean_handle(str(cfg.get("design.brand_name", "") or "")
                               ) or derived
    except Exception:  # noqa: BLE001
        pass
    saved = ""
    try:
        saved = str(cfg.get("brand.handle", "") or "") if cfg is not None else ""
    except Exception:  # noqa: BLE001
        pass

    out = [
        "═" * 66,
        "🔗 PINTEREST / INSTAGRAM HANDLE — rules + ranked fallbacks",
        "═" * 66,
        "   Rules: 3-30 chars · letters + numbers + underscore only",
        "          (hyphen ❌ dot ❌ space ❌ · anni numbers ❌)",
        "   Same set works on Instagram, so ONE handle rendu chotla vaadandi.",
        "",
        f"   Name field (idi unique kaadu): PinDrop Deals | Home & Kitchen",
        f"   Current handle in config: {saved or '(not set)'}",
        "",
        f"❌ '{derived}' Pinterest lo already taken.",
        "   Ippudu ee order lo try cheyyandi (top = best, numbers last):",
        "",
    ]
    for i, idea in enumerate(handle_ideas(), 1):
        mark = "✅" if not idea["warnings"] else "⚠️"
        out.append(f"   {i:>2}. {mark} {idea['handle']}  ({idea['chars']} chars)")
        for line in _wrap(idea["why"], 58):
            out.append(f"       {line}")
    out += [
        "",
        "🔁 Try order (2 nimishalu): Pinterest lo paste → taken aa? → next "
        "candidate → same handle Instagram lo kuda check cheyyandi.",
        "",
        "🆘 Antha 'pindrop*' taken aa? Fresh family:",
        "   " + " · ".join(plan_c()),
        "",
        "💡 Name field unique kaadu — 'PinDrop Deals | Home & Kitchen' pettachu"
        " (adi keyword field, ranking ikkada vastundi).",
        "   Handle lo keywords stuff cheyyakandi (adi URL matrame) — clean ga "
        "unchandi.",
        "",
        "⚙️  Fix cheyyi:  python -m bot handle pindrop_deals",
    ]
    if handle:
        check = validate_handle(handle)
        out += ["", f"🔍 YOUR HANDLE: {check['handle']} ({len(check['handle'])} chars)"]
        for e in check["errors"]:
            out.append(f"   ⛔ {e}")
        for w in check["warnings"]:
            out.append(f"   ⚠️ {w}")
        for n in check["notes"]:
            out.append(f"   ℹ️ {n}")
        if check["ok"] and not check["warnings"]:
            out.append("   ✅ Instagram ki kuda idi vaadachu.")
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
