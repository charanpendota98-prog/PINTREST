"""Facebook Page auto-posting — same Meta Graph family as Instagram.

Post targets: a Facebook PAGE you own (personal profiles can't be posted to
via API — pages are the professional route, and it's 100% official).

Setup (one-time):
  1. Create a Facebook Page for your deals brand
  2. Meta for Developers → app → token with pages_manage_posts +
     pages_read_engagement for that page
  3. .env:  FACEBOOK_ACCESS_TOKEN=...   FACEBOOK_PAGE_ID=...

Everything is best-effort: FB being down/off never blocks Pinterest/IG.
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("pindrop.facebook")

GRAPH = "https://graph.facebook.com/v19.0"


class FacebookError(RuntimeError):
    pass


class FacebookAPI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
        self.page_id = (os.getenv("FACEBOOK_PAGE_ID", "").strip()
                        or str(cfg.get("facebook.page_id", "")).strip())

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("facebook.enabled", False))

    @property
    def configured(self) -> bool:
        return bool(self.token and self.page_id)

    # ------------------------------------------------------------ helpers
    def _post(self, path: str, **data) -> dict:
        r = requests.post(f"{GRAPH}/{path}",
                          data={"access_token": self.token, **data}, timeout=60)
        if r.status_code >= 400:
            raise FacebookError(f"FB {r.status_code}: {r.text[:200]}")
        return r.json()

    # ------------------------------------------------------------- posts
    def post_photo(self, image_url: str, caption: str) -> str:
        """Photo post on the page with deal caption (+ link inside text)."""
        out = self._post(f"{self.page_id}/photos",
                         url=image_url, caption=caption[:5000])
        return str(out.get("id", ""))

    def post_link(self, url: str, message: str) -> str:
        """Plain link post (landing/bridge page)."""
        out = self._post(f"{self.page_id}/feed", link=url, message=message[:5000])
        return str(out.get("id", ""))

    def check(self) -> dict:
        r = requests.get(f"{GRAPH}/{self.page_id}",
                         params={"access_token": self.token,
                                 "fields": "id,name,followers_count"}, timeout=30)
        if r.status_code >= 400:
            raise FacebookError(f"FB check {r.status_code}: {r.text[:200]}")
        return r.json()
