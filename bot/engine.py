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
from pathlib import Path
from zoneinfo import ZoneInfo

from .affiliate import AffiliateLinker, price_label
from .db import DB
from .growth import hashtag_mix, hook_for, peak_window, seo_title
from .instagram import InstagramAPI, InstagramError
from .pinterest_api import PinterestAPI, PinterestError
from .pin_designer import PinDesigner, TEMPLATES
from .scraper import Scraper
from .video_maker import ReelMaker

log = logging.getLogger("pindrop.engine")


def build_seo_text(cfg, title: str, price: str, currency: str, source: str) -> str:
    """SEO-rich Pinterest description: hook + benefits + tiered hashtag mix."""
    label = price_label(price, currency) or "Best price"
    hashtags = hashtag_mix(title, source, int(cfg.get("seo.max_hashtags", 8)))
    template = cfg.get("seo.description_template")
    text = template.format(title=title, price=label, hashtags=hashtags).strip()
    # FTC / Pinterest policy: always disclose affiliate links
    if "#ad" not in text:
        text += "\n#ad #affiliate"
    return text


def build_ig_caption(cfg, title: str, price: str, currency: str, source: str = "amazon") -> str:
    """Instagram caption — no clickable links on IG, drive comments + bio."""
    label = price_label(price, currency) or "Best price"
    return cfg.get("instagram.caption_template").format(
        title=title, price=label, hashtags=hashtag_mix(title, source)
    ).strip()


