"""Configuration loader: merges config.yaml (behavior) + .env (secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DEFAULTS: dict[str, Any] = {
    "pinterest": {
        "board_name": "Best Deals",          # board to post into (auto-created if missing)
        "redirect_uri": "http://localhost:8888/callback",
    },
    "posting": {
        "pins_per_day": 8,
        "start_hour": 9,          # IST posting window start
        "end_hour": 22,           # IST posting window end
        "min_gap_minutes": 40,    # minimum gap between two pins
        "jitter_minutes": 25,     # random extra delay (looks human)
        "schedule_days_ahead": 0, # 0 = post immediately; 1-14 = schedule ahead
        "pins_per_product": 3,    # pin variations per product (different photos+designs)
        "peak_mode": True,        # post only in peak IST traffic windows
        "board_strategy": "niche",  # niche = keyword boards per category (more reach)
        # owner strategy: build IG + FB buzz first, Pinterest after
        "platform_order": ["instagram", "facebook", "pinterest"],
    },
    "link": {
        "bridge": False,          # true = pins link to YOUR domain /go/<id> (tracked)
        "public_base": "",        # e.g. https://yourdeals.in (where dashboard is hosted)
        "landing": True,          # show a high-converting mini landing page (vs raw 302)
        "whatsapp_share": False,  # WhatsApp share button on landing (owner said NO → off)
    },
    "scraping": {
        "delay_seconds": 4.0,
        "timeout_seconds": 25,
        "max_retries": 2,
        "max_images": 3,          # gallery photos to download per product
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    },
    "design": {
        "width": 1000,
        "height": 1500,
        "accent_color": "#E60023",   # Pinterest red
        "brand_name": "Deal Drops",  # small brand strip on every pin ("" = off)
        "cta_text": "Shop Now ➜",
        "price_style": "badge",      # badge | banner
    },
    "affiliate": {
        # Amazon Associates tracking tag, e.g. "mydeals-21"
        "amazon_tag": "",
        # Meesho affiliate: your affid / campaign id appended to meesho links
        "meesho_affid": "",
        # Meesho collection link generated from affiliate.meesho.com
        # (used as "all deals" CTA on landing pages / IG bio)
        "meesho_collection_link": "",
        # Paste ONE af_invite link you generated on affiliate.meesho.com —
        # the bot learns your publisher+campaign IDs and generates af_invite
        # links for EVERY Meesho product automatically (direct commission).
        "meesho_template_link": "",
        # Flipkart affiliate id (FAS). If empty, flipkart links go through
        # earnkaro/cuelinks wrapper below instead.
        "flipkart_affid": "",
        # EarnKaro: your personal ekaro.in deeplink prefix,
        # e.g. "https://ekaro.in/enkr20240101s123456" — bot appends ?url=<product>
        "earnkaro_prefix": "",
        # Cuelinks: full template with {url} placeholder,
        # e.g. "https://clk.tradedoubler.com/click?...&url={url}"
        "cuelinks_template": "",
        # Generic fallback wrapper for any other shop: template with {url}
        "generic_template": "",
        # Which wrapper to use for non-amazon links when several are set:
        # amazon > meesho > flipkart > earnkaro > cuelinks > generic
        "default_wrapper": "earnkaro",
    },
    "seo": {
        "hashtags": True,
        "max_hashtags": 8,
        "extra_hashtags": ["#onlineshopping", "#bestdeals"],
        "description_template": (
            "🔥 {title}\n💰 Price: {price}\n✅ Best price guarantee — tap to grab "
            "this deal before it's gone!\n{hashtags}"
        ),
    },
    "roundup": {
        "enabled": True,   # daily "Deals of the Day" list pin (viral format)
        "count": 5,        # products per list pin
    },
    "facebook": {
        "enabled": False,          # set true once FB page token is ready
        "page_id": "",             # or FACEBOOK_PAGE_ID in .env
        "mode": "photo",           # photo | link (landing page)
    },
    "brand": {
        # 🏷️ Pinterest profile SEO (python -m bot brand writes these)
        "display_name": "",     # "PinDrop Deals | Home & Kitchen Finds"
        "bio": "",              # <=160 chars, keywords early + CTA
    },
    "instagram": {
        "enabled": False,          # set true once token is ready
        "ig_user_id": "",          # or IG_USER_ID in .env
        "mode": "carousel",        # single | carousel | reel
        "posts_per_day": 3,
        "auto_dm": True,           # ManyChat-grade keyword DM auto-answers
        "auto_bio_link": True,     # bio website auto-updates to latest deal
        "host_designed_pins": False,  # upload designed pins to ImgBB (needs IMGBB_KEY)
        "caption_template": (
            "🔥 {title}\n💰 Price: {price}\n"
            "🛒 Comment 'LINK' — link in bio!\n{hashtags}"
        ),
        # ManyChat-style keyword triggers → auto-replies (free, built-in).
        # {title} and {price} get filled per product automatically.
        "triggers": {
            "link": "🔥 {title} — only {price}! 😍 Link in bio — grab it now!",
            "price": "💰 {title} is just {price} right now — link in bio!",
            "buy": "🛒 To buy {title}: tap the LINK IN BIO — checkout on the official store!",
            "deal": "⚡ Yes! {title} at {price} is live — link in bio!",
            "cost": "💸 Cost of {title}: only {price}! Link in bio to order.",
        },
    },
    "video": {
        "auto_reel": True,   # no product video on the page? auto-generate a viral reel from photos
        "lang": "en-IN",     # voiceover language: en-IN | hi-IN | te-IN
        "music": "",         # optional BGM mp3 path (ducked under voiceover)
        "auto_music": True,  # no audio anywhere? compose ORIGINAL copyright-free BGM
    },
    "autopilot": {
        "auto_source": True,    # hunt trending products automatically when queue is low
        "min_queue": 5,         # trigger sourcing below this many queued pins
        "discover_limit": 4,    # products to discover per store per cycle
    },
    "storage": {
        "db_path": "data/pindrop.db",
        "media_dir": "data/media",
    },
    "dashboard": {
        "host": "0.0.0.0",
        "port": 5000,
    },
    "timezone": "Asia/Kolkata",
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Config:
    raw: dict = field(default_factory=dict)

    # convenience accessors -------------------------------------------------
    def get(self, path: str, default: Any = None) -> Any:
        """Dotted lookup with a safety net for EMPTY YAML values.

        YAML turns `width:` (no value) into None, and `int(None)` used to
        crash Engine() — i.e. the whole bot refused to start because one
        line in config.yaml was left blank. An empty key is now treated as
        "not set" so the built-in default applies.
        """
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        if node is None:
            return default
        if isinstance(node, str) and not node.strip() and default not in (None, ""):
            return default      # blank line in config.yaml → use the default
        return node


    def get_int(self, path: str, default: int = 0) -> int:
        """Never trust config.yaml for numbers: a typo like `pins_per_day: 8x`
        or `abc` must fall back to the default instead of killing the bot."""
        try:
            return int(float(str(self.get(path, default)).strip()))
        except (TypeError, ValueError):
            return int(default)

    def get_float(self, path: str, default: float = 0.0) -> float:
        try:
            return float(str(self.get(path, default)).strip())
        except (TypeError, ValueError):
            return float(default)

    def get_bool(self, path: str, default: bool = False) -> bool:
        """`yes/no/on/off/1/0/true/false` all work the way a human expects."""
        val = self.get(path, default)
        if isinstance(val, bool):
            return val
        if val is None:
            return bool(default)
        return str(val).strip().lower() in ("1", "true", "yes", "y", "on")

    # --- secrets come ONLY from environment (.env) --------------------------
    @property
    def pinterest_app_id(self) -> str:
        return os.getenv("PINTEREST_APP_ID", "")

    @property
    def pinterest_app_secret(self) -> str:
        return os.getenv("PINTEREST_APP_SECRET", "")

    @property
    def pinterest_refresh_token(self) -> str:
        return os.getenv("PINTEREST_REFRESH_TOKEN", "")

    @property
    def pinterest_access_token(self) -> str:
        """Trial access token copied straight from the developer dashboard.

        Pinterest's app page has "Generate access tokens" (Trial env) which hands
        out a ready token — useful to test the pipeline before/while the app is
        pending review, because the app secret is locked until approval. It is a
        short-lived convenience path; OAuth (refresh token) stays the permanent
        one.
        """
        return os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()

    @property
    def amazon_tag(self) -> str:
        return os.getenv("AMAZON_TAG", "") or self.get("affiliate.amazon_tag", "")

    @property
    def db_path(self) -> Path:
        p = ROOT / self.get("storage.db_path", "data/pindrop.db")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def media_dir(self) -> Path:
        p = ROOT / self.get("storage.media_dir", "data/media")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def token_path(self) -> Path:
        return ROOT / "data" / "pinterest_token.json"


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    user_cfg: dict = {}
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
    merged = _deep_merge(DEFAULTS, user_cfg)
    return _attach_source(Config(raw=merged), cfg_path)

def _attach_source(cfg: Config, path: Path) -> Config:
    """Remember the YAML file a config came from (writers need it)."""
    try:
        cfg.source_path = path
    except Exception:  # noqa: BLE001
        pass
    return cfg
