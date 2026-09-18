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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .affiliate import AffiliateLinker, price_label
from .db import DB
from .growth import (festival_boost, hashtag_mix, hook_for, peak_window,
                     pick_board, seo_title)
from .facebook import FacebookAPI, FacebookError
from .instagram import InstagramAPI, InstagramError
from .keywords import KeywordCache
from .notify import Notifier
from .pinterest_api import PinterestAPI, PinterestError
from .pin_designer import PinDesigner, TEMPLATES
from .scraper import Scraper
from .trends import score_product, sourcing_plan
from .video_maker import ReelMaker, pick_music

log = logging.getLogger("pindrop.engine")


def build_seo_text(cfg, title: str, price: str, currency: str, source: str,
                   discount: int = 0, festival_kw: str = "") -> str:
    """SEO-rich Pinterest description: hook + urgency + tiered hashtag mix."""
    label = price_label(price, currency) or "Best price"
    hashtags = hashtag_mix(title + (" " + festival_kw if festival_kw else ""),
                           source, int(cfg.get("seo.max_hashtags", 8)))
    template = cfg.get("seo.description_template")
    text = template.format(title=title, price=label, hashtags=hashtags).strip()
    urgency = []
    if discount >= 15:
        urgency.append(f"⚡ FLAT {discount}% OFF — today only!")
    if festival_kw:
        urgency.append(f"🎉 {festival_kw.title()} special")
    urgency.append("⏳ Limited stock at this price — grab it now!")
    text = "\n".join([text] + urgency)
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
        self.fb = FacebookAPI(cfg)
        self.kw = KeywordCache(self.db)
        self.notify = Notifier()
        self.tz = ZoneInfo(cfg.get("timezone", "Asia/Kolkata"))
        self._last_reshare = 0.0  # daily winners-rotation timer
        self._report_day = ""     # daily report guard
        self._roundup_day = ""    # daily list-pin guard

    # ------------------------------------------------------------- links
    def pick_template(self) -> str:
        """CTR-learning loop: 70% exploit the best-clicked template, 30% explore."""
        counts = self.db.template_clicks()
        total = sum(counts.values())
        if total >= 5 and counts:
            best = max(counts, key=counts.get)
            if random.random() < 0.7:
                return best
        return random.choice(TEMPLATES)

    def _pin_link(self, product: dict) -> str:
        """Bridge link (your domain, tracked) or raw affiliate link."""
        base = str(self.cfg.get("link.public_base", "") or "").strip().rstrip("/")
        if self.cfg.get("link.bridge", False) and base:
            return f"{base}/go/{product['id']}"
        return product["affiliate_url"]

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
        # you never make media: bot enriches thin galleries from the SAME
        # product on other stores (official, watermark-free)
        try:
            prod = self.scraper.enrich_media(prod)
        except Exception as exc:  # noqa: BLE001 — enrichment is a bonus
            self.db.log("WARN", f"Media enrichment skipped: {exc}")

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
        # user's OWN videos always win (uploaded via dashboard → data/videos/)
        if not video_path:
            from .video_maker import pick_video
            uv = pick_video(self.cfg)
            if uv:
                video_path = uv
                self.db.log("INFO", f"🎬 Using YOUR uploaded video: {Path(uv).name}")
        # …otherwise AUTO-GENERATE a viral reel from the photos (the 2026 trick)
        if not video_path and self.cfg.get("video.auto_reel", True):
            try:
                from . import voiceover as vo
                hook = hook_for(label, prod.title, datetime.now(self.tz).day)
                lang = str(self.cfg.get("video.lang", "en-IN"))
                script = vo.script_for(lang, prod.title, label)
                vo_path = vo.generate(script, lang,
                                      self.cfg.media_dir / f"vo_{int(time.time()*1000)}.mp3")
                vo_secs = vo.estimate_seconds(script) if vo_path else 0.0
                music = pick_music(self.cfg)   # user's manually-added trending audio
                reel_path = self.cfg.media_dir / f"reel_{int(time.time()*1000)}.mp4"
                video_path = self.reel.make(local_imgs[0], hook, prod.title, label,
                                            reel_path, network,
                                            voiceover=vo_path or None,
                                            music=music or None, vo_seconds=vo_secs)
                self.db.log("INFO", f"Auto-reel {'with voiceover' if vo_path else ''} "
                                    f"generated: {reel_path.name}")
            except Exception as exc:  # noqa: BLE001 — reel is a bonus, never fatal
                self.db.log("WARN", f"Reel generation failed: {exc}")

        # how many pin variations?
        per_product = max(1, int(self.cfg.get("posting.pins_per_product", 2)))
        n_variants = min(per_product, len(local_imgs)) or 1

        disc = prod.discount_pct
        _, fest_kw, _ = festival_boost(datetime.now(self.tz))
        seo = build_seo_text(self.cfg, prod.title, prod.price, prod.currency,
                             network, discount=disc, festival_kw=fest_kw)
        first_id = -1
        for v in range(n_variants):
            tpl = self.pick_template()
            pin_path = self.cfg.media_dir / f"pin_{int(time.time()*1000)}_v{v}.jpg"
            self.designer.create(
                local_imgs[v], prod.title, label, pin_path, network,
                template=tpl,
                extra_images=[p for p in local_imgs if p != local_imgs[v]],
                discount=disc,
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
                score=score_product(prod.title, prod.price, prod.source),
                discount=disc,
                template=tpl,
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
        default_board = self.cfg.get("pinterest.board_name", "Best Deals")
        if self.cfg.get("posting.board_strategy", "niche") == "niche":
            board_name = pick_board(product["title"], product["source"], default_board)
        else:
            board_name = default_board
        board_id = self.api.ensure_board(board_name,
            f"{board_name} — best offers, price drops & top-rated finds. "
            "Daily deals India: online shopping discounts & combo offers.")
        link = self._pin_link(product)

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
            # keyword-stuffed SEO title (Pinterest = search engine) + LIVE
            # autocomplete phrase mined from Pinterest typeahead
            phrase = self.kw.phrase_for(product["title"])
            seo_t = seo_title(product["title"],
                              price_label(product["price"], product["currency"]),
                              product["source"], phrase=phrase)
            video_file = product.get("video_path", "") or ""
            # 🔬 PIN-BY-PIN QA GATE — broken pins never reach the API
            from . import qa as _qa
            qa_img = product.get("pin_image") or product.get("image_path") or ""
            if not video_file or not Path(video_file).exists():
                qa_ok, qa_issues = _qa.qa_pin(self.cfg, self.db, product, seo_t,
                                              product["seo_text"], qa_img, link)
                if not qa_ok:
                    reason = "QA failed: " + "; ".join(qa_issues)[:400]
                    self.db.update_post(post_id, status="failed", error=reason)
                    self.db.update_product(product["id"], status="skipped", error=reason)
                    self.db.log("WARN", f"🔬 Pin #{product['id']} quarantined — {reason}")
                    return None
            if video_file and Path(video_file).exists():
                # video pin path — real / auto-generated reel uploaded to Pinterest
                media_id = self.api.upload_video(video_file)
                pin = self.api.create_video_pin(
                    board_id, media_id, link,
                    seo_t, product["seo_text"], scheduled_for,
                )
            else:
                pin = self.api.create_image_pin(
                    board_id=board_id,
                    link=link,
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
            self.notify.posted(product["title"], str(pin.get("id")), product["source"])
            # broadcast to public Telegram deals channel (top-India trick)
            self.notify.deal(product["title"],
                             price_label(product["price"], product["currency"]),
                             link, product.get("image_url", ""))
            self._post_instagram(product, post_id)
            self._post_facebook(product)
            return pin
        except PinterestError as exc:
            attempts = int(product.get("attempts", 0) or 0) + 1
            # transient errors retry next cycle; 3 strikes = skip forever
            status = "queued" if attempts < 3 else "skipped"
            self.db.update_post(post_id, status="failed", error=str(exc)[:500])
            self.db.update_product(product["id"], status=status,
                                   error=str(exc)[:500], attempts=attempts)
            self.db.log("ERROR", f"Post failed for #{product['id']} "
                                 f"(attempt {attempts}): {exc}")
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
            elif mode == "reel" and str(product.get("video_path", "")):
                # local reel (downloaded/auto-generated) → host it publicly first
                hosted_vid = self.ig.upload_catbox(product["video_path"])
                if hosted_vid:
                    media_id = self.ig.post_reel(hosted_vid, caption)
                else:
                    self.db.log("WARN", "Instagram: reel hosting failed, skipped")
                    return
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

    def _ig_reply_for(self, media_id: str, trigger: str = "link") -> str:
        """ManyChat-style, per-PRODUCT comment reply: the trigger keyword
        picks the template, {title}/{price} fill from the product behind
        that media. Never a generic answer."""
        p = self.db.product_by_ig_media(media_id)
        if not p:
            return ""
        label = price_label(p["price"], p["currency"]) or "best price"
        tpl = (self.cfg.get("instagram.triggers") or {}).get(trigger, "")
        if not tpl:
            tpl = "🔥 {title} — only {price}! Link in bio!"
        return tpl.format(title=p["title"][:60], price=label)

    def _post_facebook(self, product: dict) -> None:
        """Cross-post to your Facebook Page (official Graph API, best-effort)."""
        if not (self.fb.enabled and self.fb.configured):
            return
        try:
            caption = build_ig_caption(self.cfg, product["title"], product["price"],
                                       product["currency"])
            mode = str(self.cfg.get("facebook.mode", "photo"))
            if mode == "link":
                base = str(self.cfg.get("link.public_base", "") or "").rstrip("/")
                url = f"{base}/go/{product['id']}" if base else product["affiliate_url"]
                fid = self.fb.post_link(url, caption)
            else:
                fid = self.fb.post_photo(product.get("image_url", ""), caption)
            self.db.log("INFO", f"Facebook post {fid} — {product['title'][:40]}")
        except FacebookError as exc:
            self.db.log("WARN", f"Facebook cross-post failed: {exc}")

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

    # ----------------------------------------------------------- autopilot
    def auto_source(self) -> int:
        """ZERO-TOUCH winner-clone sourcing: hunts products in the exact
        niches top channels push, priority order (fashion → decor → beauty…)."""
        added = 0
        limit = int(self.cfg.get("autopilot.discover_limit", 4))
        for store, query, niche in sourcing_plan():
            try:
                urls = self.scraper.discover_products(store, limit=limit, query=query)
            except Exception as exc:  # noqa: BLE001
                self.db.log("WARN", f"Discover {store} '{query}' failed: {exc}")
                urls = []
            for u in urls:
                if self.db.url_exists(u):
                    continue
                try:
                    pid = self.ingest_url(u)
                    added += pid > 0
                except ValueError:
                    continue
                self.scraper.polite_wait()
            if added:  # don't over-hunt in one cycle
                break
        if added:
            self.db.log("INFO", f"🏆 Winner-clone sourced {added} new product(s) "
                                "from top niches")
        return added

    # ----------------------------------------------------------- reshare
    def reshare_winners(self) -> int:
        """Top-0.1% rotation: re-post proven winners as FRESH pins.

        Pinterest's algorithm boosts new pins; products that already earned
        clicks get a new design + new keywords and go around again.
        """
        cands = self.db.reshare_candidates(
            min_clicks=int(self.cfg.get("reshare.min_clicks", 3)),
            rest_days=int(self.cfg.get("reshare.rest_days", 7)),
            max_shares=int(self.cfg.get("reshare.max_shares", 3)))
        n = 0
        for prod in cands[:2]:  # gentle: max 2 re-shares per cycle
            try:
                self.post_product(prod)
                n += 1
                self.db.log("INFO", f"🔁 Re-shared winner #{prod['id']} "
                                    f"({prod.get('clicks')} clicks) with fresh design")
            except Exception as exc:  # noqa: BLE001
                self.db.log("WARN", f"Reshare failed: {exc}")
        return n

    # ----------------------------------------------------------- roundups
    def post_roundup(self, segment: str | None = None) -> dict | None:
        """'Deals of the Day' list pin — the viral-save format top channels use.

        One pin lists your best N products (segment-aware: Ladies Special,
        Home & Kitchen, Kids, Gadgets); the pin links to a deals page where
        every item carries its affiliate link. Posted once a day.
        """
        from . import roundup as ru
        if not self.cfg.get("roundup.enabled", True):
            return None
        prods = self.db.all_products(limit=300)
        for p in prods:
            p["score"] = score_product(p["title"], p["price"], p["source"])
        seg = segment or random.choice(list(ru.SEGMENTS))
        items = ru.pick_roundup(prods, seg, int(self.cfg.get("roundup.count", 5)))
        if len(items) < 3:
            self.db.log("INFO", "Roundup skipped — not enough products yet")
            return None
        now = datetime.now(self.tz)
        title = ru.roundup_title(seg, len(items), now)
        out = self.cfg.media_dir / f"roundup_{int(time.time()*1000)}.jpg"
        self.designer.design_roundup(items, title, out)
        base = str(self.cfg.get("link.public_base", "") or "").rstrip("/")
        link = (f"{base}/deals/today"
                if (self.cfg.get("link.bridge", False) and base)
                else items[0]["affiliate_url"])
        seo = build_seo_text(self.cfg, title, "", "", "amazon", discount=0,
                             festival_kw=ru.trending_tag(now))
        board_name = "Deals of the Day"
        board_id = self.api.ensure_board(board_name,
            f"{board_name} — daily hand-picked list of best deals & offers "
            "India: fashion, home, kitchen, gadgets at lowest prices.")
        pin = self.api.create_image_pin(board_id, link, title, seo,
                                        alt_text=title, image_path=str(out))
        self.db.log("INFO", f"📋 Roundup pin posted ({ru.SEGMENTS[seg]['label']}): "
                            f"{title[:60]}")
        return pin

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
            # top-0.1% freshness trick: rotate proven winners as new pins daily
            if time.time() - self._last_reshare > 24 * 3600:
                self._last_reshare = time.time()
                try:
                    self.reshare_winners()
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"Reshare cycle error: {exc}")
            # daily "Deals of the Day" list pin (viral-save format)
            if 10 <= now.hour <= 20 and self._roundup_day != now.date().isoformat():
                self._roundup_day = now.date().isoformat()
                try:
                    if self.api.configured:
                        self.post_roundup()
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"Roundup failed: {exc}")

            # daily auto-report at 9 PM IST ("roju post chestunnava" — proof!)
            today = now.date().isoformat()
            if now.hour >= 21 and self._report_day != today:
                self._report_day = today
                try:
                    stats = self.db.stats()
                    clicks = sum(self.db.click_counts().values())
                    self.notify.daily_summary(stats, clicks)
                    self.db.log("INFO", f"📊 Daily report sent: {stats.get('posted', 0)} "
                                        f"posted, {clicks} clicks")
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"Daily report failed: {exc}")
            w_start, w_end = peak_window(now) if peak else (start_h, end_h)
            # festival / payday volume boost (India shopping spikes)
            fest_name, _, mult = festival_boost(now)
            eff_per_day = per_day * mult

            # 🛡️ ANTI-BAN WARM-UP: brand-new accounts blasting 8 pins/day
            # get flagged. Ramp: ~30% on day 1, +10%/day, full by week 1.
            started = self.db.oldest_activity()
            age_days = (now - started).days if started else 0
            ramp = min(1.0, 0.3 + 0.1 * age_days)
            if ramp < 1.0:
                self.db.log("INFO", f"🛡️ Warm-up day {age_days}: volume at "
                                    f"{int(ramp*100)}% (anti-flag ramp)")
            eff_per_day = eff_per_day * ramp
            # human-like daily variance (±15%) — no robotic identical volume
            eff_per_day = max(1, int(eff_per_day * random.uniform(0.85, 1.15)))
            queue = self.db.pending_products(limit=100)

            # ZERO-TOUCH: queue running dry? go hunt trending products itself
            min_q = int(self.cfg.get("autopilot.min_queue", 5))
            if len(queue) < min_q and self.cfg.get("autopilot.auto_source", True):
                self.db.log("INFO", f"Queue low ({len(queue)}) — autopilot hunting "
                                    "trending products on Amazon/Meesho/Flipkart…")
                self.auto_source()
                queue = self.db.pending_products(limit=100)

            if not queue:
                self.db.log("INFO", "Queue empty & sourcing blocked right now — "
                                    "retrying in 30 min (normal on some networks).")
                time.sleep(1800)
                continue

            if not (w_start <= now.hour < w_end):
                self.db.log("INFO", f"Outside peak window ({w_start}:00-{w_end}:00) — napping 20 min")
                time.sleep(1200)
                continue

            # spread today's pins across remaining window hours
            remaining_hours = max(1, w_end - now.hour - now.minute / 60)
            todo = min(eff_per_day, len(queue))
            if fest_name and mult > 1:
                self.db.log("INFO", f"🎉 {fest_name} boost: {eff_per_day} pins today")
            gap_s = min(self._human_gap(), remaining_hours * 3600 / max(todo, 1))
            # hour-wise CTR learning: denser posting in YOUR proven hours
            hours = self.db.click_hours()
            if sum(hours.values()) >= 10:
                utc_h = now.astimezone(timezone.utc).hour
                avg = sum(hours.values()) / max(1, len(hours))
                gap_s *= 0.6 if hours.get(utc_h, 0) > avg else 1.3
            try:
                self.post_next()
                if self.ig.enabled and self.ig.configured:
                    self.ig.auto_reply_links(
                        reply_for=self._ig_reply_for)  # per-product answers
            except PinterestError:
                time.sleep(300)  # back off on API errors
                continue
            except InstagramError:
                pass
            time.sleep(max(60, gap_s))
