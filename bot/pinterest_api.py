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
SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read"

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

    def ensure_board(self, name: str) -> str:
        """Return board_id for `name`, creating it if needed."""
        for b in self.list_boards():
            if b.get("name", "").lower() == name.lower():
                return b["id"]
        board = self.create_board(name, f"Auto-curated deals by {self.cfg.get('design.brand_name', 'PinDrop Pro')}")
        log.info("Created board '%s' (id=%s)", name, board.get("id"))
        return board["id"]

    # ---------------------------------------------------------------- pins
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
    ) -> dict:
        if image_path:
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

        body: dict = {
            "board_id": board_id,
            "link": link,
            "title": title[:100],
            "description": description[:800],
            "alt_text": (alt_text or title)[:500],
            "media_source": media_source,
        }
        if scheduled_for:
            when = scheduled_for.astimezone(timezone.utc)
            if when < datetime.now(timezone.utc) + timedelta(minutes=2):
                when = datetime.now(timezone.utc) + timedelta(minutes=10)
            if when > datetime.now(timezone.utc) + timedelta(days=14):
                raise PinterestError("Pinterest allows scheduling max 14 days ahead")
            body["created_time"] = when.strftime("%Y-%m-%dT%H:%M:%S")
        return self._request("POST", "/pins", json=body)

    # -------------------------------------------------------------- videos
    def upload_video(self, file_path: str) -> str:
        """2-step Pinterest video upload; returns media_id."""
        mime = mimetypes.guess_type(file_path)[0] or "video/mp4"
        reg = self._request(
            "POST",
            "/videos",
            data={"media_type": mime.split("/")[-1]},
            files={"file": (Path(file_path).name, open(file_path, "rb"), mime)},
        )
        upload_url = reg.get("upload_url")
        params = reg.get("upload_parameters", {}) or {}
        media_id = reg.get("id")
        if upload_url:
            with open(file_path, "rb") as fh:
                up = requests.put(upload_url, params=params, data=fh.read(), timeout=600)
            if up.status_code >= 400:
                raise PinterestError(f"Video upload failed: {up.status_code} {up.text[:200]}")
            # wait for Pinterest to finish processing
            for _ in range(30):
                time.sleep(10)
                status = self._request("GET", f"/videos/{media_id}")
                if status.get("media_status") == "ready":
                    return media_id
                if status.get("media_status") == "failed":
                    raise PinterestError("Pinterest video processing failed")
            raise PinterestError("Video processing timed out")
        return media_id

    def create_video_pin(
        self,
        board_id: str,
        media_id: str,
        link: str,
        title: str,
        description: str,
        scheduled_for: datetime | None = None,
    ) -> dict:
        body: dict = {
            "board_id": board_id,
            "link": link,
            "title": title[:100],
            "description": description[:800],
            "media_source": {"source_type": "video_id", "media_id": media_id},
        }
        if scheduled_for:
            when = scheduled_for.astimezone(timezone.utc)
            body["created_time"] = when.strftime("%Y-%m-%dT%H:%M:%S")
        return self._request("POST", "/pins", json=body)
