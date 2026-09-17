"""Posting engine — the full pipeline:

  product URL ──▶ scrape ──▶ affiliate link ──▶ download image
              ──▶ design pin graphic ──▶ SEO description
              ──▶ post to Pinterest (now or scheduled)

Plus the human-like scheduler loop used by `python -m bot run`.
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .affiliate import AffiliateLinker, price_label
from .db import DB
from .pinterest_api import PinterestAPI, PinterestError
from .pin_designer import PinDesigner
from .scraper import Scraper

log = logging.getLogger("pindrop.engine")


def build_seo_text(cfg, title: str, price: str, currency: str, source: str) -> str:
    """SEO-rich Pinterest description with hashtags."""
    label = price_label(price, currency) or "Best price"
    words = re.findall(r"[A-Za-z]{3,}", title.lower())[:6]
    tags = [f"#{w}" for w in dict.fromkeys(words)]
    extra = cfg.get("seo.extra_hashtags", []) or []
    if cfg.get("seo.hashtags", True):
        tags = (tags + list(extra))[: int(cfg.get("seo.max_hashtags", 8))]
    hashtags = " ".join(tags)
    template = cfg.get("seo.description_template")
    return template.format(title=title, price=label, hashtags=hashtags).strip()


class Engine:
    def __init__(self, cfg, db: DB | None = None):
        self.cfg = cfg
        self.db = db or DB(cfg.db_path)
        self.scraper = Scraper(cfg)
        self.linker = AffiliateLinker(cfg)
        self.designer = PinDesigner(cfg)
        self.api = PinterestAPI(cfg)
        self.tz = ZoneInfo(cfg.get("timezone", "Asia/Kolkata"))

    # ---------------------------------------------------------- ingestion
    def ingest_url(self, url: str, force: bool = False) -> int:
        """Scrape + enqueue one product. Returns product id; -1 if duplicate/bad."""
        url = url.strip()
        if not url:
            return -1
        if self.db.url_exists(url) and not force:
            self.db.log("WARN", f"Duplicate skipped: {url}")
            return -1

        prod = self.scraper.scrape(url)
        if not prod.ok:
            self.db.log("ERROR", f"Scrape failed (blocked or bad page): {url}")
            raise ValueError(
                f"Could not scrape product from {url}. The site may have blocked "
                "the request — try again later or add it via CSV."
            )

        aff_url, network = self.linker.convert(url, prod.source)
        img_path = self.scraper.download_image(prod, self.cfg.media_dir)
        if not img_path:
            raise ValueError("Product found but image download failed.")

        pin_path = self.cfg.media_dir / f"pin_{int(time.time()*1000)}.jpg"
        label = price_label(prod.price, prod.currency)
        self.designer.create(img_path, prod.title, label, pin_path, network)

        seo = build_seo_text(self.cfg, prod.title, prod.price, prod.currency, network)
        pid = self.db.add_product(
            source=prod.source,
            url=url,
            affiliate_url=aff_url,
            title=prod.title,
            price=prod.price,
            currency=prod.currency,
            image_url=prod.image_url,
            image_path=img_path,
            pin_image=str(pin_path),
            video_url=prod.video_url,
            category=prod.category,
            seo_text=seo,
        )
        self.db.log("INFO", f"Queued product #{pid}: {prod.title[:60]} [{network}]")
        return pid

    # ------------------------------------------------------------- posting
    def post_product(self, product: dict) -> dict:
        """Publish one queued product to Pinterest. Updates DB rows."""
        board_name = self.cfg.get("pinterest.board_name", "Best Deals")
        board_id = self.api.ensure_board(board_name)

        days_ahead = int(self.cfg.get("posting.schedule_days_ahead", 0))
        scheduled_for = None
        if days_ahead > 0:
            scheduled_for = datetime.now(self.tz) + timedelta(days=days_ahead)

        post_id = self.db.add_post(
            product_id=product["id"],
            board_id=board_id,
            status="pending",
            scheduled_for=scheduled_for.isoformat() if scheduled_for else "",
        )
        try:
            if product.get("video_url") or (
                product.get("image_path", "").endswith((".mp4", ".mov"))
            ):
                # video pin path
                media_id = self.api.upload_video(product["video_url"] or product["image_path"])
                pin = self.api.create_video_pin(
                    board_id, media_id, product["affiliate_url"],
                    product["title"], product["seo_text"], scheduled_for,
                )
            else:
                pin = self.api.create_image_pin(
                    board_id=board_id,
                    link=product["affiliate_url"],
                    title=product["title"],
                    description=product["seo_text"],
                    image_path=product.get("pin_image") or product.get("image_path"),
                    scheduled_for=scheduled_for,
                )
            self.db.update_post(
                post_id,
                pin_id=str(pin.get("id", "")),
                status="posted",
                posted_at=datetime.now(self.tz).isoformat(timespec="seconds"),
            )
            self.db.update_product(product["id"], status="posted")
            self.db.log("INFO", f"Posted pin {pin.get('id')} — {product['title'][:50]}")
            return pin
        except PinterestError as exc:
            self.db.update_post(post_id, status="failed", error=str(exc)[:500])
            self.db.update_product(product["id"], status="failed", error=str(exc)[:500])
            self.db.log("ERROR", f"Post failed for #{product['id']}: {exc}")
            raise

    def post_next(self) -> dict | None:
        """Post the single oldest queued product. Returns pin dict or None."""
        pending = self.db.pending_products(limit=1)
        if not pending:
            self.db.log("INFO", "Queue is empty — nothing to post.")
            return None
        return self.post_product(pending[0])

    def post_batch(self, count: int) -> list[dict]:
        """Post up to `count` queued products with human-like gaps."""
        posted: list[dict] = []
        for i in range(count):
            try:
                pin = self.post_next()
            except PinterestError:
                break
            if pin is None:
                break
            posted.append(pin)
            if i < count - 1:
                gap = self._human_gap()
                self.db.log("INFO", f"Waiting {gap:.0f}s before next pin (human-like)")
                time.sleep(gap)
        return posted

    # ----------------------------------------------------------- scheduler
    def _human_gap(self) -> float:
        mins = float(self.cfg.get("posting.min_gap_minutes", 40))
        jitter = float(self.cfg.get("posting.jitter_minutes", 25))
        return (mins + random.random() * jitter) * 60

    def run_forever(self) -> None:  # pragma: no cover - long loop
        """Daily scheduler: posts pins_per_day pins between start_hour..end_hour."""
        per_day = int(self.cfg.get("posting.pins_per_day", 8))
        start_h = int(self.cfg.get("posting.start_hour", 9))
        end_h = int(self.cfg.get("posting.end_hour", 22))
        self.db.log("INFO", f"Scheduler started: {per_day} pins/day, {start_h}:00-{end_h}:00 IST")
        print(f"\n🤖 Scheduler running — {per_day} pins/day between {start_h}:00 and {end_h}:00 IST. Ctrl+C to stop.\n")

        while True:
            now = datetime.now(self.tz)
            queue = self.db.pending_products(limit=100)
            if not queue:
                self.db.log("INFO", "Queue empty — sleeping 30 min. Add products via dashboard/CSV.")
                time.sleep(1800)
                continue

            if not (start_h <= now.hour < end_h):
                # sleep until window opens
                wake = now.replace(hour=start_h, minute=0, second=0, microsecond=0)
                if wake <= now:
                    wake += timedelta(days=1)
                sleep_s = (wake - now).total_seconds()
                self.db.log("INFO", f"Outside posting window — sleeping {sleep_s/3600:.1f}h")
                time.sleep(min(sleep_s, 3600))
                continue

            # spread today's pins across remaining window hours
            remaining_hours = max(1, end_h - now.hour - now.minute / 60)
            todo = min(per_day, len(queue))
            gap_s = min(self._human_gap(), remaining_hours * 3600 / max(todo, 1))
            try:
                self.post_next()
            except PinterestError:
                time.sleep(300)  # back off on API errors
                continue
            time.sleep(max(60, gap_s))
