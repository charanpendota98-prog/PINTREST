"""Instagram auto-poster (official Meta Graph API).

Posts the same products to your Instagram Professional page:
  * single image post     (designed pin or product photo)
  * carousel post         (up to 10 photos)
  * REELS                 (product video — needs a public video URL / hosting)

The Graph API only accepts PUBLIC https URLs, so:
  - designed pins are uploaded to ImgBB first (free key) when IMGBB_KEY is set
  - otherwise the original product photo URL (Amazon/Meesho CDN) is used

Setup (one time):
  1. Instagram account → switch to Professional (Creator/Business)
  2. Connect it to a Facebook Page (Instagram settings → Linked accounts)
  3. Create a Meta app at developers.facebook.com with products:
     "Instagram API with Instagram Login" or Facebook Login; add permissions:
       instagram_basic, instagram_content_publish, pages_show_list,
       pages_read_engagement
  4. Get a long-lived User token, find your IG user id:
       GET https://graph.facebook.com/v19.0/me/accounts  →  page id
       GET https://graph.facebook.com/v19.0/{page-id}?fields=instagram_business_account
  5. .env:  INSTAGRAM_ACCESS_TOKEN=...   IG_USER_ID=...   (optional IMGBB_KEY=...)

Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing/
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

GRAPH = "https://graph.facebook.com/v19.0"
log = logging.getLogger("pindrop.instagram")


class InstagramError(Exception):
    pass


class InstagramAPI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
        self.ig_user_id = (
            os.getenv("IG_USER_ID", "").strip()
            or str(cfg.get("instagram.ig_user_id", "") or "").strip()
        )
        self.imgbb_key = os.getenv("IMGBB_KEY", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("instagram.enabled", False))

    @property
    def configured(self) -> bool:
        return bool(self.token and self.ig_user_id)

    # ----------------------------------------------------------------- api
    def _post(self, path: str, **params) -> dict:
        resp = requests.post(
            f"{GRAPH}/{path}",
            params={"access_token": self.token},
            data=params,
            timeout=90,
        )
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if resp.status_code >= 400 or "error" in data:
            raise InstagramError(
                f"Instagram API {resp.status_code}: {str(data.get('error', data))[:300]}"
            )
        return data

    def _get(self, path: str, **params) -> dict:
        resp = requests.get(
            f"{GRAPH}/{path}", params={"access_token": self.token, **params}, timeout=60
        )
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            raise InstagramError(
                f"Instagram API {resp.status_code}: {str(data.get('error', data))[:300]}"
            )
        return data

    # --------------------------------------------------------------- check
    def check(self) -> dict:
        return self._get(
            self.ig_user_id,
            fields="username,name,media_count,followers_count,account_type",
        )

    # ------------------------------------------------------------- hosting
    def upload_imgbb(self, image_path: str) -> str:
        """Upload a local image to ImgBB (free hosting) → public URL."""
        if not self.imgbb_key:
            return ""
        try:
            data = base64.b64encode(Path(image_path).read_bytes()).decode()
            resp = requests.post(
                "https://api.imgbb.com/1/upload",
                data={"key": self.imgbb_key, "image": data},
                timeout=90,
            )
            out = resp.json()
            if out.get("success"):
                return out["data"]["url"]
            log.warning("ImgBB upload failed: %s", str(out)[:200])
        except requests.RequestException as exc:
            log.warning("ImgBB error: %s", exc)
        return ""

    # ------------------------------------------------------------- publish
    def _publish(self, container_id: str) -> str:
        data = self._post(f"{self.ig_user_id}/media_publish", creation_id=container_id)
        return str(data.get("id", ""))

    def post_single(self, image_url: str, caption: str) -> str:
        c = self._post(f"{self.ig_user_id}/media", image_url=image_url, caption=caption[:2200])
        return self._publish(c["id"])

    def post_carousel(self, image_urls: list[str], caption: str) -> str:
        children = []
        for url in image_urls[:10]:
            c = self._post(
                f"{self.ig_user_id}/media",
                image_url=url,
                media_type="CAROUSEL_CHILD",
            )
            children.append(c["id"])
        container = self._post(
            f"{self.ig_user_id}/media",
            media_type="CAROUSEL",
            children=",".join(children),
            caption=caption[:2200],
        )
        return self._publish(container["id"])

    def post_reel(self, video_url: str, caption: str) -> str:
        c = self._post(
            f"{self.ig_user_id}/media",
            media_type="REELS",
            video_url=video_url,
            caption=caption[:2200],
        )
        # reels process asynchronously; publish anyway
        return self._publish(c["id"])
