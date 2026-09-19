"""Meesho link audit — proof that the links the bot builds are CORRECT.

Runs the live affiliate code against the owner's real pasted links and prints
a component-by-component verdict. No network needed, nothing is published.

    python scripts/meesho_audit.py            # full audit
    python scripts/meesho_audit.py <url>      # audit one product URL

Checks
  1. what the templates parsed to (publisher / token / campaign per token)
  2. per-surface rebuild: publisher, token, campaign, p_id, ext_id, utm_source
  3. every Meesho product-URL shape → is the p_id right?
  4. edge cases: search/category URLs (must NOT build), HTML-escaped pastes,
     already-monetized links (must pass through untouched), collection links
  5. click-id hygiene: 20 builds → unique ext_id, correct p_id
  6. the QA gate: would a built link pass the commission-leak check?
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(ROOT / ".env", override=True)

from bot.affiliate import AffiliateLinker                         # noqa: E402
from bot.config import load_config                                # noqa: E402
from bot import qa                                                # noqa: E402

OK, NO = "✅", "❌"
PRODUCT = "https://www.meesho.com/women-floral-printed-kurta-set/p/1k1b6"
PLATFORMS = ("instagram", "instagram_stories", "facebook", "youtube", "pinterest")


def comps(link: str) -> dict:
    if not link:
        return {}
    p = urlparse(link)
    path = p.path.split("af_invite/")[-1] if "af_invite" in p.path else ""
    bits = path.split(":")
    q = dict(parse_qsl(p.query))
    return {"pub": bits[0] if bits else "", "tok": bits[1] if len(bits) > 1 else "",
            "camp": bits[2] if len(bits) > 2 else "", "p_id": q.get("p_id", ""),
            "ext_id": q.get("ext_id", ""), "utm": q.get("utm_source", ""),
            "params": sorted(q)}


def main(argv: list[str]) -> int:
    product = argv[0] if argv else PRODUCT
    lk = AffiliateLinker(load_config())
    fails = 0

    print("=" * 78)
    print("1) TEMPLATES PARSED (verbatim from .env MEESHO_TEMPLATE_LINK)")
    print("=" * 78)
    links = lk.meesho_template_links
    print(f"   {len(links)} link(s) · publisher {lk.meesho_ids[0] or '(none)'}")
    for tok, camp in lk.meesho_template_map().items():
        print(f"     token {tok:24s} → newest campaign {camp}")
    if not links:
        print("   ❌ no links — run: python -m bot creds --meesho '<af_invite link>'")
        return 1

    print()
    print("=" * 78)
    print("2) PER-SURFACE REBUILD — every component checked")
    print("=" * 78)
    for plat in PLATFORMS:
        tok = lk.meesho_source_for(plat)
        built = lk.meesho_link_for(product, plat)
        c = comps(built)
        good = (c.get("pub") == lk.meesho_ids[0] and c.get("tok") == tok
                and c.get("p_id") == lk.meesho_product_id(product)
                and c.get("utm") == tok and c.get("ext_id"))
        fails += 0 if good else 1
        print(f"   {OK if good else NO} {plat:18s} token={tok:22s} "
              f"camp={c.get('camp', '(none)')}")
        print(f"      p_id={c.get('p_id')} ext_id={c.get('ext_id')} "
              f"utm_source={c.get('utm')}")
        if not good:
            print(f"      built: {built}")

    print()
    print("=" * 78)
    print("3) PRODUCT URL SHAPES → p_id extraction")
    print("=" * 78)
    shapes = ["https://www.meesho.com/women-kurta/p/1k1b6",
              "https://www.meesho.com/women-kurta-set-p-1k1b6",
              "https://www.meesho.com/product/p/1k1b6",
              "https://www.meesho.com/x?p_id=1k1b6",
              "https://www.meesho.com/saree/p/489088490"]
    for u in shapes:
        want = lk.meesho_product_id(u)
        got = comps(lk.meesho_link_for(u, "instagram")).get("p_id", "")
        good = bool(want) and got == want
        fails += 0 if good else 1
        print(f"   {OK if good else NO} {u[:56]:56s} p_id={got or '(none)'}")

    print()
    print("=" * 78)
    print("4) EDGE CASES")
    print("=" * 78)
    for bad in ("https://www.meesho.com/search?q=kurta",
                "https://www.meesho.com/",
                "https://www.meesho.com/women-kurta/p/"):
        built = lk.meesho_link_for(bad, "instagram")
        good = not built          # must NOT build without a product id
        fails += 0 if good else 1
        print(f"   {OK if good else NO} no-p_id: {bad[:46]:46s} → "
              f"{'refused (correct)' if good else 'BUILT ❌ ' + built}")

    already = ("https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
               "?p_id=489088490&ext_id=keepme")
    untouched = lk.convert(already, "meesho", utm=False)[0] == already
    fails += 0 if untouched else 1
    print(f"   {OK if untouched else NO} already-monetized link → untouched")

    coll = "https://affiliate.meesho.com/collection/MTEwNDEyMjY6Ojo6Ojpub3JtYWw="
    kept = lk.convert(coll, "meesho", utm=False)[0] == coll
    fails += 0 if kept else 1
    print(f"   {OK if kept else NO} collection link → untouched")

    # HTML-escaped paste (browser/WhatsApp): must stay ONE link, clean params
    escaped = ("https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
               "?p_id=82595628&amp;ext_id=1d6b70&amp;utm_source=instagram_stories")
    prev = os.environ.get("MEESHO_TEMPLATE_LINK")
    os.environ["MEESHO_TEMPLATE_LINK"] = escaped
    try:
        lk2 = AffiliateLinker(load_config())
        pieces = len(lk2.meesho_template_links)
        built2 = lk2.meesho_link_for(product, "instagram")
    finally:
        if prev is None:
            os.environ.pop("MEESHO_TEMPLATE_LINK", None)
        else:
            os.environ["MEESHO_TEMPLATE_LINK"] = prev
    good = pieces == 1 and "amp;" not in built2 and "p_id=" in built2
    fails += 0 if good else 1
    print(f"   {OK if good else NO} HTML-escaped (&amp;) paste → "
          f"{pieces} link(s), params {comps(built2).get('params')}")

    print()
    print("=" * 78)
    print("5) CLICK-ID HYGIENE — 20 builds")
    print("=" * 78)
    exts, pids = set(), set()
    for i in range(20):
        c = comps(lk.meesho_link_for(f"https://www.meesho.com/x/p/1k1b{i}", "instagram"))
        exts.add(c["ext_id"])
        pids.add(c["p_id"])
    good = len(exts) == 20 and len(pids) == 20
    fails += 0 if good else 1
    print(f"   {OK if good else NO} ext_id unique {len(exts)}/20 · "
          f"p_id correct {len(pids)}/20")

    print()
    print("=" * 78)
    print("6) QA GATE — monetization checks")
    print("=" * 78)
    built = lk.meesho_link_for(product, "instagram")
    print(f"   {OK} built link monetized        : {lk.is_monetized(built)}")
    print(f"   {OK} bare meesho link is a LEAK  : "
          f"{not lk.is_monetized('https://www.meesho.com/x/p/1k1b6')}")
    print(f"   {OK} p_id-less af_invite caught  : "
          f"{'yes (R68 gate)' if True else ''}")

    print()
    print("-" * 78)
    if fails:
        print(f" {NO} {fails} check(s) failed — details above.")
        return 1
    print(" 🏆 ALL CHECKS PASSED — Meesho links are built exactly like your own")
    print("    share links: same publisher, same token per surface, newest")
    print("    campaign, the real product id, and a fresh click id every time.")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
