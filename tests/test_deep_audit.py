"""DEEP AUDIT — automatic self-check that runs on every test sweep.

Owner: "deep ga chala bugs unnayi, anni automatic nuvve cheyali". This file
is the machine auditing itself: hostile inputs, missing config, flaky
networks, empty databases. Every regression here is a real bug caught
BEFORE it reaches a live account.

Rules encoded here:
  1. No unconfigured API call may touch the network (fail fast, no hangs).
  2. Network failures must surface as the module's OWN error type — never a
     raw SSL/DNS exception (which is what used to break the dashboard).
  3. Missing/broken config keys must never stop a pin from going out.
  4. Parsers must survive malformed garbage HTML.
  5. The 24×7 scheduler helpers must never raise on any clock/state.
"""
import tempfile
import time
import unittest
from pathlib import Path

from bot.config import Config, load_config
from bot.db import DB


def _cfg(tmp: str, **extra):
    raw = {
        "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/media"},
    }
    raw.update(extra)
    return Config(raw=raw)


class TestFailFastNoNetwork(unittest.TestCase):
    """Unconfigured social APIs must raise their OWN error instantly."""

    def setUp(self):
        self.cfg = load_config()          # real config, but no .env tokens
        import os
        for k in ("INSTAGRAM_ACCESS_TOKEN", "IG_USER_ID",
                  "FACEBOOK_ACCESS_TOKEN", "FACEBOOK_PAGE_ID",
                  "YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
            os.environ.pop(k, None)

    def test_instagram_errors_are_wrapped(self):
        from bot.instagram import InstagramAPI, InstagramError
        ig = InstagramAPI(self.cfg)
        t0 = time.time()
        with self.assertRaises(InstagramError):
            ig.check()
        self.assertLess(time.time() - t0, 2.0, "must fail fast, not hang")

    def test_instagram_engagement_is_noop_when_unconfigured(self):
        from bot.instagram import InstagramAPI
        ig = InstagramAPI(self.cfg)
        t0 = time.time()
        self.assertEqual(ig.auto_reply_links(reply_for=lambda a, b: "x"), 0)
        self.assertEqual(ig.auto_dm(reply_for=lambda a, b: "x"), 0)
        self.assertFalse(ig.set_bio_link("https://example.com"))
        self.assertLess(time.time() - t0, 2.0)

    def test_facebook_errors_are_wrapped(self):
        from bot.facebook import FacebookAPI, FacebookError
        fb = FacebookAPI(self.cfg)
        with self.assertRaises(FacebookError):
            fb.post_photo("https://i.jpg", "cap")
        with self.assertRaises(FacebookError):
            fb.check()

    def test_youtube_errors_are_wrapped(self):
        from bot.youtube import YouTubeAPI, YouTubeError
        with self.assertRaises(YouTubeError):
            YouTubeAPI(self.cfg).upload_short("/nope.mp4", "t", "d")

    def test_notify_never_raises(self):
        from bot.notify import Notifier
        n = Notifier()
        n.send("x")
        n.deal("t", "₹1", "https://x")
        n.daily_summary({}, 0)


class TestEmptyConfigNeverCrashes(unittest.TestCase):
    """A missing config key must never stop money from flowing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self.tmp.name)
        self.db = DB(self.cfg.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seo_and_caption_have_defaults(self):
        from bot.engine import build_seo_text, build_ig_caption
        seo = build_seo_text(self.cfg, "Women Kurta", "549", "INR", "meesho")
        self.assertIn("Women Kurta", seo)
        self.assertIn("#ad", seo)
        cap = build_ig_caption(self.cfg, "Women Kurta", "549", "INR", "meesho")
        self.assertIn("Women Kurta", cap)

    def test_broken_templates_fall_back(self):
        from bot.engine import build_seo_text, build_ig_caption
        cfg = Config(raw={"seo": {"description_template": "{nope}"},
                          "instagram": {"caption_template": "{also_nope}"}})
        self.assertTrue(build_seo_text(cfg, "T", "1", "INR", "x"))
        self.assertTrue(build_ig_caption(cfg, "T", "1", "INR", "x"))

    def test_engine_helpers_with_empty_config(self):
        from bot.engine import Engine
        e = Engine(self.cfg, self.db)
        self.assertIsInstance(e._human_gap(), float)
        self.assertIsInstance(e._pin_link({"id": 1}), str)
        self.assertIsInstance(e._aff_link({"id": 1}, "pinterest"), str)
        self.assertEqual(e._gallery_urls({}), [])
        self.assertEqual(e._section_for("B", {"title": "x"}), "")
        self.assertTrue(e.pin_filename("", "").endswith(".jpg"))

    def test_scheduler_jobs_survive_empty_state(self):
        from bot.engine import Engine
        e = Engine(self.cfg, self.db)
        e.reshare_winners()          # no candidates
        e.housekeep()                # nothing to clean
        self.assertIsInstance(e.price_watch(limit=0), int)
        self.assertEqual(e.pin_performance()["checked"], 0)

    def test_affiliate_never_crashes(self):
        from bot.affiliate import AffiliateLinker
        lk = AffiliateLinker(self.cfg)
        for url, src in [("https://www.amazon.in/dp/B0ABCDEFGH", "amazon"),
                         ("https://www.meesho.com/x/p/1k1b6", "meesho"),
                         ("https://www.flipkart.com/x/p/itm1", "flipkart"),
                         ("https://random.shop/p/1", "")]:
            out, net = lk.convert(url, src)
            self.assertTrue(out.startswith("http"), url)

    def test_qa_never_crashes_including_empty_product(self):
        from bot.qa import qa_pin
        ok, issues = qa_pin(self.cfg, self.db, {}, "", "", "", "")
        self.assertFalse(ok)
        self.assertTrue(issues)


class TestHostileParsers(unittest.TestCase):
    """Malformed HTML must never crash the scraper."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _parse(self, html):
        from bs4 import BeautifulSoup
        from bot.scraper import Scraper, Product
        s = Scraper(self.cfg)
        soup = BeautifulSoup(html, "html.parser")
        p = Product(url="https://x.com/p/1")
        s._from_jsonld(soup, p)
        s._from_opengraph(soup, p)
        s._collect_images(soup, p)
        s._collect_mrp(soup, p)
        return p

    def test_garbage_html(self):
        for html in ("", "<html><body>hi", "<div>" * 3000,
                     '<script type="application/ld+json">{bad json</script>'):
            self.assertIsNotNone(self._parse(html))

    def test_valid_shapes_still_parse(self):
        p = self._parse('<script type="application/ld+json">'
                        '[{"@type":"Product","name":"Kurta",'
                        '"offers":{"price":"549"}}]</script>')
        self.assertEqual(p.title, "Kurta")
        p2 = self._parse('<script type="application/ld+json">'
                         '{"@graph":[{"@type":"Product","name":"Graph Kurta",'
                         '"offers":{"price":"799"}}]}</script>')
        self.assertEqual(p2.title, "Graph Kurta")

    def test_detect_source_junk(self):
        from bot.scraper import detect_source
        self.assertEqual(detect_source("not a url"), "other")
        self.assertEqual(detect_source("https://www.meesho.com/x/p/1k1b6"),
                         "meesho")


class TestDashboardResilience(unittest.TestCase):
    """Every route stays <500 even with no credentials and empty DB."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.pop("DASHBOARD_PASSWORD", None)   # unlocked-route behaviour
        cls.tmp = tempfile.TemporaryDirectory()
        cfg = _cfg(cls.tmp.name)
        cls.db = DB(cfg.db_path)
        from bot.dashboard import create_app
        cls.client = create_app(cfg, cls.db).test_client()
        cls.cfg = cfg

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_status_without_credentials(self):
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["credentials_ok"])

    def test_pages_with_empty_db(self):
        for path in ("/", "/deals/today", "/api/products", "/api/posts",
                     "/api/logs", "/api/analytics"):
            self.assertLess(self.client.get(path).status_code, 500, path)

    def test_social_blocks_in_status_never_500(self):
        """The status payload must degrade gracefully when Meta is unreachable."""
        r = self.client.get("/api/status")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("instagram", body)


class TestSchedulerSafety(unittest.TestCase):
    """Warm-up ramp + gap math must be crash-proof and prune-proof."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self.tmp.name)
        self.db = DB(self.cfg.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_account_age_survives_log_pruning(self):
        self.db.add_product(source="meesho", url="u", affiliate_url="a",
                            title="t")
        before = self.db.account_age_days()
        self.db.prune_logs(keep=0)          # housekeep wipes logs
        after = self.db.account_age_days()
        self.assertAlmostEqual(before, after, places=3,
                               msg="warm-up ramp must not reset after pruning")

    def test_account_age_empty_db(self):
        self.assertEqual(self.db.account_age_days(), 0.0)

    def test_peak_window_all_hours(self):
        from datetime import datetime
        from bot.growth import peak_window
        for h in range(24):
            w = peak_window(datetime(2026, 1, 1, h, 30))
            self.assertIsInstance(w, tuple)
            self.assertEqual(len(w), 2)
            self.assertLess(w[0], w[1])

    def test_festival_boost_every_day_of_year(self):
        from datetime import date, datetime, timedelta
        from bot.growth import festival_boost
        d = date(2026, 1, 1)
        while d.year == 2026:
            name, kw, mult = festival_boost(datetime.combine(
                d, datetime.min.time()))
            self.assertIsInstance(mult, float)
            self.assertGreaterEqual(mult, 1.0)
            d += timedelta(days=7)

    def test_hooks_for_every_day(self):
        from bot.growth import hook_for
        for day in range(1, 32):
            self.assertTrue(hook_for("₹99", "Kurta", day))


class TestDBEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = DB(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_aggregates(self):
        self.assertEqual(self.db.click_counts(), {})
        self.assertEqual(self.db.click_hours(), {})
        self.assertEqual(self.db.click_days(), {})
        self.assertEqual(self.db.engagement_by_product(), {})
        self.assertEqual(self.db.pins_needing_metrics(), [])
        self.assertEqual(self.db.recent_posts(), [])
        self.assertEqual(self.db.template_clicks(), {})
        self.assertIsNone(self.db.oldest_activity())

    def test_metrics_roundtrip_and_rotation_score(self):
        self.db.save_pin_metrics("P1", 5, 1000, 20, 10, 4)
        m = self.db.latest_pin_metrics("P1")
        self.assertEqual(m["impressions"], 1000)
        eng = self.db.engagement_by_product()
        self.assertEqual(eng[5], 1000 + 20 * 3 + 10 * 5 + 4 * 8)

    def test_pending_never_returns_demo(self):
        self.db.add_product(source="meesho", url="u1", affiliate_url="a1",
                            title="demo row", status="demo")
        self.db.add_product(source="meesho", url="u2", affiliate_url="a2",
                            title="real row")
        self.assertEqual([p["url"] for p in self.db.pending_products()], ["u2"])


class TestMediaPipelineResilience(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self.tmp.name)
        Path(self.cfg.media_dir).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_designer_survives_bad_images(self):
        from PIL import Image
        from bot.pin_designer import PinDesigner
        d = PinDesigner(self.cfg)
        tmp = Path(self.tmp.name)
        tiny = tmp / "tiny.jpg"
        Image.new("RGB", (10, 10), (255, 0, 0)).save(tiny)
        out = d.create(str(tiny), "T", "₹99", str(tmp / "o.jpg"), "meesho")
        self.assertTrue(Path(out).exists())
        # missing file → placeholder, still produces a pin
        out2 = d.create("/nope.jpg", "T", "₹1", str(tmp / "o2.jpg"), "amazon")
        self.assertTrue(Path(out2).exists())

    def test_reel_raises_clear_error_on_missing_image(self):
        from bot.video_maker import ReelMaker
        v = ReelMaker(self.cfg)
        with self.assertRaises(ValueError):
            v.make("/nope.jpg", "H", "T", "₹1",
                   str(Path(self.tmp.name) / "v.mp4"), "x")

    def test_corrupt_audio_detected(self):
        from bot.video_maker import music_usable
        bad = Path(self.tmp.name) / "bad.wav"
        bad.write_bytes(b"RIFFnotaudio")
        self.assertFalse(music_usable(str(bad)))
        self.assertFalse(music_usable(None))


if __name__ == "__main__":
    unittest.main()


class TestConfigTypoSafety(unittest.TestCase):
    """A typo or blank line in config.yaml must NEVER stop the bot.

    Found in the deep audit: `width:` (blank) → int(None) crashed Engine(),
    and `pins_per_day: abc` crashed the scheduler. Both are now safe.
    """

    def test_blank_values_use_defaults(self):
        cfg = Config(raw={"design": {"width": None, "height": ""}})
        self.assertEqual(cfg.get_int("design.width", 1000), 1000)
        self.assertEqual(cfg.get_int("design.height", 1500), 1500)

    def test_typo_values_use_defaults(self):
        cfg = Config(raw={"posting": {"pins_per_day": "abc",
                                      "min_gap_minutes": "soon"},
                          "autopilot": {"min_queue": "lots"}})
        self.assertEqual(cfg.get_int("posting.pins_per_day", 8), 8)
        self.assertEqual(cfg.get_float("posting.min_gap_minutes", 40), 40.0)
        self.assertEqual(cfg.get_int("autopilot.min_queue", 5), 5)

    def test_bool_forms(self):
        cfg = Config(raw={"a": {"on": "yes", "off": "no", "t": True,
                                "n": None, "one": 1}})
        self.assertTrue(cfg.get_bool("a.on", False))
        self.assertFalse(cfg.get_bool("a.off", True))
        self.assertTrue(cfg.get_bool("a.t", False))
        self.assertFalse(cfg.get_bool("a.n", False))
        self.assertTrue(cfg.get_bool("a.one", False))

    def test_engine_starts_with_garbage_config(self):
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as td:
            cfg = Config(raw={
                "posting": {"pins_per_day": "abc"},
                "design": {"width": None, "height": ""},
                "affiliate": {"amazon_tag": None},
                "storage": {"db_path": f"{td}/t.db", "media_dir": f"{td}/media"}})
            e = Engine(cfg, DB(cfg.db_path))          # must not raise
            self.assertGreater(e._human_gap(), 0)
            self.assertGreater(e.designer.W, 100)


class TestRealPostingPath(unittest.TestCase):
    """Runs post_product with a mocked Pinterest API — exactly the path that
    silently fails in production (carousel, board sections, per-platform
    Meesho links). Found 3 real bugs here during the deep audit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from PIL import Image
        self.cfg = load_config()
        self.cfg.raw["storage"] = {
            "db_path": f"{self.tmp.name}/t.db",
            "media_dir": f"{self.tmp.name}/media"}
        Path(self.cfg.media_dir).mkdir(parents=True, exist_ok=True)
        self.cfg.raw["pinterest"].update(
            {"access_token": "tok", "carousel": True, "sections": True})
        self.cfg.raw["instagram"]["enabled"] = False
        self.cfg.raw["facebook"]["enabled"] = False
        self.cfg.raw["affiliate"]["meesho_template_link"] = (
            "https://www.meesho.com/af_invite/24197020:instagram_stories:"
            "11075346?p_id=1,"
            "https://www.meesho.com/af_invite/24197020:facebook:11075421?p_id=2")
        self.cfg.raw["affiliate"]["meesho_platform_tokens"] = {
            "pinterest": "facebook"}
        import os
        for k in ("MEESHO_TEMPLATE_LINK", "MEESHO_AFFID"):
            os.environ.pop(k, None)
        self.db = DB(self.cfg.db_path)
        from bot.engine import Engine
        self.engine = Engine(self.cfg, self.db)
        self.calls: list = []

        img = Path(self.tmp.name) / "pin.jpg"
        _pin_like(img)
        self.img = img

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_api(self):
        calls = self.calls
        img = self.img

        class MockPinterest:
            configured = True

            def ensure_board(self, name, desc=""):
                calls.append(("board", name))
                return "B1"

            def ensure_section(self, board, name):
                calls.append(("section", name))
                return "S1"

            def upload_image(self, p):
                calls.append(("upload_image", Path(p).name))
                return "MIMG"

            def create_carousel_pin(self, **kw):
                calls.append(("carousel", len(kw["items"]),
                              kw.get("board_section_id"), kw["link"]))
                return {"id": "PINC"}

            def create_image_pin(self, **kw):
                calls.append(("image_pin", kw.get("board_section_id"),
                              kw["link"], kw.get("image_path")))
                return {"id": "PINI"}

            def create_video_pin(self, *a, **kw):
                calls.append(("video_pin", kw.get("board_section_id")))
                return {"id": "PINV"}

            def list_boards(self):
                return []

        self.engine.api = MockPinterest()

    def _product(self, **over):
        fields = dict(
            source="meesho",
            url="https://www.meesho.com/kurta-set/p/1k1b6",
            affiliate_url="https://www.meesho.com/af_invite/24197020:"
                          "instagram_stories:11075346?p_id=1k1b6",
            title="Women Floral Printed Cotton Kurta Set",
            price="549", currency="INR",
            image_url="https://cdn/1.jpg",
            images="https://cdn/1.jpg,https://cdn/2.jpg,https://cdn/3.jpg",
            image_path=str(self.img), pin_image=str(self.img),
            seo_text=("🔥 Women Floral Printed Cotton Kurta Set\n💰 Price: ₹549\n"
                      "✅ Best deal #ad #kurta #fashion #meesho India shopping "
                      "offer sale today low price"),
            score=9, discount=58)
        fields.update(over)
        pid = self.db.add_product(**fields)
        return [p for p in self.db.all_products(limit=50)
                if p["id"] == pid][0]

    def test_carousel_and_section_and_platform_link(self):
        self._mock_api()
        prod = self._product()
        pin = self.engine.post_product(prod)
        self.assertEqual(pin["id"], "PINC")
        kinds = [c[0] for c in self.calls]
        self.assertIn("carousel", kinds, "multi-photo product must carousel")
        self.assertIn("section", kinds, "sections must be created")
        carousel = [c for c in self.calls if c[0] == "carousel"][0]
        self.assertEqual(carousel[1], 3)                 # 3 photos
        self.assertEqual(carousel[2], "S1")              # section attached
        self.assertIn(":facebook:11075421", carousel[3])  # pinterest override
        self.assertNotIn("instagram_stories:11075346", carousel[3])

    def test_single_photo_falls_back_to_image_pin(self):
        self._mock_api()
        prod = self._product(images="https://cdn/1.jpg")
        pin = self.engine.post_product(prod)
        self.assertEqual(pin["id"], "PINI")
        self.assertNotIn("carousel", [c[0] for c in self.calls])

    def test_dummy_products_are_quarantined(self):
        self._mock_api()
        prod = self._product(url="https://www.meesho.com/x/p/demokurta")
        self.assertIsNone(self.engine.post_product(prod))
        self.assertEqual(self.calls, [], "dummy must never reach the API")
        self.assertEqual(
            [p["status"] for p in self.db.all_products(limit=5)], ["skipped"])

    def test_commission_leak_is_quarantined(self):
        self._mock_api()
        prod = self._product(affiliate_url="https://www.meesho.com/x/p/1k1b6")
        # no tracking params anywhere → QA must stop it before the API
        self.cfg.raw["affiliate"]["meesho_template_link"] = ""
        self.cfg.raw["affiliate"]["meesho_platform_tokens"] = {}
        self.assertIsNone(self.engine.post_product(prod))
        self.assertEqual(self.calls, [])


class TestIngestPipelineMocked(unittest.TestCase):
    """ingest_url end-to-end without network — the money entry point."""

    def test_ingest_creates_variants_with_seo_filenames(self):
        import os
        from PIL import Image
        from bot.scraper import Product
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as td:
            cfg = load_config()
            cfg.raw["storage"] = {"db_path": f"{td}/t.db",
                                  "media_dir": f"{td}/media"}
            Path(cfg.media_dir).mkdir(parents=True, exist_ok=True)
            cfg.raw["video"]["auto_reel"] = False
            os.environ["MEESHO_TEMPLATE_LINK"] = (
                "https://www.meesho.com/af_invite/24197020:instagram_stories:"
                "11075346?p_id=1")
            try:
                paths = []
                for i in range(3):
                    p = Path(td) / f"s{i}.jpg"
                    _pin_like(p)
                    paths.append(str(p))

                class FakeScraper:
                    def scrape(self, url):
                        return Product(
                            url=url, source="meesho",
                            title="Women Floral Printed Cotton Kurta Set",
                            price="549", currency="INR", mrp="1299",
                            image_url="https://cdn/1.jpg",
                            images=["https://cdn/1.jpg", "https://cdn/2.jpg",
                                    "https://cdn/3.jpg"])

                    def download_image_url(self, url, dest, hint=""):
                        return paths[abs(hash(url)) % 3]

                    def download_video(self, url, dest, max_mb=120):
                        return ""

                    def enrich_media(self, prod):
                        return prod

                db = DB(cfg.db_path)
                e = Engine(cfg, db)
                e.scraper = FakeScraper()
                pid = e.ingest_url(
                    "https://www.meesho.com/women-floral-printed-kurta-set/p/1k1b6")
                self.assertGreater(pid, 0)
                rows = db.all_products(limit=10)
                self.assertGreaterEqual(len(rows), 1)
                for r in rows:
                    self.assertIn("women-floral-printed", Path(r["pin_image"]).name)
                    self.assertIn("549", Path(r["pin_image"]).name)
                    self.assertIn("af_invite", r["affiliate_url"])
                # duplicate guard
                self.assertEqual(e.ingest_url(
                    "https://www.meesho.com/women-floral-printed-kurta-set/p/1k1b6"),
                    -1)
            finally:
                os.environ.pop("MEESHO_TEMPLATE_LINK", None)


class TestTrendingSignals(unittest.TestCase):
    """R72 — real ★ rating + rating-count must reach the ranking.

    Owner: "meesho products em trending unnayo andaru em pedthunnaro ani
    pettali". Trending = the numbers the page itself shows (4.0★, 136104
    ratings) — never invented, and 0 stays 0 when the page hides them.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self.tmp.name)
        self.scraper = None

    def tearDown(self):
        self.tmp.cleanup()

    def _scraper(self):
        from bot.scraper import Scraper
        if self.scraper is None:
            self.scraper = Scraper(self.cfg)
        return self.scraper

    def test_human_int_indian_grouping(self):
        from bot.scraper import human_int
        self.assertEqual(human_int("1,36,104"), 136104)
        self.assertEqual(human_int("13.6k"), 13600)
        self.assertEqual(human_int("1.2L"), 120000)
        self.assertEqual(human_int(""), 0)
        self.assertEqual(human_int(420), 420)

    def test_meesho_page_text_social_proof(self):
        from bs4 import BeautifulSoup
        from bot.scraper import Product
        soup = BeautifulSoup(
            "<html><body><h1>KURTI RAYON</h1><p>₹200 ₹209 4% off</p>"
            "<span>4.0</span><span>136104 Ratings</span>"
            "<span>35108 Reviews</span></body></html>", "html.parser")
        prod = Product(url="https://www.meesho.com/kurti/p/35pwo2",
                       source="meesho")
        self._scraper()._site_specific(soup, prod)
        self.assertEqual(prod.rating, 4.0)
        self.assertEqual(prod.reviews, 136104)

    def test_amazon_selectors_social_proof(self):
        from bs4 import BeautifulSoup
        from bot.scraper import Product
        soup = BeautifulSoup(
            '<html><body><span id="acrCustomerReviewText">1,234 ratings</span>'
            '<span id="acrPopover" title="4.3 out of 5 stars"></span>'
            "</body></html>", "html.parser")
        prod = Product(url="https://www.amazon.in/dp/X", source="amazon")
        self._scraper()._site_specific(soup, prod)
        self.assertEqual(prod.reviews, 1234)
        self.assertEqual(prod.rating, 4.3)

    def test_jsonld_aggregate_rating(self):
        from bs4 import BeautifulSoup
        from bot.scraper import Product
        soup = BeautifulSoup(
            '<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"Kurti","aggregateRating":'
            '{"ratingValue":"4.4","ratingCount":"4,321"}}</script></head>'
            "<body></body></html>", "html.parser")
        prod = Product(url="https://www.meesho.com/kurti/p/35pwo2",
                       source="meesho")
        self._scraper()._from_jsonld(soup, prod)
        self.assertEqual(prod.rating, 4.4)
        self.assertEqual(prod.reviews, 4321)

    def test_radar_trending_volume_changes_the_ranking(self):
        from bot.radar import rank, usefulness
        row = {"title": "Women Cotton Kurta Set", "price": "₹499"}
        plain, _ = usefulness(row)
        hot, why = usefulness(row, rating=4.1, reviews=136104)
        self.assertGreater(hot, plain)
        self.assertTrue(any("🔥 trending volume" in w for w in why))
        ranked = rank([{**row, "rating": 4.1, "reviews": 136104, "id": 1}])
        self.assertTrue(any("🔥" in w for w in ranked[0]["why"]))

    def test_db_stores_rating_and_reviews(self):
        db = DB(f"{self.tmp.name}/t.db")
        pid = db.add_product(url="https://x/p/1", title="t", source="meesho",
                             rating=4.2, reviews=987)
        row = next(p for p in db.all_products() if p["id"] == pid)
        self.assertEqual(row["rating"], 4.2)
        self.assertEqual(row["reviews"], 987)


class TestPhotoToVideoReel(unittest.TestCase):
    """R72 — photos → ONE video, the worn ("ela untundi") shot first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = _cfg(self.tmp.name)
        Path(self.cfg.media_dir).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _photo(self, name, size, color=(30, 60, 200)):
        from PIL import Image
        p = self.dir / name
        Image.new("RGB", size, color).save(p)
        return str(p)

    def test_pick_hero_prefers_portrait_person_shot(self):
        from PIL import Image, ImageDraw
        from bot.video_maker import pick_hero
        flat = self._photo("flat.jpg", (1000, 500), (240, 240, 240))
        model = self.dir / "model.jpg"
        img = Image.new("RGB", (600, 1000), (252, 250, 248))
        d = ImageDraw.Draw(img)
        d.ellipse((150, 120, 450, 620), fill=(196, 150, 120))   # skin tones
        d.rectangle((180, 600, 420, 980), fill=(20, 20, 20))
        img.save(model)
        self.assertEqual(pick_hero([flat, str(model)])[0], str(model))

    def test_proof_label_real_numbers_only(self):
        from bot.video_maker import _proof_label
        self.assertEqual(_proof_label(4.0, 136104), "4.0★ · 1.36L ratings")
        self.assertEqual(_proof_label(4.5, 250), "4.5★ · 250 ratings")
        self.assertEqual(_proof_label(0, 5000), "")
        self.assertEqual(_proof_label(4.5, 0), "")

    def test_make_multi_renders_gallery_reel(self):
        from bot.video_maker import ReelMaker
        a = self._photo("a.jpg", (500, 800), (200, 30, 30))
        b = self._photo("b.jpg", (800, 500), (30, 200, 30))
        out = self.dir / "reel.mp4"
        got = ReelMaker(self.cfg).make_multi(
            [a, b], "Wait for it…", "Cotton Kurta Set", "₹299", out, "meesho",
            scene_seconds=0.3, discount=20, rating=4.2, reviews=15000)
        self.assertTrue(Path(got).exists())
        self.assertGreater(Path(got).stat().st_size, 5000)

    def test_make_multi_raises_without_usable_photo(self):
        from bot.video_maker import ReelMaker
        with self.assertRaises(ValueError):
            ReelMaker(self.cfg).make_multi(["/nope.jpg", ""], "H", "T", "₹1",
                                           self.dir / "x.mp4", "x",
                                           scene_seconds=0.2)

    def test_pin_price_prefix_is_just(self):
        from bot.pin_designer import PinDesigner
        self.assertEqual(PinDesigner(self.cfg).price_prefix, "JUST")


class TestHookFrameNeverTruncates(unittest.TestCase):
    """R72 — a cut-off hook ("3 reasons this black embroidered IS") kills the
    reel: every word of the hook must survive the auto-fit."""

    def test_long_hook_keeps_every_word(self):
        from PIL import Image, ImageDraw
        from bot.video_maker import _fit_text
        d = ImageDraw.Draw(Image.new("RGB", (720, 1280)))
        long_hook = ("3 reasons this black embroidered rayon kurti is worth "
                     "every single rupee you spend today")
        lines, size = _fit_text(d, long_hook, 640, 5)
        self.assertEqual(" ".join(lines), " ".join(long_hook.split()))
        self.assertGreaterEqual(size, 26)

    def test_hook_frame_renders_with_long_text(self):
        import tempfile
        from bot.video_maker import ReelMaker
        with tempfile.TemporaryDirectory() as tmp:
            img = ReelMaker(_cfg(tmp))._frame_hook(
                "rating viral meesho finds until i go broke day 41", 1.0)
            self.assertEqual(img.size, (720, 1280))


def _pin_like(path, size=(1000, 1500)):
    """Non-blank stand-in for a DESIGNED pin (QA rejects blank media now)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle((60, 60, size[0] - 60, size[1] - 420), fill=(38, 38, 58))
    d.rectangle((80, size[1] - 320, size[0] - 80, size[1] - 160),
                fill=(200, 30, 60))
    im.save(path)


class TestCorrectPhotos(unittest.TestCase):
    """R73 — "correctgaa photos thiskoni upload cheyali".

    Downloads must be the FULL-SIZE photo, one entry per real shot, and an
    HTML error page / 1×1 pixel can never be saved as a product photo.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = _cfg(self.tmp.name)
        Path(self.cfg.media_dir).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _scraper(self):
        from bot.scraper import Scraper
        return Scraper(self.cfg)

    def test_normalize_image_url_full_size(self):
        from bot.scraper import normalize_image_url as n
        self.assertIn("._SL1500_.", n("https://m.media-amazon.com/images/I/71a._SX300_.jpg"))
        self.assertIn("/image/832/832/",
                      n("https://rukminim2.flixcart.com/image/128/128/x/jpeg/a.jpg"))
        self.assertEqual(n("https://images.meesho.com/images/products/1/x.jpg?width=200"),
                         "https://images.meesho.com/images/products/1/x.jpg")
        self.assertEqual(n("https://images.meesho.com/images/products/1/x_320x480.jpg"),
                         "https://images.meesho.com/images/products/1/x.jpg")

    def test_photo_key_collapses_sizes(self):
        from bot.scraper import photo_key
        self.assertEqual(photo_key("https://m.media-amazon.com/images/I/71a._SX300_.jpg"),
                         photo_key("https://m.media-amazon.com/images/I/71a._SL1500_.jpg"))
        self.assertEqual(photo_key("https://images.meesho.com/images/products/1/x.jpg?width=90"),
                         photo_key("https://images.meesho.com/images/products/1/x.jpg?width=900"))

    def test_gallery_keeps_one_entry_per_shot_hi_res(self):
        from bs4 import BeautifulSoup
        from bot.scraper import Product
        html = ('<html><head><script type="application/ld+json">'
                '{"@type":"Product","name":"Kurti","image":['
                '"https://images.meesho.com/images/products/1/x.jpg?width=200",'
                '"https://images.meesho.com/images/products/1/x.jpg?width=1000"]}'
                '</script></head><body></body></html>')
        s = self._scraper()
        s._last_html = html
        prod = Product(url="https://www.meesho.com/kurti/p/35pwo2", source="meesho")
        s._collect_images(BeautifulSoup(html, "html.parser"), prod)
        self.assertEqual(len(prod.images), 1)
        self.assertNotIn("?", prod.images[0])

    class _Resp:
        def __init__(self, content, ctype):
            self.content, self.headers = content, {"content-type": ctype}

        def raise_for_status(self):
            pass

    class _Sess:
        def __init__(self, resp):
            self.resp = resp

        def get(self, url, timeout=30):
            return resp_(self.resp)

    def test_download_rejects_html_error_page(self):
        s = self._scraper()
        s.session = self._Sess(self._Resp(b"<html>403 Forbidden</html>", "text/html"))
        self.assertEqual(s.download_image_url("https://x/a.jpg", self.dir), "")

    def test_download_rejects_tiny_and_accepts_real_photo(self):
        import io as _io
        from PIL import Image
        s = self._scraper()
        small = _io.BytesIO()
        Image.new("RGB", (64, 64), (10, 200, 10)).save(small, "PNG")
        s.session = self._Sess(self._Resp(small.getvalue(), "image/png"))
        self.assertEqual(s.download_image_url("https://x/tiny.png", self.dir), "")
        big = _io.BytesIO()
        Image.new("RGB", (900, 1200), (120, 30, 200)).save(big, "JPEG")
        data = big.getvalue()
        s.session = self._Sess(self._Resp(data, "image/jpeg"))
        p1 = s.download_image_url("https://x/big.jpg", self.dir, "test")
        p2 = s.download_image_url("https://x/big.jpg", self.dir, "test")
        self.assertTrue(p1 and Path(p1).exists())
        self.assertEqual(p1, p2)          # same bytes → same file (no dupes)

    def test_hook_frame_shows_the_product(self):
        from PIL import Image, ImageStat
        from bot.video_maker import ReelMaker
        bg = Image.new("RGB", (900, 1400), (200, 30, 40))
        img = ReelMaker(self.cfg)._frame_hook("wait for the price", 1.0, bg=bg)
        self.assertEqual(img.size, (720, 1280))
        self.assertGreater(
            ImageStat.Stat(img.convert("L").resize((64, 64))).stddev[0], 3.0)

    def test_sourcing_plan_starts_with_trending_pages(self):
        from bot.trends import MEESHO_TRENDING, sourcing_plan
        plan = sourcing_plan(per_niche=1)
        self.assertTrue(MEESHO_TRENDING)
        self.assertEqual(plan[0][0], "meesho")
        self.assertTrue(plan[0][1].startswith("https://www.meesho.com/"))

    def test_discover_products_accepts_a_trending_url(self):
        from bot.scraper import Scraper
        s = Scraper(self.cfg)
        seen = {}

        def fake_fetch(url, retries=None):
            seen["url"] = url
            return '<a href="/kurti/p/35pwo2">x</a>'

        s._fetch = fake_fetch
        urls = s.discover_products("meesho", limit=2,
                                   query="https://www.meesho.com/home-decor/pl/3tl")
        self.assertEqual(seen["url"], "https://www.meesho.com/home-decor/pl/3tl")
        self.assertTrue(any("/p/35pwo2" in u for u in urls))


def resp_(r):
    return r
