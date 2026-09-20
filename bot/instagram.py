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
    @staticmethod
    def _payload(resp) -> dict:
        """Parse a Graph response; never raise a raw JSON/HTTP error."""
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": (resp.text or "")[:300]}
        return data if isinstance(data, dict) else {"data": data}

    def _call(self, method: str, path: str, *, params: dict | None = None,
              data: dict | None = None, json_body: dict | None = None,
              timeout: int = 90) -> dict:
        """Single funnel for every Graph call.

        Network failures (SSL/DNS/timeout) and non-JSON bodies become
        InstagramError, so the dashboard, doctor and the 24×7 loop can never
        crash on a flaky connection.
        """
        if not self.configured:
            raise InstagramError("Instagram not configured (INSTAGRAM_ACCESS_TOKEN + IG_USER_ID)")
        try:
            resp = requests.request(
                method, f"{GRAPH}/{path}",
                params={"access_token": self.token, **(params or {})},
                data=data, json=json_body, timeout=timeout)
        except requests.RequestException as exc:
            raise InstagramError(f"Instagram network error: {exc}") from exc
        body = self._payload(resp)
        if resp.status_code >= 400 or "error" in body:
            raise InstagramError(
                f"Instagram API {resp.status_code}: {str(body.get('error', body))[:300]}"
            )
        return body

    def _post(self, path: str, **params) -> dict:
        return self._call("POST", path, data=params)

    def _post_json(self, path: str, body: dict) -> dict:
        return self._call("POST", path, json_body=body)

    def _get(self, path: str, **params) -> dict:
        return self._call("GET", path, params=params, timeout=60)

    # --------------------------------------------------------------- check
    def check(self) -> dict:
        return self._get(
            self.ig_user_id,
            fields="username,name,media_count,followers_count,account_type",
        )

    # ------------------------------------------------------------- hosting
    def upload_catbox(self, file_path: str) -> str:
        """Host a LOCAL reel video at a public URL (catbox.moe — free,
        anonymous, no account). IG pulls the video once at publish time."""
        try:
            with open(file_path, "rb") as fh:
                r = requests.post(
                    "https://catbox.moe/user/api.php",
                    data={"reqtype": "fileupload"},
                    files={"fileToUpload": fh},
                    timeout=180,
                )
            url = r.text.strip()
            if r.ok and url.startswith("http"):
                return url
            log.warning("Catbox upload failed: %s", url[:120])
        except requests.RequestException as exc:
            log.warning("Catbox upload error: %s", exc)
        return ""

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

    def post_story(self, image_url: str) -> str:
        """Publish an Instagram STORY (24h, top of feed = cheap reach).

        Honest note: the API cannot attach a tappable link STICKER (that's
        app-only). So the story carries a 'link in bio / DM us' CTA, and our
        bio auto-link + ManyChat-grade auto-DM deliver the actual buy link.
        """
        c = self._post(f"{self.ig_user_id}/media",
                       media_type="STORIES", image_url=image_url)
        return self._publish(c["id"])

    def post_story_video(self, video_url: str) -> str:
        c = self._post(f"{self.ig_user_id}/media",
                       media_type="STORIES", video_url=video_url)
        return self._publish(c["id"])

    # ------------------------------------------------------- engagement
    def auto_reply_links(self, reply: str = "🔗 Link in bio! Tap our bio & grab "
                         "the deal 😍",
                         max_per_cycle: int = 5,
                         reply_for=None,
                         dm_for=None,
                         is_answered=None,
                         mark_answered=None) -> int:
        """Answer trigger comments the ManyChat way: **DM first, reply second**.

        1. Someone comments "link" / "price" / "buy" (any configured keyword).
        2. The bot sends them a PRIVATE message with the product + buy link
           (official private-reply API, allowed for 7 days after the comment).
        3. It also leaves a short public reply so the comment gets visible
           engagement (boosts reach) — switch off with instagram.public_reply.

        Params
        ------
        reply_for(media_id, trigger) -> public reply text (per product)
        dm_for(media_id, trigger)    -> DM text with the DIRECT product link
        is_answered(comment_id)      -> already handled? (DB ledger, no dupes)
        mark_answered(comment_id)    -> record that we handled it

        Safety-first: capped per cycle, human-ish random delays, per-comment
        ledger so nobody is ever messaged twice, and every API error is
        logged + skipped (never fatal).
        """
        if not (self.enabled and self.configured):
            return 0

        import random as _r
        import time as _t
        n = 0
        dm_on = bool(self.cfg.get("instagram.private_dm", True))
        public_on = bool(self.cfg.get("instagram.public_reply", True))
        triggers = list((self.cfg.get("instagram.triggers") or {"link": ""}).keys())
        try:
            medias = self._get(f"{self.ig_user_id}/media", fields="id").get("data", [])[:8]
        except InstagramError:
            return 0
        for m in medias:
            if n >= max_per_cycle:
                break
            try:
                comments = self._get(
                    f"{m['id']}/comments",
                    fields="id,text,username").get("data", [])
            except InstagramError:
                continue
            for c in comments:
                if n >= max_per_cycle:
                    break
                cid = str(c.get("id") or "")
                low = (c.get("text") or "").lower()
                hit = next((k for k in triggers if k in low), "")
                if not hit or not cid:
                    continue
                if is_answered:
                    try:
                        if is_answered(cid):
                            continue          # never DM the same person twice
                    except Exception:  # noqa: BLE001
                        pass
                sent = False
                if dm_on and dm_for:
                    try:
                        body = dm_for(m["id"], hit) or ""
                    except Exception:  # noqa: BLE001
                        body = ""
                    if body:
                        sent = self.private_reply_to_comment(cid, body)
                        if not sent:
                            # token without messages scope: fall back to the
                            # public "link in bio" reply so the comment is
                            # still answered
                            public_on = True
                if public_on:
                    msg = reply
                    if reply_for:
                        try:
                            msg = reply_for(m["id"], hit) or reply
                        except Exception:  # noqa: BLE001
                            msg = reply
                    try:
                        self._post(f"{m['id']}/comments", message=msg)
                        sent = True
                    except InstagramError as exc:
                        log.warning("Comment reply skipped: %s", str(exc)[:120])
                if sent:
                    n += 1
                    if mark_answered:
                        try:
                            mark_answered(cid)
                        except Exception:  # noqa: BLE001
                            pass
                    # human-ish delay (configurable so tests/ops can zero it)
                    delay = self.cfg.get_float(
                        "instagram.reply_delay_seconds", 3.0)
                    if delay > 0:
                        _t.sleep(delay + _r.random() * 2)
        if n:
            log.info("Answered %d trigger comment(s) (%s)", n,
                     "DM" if dm_on else "public")
        return n

    # ------------------------------------------------- auto bio link
    def set_bio_link(self, url: str) -> bool:
        """'Insta auto direct link': after every post, the bio website is
        auto-updated to THIS deal (official Graph API profile update).
        Followers tap bio → straight to the money link. Best-effort."""
        if not self.cfg.get("instagram.auto_bio_link", True):
            return False
        if not (self.enabled and self.configured):
            return False
        try:
            self._post(f"{self.ig_user_id}", website=url)
            log.info("IG bio link → %s", url[:80])
            return True
        except InstagramError as exc:
            log.warning("Bio link update skipped: %s", str(exc)[:120])
            return False

    # ------------------------------------------------- ManyChat-style DMs
    def message_user(self, user_id: str, text: str) -> bool:
        """Send a DM to a user id (inside Instagram's 24h message window)."""
        try:
            self._post_json(f"{self.ig_user_id}/messages", {
                "recipient": {"id": str(user_id)},
                "message": {"text": str(text)[:1000]},
            })
            return True
        except InstagramError as exc:
            log.warning("DM send skipped: %s", str(exc)[:120])
            return False

    def private_reply_to_comment(self, comment_id: str, text: str) -> bool:
        """ManyChat's signature move, via the OFFICIAL API: reply to a comment
        with a PRIVATE message (DM) to whoever wrote it.

        Instagram allows this for 7 days after the comment, and it is the exact
        same endpoint ManyChat uses — no third party, no password sharing, no
        automation-detection trickery. Falls back to nothing (returns False)
        when the token lacks instagram_manage_messages.
        """
        if not (self.enabled and self.configured):
            return False
        if not comment_id:
            return False
        try:
            self._post_json(f"{self.ig_user_id}/messages", {
                "recipient": {"comment_id": str(comment_id)},
                "message": {"text": str(text)[:1000]},
            })
            return True
        except InstagramError as exc:
            log.warning("Private reply skipped: %s", str(exc)[:140])
            return False

    def auto_dm(self, reply_for=None, max_per_cycle: int = 5) -> int:
        """ManyChat-grade AUTO-DM via the OFFICIAL Instagram Messaging API
        (no third-party, no ban risk): polls conversations, answers keyword
        DMs ("link", "price", "buy"…) with the matching product + link.

        Needs instagram_manage_messages scope on the token. Best-effort:
        any API hiccup is logged and skipped, never fatal.
        """
        if not (self.enabled and self.configured):
            return 0
        import random as _r
        import time as _t
        if not self.cfg.get("instagram.auto_dm", True):
            return 0
        triggers = list((self.cfg.get("instagram.triggers") or {"link": ""}).keys())
        n = 0
        try:
            convs = self._get(
                f"{self.ig_user_id}/conversations",
                fields="messages{from,text,timestamp}",
            ).get("data", [])
        except InstagramError as exc:
            log.warning("DM poll skipped: %s", str(exc)[:120])
            return 0
        for conv in convs[:12]:
            if n >= max_per_cycle:
                break
            msgs = (conv.get("messages") or {}).get("data", [])
            if not msgs:
                continue
            last = msgs[0]
            frm = last.get("from") or {}
            if str(frm.get("id", "")) == str(self.ig_user_id):
                continue  # last message was ours — human already handled
            text = (last.get("text") or "").lower()
            hit = next((k for k in triggers if k in text), "")
            if not hit:
                continue
            body = ""
            if reply_for:
                try:
                    body = reply_for(hit, text) or ""
                except Exception:  # noqa: BLE001
                    body = ""
            if not body:
                body = "🔗 Link in bio! 😍"
            try:
                if self.message_user(frm.get("id"), body):
                    n += 1
                    delay = self.cfg.get_float(
                        "instagram.reply_delay_seconds", 3.0)
                    if delay > 0:
                        _t.sleep(delay + _r.random() * 2)
            except InstagramError as exc:
                log.warning("DM send skipped: %s", str(exc)[:120])
        if n:
            log.info("Auto-DM answered %d conversation(s)", n)
        return n
