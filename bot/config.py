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
        "pins_per_product": 2,    # pin variations per product (different photos+designs)
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
    "instagram": {
        "enabled": False,          # set true once token is ready
        "ig_user_id": "",          # or IG_USER_ID in .env
        "mode": "carousel",        # single | carousel | reel
        "posts_per_day": 3,
        "host_designed_pins": False,  # upload designed pins to ImgBB (needs IMGBB_KEY)
        "caption_template": (
            "🔥 {title}\n💰 Price: {price}\n"
            "🛒 Comment 'LINK' — link in bio!\n{hashtags}"
        ),
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
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

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
    return Config(raw=merged)
