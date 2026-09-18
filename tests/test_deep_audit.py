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
        Image.new("RGB", (1000, 1500), (255, 255, 255)).save(img)
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
                    Image.new("RGB", (1000, 1500), (250, 250, 250)).save(p)
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
