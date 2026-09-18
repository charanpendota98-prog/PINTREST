"""Official Pinterest API v5 client.

Covers everything the bot needs:
  * OAuth2 (authorization-code + PKCE for first login, then refresh tokens)
  * user account check
  * board list/create/find
  * image pins (url or base64) + scheduled pins (created_time)
  * video upload (2-step) + video pins

Tokens are cached in data/pinterest_token.json and auto-refreshed.
Docs: https://developers.pinterest.com/docs/api/v5/
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = "https://api.pinterest.com/v5"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
AUTH_URL = "https://www.pinterest.com/oauth/"
SCOPES = ("boards:read,boards:write,pins:read,pins:write,"
          "user_accounts:read,trends:read")

log = logging.getLogger("pindrop.pinterest")


class PinterestError(Exception):
    pass


class PinterestAPI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.app_id = cfg.pinterest_app_id
        self.app_secret = cfg.pinterest_app_secret
        self._token_path: Path = cfg.token_path
        self._token: dict = {}
        self._load_token()

    # ---------------------------------------------------------------- auth
    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_secret and self._refresh_token)

    @property
    def _refresh_token(self) -> str:
        return (self._token.get("refresh_token") or self.cfg.pinterest_refresh_token).strip()

    def auth_url(self) -> tuple[str, str]:
        """Returns (url_for_user_to_visit, code_verifier)."""
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        params = {
            "response_type": "code",
            "client_id": self.app_id,
            "redirect_uri": self.cfg.get("pinterest.redirect_uri"),
            "scope": SCOPES,
            "state": secrets.token_urlsafe(16),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return url, verifier

    def exchange_code(self, code: str, verifier: str) -> dict:
        resp = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(self.app_id, self.app_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.cfg.get("pinterest.redirect_uri"),
                "code_verifier": verifier,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise PinterestError(f"Token exchange failed: {resp.status_code} {resp.text[:300]}")
        self._save_token(resp.json())
        return self._token

    def ensure_access_token(self) -> str:
        """Return a valid access token, refreshing when needed."""
        exp = self._token.get("expires_at", 0)
        if self._token.get("access_token") and time.time() < exp - 300:
            return self._token["access_token"]
        if not self._refresh_token:
            raise PinterestError(
                "No Pinterest credentials. Run: python -m bot auth   (first time)"
            )
        resp = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(self.app_id, self.app_secret),
            data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
            timeout=30,
        )
        if resp.status_code != 200:
            raise PinterestError(
                f"Token refresh failed ({resp.status_code}). "
                f"Run `python -m bot auth` again. Detail: {resp.text[:300]}"
            )
        self._save_token(resp.json())
        return self._token["access_token"]

    def _save_token(self, data: dict) -> None:
        data["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        # keep old refresh token if API didn't return a new one
        if not data.get("refresh_token") and self._token.get("refresh_token"):
            data["refresh_token"] = self._token["refresh_token"]
        self._token = data
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(data, indent=2))
        try:
            os.chmod(self._token_path, 0o600)
        except OSError:
            pass

    def _load_token(self) -> None:
        if self._token_path.exists():
            try:
                self._token = json.loads(self._token_path.read_text())
            except json.JSONDecodeError:
                self._token = {}

    # ------------------------------------------------------------- request
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.ensure_access_token()}"}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = path if path.startswith("http") else f"{API}{path}"
        for attempt in range(3):
            try:
                resp = requests.request(
                    method, url, headers=self._headers(), timeout=60, **kwargs
                )
            except requests.RequestException as exc:
                raise PinterestError(f"Network error: {exc}") from exc
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                log.warning("Rate limited by Pinterest; sleeping %ss", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            try:
                data = resp.json()
            except ValueError:
                data = {"raw": resp.text[:300]}
            if resp.status_code >= 400:
                raise PinterestError(
                    f"Pinterest API {resp.status_code}: {json.dumps(data)[:500]}"
                )
            return data
        raise PinterestError("Pinterest API: too many retries")

    # ------------------------------------------------------------ account
    def user_account(self) -> dict:
        return self._request("GET", "/user_account")

    # -------------------------------------------------------------- boards
    def list_boards(self) -> list[dict]:
        boards, bookmark = [], None
        while True:
            params = {"page_size": 100}
            if bookmark:
                params["bookmark"] = bookmark
            data = self._request("GET", "/boards", params=params)
            boards += data.get("items", [])
            bookmark = data.get("bookmark")
            if not bookmark:
                return boards

    def create_board(self, name: str, description: str = "") -> dict:
        body = {"name": name, "privacy": "PUBLIC"}
        if description:
            body["description"] = description
        return self._request("POST", "/boards", json=body)

    def ensure_board(self, name: str, description: str = "") -> str:
        """Return board_id for `name`, creating it if needed (SEO description)."""
        for b in self.list_boards():
            if b.get("name", "").lower() == name.lower():
                return b["id"]
        brand = self.cfg.get("design.brand_name", "PinDrop Pro")
        desc = description or (f"{name} — latest offers, price drops & top-rated "
                               f"finds curated by {brand}. Best deals India: "
                               f"online shopping, discounts & combo offers.")
        board = self.create_board(name, desc)
        log.info("Created board '%s' (id=%s)", name, board.get("id"))
        return board["id"]

    # ---------------------------------------------------------------- pins
    def _pin_body(self, board_id: str, link: str, title: str, description: str,
                  media_source: dict, alt_text: str = "",
                  scheduled_for: datetime | None = None,
                  board_section_id: str = "") -> dict:
        body: dict = {
            "board_id": board_id,
            "link": link,
            "title": title[:100],
            "description": description[:800],
            "alt_text": (alt_text or title)[:500],
            "media_source": media_source,
        }
        if board_section_id:
            body["board_section_id"] = board_section_id
        if scheduled_for:
            when = scheduled_for.astimezone(timezone.utc)
            if when < datetime.now(timezone.utc) + timedelta(minutes=2):
                when = datetime.now(timezone.utc) + timedelta(minutes=10)
            if when > datetime.now(timezone.utc) + timedelta(days=14):
                raise PinterestError("Pinterest allows scheduling max 14 days ahead")
            body["created_time"] = when.strftime("%Y-%m-%dT%H:%M:%S")
        return body

    @property
    def upload_images(self) -> bool:
        """Upload designed pins through the API instead of hotlinking a CDN.

        Why: `source_type: image_url` makes PINTEREST fetch the URL. Store
        CDNs sometimes block that fetch (or the image 404s later) and the pin
        silently fails. Uploading our own file guarantees the exact designed
        pin ships, forever.
        """
        return bool(self.cfg.get("pinterest.upload_images", True))

    def upload_image(self, file_path: str) -> str:
        """Upload a local image → media_id (v5 /media, image_base64 fallback)."""
        try:
            return self.upload_media(file_path, "image")
        except PinterestError as exc:
            log.info("image upload path unavailable (%s) — using base64", exc)
            return ""

    def upload_media(self, file_path: str, media_type: str = "video") -> str:
        """Upload media via the CURRENT v5 endpoint, legacy fallback.

        v5: POST /media (register) → upload to the returned S3 target →
            GET /media/{id} until status is succeeded/ready.
        Legacy /videos is still tried for video when registration is refused
        (older apps), so an account is never left unable to post video pins.
        """
        p = Path(file_path)
        if not p.is_file():
            raise PinterestError(f"media file missing: {file_path!r}")
        mime = mimetypes.guess_type(str(p))[0] or (
            "video/mp4" if media_type == "video" else "image/jpeg")
        try:
            reg = self._request("POST", "/media", json={"media_type": media_type})
        except PinterestError as exc:
            if media_type == "video":
                return self._upload_video_legacy(file_path)
            data = base64.b64encode(p.read_bytes()).decode()
            return "base64:" + data          # caller falls back to inline
        media_id = str(reg.get("media_id") or reg.get("id") or "")
        upload_url = reg.get("upload_url")
        params = reg.get("upload_parameters") or {}
        if not media_id or not upload_url:
            raise PinterestError(f"media register returned no target: {reg}")
        try:
            with p.open("rb") as fh:
                if params:
                    # S3 presigned POST → multipart form with the signed fields
                    up = requests.post(upload_url, data=params,
                                       files={"file": (p.name, fh.read(), mime)},
                                       timeout=900)
                else:
                    up = requests.put(upload_url, data=fh.read(), timeout=900)
        except requests.RequestException as exc:
            raise PinterestError(f"media upload network error: {exc}") from exc
        if up.status_code >= 400:
            raise PinterestError(
                f"media upload failed: {up.status_code} {up.text[:200]}")
        # wait for processing (videos take longer than images)
        for i in range(30):
            try:
                st = self._request("GET", f"/media/{media_id}")
            except PinterestError:
                return media_id
            status = str(st.get("status") or st.get("media_status") or "")
            if status in ("succeeded", "ready", "success"):
                return media_id
            if status in ("failed", "error"):
                raise PinterestError(f"Pinterest media processing failed: {st}")
            time.sleep(4 if media_type == "image" else 10)
        raise PinterestError("media processing timed out")

    def _upload_video_legacy(self, file_path: str) -> str:
        """Legacy /videos flow (kept for older apps during transition)."""
        mime = mimetypes.guess_type(file_path)[0] or "video/mp4"
        with open(file_path, "rb") as fh:
            reg = self._request("POST", "/videos",
                                data={"media_type": mime.split("/")[-1]},
                                files={"file": (Path(file_path).name, fh, mime)})
        upload_url = reg.get("upload_url")
        params = reg.get("upload_parameters", {}) or {}
        media_id = reg.get("id")
        if upload_url:
            with open(file_path, "rb") as fh:
                up = requests.put(upload_url, params=params, data=fh.read(),
                                  timeout=600)
            if up.status_code >= 400:
                raise PinterestError(
                    f"Video upload failed: {up.status_code} {up.text[:200]}")
            for _ in range(30):
                time.sleep(10)
                status = self._request("GET", f"/videos/{media_id}")
                if status.get("media_status") == "ready":
                    return media_id
                if status.get("media_status") == "failed":
                    raise PinterestError("Pinterest video processing failed")
            raise PinterestError("Video processing timed out")
        return media_id

    def upload_video(self, file_path: str) -> str:
        """2-step Pinterest video upload; returns media_id (v5 first)."""
        return self.upload_media(file_path, "video")

    def create_image_pin(
        self,
        board_id: str,
        link: str,
        title: str,
        description: str,
        image_path: str | None = None,
        image_url: str | None = None,
        alt_text: str = "",
        scheduled_for: datetime | None = None,
        board_section_id: str = "",
    ) -> dict:
        """Single image pin.

        Priority: API-uploaded image_id (most reliable) → inline base64 →
        public image_url. Whichever path is used, Pinterest gets a real file.
        """
        media_source: dict | None = None
        if image_path:
            if self.upload_images:
                try:
                    media_id = self.upload_image(image_path)
                    if media_id.startswith("base64:"):
                        raise PinterestError("using inline base64")
                    if media_id:
                        media_source = {"source_type": "image_id",
                                        "media_id": media_id}
                except Exception as exc:  # noqa: BLE001 — any upload hiccup
                    log.info("falling back to inline pin (%s)", exc)
            if media_source is None and image_url and not image_path:
                media_source = {"source_type": "image_url", "url": image_url}
            if media_source is None:
                data = base64.b64encode(Path(image_path).read_bytes()).decode()
                media_source = {
                    "source_type": "image_base64",
                    "content_type": mimetypes.guess_type(image_path)[0] or "image/jpeg",
                    "data": data,
                }
        elif image_url:
            media_source = {"source_type": "image_url", "url": image_url}
        else:
            raise PinterestError("create_image_pin needs image_path or image_url")

        return self._request("POST", "/pins", json=self._pin_body(
            board_id, link, title, description, media_source, alt_text,
            scheduled_for, board_section_id))

    def create_carousel_pin(
        self,
        board_id: str,
        items: list[dict],
        link: str,
        title: str,
        description: str,
        alt_text: str = "",
        scheduled_for: datetime | None = None,
        board_section_id: str = "",
    ) -> dict:
        """Carousel pin (up to 5 images) — the highest-engagement pin format.

        items: [{"url": <public image url>, "title": ..., "link": ...}, ...]
        The FIRST item is the hero; each item may carry its own link so the
        buyer lands on the exact variant they tapped.
        """
        clean = [i for i in items if i.get("url")][:5]
        if len(clean) < 2:
            raise PinterestError("carousel needs 2-5 public image URLs")
        media_source = {
            "source_type": "multiple_image_urls",
            "items": [{"url": i["url"],
                       "title": (i.get("title") or title)[:100],
                       "description": (i.get("description") or description)[:500],
                       "link": i.get("link") or link} for i in clean],
        }
        return self._request("POST", "/pins", json=self._pin_body(
            board_id, link, title, description, media_source, alt_text,
            scheduled_for, board_section_id))

    def create_video_pin(
        self,
        board_id: str,
        media_id: str,
        link: str,
        title: str,
        description: str,
        alt_text: str = "",
        scheduled_for: datetime | None = None,
        board_section_id: str = "",
    ) -> dict:
        return self._request("POST", "/pins", json=self._pin_body(
            board_id, link, title, description,
            {"source_type": "video_id", "media_id": media_id},
            alt_text, scheduled_for, board_section_id))

    # ------------------------------------------------------------- sections
    def list_sections(self, board_id: str) -> list[dict]:
        sections, bookmark = [], None
        while True:
            params = {"page_size": 100}
            if bookmark:
                params["bookmark"] = bookmark
            data = self._request("GET", f"/boards/{board_id}/sections",
                                 params=params)
            sections += data.get("items", [])
            bookmark = data.get("bookmark")
            if not bookmark:
                return sections

    def ensure_section(self, board_id: str, name: str) -> str:
        """Board section (sub-board) for a niche — keeps a big board tidy and
        lets Pinterest show a more relevant board on each pin."""
        try:
            for sec in self.list_sections(board_id):
                if sec.get("name", "").lower() == name.lower():
                    return sec["id"]
            sec = self._request("POST", f"/boards/{board_id}/sections",
                                json={"name": name[:50]})
            log.info("Created board section '%s' (id=%s)", name, sec.get("id"))
            return str(sec.get("id", ""))
        except PinterestError as exc:
            log.info("board section unavailable (%s) — pinning to board root", exc)
            return ""

    # ------------------------------------------------------------ analytics
    def pin_analytics(self, pin_id: str, days: int = 7,
                      metrics: tuple[str, ...] = ("IMPRESSION", "SAVE",
                                                  "PIN_CLICK", "OUTBOUND_CLICK")
                      ) -> dict:
        """Real Pinterest metrics for one pin (impressions, saves, clicks).

        This is the honest source of truth for 'did this pin work?' — our own
        landing-click counter only sees people who reached the bridge page.
        """
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(1, days))
        params = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "metric_types": ",".join(metrics),
            "granularity": "TOTAL",
        }
        data = self._request("GET", f"/pins/{pin_id}/analytics", params=params)
        out: dict[str, float] = {"pin_id": pin_id}
        for k, v in (data or {}).items():
            if isinstance(v, (int, float)) and k.upper() == k:
                out[k.lower()] = float(v)
        # some responses nest under 'summary_metrics'
        for m in data.get("summary_metrics", []) or []:
            if isinstance(m, dict) and m.get("metric_type"):
                try:
                    out[m["metric_type"].lower()] = float(m.get("value", 0) or 0)
                except (TypeError, ValueError):
                    continue
        return out

    # --------------------------------------------------------------- trends
    def trends_top(self, region: str = "IN", trend_type: str = "growing",
                   limit: int = 20, interests: str = "") -> list[dict]:
        """Official Pinterest Trends keywords for your region.

        trend_type: growing | monthly | seasonal | yearly
        Needs the `trends:read` scope (re-run `bot auth` once). Best-effort:
        callers fall back to the built-in winner list when it 403s.
        """
        params: dict = {"limit": max(1, min(limit, 50))}
        if interests:
            params["interests"] = interests
        data = self._request(
            "GET", f"/trends/keywords/{region}/top/{trend_type}", params=params)
        return data.get("trends", data.get("items", [])) or []