class Engine:
    def __init__(self, cfg, db: DB | None = None):
        self.cfg = cfg
        self.db = db or DB(cfg.db_path)
        self.scraper = Scraper(cfg)
        self.linker = AffiliateLinker(cfg)
        self.designer = PinDesigner(cfg)
        self.reel = ReelMaker(cfg)
        self.api = PinterestAPI(cfg)
        self.ig = InstagramAPI(cfg)
        self.tz = ZoneInfo(cfg.get("timezone", "Asia/Kolkata"))

    # ---------------------------------------------------------- ingestion
    def ingest_url(self, url: str, force: bool = False) -> int:
        """Scrape + enqueue one product as MULTIPLE pin variations.

        Downloads the whole photo gallery (+ video when available), designs a
        different pin template per photo and queues each as its own pin — all
        carrying the same affiliate link. Returns first product id.
        """
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
                "the request — try again later or add it via CSV / manual add."
            )

        aff_url, network = self.linker.convert(url, prod.source)
        label = price_label(prod.price, prod.currency)

        # download full gallery (up to max_images photos)
        max_imgs = max(1, int(self.cfg.get("scraping.max_images", 3)))
        local_imgs: list[str] = []
        for img_url in (prod.images or [prod.image_url])[:max_imgs]:
            p = self.scraper.download_image_url(img_url, self.cfg.media_dir, prod.title)
            if p and p not in local_imgs:
                local_imgs.append(p)
        if not local_imgs:
            raise ValueError("Product found but image download failed.")

        # video: prefer the page's real product video…
        video_path = ""
        if prod.video_url:
            video_path = self.scraper.download_video(prod.video_url, self.cfg.media_dir)
            if video_path:
                self.db.log("INFO", f"Video downloaded for: {prod.title[:50]}")
        # …otherwise AUTO-GENERATE a viral reel from the photos (the 2026 trick)
        if not video_path and self.cfg.get("video.auto_reel", True):
            try:
                hook = hook_for(label, prod.title, datetime.now(self.tz).day)
                reel_path = self.cfg.media_dir / f"reel_{int(time.time()*1000)}.mp4"
                video_path = self.reel.make(local_imgs[0], hook, prod.title, label,
                                            reel_path, network)
                self.db.log("INFO", f"Auto-reel generated: {reel_path.name}")
            except Exception as exc:  # noqa: BLE001 — reel is a bonus, never fatal
                self.db.log("WARN", f"Reel generation failed: {exc}")

        # how many pin variations?
        per_product = max(1, int(self.cfg.get("posting.pins_per_product", 2)))
        n_variants = min(per_product, len(local_imgs)) or 1

        seo = build_seo_text(self.cfg, prod.title, prod.price, prod.currency, network)
        templates = list(TEMPLATES)
        random.shuffle(templates)
        first_id = -1
        for v in range(n_variants):
            pin_path = self.cfg.media_dir / f"pin_{int(time.time()*1000)}_v{v}.jpg"
            self.designer.create(
                local_imgs[v], prod.title, label, pin_path, network,
                template=templates[v % len(templates)],
                extra_images=[p for p in local_imgs if p != local_imgs[v]],
            )
            pid = self.db.add_product(
                source=prod.source,
                url=url,
                affiliate_url=aff_url,
                title=prod.title,
                price=prod.price,
                currency=prod.currency,
                image_url=prod.image_url,
                image_path=local_imgs[v],
                pin_image=str(pin_path),
                video_url=prod.video_url,
                video_path=video_path if v == 0 else "",  # one video pin per product
                variant=v,
                category=prod.category,
                seo_text=seo,
            )
            if first_id < 0:
                first_id = pid
        self.db.log(
            "INFO",
            f"Queued #{first_id}: {prod.title[:50]} [{network}] — "
            f"{n_variants} pin variation(s){'+ 1 video pin' if video_path else ''}",
        )
        return first_id

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
            # keyword-stuffed SEO title (Pinterest = search engine)
            seo_t = seo_title(product["title"],
                              price_label(product["price"], product["currency"]),
                              product["source"])
            video_file = product.get("video_path", "") or ""
            if video_file and Path(video_file).exists():
                # video pin path — real / auto-generated reel uploaded to Pinterest
                media_id = self.api.upload_video(video_file)
                pin = self.api.create_video_pin(
                    board_id, media_id, product["affiliate_url"],
                    seo_t, product["seo_text"], scheduled_for,
                )
            else:
                pin = self.api.create_image_pin(
                    board_id=board_id,
                    link=product["affiliate_url"],
                    title=seo_t,
                    description=product["seo_text"],
                    alt_text=product["title"][:500],
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
            self._post_instagram(product, post_id)
            return pin
        except PinterestError as exc:
            self.db.update_post(post_id, status="failed", error=str(exc)[:500])
            self.db.update_product(product["id"], status="failed", error=str(exc)[:500])
            self.db.log("ERROR", f"Post failed for #{product['id']}: {exc}")
            raise

    # ---------------------------------------------------------- instagram
    def _post_instagram(self, product: dict, post_id: int) -> None:
        """Cross-post the same product to Instagram (optional, best-effort)."""
        if not (self.ig.enabled and self.ig.configured):
            return
        caption = build_ig_caption(self.cfg, product["title"], product["price"],
                                   product["currency"])
        mode = self.cfg.get("instagram.mode", "carousel")
        try:
            urls: list[str] = []
            # 1) designed pin hosted publicly (ImgBB) when configured
            if self.cfg.get("instagram.host_designed_pins") and self.ig.imgbb_key:
                hosted = self.ig.upload_imgbb(product["pin_image"])
                if hosted:
                    urls.append(hosted)
            # 2) original product photo(s) from shop CDN
            if product.get("image_url") and product["image_url"] not in urls:
                urls.append(product["image_url"])

            media_id = ""
            if mode == "reel" and str(product.get("video_url", "")).startswith("http"):
                media_id = self.ig.post_reel(product["video_url"], caption)
            elif len(urls) > 1 and mode == "carousel":
                media_id = self.ig.post_carousel(urls, caption)
            elif urls:
                media_id = self.ig.post_single(urls[0], caption)
            else:
                self.db.log("WARN", "Instagram: no public media available, skipped")
                return
            self.db.update_post(post_id, ig_post_id=media_id)
            self.db.log("INFO", f"Instagram post {media_id} — {product['title'][:40]}")
        except InstagramError as exc:
            self.db.update_post(post_id, ig_error=str(exc)[:400])
            self.db.log("WARN", f"Instagram cross-post failed: {exc}")

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
        """24×7 scheduler: posts inside PEAK traffic windows (or configured hours)."""
        per_day = int(self.cfg.get("posting.pins_per_day", 8))
        peak = bool(self.cfg.get("posting.peak_mode", True))
        start_h = int(self.cfg.get("posting.start_hour", 9))
        end_h = int(self.cfg.get("posting.end_hour", 22))
        self.db.log("INFO", f"Scheduler started: {per_day} pins/day, "
                            f"{'PEAK windows' if peak else f'{start_h}:00-{end_h}:00'} IST")
        print(f"\n🤖 Scheduler running 24×7 — {per_day} pins/day in "
              f"{'peak traffic windows' if peak else f'{start_h}:00-{end_h}:00'} IST. Ctrl+C to stop.\n")

        while True:
            now = datetime.now(self.tz)
            w_start, w_end = peak_window(now) if peak else (start_h, end_h)
            queue = self.db.pending_products(limit=100)
            if not queue:
                self.db.log("INFO", "Queue empty — sleeping 30 min. Add products via dashboard/CSV.")
                time.sleep(1800)
                continue

            if not (w_start <= now.hour < w_end):
                self.db.log("INFO", f"Outside peak window ({w_start}:00-{w_end}:00) — napping 20 min")
                time.sleep(1200)
                continue

            # spread today's pins across remaining window hours
            remaining_hours = max(1, w_end - now.hour - now.minute / 60)
            todo = min(per_day, len(queue))
            gap_s = min(self._human_gap(), remaining_hours * 3600 / max(todo, 1))
            try:
                self.post_next()
            except PinterestError:
                time.sleep(300)  # back off on API errors
                continue
            time.sleep(max(60, gap_s))
