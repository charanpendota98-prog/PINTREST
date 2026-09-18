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


# Built-in fallbacks: a missing/broken template in config.yaml must NEVER
# stop a pin from going out (the pin is the money).
DEFAULT_SEO_TEMPLATE = ("{title} | {price} | best deal today\n"
                        "{hashtags}")
DEFAULT_IG_CAPTION = ("\U0001F525 {title}\n\U0001F4B0 Price: {price}\n"
                      "\U0001F6D2 Comment 'LINK' — link in bio!\n{hashtags}")


def build_seo_text(cfg, title: str, price: str, currency: str, source: str,
                   discount: int = 0, festival_kw: str = "") -> str:
    """SEO-rich Pinterest description: hook + urgency + tiered hashtag mix."""
    label = price_label(price, currency) or "Best price"
    hashtags = hashtag_mix(title + (" " + festival_kw if festival_kw else ""),
                           source, cfg.get_int("seo.max_hashtags", 8))
    template = (cfg.get("seo.description_template")
                or DEFAULT_SEO_TEMPLATE)
    try:
        text = template.format(title=title, price=label,
                               hashtags=hashtags).strip()
    except (KeyError, IndexError, ValueError):
        # a broken custom template must never stop a pin from going out
        text = DEFAULT_SEO_TEMPLATE.format(
            title=title, price=label, hashtags=hashtags).strip()
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
    tags = hashtag_mix(title, source)
    tpl = (cfg.get("instagram.caption_template") or DEFAULT_IG_CAPTION)
    try:
        return tpl.format(title=title, price=label, hashtags=tags).strip()
    except (KeyError, IndexError, ValueError):
        return DEFAULT_IG_CAPTION.format(
            title=title, price=label, hashtags=tags).strip()


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
        # Rescue anything a crashed worker left in 'posting' (older than 20
        # min only — a post genuinely in flight right now is never stolen).
        try:
            rescued = self.db.release_stale_claims()
            if rescued:
                self.db.log("WARN", f"♻️  Recovered {rescued} product(s) stuck "
                                    "in 'posting' — back in the queue")
        except Exception as exc:  # noqa: BLE001 — startup must never crash
            log.warning("stale-claim recovery skipped: %s", exc)
        self._last_reshare = 0.0  # daily winners-rotation timer
        self._report_day = ""     # daily report guard
        self._roundup_day = ""    # daily list-pin guard

    # ------------------------------------------------------------- links
    def pin_filename(self, title: str, price_label: str,
                     variant: int = 0) -> str:
        """Pinterest image SEO: Pinterest indexes the IMAGE FILENAME.

        `women-floral-anarkali-kurta-549-<ts>_v0.jpg` ranks for far more
        searches than `pin_1726634.jpg`. Keyword + price + variant, always
        unique, always filesystem-safe.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", (title or "deal").lower()).strip("-")
        slug = (slug or "deal")[:40].strip("-")
        price_slug = re.sub(r"[^0-9]", "", price_label or "") or "0"
        return (f"{slug}-{price_slug}-{int(time.time() * 1000)}"
                f"_v{variant}.jpg")

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
        """Bridge link (your domain, tracked) or the PIN Pinterest link.

        Uses the pinterest-tuned Meesho link (or your platform override) so
        the Meesho report labels Pinterest clicks correctly — money is the
        same publisher either way, the label is what changes.
        """
        base = str(self.cfg.get("link.public_base", "") or "").strip().rstrip("/")
        if self.cfg.get("link.bridge", False) and base:
            return f"{base}/go/{product['id']}"
        return self._aff_link(product, "pinterest")

    def _aff_link(self, product: dict, platform: str = "") -> str:
        """Affiliate link tuned for the platform being posted to.

        Meesho gives each platform its OWN source token + campaign id
        (instagram_stories / facebook / ...). Posting a Pinterest pin with a
        'facebook' token muddies the Meesho report — so rebuild the link per
        platform for Meesho products. Every other store keeps its stored
        link (Amazon tag etc. is platform-agnostic).
        """
        stored = product.get("affiliate_url", "")
        if (product.get("source") or "") != "meesho" or not platform:
            return stored
        if self.cfg.get("affiliate.meesho_per_platform", True) is False:
            return stored
        try:
            base_url = product.get("url") or ""
            if not base_url or AffiliateLinker.MEESHO_MONETIZED.search(base_url):
                return stored
            fresh = AffiliateLinker(self.cfg).meesho_link_for(
                base_url, platform=platform)
            return fresh or stored
        except Exception as exc:  # noqa: BLE001 — never break a post over this
            self.db.log("WARN", f"per-platform Meesho link skipped: {exc}")
            return stored

    def _gallery_urls(self, product: dict) -> list[str]:
        """Public image URLs for this product (for carousel pins)."""
        urls: list[str] = []
        raw = product.get("images") or ""
        if raw:
            try:
                import json as _json
                urls += [u for u in _json.loads(raw) if isinstance(u, str)]
            except (ValueError, TypeError):
                urls += [u.strip() for u in str(raw).split(",") if u.strip()]
        single = product.get("image_url") or ""
        if single and single not in urls:
            urls.insert(0, single)
        out, seen = [], set()
        for u in urls:
            if u.startswith("http") and u not in seen:
                seen.add(u)
                out.append(u)
        return out[:5]

    def _section_for(self, board_id: str, product: dict) -> str:
        """Board section per niche (keeps a big board tidy + more relevant)."""
        if not self.cfg.get("pinterest.sections", False):
            return ""
        try:
            name = pick_board(product.get("title", ""), product.get("source", ""),
                              str(self.cfg.get("pinterest.board_name", "Best Deals")))
            return self.api.ensure_section(board_id, name)
        except Exception as exc:  # noqa: BLE001 — sections are a bonus
            self.db.log("WARN", f"board section skipped: {exc}")
            return ""

    # ---------------------------------------------------------- ingestion
    def ingest_url(self, url: str, force: bool = False, prefetched=None) -> int:
        """Scrape + enqueue one product as MULTIPLE pin variations.

        Downloads the whole photo gallery (+ video when available), designs a
        different pin template per photo and queues each as its own pin — all
        carrying the same affiliate link. Returns first product id.

        `prefetched` (optional Product) skips the scrape — the radar already
        fetched it while ranking candidates, and re-scraping would waste a
        request (and risk a rate-limit block).
        """
        url = url.strip()
        if not url:
            return -1
        if self.db.url_exists(url) and not force:
            self.db.log("WARN", f"Duplicate skipped: {url}")
            return -1

        prod = prefetched if prefetched is not None else self.scraper.scrape(url)
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
        max_imgs = max(1, self.cfg.get_int("scraping.max_images", 3))
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
        per_product = max(1, self.cfg.get_int("posting.pins_per_product", 2))
        n_variants = min(per_product, len(local_imgs)) or 1

        disc = prod.discount_pct
        _, fest_kw, _ = festival_boost(datetime.now(self.tz))
        # 📈 live Pinterest Trends keywords (official API, cached 24h)
        trend_kw = ""
        try:
            from .trends import cached_keywords
            kws = cached_keywords(self.cfg, limit=6)
            trend_kw = " ".join(kws[:3])
        except Exception:  # noqa: BLE001
            trend_kw = ""
        seo = build_seo_text(self.cfg, prod.title, prod.price, prod.currency,
                             network, discount=disc,
                             festival_kw=" ".join(x for x in (fest_kw, trend_kw) if x))
        first_id = -1
        for v in range(n_variants):
            tpl = self.pick_template()
            pin_path = self.cfg.media_dir / self.pin_filename(
                prod.title, label, variant=v)
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
                images=",".join((prod.images or [])[:5]),
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
        """Publish one queued product to Pinterest. Updates DB rows.

        FIRST thing it does is claim the row atomically: the scheduler and a
        dashboard "Post now" click can fire at the same instant, and posting
        the same product twice is a duplicate-pin spam signal. The loser of
        the claim exits without touching the API.
        """
        pid = int(product["id"])
        if str(product.get("status", "queued")) == "queued" \
                and not self.db.claim_product(pid):
            self.db.log("INFO", f"#{pid} already being posted by another worker "
                                "— skipping (no duplicate pin)")
            return None
        default_board = self.cfg.get("pinterest.board_name", "Best Deals")
        if self.cfg.get("posting.board_strategy", "niche") == "niche":
            board_name = pick_board(product["title"], product["source"], default_board)
        else:
            board_name = default_board
        link = self._pin_link(product)
        # 🧠 self-learning hook: pick the archetype that earns clicks, record
        # it on the row so clicks can be attributed back to it later
        if not product.get("hook"):
            product["hook"] = self._pick_hook()
            try:
                self.db.update_product(product["id"], hook=product["hook"])
            except Exception:  # noqa: BLE001
                pass

        days_ahead = self.cfg.get_int("posting.schedule_days_ahead", 0)
        scheduled_for = None
        if days_ahead > 0:
            scheduled_for = datetime.now(self.tz) + timedelta(days=days_ahead)

        # keyword-stuffed SEO title (Pinterest = search engine) + LIVE
        # autocomplete phrase mined from Pinterest typeahead
        phrase = self.kw.phrase_for(product["title"])
        seo_t = seo_title(product["title"],
                          price_label(product["price"], product["currency"]),
                          product["source"], phrase=phrase)
        video_file = product.get("video_path", "") or ""
        # 🔬 PIN-BY-PIN QA GATE runs BEFORE any API call: junk/untracked
        # products must never even create a board or a post row.
        from . import qa as _qa
        qa_img = product.get("pin_image") or product.get("image_path") or ""
        if not video_file or not Path(video_file).exists():
            qa_ok, qa_issues = _qa.qa_pin(self.cfg, self.db, product, seo_t,
                                          product["seo_text"], qa_img, link)
            if not qa_ok:
                reason = "QA failed: " + "; ".join(qa_issues)[:400]
                self.db.update_product(product["id"], status="skipped",
                                       claim_ts="", error=reason)
                self.db.log("WARN", f"🔬 Pin #{product['id']} quarantined — {reason}")
                return None

        # From here on the row is CLAIMED: every single exit path must either
        # post it or hand it back to the queue — a claim must never leak.
        post_id = None
        try:
            # board (auto-created, SEO description)
            board_id = self.api.ensure_board(board_name,
                f"{board_name} — best offers, price drops & top-rated finds. "
                "Daily deals India: online shopping discounts & combo offers.")
            post_id = self.db.add_post(
                product_id=product["id"],
                board_id=board_id,
                status="pending",
                scheduled_for=scheduled_for.isoformat() if scheduled_for else "",
            )
            # PLATFORM ORDER (owner strategy): IG + Facebook FIRST,
            # Pinterest after — "anni chesaka chuddam"
            order = [p for p in self.cfg.get("posting.platform_order",
                                             ["instagram", "facebook", "pinterest"])]
            done: set[str] = set()
            for plat in order:
                if plat == "pinterest":
                    break
                if plat == "instagram":
                    self._post_instagram(product, post_id)
                elif plat == "facebook":
                    self._post_facebook(product)
                elif plat == "youtube":
                    self._post_youtube(product)
                done.add(plat)
            section_id = self._section_for(board_id, product)
            if video_file and Path(video_file).exists():
                # video pin path — real / auto-generated reel uploaded to Pinterest
                media_id = self.api.upload_video(video_file)
                pin = self.api.create_video_pin(
                    board_id, media_id, link,
                    seo_t, product["seo_text"],
                    alt_text=product["title"][:500],
                    scheduled_for=scheduled_for,
                    board_section_id=section_id,
                )
            else:
                pin = None
                # CAROUSEL first (highest engagement format) when the product
                # has 2+ public photos; silently falls back to a single pin
                if self.cfg.get("pinterest.carousel", True):
                    urls = self._gallery_urls(product)
                    if len(urls) >= 2:
                        try:
                            pin = self.api.create_carousel_pin(
                                board_id=board_id,
                                items=[{"url": u, "title": seo_t, "link": link}
                                       for u in urls],
                                link=link,
                                title=seo_t,
                                description=product["seo_text"],
                                alt_text=product["title"][:500],
                                scheduled_for=scheduled_for,
                                board_section_id=section_id,
                            )
                            self.db.log("INFO",
                                        f"🎠 Carousel pin created ({len(urls)} images)")
                        except PinterestError as exc:
                            self.db.log("WARN", f"carousel unavailable "
                                                f"({str(exc)[:120]}) — single pin")
                            pin = None
                if pin is None:
                    pin = self.api.create_image_pin(
                        board_id=board_id,
                        link=link,
                        title=seo_t,
                        description=product["seo_text"],
                        alt_text=product["title"][:500],
                        image_path=product.get("pin_image") or product.get("image_path"),
                        scheduled_for=scheduled_for,
                        board_section_id=section_id,
                    )
            self.db.update_post(
                post_id,
                pin_id=str(pin.get("id", "")),
                status="posted",
                posted_at=datetime.now(self.tz).isoformat(timespec="seconds"),
            )
            self.db.update_product(product["id"], status="posted", claim_ts="")
            self.db.log("INFO", f"Posted pin {pin.get('id')} — {product['title'][:50]}")
            self.notify.posted(product["title"], str(pin.get("id")), product["source"])
            # broadcast to public Telegram deals channel (top-India trick)
            self.notify.deal(product["title"],
                             price_label(product["price"], product["currency"]),
                             link, product.get("image_url", ""))
            # platforms that come AFTER pinterest in the configured order
            for plat in order:
                if plat in done or plat == "pinterest":
                    continue
                if plat == "instagram":
                    self._post_instagram(product, post_id)
                elif plat == "facebook":
                    self._post_facebook(product)
                elif plat == "youtube":
                    self._post_youtube(product)
            return pin
        except PinterestError as exc:
            attempts = int(product.get("attempts", 0) or 0) + 1
            # transient errors retry next cycle; 3 strikes = skip forever
            status = "queued" if attempts < 3 else "skipped"
            if post_id:
                self.db.update_post(post_id, status="failed", error=str(exc)[:500])
            self.db.update_product(product["id"], status=status, claim_ts="",
                                   error=str(exc)[:500], attempts=attempts)
            self.db.log("ERROR", f"Post failed for #{product['id']} "
                                 f"(attempt {attempts}): {exc}")
            raise
        except Exception as exc:  # noqa: BLE001 — never strand a claimed row
            if post_id:
                self.db.update_post(post_id, status="failed", error=str(exc)[:500])
            self.db.update_product(product["id"], status="queued", claim_ts="",
                                   error=str(exc)[:500])
            self.db.log("WARN", f"#{product['id']} unexpected error, claim "
                                f"released for retry: {exc}")
            raise

    # ---------------------------------------------------------- instagram
    def _post_instagram(self, product: dict, post_id: int) -> None:
        """Cross-post the same product to Instagram (optional, best-effort)."""
        if not (self.ig.enabled and self.ig.configured):
            return
        caption = build_ig_caption(self.cfg, product["title"], product["price"],
                                   product["currency"])
        try:
            from . import playbook as pb
            label_h = price_label(product["price"], product["currency"])
            hook = pb.hook_line(product["title"], label_h,
                                archetype=product.get("hook") or "auto",
                                seed=product.get("id"))
            if hook:
                caption = f"{hook}\n\n{caption}"
        except Exception:  # noqa: BLE001 — caption is never worth a failure
            pass
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
            # auto direct link: bio website becomes THIS deal
            bio_link = (f"{str(self.cfg.get('link.public_base','') or '').rstrip('/')}/go/{product['id']}"
                        if (self.cfg.get("link.bridge", False)
                            and self.cfg.get("link.public_base"))
                        else self._aff_link(product, "instagram"))
            self.ig.set_bio_link(bio_link)
            # story = extra 24h surface (cheap reach, CTA + auto-DM covers
            # the missing link sticker which the API cannot attach)
            if self.cfg.get("instagram.stories", True) and urls:
                try:
                    sid = self.ig.post_story(urls[0])
                    self.db.log("INFO", f"Instagram story {sid} live")
                except Exception as exc:  # noqa: BLE001 — story is a bonus
                    self.db.log("WARN", f"Instagram story skipped: {exc}")
        except InstagramError as exc:
            self.db.update_post(post_id, ig_error=str(exc)[:400])
            self.db.log("WARN", f"Instagram cross-post failed: {exc}")

    def _post_youtube(self, product: dict) -> None:
        """Publish the product's reel as a YouTube Short (optional, best-effort).

        YouTube descriptions allow clickable links and Shorts keep earning
        search traffic for years — same evergreen logic as Pinterest.
        """
        from .youtube import YouTubeAPI, YouTubeError
        yt = YouTubeAPI(self.cfg)
        if not (yt.enabled and yt.configured):
            return
        video = str(product.get("video_path") or "")
        if not video:
            self.db.log("WARN", "YouTube: no reel for this product, skipped")
            return
        link = self._aff_link(product, "youtube")
        label = price_label(product["price"], product["currency"])
        # 📚 playbook: PAS/Hinglish hook first, on-screen text for muted
        # viewers, max 3 products, 3-5 hashtags, pinned comment with the link.
        from . import playbook as pb
        row = {**product, "price_label": label}
        script = pb.shorts_script([row], seed=product.get("id"))
        if product.get("hook") and product["hook"] != "auto":
            script["hook"] = pb.hook_line(product["title"], label,
                                          archetype=product["hook"],
                                          seed=product.get("id")) or script["hook"]
        hook = script["hook"] or product["title"]
        # title: keyword-rich (YouTube search is a discovery lever, and long
        # hooks would overflow the 100-char limit); the hook drives the
        # description + on-screen text where it actually stops the scroll.
        title = script.get("title") or product["title"]
        bullets = "\n".join(f"• {b}" for b in script["beats"])
        onscreen = " | ".join(script["onscreen"][:3])
        desc = (f"{hook}\n\n{bullets}\n\n"
                f"🛒 Buy here (live price): {link}\n"
                f"📌 More deals every day: "
                f"{str(self.cfg.get('link.public_base', '') or '').rstrip('/')}\n\n"
                f"On-screen: {onscreen}\n\n"
                f"{' '.join(script['hashtags'])} #Shopping #Offer")
        try:
            vid = yt.upload_short(video, title, desc,
                                  tags=[t.lstrip("#").lower()
                                        for t in script["hashtags"]] +
                                       ["deals", "india", "shopping"])
            self.db.log("INFO", f"YouTube Short uploaded: {vid}")
            # pinned comment = +10-15% conversion (research) — best effort
            pinned = f"{script['pinned_comment']}\n{link}"
            if vid and yt.comment_on_video(vid, pinned):
                self.db.log("INFO", f"📌 Pinned product comment on Short {vid}")
        except YouTubeError as exc:
            self.db.log("WARN", f"YouTube upload failed: {exc}")

    def _ig_dm_for(self, trigger: str, text: str) -> str:
        """ManyChat-style DM answer with a REAL product + its buy link:
        matches the DM words against your posted products; fallback =
        today's deals page."""
        base = str(self.cfg.get("link.public_base", "") or "").rstrip("/")
        bridge = bool(self.cfg.get("link.bridge", False)) and base
        words = [w for w in text.lower().split() if len(w) > 3]
        for p in self.db.recent_posts(limit=60):
            t = (p.get("title") or "").lower()
            if any(w in t for w in words):
                link = (f"{base}/go/{p['product_id']}" if bridge
                        else self._aff_link(p, "instagram"))
                return (f"🔥 {p['title'][:60]} — grab it here 😍 {link}")
        if base:
            return f"😍 Today's best deals, all in one place: {base}/deals/today"
        return "🔗 Link in bio! 😍"

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
            # Facebook ALLOWS clickable links in post text → auto-link!
            base = str(self.cfg.get("link.public_base", "") or "").rstrip("/")
            fb_link = (f"{base}/go/{product['id']}"
                       if (self.cfg.get("link.bridge", False) and base)
                       else self._aff_link(product, "facebook"))
            caption = f"{caption}\n\n🛒 Direct link: {fb_link}"
            mode = str(self.cfg.get("facebook.mode", "photo"))
            if mode == "link":
                base = str(self.cfg.get("link.public_base", "") or "").rstrip("/")
                url = (f"{base}/go/{product['id']}" if base
                       else self._aff_link(product, "facebook"))
                fid = self.fb.post_link(url, caption)
            else:
                fid = self.fb.post_photo(product.get("image_url", ""), caption)
            self.db.log("INFO", f"Facebook post {fid} — {product['title'][:40]}")
        except FacebookError as exc:
            self.db.log("WARN", f"Facebook cross-post failed: {exc}")

    def post_next(self, tries: int = 3) -> dict | None:
        """Post the next queued product. Returns the pin dict or None.

        `tries > 1` matters when several workers share the queue: if another
        process claims the head product first, we simply take the next one
        instead of idling. QA-quarantined products are skipped the same way.
        """
        pending = self.db.pending_products(limit=max(5, tries))
        if not pending:
            self.db.log("INFO", "Queue is empty — nothing to post.")
            return None
        # feed variety: don't post 3 of the same topic in a row (spam signal)
        try:
            from . import topics
            recent = [r.get("title", "") for r in
                      (self.db.recent_posts(limit=2) or [])]
            ordered = topics.order_for_variety(pending, recent)
        except Exception:  # noqa: BLE001 — variety is a bonus, never a blocker
            ordered = pending
        for product in ordered[:max(1, tries)]:
            pin = self.post_product(product)
            if pin is not None:
                return pin
        return None

    def post_batch(self, count: int, human_gaps: bool = True,
                   quick_gap: float = 6.0) -> list[dict]:
        """Post up to `count` queued products.

        `human_gaps=True` (autopilot) waits the configured 40m±25 gap between
        pins so the account looks human. Manual "post now" from the panel uses
        `human_gaps=False`: nobody should wait hours in a browser tab — it only
        keeps a short anti-hammer pause between API calls.
        """
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
                if human_gaps:
                    gap = self._human_gap()
                    self.db.log("INFO", f"Waiting {gap:.0f}s before next pin (human-like)")
                else:
                    gap = quick_gap
                time.sleep(gap)
        return posted

    # ----------------------------------------------------------- autopilot
    def auto_source(self) -> int:
        """ZERO-TOUCH winner-clone sourcing: hunts products in the exact
        niches top channels push, priority order (fashion → decor → beauty…)."""
        added = 0
        limit = self.cfg.get_int("autopilot.discover_limit", 4)
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
                    if pid > 0:
                        self._score_usefulness(pid)
                except ValueError:
                    continue
                self.scraper.polite_wait()
            if added:  # don't over-hunt in one cycle
                break
        if added:
            self.db.log("INFO", f"🏆 Winner-clone sourced {added} new product(s) "
                                "from top niches")
        return added

    def _self_audit(self) -> None:
        """Once a day: am I still healthy? Links, secrets, queue, breaker.

        Logs a single readable line per issue (and one summary) so the owner
        only has to glance at the dashboard — nobody has to check anything.
        """
        from . import control, health, radar, ready
        notes: list[str] = []
        try:
            secrets = health.audit_secrets(self.cfg)
            bad = [s for s in secrets if s.get("exists") and not s.get("ok")]
            if bad:
                notes.append(f"{len(bad)} credential file(s) not private "
                             f"(chmod 600 .env data/*.txt)")
        except Exception:  # noqa: BLE001
            pass
        try:
            s = ready.summary(self.cfg)
            if not s["ready"]:
                left = ", ".join(i["label"] for i in s["you_must_do"][:3])
                notes.append(f"setup {s['percent']}% — still needed: {left}")
        except Exception:  # noqa: BLE001
            pass
        try:
            stats = self.db.stats()
            if int(stats.get("queued", 0)) == 0:
                notes.append("queue empty (radar/autopilot will refill it)")
        except Exception:  # noqa: BLE001
            pass
        try:
            if control.is_paused(self.db):
                notes.append("posting is PAUSED by owner")
            if self.api_paused():
                notes.append("API breaker open (token/rate limit)")
        except Exception:  # noqa: BLE001
            pass
        try:
            view = radar.radar_view(self.cfg, self.db, n=1)
            best = view["best"][0]["usefulness"] if view.get("best") else 0
        except Exception:  # noqa: BLE001
            best = 0
        if notes:
            for n in notes:
                self.db.log("WARN", f"📋 self-audit: {n}")
        else:
            self.db.log("INFO", "📋 self-audit: all good — posting healthy, "
                                f"best product {best}/100")

    # ------------------------------------------------ API circuit breaker
    def api_paused(self) -> dict:
        """Open breaker state (or {}) — persisted, survives restarts."""
        from . import breaker
        state = breaker.load(self.db.get_state(breaker.STATE_KEY))
        if not state or not breaker.is_open(state, time.time()):
            return {}
        return state

    def _api_failed(self, exc: Exception) -> float:
        """Record an API failure; returns how long posting must pause."""
        from . import breaker
        prev = breaker.load(self.db.get_state(breaker.STATE_KEY))
        state = breaker.record_failure(prev, str(exc), time.time())
        try:
            self.db.set_state(breaker.STATE_KEY, breaker.dump(state))
        except Exception:  # noqa: BLE001 — breaker must never break the loop
            pass
        wait = breaker.remaining(state, time.time())
        self.db.log("ERROR", f"🚧 API breaker OPEN ({state['kind']}) for "
                             f"{breaker.human(wait)} — {state['hint']}")
        return wait

    def _api_ok(self) -> None:
        from . import breaker
        if self.db.get_state(breaker.STATE_KEY):
            try:
                self.db.del_state(breaker.STATE_KEY)
            except Exception:  # noqa: BLE001
                pass

    def _pick_hook(self) -> str:
        """Choose a hook archetype, biased by what earned clicks so far.

        Reads `db.hook_performance()` (clicks per archetype) and lets the
        playbook balance explore/exploit. Never raises — falls back to 'auto'.
        """
        try:
            from . import playbook as pb
            perf = self.db.hook_performance()
            return pb.pick_archetype(perf)
        except Exception:  # noqa: BLE001 — choosing a hook must never fail
            return "auto"

    def _score_usefulness(self, pid: int) -> int:
        """Re-rank one queued product by the radar's usefulness score.

        `pending_products()` posts HIGHEST score first, so this is what makes
        the most USEFUL products go out before random cheap fillers.
        """
        try:
            from . import radar
            row = next((p for p in self.db.all_products(limit=500)
                        if p["id"] == pid), None)
            if not row:
                return 0
            score, why = radar.usefulness(row)
            self.db.update_product(pid, score=score)
            self.db.log("INFO", f"🧭 Radar score {score}/100 for #{pid}"
                                f"{' — ' + why[0] if why else ''}")
            return score
        except Exception as exc:  # noqa: BLE001 — never break sourcing
            self.db.log("WARN", f"radar scoring skipped for #{pid}: {exc}")
            return 0

    # ----------------------------------------------------------- reshare
    def reshare_winners(self) -> int:
        """Top-0.1% rotation: re-post proven winners as FRESH pins.

        Pinterest's algorithm boosts new pins; products that already earned
        clicks get a new design + new keywords and go around again.

        Guarded by a named lock: winners are already 'posted' (so the queue
        claim cannot protect them), and two processes re-sharing the same
        winner at once = duplicate pin.
        """
        from .lock import AlreadyRunning, acquire, release
        try:
            _lk = acquire(self.cfg, "reshare", stale_after=1800)
        except AlreadyRunning:
            self.db.log("INFO", "reshare skipped — another worker is rotating "
                                "winners right now")
            return 0
        try:
            return self._reshare_winners_locked()
        finally:
            release(_lk)

    def _reshare_winners_locked(self) -> int:
        cands = self.db.reshare_candidates(
            min_clicks=self.cfg.get_int("reshare.min_clicks", 3),
            rest_days=self.cfg.get_int("reshare.rest_days", 7),
            max_shares=self.cfg.get_int("reshare.max_shares", 3))
        # 📈 Pinterest-reported engagement (saves/clicks) also qualifies a
        # winner — even before our own landing counter sees traffic
        try:
            eng = self.db.engagement_by_product()
            if eng:
                known = {c["id"] for c in cands}
                extra = [p for p in self.db.all_products(limit=200)
                         if p["id"] in eng and eng[p["id"]] >= 25
                         and p["id"] not in known
                         and p.get("status") == "posted"]
                extra.sort(key=lambda p: eng[p["id"]], reverse=True)
                cands = extra[:1] + cands          # pinterest-proven first
        except Exception as exc:  # noqa: BLE001
            self.db.log("WARN", f"engagement rotation skipped: {exc}")
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

    # -------------------------------------------------------- price watch
    def price_watch(self, limit: int = 5) -> int:
        """Top-channel trick: re-check posted winners for PRICE DROPS and
        re-announce them ("📉 price drop" pins convert hard). Polite + capped."""
        import re as _re
        n = 0
        posted = [p for p in self.db.all_products(limit=150)
                  if p.get("status") == "posted"][:limit]
        for p in posted:
            try:
                fresh = self.scraper.scrape(p["url"])
            except Exception:  # noqa: BLE001
                continue
            if not fresh.ok or not fresh.price:
                continue
            def val(s):
                try:
                    return float(_re.sub(r"[^\d.]", "", s.replace(",", "")) or 0)
                except ValueError:
                    return 0.0
            old, new = val(p["price"]), val(fresh.price)
            if old and new and new <= old * 0.90:  # ≥10% drop
                self.db.update_product(p["id"], price=fresh.price,
                                       discount=fresh.discount_pct)
                self.db.log("INFO", f"📉 PRICE DROP #{p['id']}: {p['price']} → "
                                    f"{fresh.price} — re-announcing")
                try:
                    self.post_product({**p, "price": fresh.price,
                                       "discount": fresh.discount_pct,
                                       "status": "queued"})
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"Price-drop re-post failed: {exc}")
                n += 1
            self.scraper.polite_wait()
        return n

    # -------------------------------------------------------- housekeeping
    def pin_performance(self, limit: int = 20) -> dict:
        """Pull REAL Pinterest metrics for recent pins (impressions, saves,
        clicks) → stored in DB and used by the winners-rotation.

        Honest source of truth: our landing counter only sees people who
        reached the bridge page; Pinterest tells us the full funnel.
        """
        if not self.cfg.get("pinterest.analytics", True):
            return {"checked": 0, "skipped": "disabled"}
        if not self.api.configured:
            return {"checked": 0, "skipped": "no credentials"}
        checked = top = 0
        best = None
        for row in self.db.pins_needing_metrics(limit=limit):
            try:
                m = self.api.pin_analytics(str(row["pin_id"]), days=7)
            except Exception as exc:  # noqa: BLE001 — analytics are a bonus
                self.db.log("WARN", f"pin analytics skipped: {exc}")
                break
            self.db.save_pin_metrics(
                str(row["pin_id"]), int(row["product_id"] or 0),
                m.get("impression", 0), m.get("save", 0),
                m.get("pin_click", 0), m.get("outbound_click", 0))
            checked += 1
            score = (m.get("impression", 0) + m.get("save", 0) * 3
                     + m.get("pin_click", 0) * 5 + m.get("outbound_click", 0) * 8)
            if score and (best is None or score > best[1]):
                best = (row.get("title") or "", score)
            if score >= 20:
                top += 1
        if best:
            self.db.log("INFO", f"📈 Pin performance: {checked} pins measured, "
                                f"{top} performing — best: {best[0][:40]}")
        return {"checked": checked, "performing": top,
                "best": best[0] if best else ""}

    def housekeep(self) -> None:
        """Long-runtime hygiene: prune old logs + stale media (months-safe)."""
        try:
            import os as _os
            cutoff = time.time() - 14 * 86400
            freed = 0
            for f in self.cfg.media_dir.glob("*"):
                try:
                    if f.is_file() and not f.name.startswith("demo_") \
                            and _os.path.getmtime(f) < cutoff:
                        freed += f.stat().st_size
                        f.unlink()
                except OSError:
                    continue
            self.db.prune_logs(keep=3000)
            self.db.log("INFO", f"🧹 Housekeeping: freed {freed // (1024*1024)} MB, "
                                "logs pruned")
        except Exception as exc:  # noqa: BLE001
            self.db.log("WARN", f"Housekeeping skipped: {exc}")

    # ----------------------------------------------------------- list posts
    def post_ig_list(self, segment: str | None = None) -> str | None:
        """Instagram CAROUSEL list post — the highest-engagement IG format.

        2026 data: carousels beat Reels on engagement (0.50-0.55% vs 0.50%)
        and earn ~3x the saves; slide 1 carries ~80% of the engagement, so it
        is a hook card, then one product per slide, then a save-CTA slide.
        Runs at most once a day (a wall of list posts kills reach).
        """
        from . import playbook as pb
        from . import roundup as ru
        if not (self.ig.enabled and self.ig.configured):
            return None
        today = datetime.now(self.tz).date().isoformat()
        if getattr(self, "_ig_list_day", "") == today:
            return None
        prods = [p for p in self.db.all_products(limit=300)
                 if (p.get("pin_image") or p.get("image_path"))]
        seg = segment or random.choice(list(ru.SEGMENTS))
        items = ru.pick_roundup(prods, seg,
                                self.cfg.get_int("instagram.list_count", 6))
        if len(items) < 3:
            self.db.log("INFO", "IG list post skipped — not enough products")
            return None
        plan = pb.ig_carousel_plan(items)
        urls: list[str] = []
        # slide 1: the designed hook card (text-forward = 80% of engagement)
        try:
            hook_img = self.cfg.media_dir / f"ig_hook_{int(time.time()*1000)}.jpg"
            self.designer.design_roundup(items, plan["slide1"], hook_img)
            hosted = self.ig.upload_imgbb(str(hook_img)) or \
                self.ig.upload_catbox(str(hook_img))
            if hosted:
                urls.append(hosted)
        except Exception as exc:  # noqa: BLE001 — slide 1 is best-effort
            self.db.log("WARN", f"IG hook slide skipped: {exc}")
        for p in items:
            img = p.get("pin_image") or p.get("image_path")
            try:
                hosted = self.ig.upload_imgbb(img) or self.ig.upload_catbox(img)
            except Exception:  # noqa: BLE001
                hosted = ""
            if hosted:
                urls.append(hosted)
        if len(urls) < 2:
            self.db.log("WARN", "IG list post skipped — media hosting failed")
            return None
        caption = plan["caption"] + " " + " ".join(plan["hashtags"])
        try:
            media_id = self.ig.post_carousel(urls, caption)
        except InstagramError as exc:
            self.db.log("WARN", f"IG list post failed: {exc}")
            return None
        self._ig_list_day = today
        self.db.log("INFO", f"📚 IG carousel list posted ({len(urls)} slides, "
                            f"{ru.SEGMENTS[seg]['label']}): {media_id}")
        return media_id

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
        items = ru.pick_roundup(prods, seg, self.cfg.get_int("roundup.count", 5))
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
        mins = self.cfg.get_float("posting.min_gap_minutes", 40)
        jitter = self.cfg.get_float("posting.jitter_minutes", 25)
        return (mins + random.random() * jitter) * 60

    def run_forever(self) -> None:  # pragma: no cover - long loop
        """24×7 scheduler: posts inside PEAK traffic windows (or configured hours)."""
        per_day = self.cfg.get_int("posting.pins_per_day", 8)
        peak = bool(self.cfg.get("posting.peak_mode", True))
        start_h = self.cfg.get_int("posting.start_hour", 9)
        end_h = self.cfg.get_int("posting.end_hour", 22)
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

            # 📚 daily Instagram CAROUSEL list post — highest-engagement IG
            # format; slide 1 hook, one product per slide, save-CTA last.
            if self.cfg.get("instagram.list_posts", True):
                try:
                    from . import playbook as _pb
                    if _pb.in_best_window("instagram", now.hour):
                        self.post_ig_list()
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"IG list post failed: {exc}")

            # daily auto-report at 9 PM IST ("roju post chestunnava" — proof!)
            today = now.date().isoformat()
            if now.hour <= 4 and getattr(self, "_house_day", "") != today:
                self._house_day = today
                self.housekeep()
            # daily price-drop radar (re-announce winners that got cheaper)
            if 11 <= now.hour <= 19 and getattr(self, "_price_day", "") != today:
                self._price_day = today
                try:
                    self.price_watch()
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"Price watch skipped: {exc}")
            # daily Pinterest analytics pull (real impressions/saves/clicks)
            if 11 <= now.hour <= 20 and getattr(self, "_perf_day", "") != today:
                self._perf_day = today
                try:
                    self.pin_performance(limit=20)
                except Exception as exc:  # noqa: BLE001
                    self.db.log("WARN", f"pin performance job error: {exc}")
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
            age_days = int(self.db.account_age_days())
            ramp = min(1.0, 0.3 + 0.1 * age_days)
            if ramp < 1.0:
                self.db.log("INFO", f"🛡️ Warm-up day {age_days}: volume at "
                                    f"{int(ramp*100)}% (anti-flag ramp)")
            eff_per_day = eff_per_day * ramp
            # human-like daily variance (±15%) — no robotic identical volume
            eff_per_day = max(1, int(eff_per_day * random.uniform(0.85, 1.15)))
            queue = self.db.pending_products(limit=100)

            # ZERO-TOUCH: queue running dry? go hunt trending products itself
            min_q = self.cfg.get_int("autopilot.min_queue", 5)
            if len(queue) < min_q and self.cfg.get("autopilot.auto_source", True):
                # 🧭 RADAR FIRST: hunt, SCORE, and queue only genuinely useful
                # products (problem-solvers, impulse-priced, repeat-purchase).
                hunted = []
                if self.cfg.get("radar.enabled", True):
                    try:
                        from . import radar as _radar
                        hunted = _radar.radar_hunt(self.cfg, self,
                                                   n=self.cfg.get_int("radar.hunt_count", 3))
                    except Exception as exc:  # noqa: BLE001 — never break the loop
                        self.db.log("WARN", f"radar hunt failed, falling back: {exc}")
                if hunted:
                    best = hunted[0]
                    self.db.log("INFO", f"🧭 Radar queued {len(hunted)} top product(s) "
                                        f"— best {best['usefulness']}/100 "
                                        f"({best['title'][:40]})")
                else:
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
            # day-wise learning: your proven weekdays post denser too
            days = self.db.click_days()
            if sum(days.values()) >= 10:
                avg_d = sum(days.values()) / max(1, len(days))
                gap_s *= 0.7 if days.get(now.weekday(), 0) > avg_d else 1.2
            # 📋 daily self-audit — the bot checks itself and says so
            try:
                if getattr(self, "_last_audit_day", "") != now.date().isoformat():
                    self._last_audit_day = now.date().isoformat()
                    self._self_audit()
            except Exception as exc:  # noqa: BLE001 — audit never breaks a run
                self.db.log("WARN", f"self-audit skipped: {exc}")

            # owner control plane: pause / daily cap / quiet hours
            from . import control
            hold = control.gate(self.db, self.cfg, now.hour, tz=self.tz)
            if hold:
                self.db.log("INFO", f"⏳ Holding off — {hold}")
                time.sleep(600)
                continue
            paused = self.api_paused()
            if paused:
                wait = min(900.0, max(30.0, float(paused["until"]) - time.time()))
                self.db.log("INFO", f"🚧 Posting paused ({paused.get('hint', '')}) "
                                    f"— retry in {int(wait)}s")
                time.sleep(wait)
                continue
            try:
                self.post_next()
                self._api_ok()          # success clears the breaker
                if self.ig.enabled and self.ig.configured:
                    self.ig.auto_reply_links(
                        reply_for=self._ig_reply_for)  # per-product answers
                    self.ig.auto_dm(reply_for=self._ig_dm_for)  # ManyChat-grade DMs
            except PinterestError as exc:
                # 401/403 → long pause (retrying cannot fix a token),
                # 429 → escalating cooldown. Never hammer the API.
                time.sleep(min(self._api_failed(exc), 1800))
                continue
            except InstagramError:
                pass
            except Exception as exc:  # noqa: BLE001 — 24×7 CRASH-NET:
                # whatever surprise happens, the machine NEVER dies
                self.db.log("ERROR", f"Cycle error (auto-recovered): {exc}")
                time.sleep(120)
                continue
            time.sleep(max(60, gap_s))
