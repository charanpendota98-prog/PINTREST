"""YouTube Shorts uploader — optional extra money surface.

Why YouTube: Shorts descriptions allow clickable affiliate links and
YouTube search keeps sending traffic for YEARS (Pinterest-style evergreen),
which is why Meesho's own "Get commission link" screen lists
"YouTube Shorts/videos". We already generate a vertical reel per product —
this module publishes that same reel as a Short with your link inside.

Setup (one time, your Google account — 4 minutes):
  1. console.cloud.google.com → new project → enable "YouTube Data API v3"
  2. OAuth consent screen (External, add yourself as test user)
  3. Create OAuth client ID → type: Desktop app
  4. .env:  YT_CLIENT_ID=...   YT_CLIENT_SECRET=...
  5. python -m bot yt-auth-url      → open URL, click Allow, copy code
     python -m bot yt-auth --code <CODE>   → refresh token saved

Everything is best-effort: a failed upload NEVER blocks the Pinterest post.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("pindrop.youtube")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=multipart&part=snippet,status")
SCOPES = "https://www.googleapis.com/auth/youtube.upload"


class YouTubeError(RuntimeError):
    pass


class YouTubeAPI:
    def __init__(self, cfg):
        self.cfg = cfg
        self.redirect_uri = str(cfg.get("youtube.redirect_uri",
                                        "http://localhost:8080/"))
        self.token_path = Path(str(cfg.get("youtube.token_file",
                                           "data/yt_token.json")))
        if not self.token_path.is_absolute():
            self.token_path = Path(__file__).resolve().parent.parent / self.token_path
        self._cached_token = ""

    # ------------------------------------------------------------- config
    @property
    def client_id(self) -> str:
        # read env live (so exporting credentials after import still works)
        return (os.getenv("YT_CLIENT_ID", "") or
                self.cfg.get("youtube.client_id", "") or "").strip()

    @property
    def client_secret(self) -> str:
        return (os.getenv("YT_CLIENT_SECRET", "") or
                self.cfg.get("youtube.client_secret", "") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("youtube.enabled", False))

    @property
    def refresh_token(self) -> str:
        if os.getenv("YT_REFRESH_TOKEN", "").strip():
            return os.getenv("YT_REFRESH_TOKEN", "").strip()
        try:
            if self.token_path.exists():
                return json.loads(self.token_path.read_text()).get(
                    "refresh_token", "")
        except (OSError, ValueError):
            return ""
        return ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "client": bool(self.client_id and self.client_secret),
            "refresh_token": bool(self.refresh_token),
            "configured": self.configured,
        }

    # --------------------------------------------------------------- auth
    def auth_url(self) -> str:
        from urllib.parse import urlencode
        if not (self.client_id and self.client_secret):
            raise YouTubeError(
                "YT_CLIENT_ID / YT_CLIENT_SECRET missing in .env — create an "
                "OAuth 'Desktop app' client at console.cloud.google.com "
                "(enable YouTube Data API v3).")
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> str:
        """Swap the pasted code for a long-lived refresh token (saved)."""
        if not (self.client_id and self.client_secret):
            raise YouTubeError("YT_CLIENT_ID / YT_CLIENT_SECRET missing in .env")
        resp = requests.post(TOKEN_URL, data={
            "code": code.strip(),
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
        if resp.status_code != 200:
            raise YouTubeError(f"token exchange failed: "
                               f"{resp.status_code} {resp.text[:300]}")
        data = resp.json()
        rt = data.get("refresh_token", "")
        if not rt:
            raise YouTubeError("Google did not return a refresh token — "
                               "re-run yt-auth-url (consent prompt forces it)")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps({"refresh_token": rt}, indent=2))
        try:
            self.token_path.chmod(0o600)
        except OSError:
            pass
        self._cached_token = data.get("access_token", "")
        return rt

    def _access_token(self) -> str:
        if self._cached_token:
            return self._cached_token
        if not self.configured:
            raise YouTubeError("YouTube not configured (see bot yt-auth-url)")
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            raise YouTubeError(f"token refresh failed: {resp.status_code} "
                               f"{resp.text[:200]}")
        self._cached_token = resp.json().get("access_token", "")
        if not self._cached_token:
            raise YouTubeError("no access_token in refresh response")
        return self._cached_token

    # ------------------------------------------------------------- upload
    def upload_short(self, video_path: str, title: str, description: str,
                     tags: list[str] | None = None) -> str:
        """Upload a vertical reel as a Short. Returns the video id."""
        p = Path(video_path or "")
        if not p.is_file():
            raise YouTubeError(f"video file missing: {video_path!r}")
        token = self._access_token()
        snippet = {
            "title": (title or "Deal")[:95] + " #Shorts",
            "description": description[:4900],
            "tags": (tags or [])[:15],
            "categoryId": str(self.cfg.get("youtube.category_id", "26")),  # 26 = Howto/Style
        }
        status = {
            "privacyStatus": str(self.cfg.get("youtube.privacy", "public")),
            "selfDeclaredMadeForKids": bool(
                self.cfg.get("youtube.made_for_kids", False)),
        }
        body = {"snippet": snippet, "status": status}
        files = {
            "metadata": ("metadata.json", json.dumps(body),
                         "application/json; charset=UTF-8"),
            "video": (p.name, p.read_bytes(), "video/mp4"),
        }
        resp = requests.post(
            UPLOAD_URL, files=files,
            headers={"Authorization": f"Bearer {token}"}, timeout=300)
        if resp.status_code not in (200, 201):
            raise YouTubeError(f"upload failed: {resp.status_code} "
                               f"{resp.text[:300]}")
        return str(resp.json().get("id", ""))
