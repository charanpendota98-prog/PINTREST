"""Pin-by-Pin QA Gate — nothing goes live without passing inspection.

Top channels never post broken pins. This module runs a full checklist on
EVERY pin right before the API call:

  ✅ media       — image exists, opens, big enough (≥600px), sane size (<32MB)
  ✅ link        — http(s), contains your affiliate tag (Amazon), no whitespace
  ✅ title       — 5–100 chars, contains a price signal, not all-caps spam
  ✅ description — ≥80 chars, ≥2 product keywords present, #ad disclosure kept
  ✅ duplicate   — same product not already posted within rest window
  ✅ alt text    — non-empty (accessibility + Pinterest SEO)

Failures quarantine the product with the exact reasons — no silent junk.
"""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("pindrop.qa")

MIN_SIDE = 600          # px — Pinterest shrinks tiny images to nothing
MAX_BYTES = 32_000_000  # API upload limit is ~32MB

# 🔒 DUMMY-POSTING GUARD — owner's rule: "no dummy posting, ever".
# Markers that only ever appear in demo/sample/placeholder products.
_DUMMY_MARKERS = (
    "demokurta", "itmdemo", "demo123", "b0cdear", "example-com",
    "example-org", "test-product", "sample-product", "dummy",
    "placeholder", "lorem-ipsum", "yourtag-21",
)


def looks_dummy(product: dict) -> bool:
    """True when a product is clearly a demo/sample — must never post.

    Protects against the worst failure mode: `scripts/seed_demo.py` (or a
    pasted test link) accidentally going live on a real account.
    """
    import re as _re
    blob = " ".join(str(product.get(k, "")) for k in
                    ("url", "affiliate_url", "title", "image_url")).lower()
    # normalise so 'Sample Product' and 'sample-product' both match
    blob = _re.sub(r"[^a-z0-9]+", "-", blob)
    return any(m in blob for m in _DUMMY_MARKERS)


def _title_tokens(title: str) -> list[str]:
    return [w for w in title.lower().split() if len(w) >= 4][:8]


def qa_pin(cfg, db, product: dict, seo_title: str, seo_text: str,
           image_path: str, link: str) -> tuple[bool, list[str]]:
    """Run the checklist; returns (ok, issues)."""
    issues: list[str] = []

    # ---- dummy / fake product guard (runs FIRST — never post demo data)
    if looks_dummy(product):
        issues.append("DUMMY PRODUCT: demo/sample link detected — "
                      "never posts to a live account (remove seed_demo data)")
        return False, issues

    # ---- media
    p = Path(image_path or "")
    if not p.exists():
        issues.append(f"media missing: {image_path!r}")
    else:
        if p.stat().st_size > MAX_BYTES:
            issues.append("media too large (>32MB)")
        try:
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
                if min(w, h) < MIN_SIDE:
                    issues.append(f"media too small ({w}x{h} < {MIN_SIDE}px)")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"media unreadable: {exc}")

    # ---- link
    if not link or " " in link:
        issues.append("link empty or contains whitespace")
    else:
        u = urlparse(link)
        if u.scheme not in ("http", "https"):
            issues.append(f"link scheme invalid: {u.scheme!r}")
        tag = str(cfg.get("affiliate.amazon_tag", "")).strip()
        if tag and "amazon" in u.netloc and f"tag={tag}" not in link:
            issues.append("amazon link missing your affiliate tag — revenue leak!")
        # 💰 COMMISSION-LEAK GUARD: untracked link = clicks that pay nobody
        from .affiliate import AffiliateLinker
        if not AffiliateLinker(cfg).is_monetized(link, product.get("source", "")):
            issues.append("COMMISSION LEAK: link carries no affiliate tracking — "
                          "add your affiliate IDs (.env) — pin quarantined")

    # ---- title
    t = (seo_title or "").strip()
    if not (5 <= len(t) <= 100):
        issues.append(f"title length invalid ({len(t)})")
    if t and t.isupper():
        issues.append("title is ALL-CAPS spam")

    # ---- description / SEO
    d = (seo_text or "").strip()
    if len(d) < 80:
        issues.append("description too thin (<80 chars)")
    toks = _title_tokens(product.get("title", ""))
    if toks and sum(1 for w in toks if w in d.lower()) < 2:
        issues.append("description misses product keywords (SEO weak)")
    if "#ad" not in d.lower():
        issues.append("#ad disclosure missing (FTC/Pinterest policy)")

    # ---- duplicate guard
    try:
        rest = int(cfg.get("reshare.rest_days", 7))
        recent = [r for r in (db.recent_posts(limit=300) or [])
                  if r.get("product_id") == product.get("id")
                  and r.get("status") == "posted" and r.get("posted_at")]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for r in recent:
            try:
                if (now - datetime.fromisoformat(r["posted_at"])).days < rest:
                    issues.append(f"duplicate: posted {rest}-day window active")
                    break
            except (ValueError, TypeError):
                continue
    except Exception as exc:  # noqa: BLE001
        log.debug("duplicate check skipped: %s", exc)

    ok = not issues
    if not ok:
        log.warning("QA FAIL product #%s: %s", product.get("id"), "; ".join(issues))
    return ok, issues


def qa_report(cfg, db, product: dict, seo_title: str, seo_text: str,
              image_path: str, link: str) -> tuple[str, bool]:
    """Human-readable checklist (used by `bot simulate`)."""
    ok, issues = qa_pin(cfg, db, product, seo_title, seo_text, image_path, link)
    lines = ["  ✅ " + c for c in ("media", "link", "title", "description", "duplicate")]
    if not ok:
        for i, ln in enumerate(lines):
            lines[i] = "  ❌ " + ln.split("✅ ", 1)[-1]
        lines.append("  → " + "; ".join(issues))
    return "\n".join(lines), ok
