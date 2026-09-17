"""Live Pinterest keyword research (the #1 "top views" trick).

Pinterest is a search engine — pins rank for the EXACT phrases people type.
Top creators mine Pinterest's own autocomplete (typeahead) for those phrases
and stuff them into titles/descriptions. This module does the same, with a
local cache + graceful offline fallback.

Endpoint is Pinterest's public typeahead resource (same data the search bar
uses). If it's ever blocked, the growth keyword bank is used instead.
"""
from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger("pindrop.keywords")

TYPEAHEAD = "https://www.pinterest.com/resource/TypeaheadResource/get/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*, q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}
CACHE_TTL = 6 * 3600  # 6h


def fetch_suggestions(seed: str, timeout: int = 10) -> list[str]:
    """Return live Pinterest autocomplete phrases for `seed` (or [])."""
    seed = (seed or "").strip()
    if not seed:
        return []
    data = json.dumps({"options": {"query": seed, "scope": "pins"}})
    try:
        resp = requests.get(
            TYPEAHEAD,
            params={"source_url": f"/search/pins/?q={seed}", "data": data},
            headers=HEADERS,
            timeout=timeout,
        )
        out = resp.json()
        results = (
            out.get("resource_response", {}).get("data", {}).get("results", []) or []
        )
        phrases = []
        for r in results:
            if isinstance(r, str):
                phrases.append(r)
            elif isinstance(r, dict):
                phrases.append(r.get("text") or " ".join(
                    t.get("text", "") for t in r.get("tokens", []) if isinstance(t, dict)
                ))
        clean = [p.strip() for p in phrases if p and p.strip()]
        if clean:
            log.info("Typeahead('%s') -> %d live phrases", seed, len(clean))
        return clean[:10]
    except (requests.RequestException, ValueError) as exc:
        log.warning("Typeahead unavailable (%s) — using offline keyword bank", exc)
        return []


class KeywordCache:
    """DB-backed cache so we never hammer Pinterest and work offline."""

    def __init__(self, db):
        self.db = db
        with db._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS keywords (
                       term TEXT PRIMARY KEY, suggestions TEXT NOT NULL, ts REAL NOT NULL
                   )"""
            )

    def get(self, seed: str) -> list[str]:
        with self.db._conn() as c:
            row = c.execute(
                "SELECT suggestions, ts FROM keywords WHERE term=?", (seed.lower(),)
            ).fetchone()
        if row and (time.time() - row["ts"]) < CACHE_TTL:
            return json.loads(row["suggestions"])
        fresh = fetch_suggestions(seed)
        keep = fresh or (json.loads(row["suggestions"]) if row else [])
        with self.db._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO keywords(term, suggestions, ts) VALUES(?,?,?)",
                (seed.lower(), json.dumps(keep), time.time()),
            )
        return keep

    def phrase_for(self, title: str) -> str:
        """Pick one live search phrase matching the product (or '')."""
        seed = " ".join(title.split()[:2])
        for p in self.get(seed):
            low = p.lower()
            if any(w in low for w in title.lower().split()[:3]):
                return p
        return ""
