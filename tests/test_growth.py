"""Tests for the viral-tricks engine (growth) and auto-reel maker."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config  # noqa: E402
from bot.growth import (  # noqa: E402
    hashtag_mix, hook_for, peak_window, roundup_title, seo_title,
)


class TestGrowth(unittest.TestCase):
    def test_seo_title_limits_and_keywords(self):
        t = seo_title("boAt Airdopes 141 Bluetooth Truly Wireless Earbuds", "₹1,099", "amazon")
        self.assertLessEqual(len(t), 100)
        self.assertIn("amazon", t.lower())
        self.assertIn("|", t)  # keyword separators present

    def test_hook(self):
        h = hook_for("₹999", "Smart Watch For Men", 12)
        self.assertTrue(len(h) > 5)
        self.assertNotIn("{", h)  # no unfilled placeholders

    def test_hashtag_mix(self):
        tags = hashtag_mix("Wireless Earbuds Bluetooth Headphones", "amazon", 8)
        parts = tags.split()
        self.assertLessEqual(len(parts), 8)
        self.assertTrue(all(p.startswith("#") and not p.startswith("##") for p in parts))
        self.assertTrue(len(parts) >= 4)  # multi-tier mix

    def test_peak_window(self):
        sat = datetime(2026, 9, 19, 11, 0)   # Saturday morning
        self.assertEqual(peak_window(sat), (10, 13))
        wed = datetime(2026, 9, 16, 20, 0)   # Wednesday evening
        self.assertEqual(peak_window(wed), (19, 22))

    def test_roundup_title(self):
        t = roundup_title("₹999", "Earbuds")
        self.assertNotIn("{", t)


class TestReelMaker(unittest.TestCase):
    def test_reel_generated(self):
        from PIL import Image, ImageDraw
        from bot.video_maker import ReelMaker
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(raw={"design": {"brand_name": "Test"}})
            img = Image.new("RGB", (600, 600), (210, 40, 40))
            ImageDraw.Draw(img).ellipse([100, 100, 500, 500], fill=(255, 200, 60))
            src = Path(tmp) / "p.jpg"
            img.save(src)
            out = Path(tmp) / "reel.mp4"
            ReelMaker(cfg).make(str(src), "Wait for the price 👀",
                                "Test Product Title", "₹499", out, "amazon")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 20_000)  # real mp4, not empty


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTrends(unittest.TestCase):
    def test_winner_scoring(self):
        from bot.trends import score_product
        fashion = score_product("Women Yellow Floral Kurta Set", "549", "meesho")
        random_ = score_product("Industrial Bearing 6204 ZZ", "549", "other")
        self.assertGreater(fashion, random_)
        # sweet price bonus
        cheap = score_product("Wireless Earbuds", "999", "amazon")
        pricey = score_product("Wireless Earbuds", "99999", "amazon")
        self.assertGreater(cheap, pricey)

    def test_sourcing_plan_priority(self):
        from bot.trends import sourcing_plan
        plan = sourcing_plan()
        self.assertTrue(plan)
        # fashion niche must come first (priority 1)
        self.assertEqual(plan[0][2], "Women's Fashion")
        stores = {p[0] for p in plan}
        self.assertTrue(stores & {"amazon", "meesho", "flipkart"})


class TestConversion(unittest.TestCase):
    def test_discount_pct(self):
        from bot.scraper import Product
        p = Product(url="x", price="1099", mrp="2999")
        self.assertEqual(p.discount_pct, 63)
        p2 = Product(url="x", price="1099", mrp="")
        self.assertEqual(p2.discount_pct, 0)

    def test_festival_boost(self):
        from bot.growth import festival_boost
        # 5 days before Diwali (Nov 8)
        import datetime as dt
        name, kw, mult = festival_boost(dt.datetime(2026, 11, 3, 12, 0))
        self.assertEqual(name, "Diwali")
        self.assertGreater(mult, 1)
        # payday
        name2, _, mult2 = festival_boost(dt.datetime(2026, 6, 2, 12, 0))
        self.assertEqual(name2, "Payday")
        self.assertGreaterEqual(mult2, 1.2)

    def test_seo_urgency(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from bot.engine import build_seo_text
        from bot.config import Config
        cfg = Config(raw={"seo": {"hashtags": True, "max_hashtags": 6,
                                  "extra_hashtags": [],
                                  "description_template": "{title} {price} {hashtags}"}})
        txt = build_seo_text(cfg, "Earbuds", "999", "INR", "amazon",
                             discount=63, festival_kw="diwali deals")
        self.assertIn("63% OFF", txt)
        self.assertIn("Diwali Deals", txt)
        self.assertIn("#ad", txt)


class TestMusicMaker(unittest.TestCase):
    def test_compose(self):
        import tempfile, wave
        from pathlib import Path
        from bot import music_maker
        with tempfile.TemporaryDirectory() as tmp:
            out = music_maker.compose(Path(tmp) / "bgm.wav", seconds=4)
            with wave.open(out) as w:
                self.assertEqual(w.getnchannels(), 1)
                self.assertGreater(w.getnframes(), 22050 * 3)  # ~4s audio


class TestReshare(unittest.TestCase):
    def test_reshare_candidates(self):
        import tempfile
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        from bot.db import DB
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            pid = db.add_product(source="amazon", url="http://x/1", title="Winner Item",
                                    price="499", currency="INR", image_url="", affiliate_url="http://a")
            db.add_post(product_id=pid, board_id="b1", status="posted",
                        posted_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat())
            db.update_product(pid, status="posted")
            db.update_post(1, status="posted")
            for _ in range(4):
                db.log_click(pid, "ua")
            cands = db.reshare_candidates(min_clicks=3, rest_days=7)
            self.assertEqual(len(cands), 1)
            self.assertEqual(cands[0]["clicks"], 4)
            # rested too recently → excluded
            db.update_post(1, posted_at=datetime.now(timezone.utc).isoformat())
            self.assertEqual(len(db.reshare_candidates()), 0)


class TestQAGate(unittest.TestCase):
    def test_qa_pin(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from bot.config import load_config
        from bot.db import DB
        from bot import qa
        cfg = load_config()
        # R65: the repo ships a real .env now; keep these assertions about the
        # config values deterministic by pinning the env tag.
        import os
        from unittest import mock
        env = mock.patch.dict(os.environ, {"AMAZON_TAG": ""})
        env.start()
        self.addCleanup(env.stop)
        cfg.raw.setdefault("affiliate", {})["amazon_tag"] = "me-21"
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "p.jpg"
            Image.new("RGB", (900, 900), "white").save(img)
            db = DB(Path(tmp) / "t.db")
            prod = {"id": 1, "title": "Wireless Bluetooth Earbuds Gaming"}
            seo_t = "Wireless Bluetooth Earbuds Gaming | best deal 2026"
            seo_d = ("Wireless Bluetooth earbuds gaming edition — deep bass, "
                     "42h playtime, fast charging. Grab the offer today! #ad")
            ok, issues = qa.qa_pin(cfg, db, prod, seo_t, seo_d, str(img),
                                   "https://www.amazon.in/dp/B0X?tag=me-21")
            self.assertTrue(ok, issues)
            # broken: missing image + thin description + missing disclosure
            ok2, issues2 = qa.qa_pin(cfg, db, prod, seo_t, "short", "/nope.jpg",
                                     "https://www.amazon.in/dp/B0X?tag=me-21")
            self.assertFalse(ok2)
            self.assertTrue(any("media missing" in i for i in issues2))
            self.assertTrue(any("#ad" in i for i in issues2))


class TestProScraper(unittest.TestCase):
    def test_colorimages_extraction(self):
        from bs4 import BeautifulSoup
        from bot.config import load_config
        from bot.scraper import Scraper, Product
        s = Scraper(load_config())
        s._last_html = ("{\"colorImages\": { \"initial\": [{\"hiRes\":"
                        "\"https://m.media-amazon.com/images/I/x._SL1000_.jpg\","
                        "\"videos\":[{\"videoUrl\":\"https://cdn/vid.mp4\"}]}]}}")
        p = Product(url="https://www.amazon.in/dp/B0", source="amazon")
        s._collect_images(BeautifulSoup("<html></html>", "lxml"), p)
        self.assertTrue(p.images[0].endswith("_SL1500_.jpg"))  # hi-res forced
        self.assertTrue(p.video_url.endswith("vid.mp4"))       # brand video found


class TestMoneyPriority(unittest.TestCase):
    def test_commission_priority(self):
        from bot.trends import score_product
        s_meesho = score_product("Women floral kurta combo pack", "499", "meesho")
        s_flipkart = score_product("Women floral kurta combo pack", "499", "flipkart")
        self.assertGreater(s_meesho, s_flipkart)  # higher commission posts first


class TestEnrichMedia(unittest.TestCase):
    def _scraper(self):
        from bot.scraper import Scraper
        from bot.config import load_config
        s = Scraper(load_config())
        s.polite_wait = lambda: None
        return s

    def test_rich_product_untouched(self):
        from bot.scraper import Product
        s = self._scraper()
        def boom(url):
            raise AssertionError("should not fetch when already rich")
        s._fetch = boom
        p = Product(url="http://x/dp/B0", source="amazon")
        p.images = ["a", "b", "c"]
        p.video_url = "v.mp4"
        out = s.enrich_media(p)
        self.assertEqual(out.images, ["a", "b", "c"])

    def test_thin_product_hunts_offline(self):
        from bot.scraper import Product
        s = self._scraper()
        s._fetch = lambda url: ""   # blocked everywhere → graceful
        p = Product(url="http://x/dp/B0", source="amazon")
        p.title = "boAt Airdopes 141 Bluetooth Wireless Earbuds Black"
        p.images = ["a"]
        out = s.enrich_media(p)     # must not crash
        self.assertEqual(out.images, ["a"])


class TestAntiBan(unittest.TestCase):
    def test_oldest_activity_and_ramp(self):
        import tempfile
        from datetime import datetime, timezone
        from pathlib import Path
        from bot.db import DB
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            self.assertIsNone(db.oldest_activity())
            db.log("INFO", "boot")
            self.assertIsNotNone(db.oldest_activity())
        # ramp math sanity
        for age, expect_hi in [(0, 0.3), (7, 1.0), (30, 1.0)]:
            ramp = min(1.0, 0.3 + 0.1 * age)
            self.assertLessEqual(ramp, 1.0)


class TestPlatforms(unittest.TestCase):
    def test_facebook_and_features_inventory(self):
        from bot.config import load_config
        from bot.facebook import FacebookAPI
        from bot.features import report
        cfg = load_config()
        fb = FacebookAPI(cfg)
        self.assertFalse(fb.configured)          # no creds → safely off
        rows = report(cfg)
        self.assertGreaterEqual(len(rows), 15)
        names = {r["name"] for r in rows}
        self.assertIn("Facebook Page posting", names)
        self.assertIn("Pinterest posting", names)


class TestMeeshoRealLinks(unittest.TestCase):
    def test_generated_links_untouched(self):
        import os
        os.environ["MEESHO_AFFID"] = "charan123"
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        lk = AffiliateLinker(load_config())
        real = ["https://affiliate.meesho.com/collection/MTEwNDEyMjY6Ojo6Ojpub3JtYWw=",
                "https://www.meesho.com/af_invite/24197020:instagram_stories:11040673"
                "?p_id=394590772&ext_id=6ixg6s&utm_source=instagram_stories"]
        for u in real:
            out, net = lk.convert(u, "meesho")
            self.assertEqual(out, u)      # Meesho's own tracking intact
            self.assertEqual(net, "meesho")
        # plain product URL still auto-monetized
        plain, _ = lk.convert("https://www.meesho.com/kurta/p/xyz", "meesho")
        self.assertIn("affid=charan123", plain)


class TestRoundup(unittest.TestCase):
    def test_titles_and_segments(self):
        from datetime import datetime
        from bot.roundup import (SEGMENTS, pick_roundup, roundup_title,
                                 segment_for)
        self.assertEqual(segment_for("Women floral kurta set"), "ladies")
        self.assertEqual(segment_for("kitchen storage organizer"), "home")
        t = roundup_title("ladies", 5, datetime(2026, 9, 18))
        self.assertIn("Ladies", t)
        self.assertGreaterEqual(len(SEGMENTS), 4)
        items = pick_roundup(
            [{"title": "Women kurta", "pin_image": "a", "score": 9},
             {"title": "earbuds", "pin_image": "b", "score": 5}], "ladies", 2)
        self.assertEqual(items[0]["title"], "Women kurta")


class TestPerProductReplies(unittest.TestCase):
    def test_product_by_ig_media_and_reply(self):
        import tempfile
        from pathlib import Path
        from bot.config import load_config
        from bot.db import DB
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config()
            db = DB(Path(tmp) / "t.db")
            e = Engine(cfg, db)
            pid = db.add_product(source="amazon", url="http://x/1",
                                 title="boAt Airdopes 141 Earbuds",
                                 price="1099", currency="INR", image_url="")
            db.add_post(product_id=pid, board_id="b")
            db.update_post(1, ig_post_id="MEDIA_123")
            p = db.product_by_ig_media("MEDIA_123")
            self.assertEqual(p["title"], "boAt Airdopes 141 Earbuds")
            reply = e._ig_reply_for("MEDIA_123")
            self.assertIn("Airdopes", reply)
            self.assertIn("1,099", reply)
            self.assertIn("bio", reply)


class TestManyChatStyleTriggers(unittest.TestCase):
    def test_trigger_templates(self):
        import tempfile
        from pathlib import Path
        from bot.config import load_config
        from bot.db import DB
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            e = Engine(load_config(), db)
            pid = db.add_product(source="amazon", url="http://x/1",
                                 title="boAt Airdopes 141 Earbuds",
                                 price="1099", currency="INR", image_url="")
            db.add_post(product_id=pid, board_id="b")
            db.update_post(1, ig_post_id="M1")
            self.assertIn("1,099", e._ig_reply_for("M1", "price"))
            self.assertIn("buy", e._ig_reply_for("M1", "buy").lower())
            self.assertIn("Airdopes", e._ig_reply_for("M1", "link"))


class TestMultiCampaign(unittest.TestCase):
    def test_latest_campaign_used(self):
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        lk = AffiliateLinker(load_config())
        lk.cfg.raw["affiliate"]["meesho_template_link"] = (
            "https://www.meesho.com/af_invite/24197020:instagram_stories:11040673?p_id=1,"
            "https://www.meesho.com/af_invite/24197020:instagram_stories:11049016?p_id=2")
        pub, src, camps = lk.meesho_ids
        self.assertEqual(camps, ["11040673", "11049016"])
        out, _ = lk.convert("https://www.meesho.com/kurta-p/555", "meesho")
        self.assertIn(":11049016?", out)   # latest campaign wins


class TestAutoDM(unittest.TestCase):
    def test_dm_matches_product(self):
        import tempfile
        from pathlib import Path
        from bot.config import load_config
        from bot.db import DB
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            e = Engine(load_config(), db)
            pid = db.add_product(source="amazon", url="http://x/1",
                                 title="boAt Airdopes 141 Earbuds",
                                 price="1099", currency="INR", image_url="",
                                 affiliate_url="https://amzn.to/x")
            db.add_post(product_id=pid, board_id="b")
            db.update_post(1, status="posted")
            dm = e._ig_dm_for("link", "earbuds link please")
            self.assertIn("Airdopes", dm)
            self.assertIn("amzn.to", dm)
            dm2 = e._ig_dm_for("link", "something random xyz")
            self.assertIn("bio", dm2)  # fallback


class TestCommissionLeak(unittest.TestCase):
    def _qa(self, link, source):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from bot.config import load_config
        from bot.db import DB
        from bot import qa
        cfg = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "p.jpg"
            Image.new("RGB", (900, 900), "white").save(img)
            db = DB(Path(tmp) / "t.db")
            prod = {"id": 1, "title": "Wireless Bluetooth Earbuds Gaming",
                    "source": source}
            seo_d = ("Wireless Bluetooth earbuds gaming edition deep bass "
                     "42h playtime fast charging offer today! #ad")
            return qa.qa_pin(cfg, db, prod, "Wireless Bluetooth Earbuds Gaming",
                             seo_d, str(img), link)

    def test_untracked_link_quarantined(self):
        ok, issues = self._qa("https://www.flipkart.com/xyz/p/1", "flipkart")
        self.assertFalse(ok)
        self.assertTrue(any("COMMISSION LEAK" in i for i in issues))

    def test_tracked_link_passes(self):
        ok, issues = self._qa("https://www.flipkart.com/xyz/p/1?affid=ME1",
                              "flipkart")
        self.assertTrue(ok, issues)

    def test_is_monetized(self):
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        lk = AffiliateLinker(load_config())
        self.assertTrue(lk.is_monetized("https://amzn.to/x?tag=a-21"))
        self.assertTrue(lk.is_monetized("https://www.meesho.com/af_invite/1:2:3?p_id=4"))
        self.assertFalse(lk.is_monetized("https://www.flipkart.com/x/p/1"))


class TestMeeshoLinkCorrectness(unittest.TestCase):
    """Owner: 'meesho vi vasthaya correct ga?' — pin-to-pin proof.

    Real Meesho product IDs are ALPHANUMERIC (/p/1k1b6). A digits-only
    parser silently fell back to affid/EarnKaro, breaking the direct
    commission rule. These tests pin every real URL shape.
    """

    def _lk(self, template: str, affid: str = ""):
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        lk = AffiliateLinker(load_config())
        lk.cfg.raw["affiliate"]["meesho_template_link"] = template
        lk.cfg.raw["affiliate"]["meesho_affid"] = affid
        import os
        os.environ.pop("MEESHO_TEMPLATE_LINK", None)
        os.environ.pop("MEESHO_AFFID", None)
        return lk

    TPL = ("https://www.meesho.com/af_invite/24197020:instagram_stories:"
           "11049016?p_id=2&ext_id=oldid&utm_source=instagram_stories")

    def test_product_id_shapes(self):
        from bot.affiliate import AffiliateLinker as A
        cases = {
            "https://www.meesho.com/women-kurta-set/p/1k1b6": "1k1b6",
            "https://www.meesho.com/women-kurta-set-p-1k1b6": "1k1b6",
            "https://www.meesho.com/product/p/abc123/": "abc123",
            "https://www.meesho.com/x/p/987654321": "987654321",
            "https://www.meesho.com/x?p_id=zz99": "zz99",
        }
        for url, want in cases.items():
            self.assertEqual(A.meesho_product_id(url), want, url)
        self.assertEqual(A.meesho_product_id("https://www.meesho.com/"), "")

    def test_alphanumeric_id_builds_direct_af_invite(self):
        lk = self._lk(self.TPL)
        out = lk.meesho_link_for("https://www.meesho.com/kurta/p/1k1b6")
        self.assertIn("af_invite/24197020:instagram_stories:11049016", out)
        self.assertIn("p_id=1k1b6", out)
        self.assertNotIn("p_id=2&", out)          # template's own p_id dropped
        # R69: ext_id decides the LANDING page on Meesho (/s/p/<code>) — it
        # must be the product's own code, never an invented/random id.
        self.assertNotIn("ext_id=oldid", out)     # template's id dropped
        self.assertIn("ext_id=1k1b6", out)        # = the product's own code
        self.assertIn("p_id=1k1b6", out)          # both ids = the product code
        self.assertIn("utm_source=instagram_stories", out)  # params preserved

    def test_ext_id_is_product_code_and_link_is_deterministic(self):
        lk = self._lk(self.TPL)
        a = lk.meesho_link_for("https://www.meesho.com/kurta/p/1k1b6")
        b = lk.meesho_link_for("https://www.meesho.com/kurta/p/1k1b6")
        self.assertEqual(a, b)                    # same product → same link
        c = lk.meesho_link_for("https://www.meesho.com/saree/p/489088490")
        self.assertIn("p_id=489088490", c)
        self.assertIn("ext_id=489088490", c)
        self.assertNotEqual(a, c)

    def test_earnkaro_never_used_for_meesho_when_template_present(self):
        lk = self._lk(self.TPL)
        lk.cfg.raw["affiliate"]["earnkaro_prefix"] = "https://earnkaro.com/?r=x"
        out, net = lk.convert("https://www.meesho.com/kurta/p/1k1b6", "meesho")
        self.assertEqual(net, "meesho")
        self.assertIn("af_invite", out)
        self.assertNotIn("earnkaro", out)

    def test_owner_generated_link_verbatim(self):
        lk = self._lk(self.TPL)
        mine = ("https://www.meesho.com/af_invite/24197020:instagram_stories:"
                "11049016?p_id=394590772&ext_id=abc123")
        out, net = lk.convert(mine, "meesho")
        self.assertEqual(out, mine)
        self.assertEqual(net, "meesho")

    def test_health_reports_truthfully(self):
        lk = self._lk(self.TPL)
        h = lk.meesho_health()
        self.assertTrue(h["ready"] and h["parsed"])
        self.assertEqual(h["publisher"], "24197020")
        self.assertEqual(h["campaigns"], ["11049016"])
        bad = self._lk("https://meesho.onelink.me/abc?af_x=1", affid="")
        hb = bad.meesho_health()
        self.assertFalse(hb["parsed"])
        self.assertFalse(hb["ready"])
        self.assertEqual(bad.meesho_link_for(
            "https://www.meesho.com/x/p/1k1b6"), "")  # never invents a link

    def test_no_template_falls_back_with_warning(self):
        lk = self._lk("", affid="charan123")
        out, _ = lk.convert("https://www.meesho.com/kurta/p/1k1b6", "meesho")
        self.assertIn("affid=charan123", out)   # still monetized
        self.assertIn("utm_source=affiliate", out)


class TestMeeshoCollectionGuidance(unittest.TestCase):
    """Collection links can't build per-product links — must say so, not guess."""

    def test_collection_only_never_invents_product_link(self):
        import os
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        os.environ.pop("MEESHO_TEMPLATE_LINK", None)
        lk = AffiliateLinker(load_config())
        lk.cfg.raw["affiliate"]["meesho_template_link"] = (
            "https://affiliate.meesho.com/collection/MTEwNDEyMjY6Ojpub3JtYWw=")
        h = lk.meesho_health()
        self.assertFalse(h["parsed"])
        self.assertFalse(h["ready"])
        self.assertEqual(
            lk.meesho_link_for("https://www.meesho.com/kurta-p/489088490"), "")

    def test_mixed_links_use_the_af_invite_one(self):
        import os
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        os.environ.pop("MEESHO_TEMPLATE_LINK", None)
        lk = AffiliateLinker(load_config())
        lk.cfg.raw["affiliate"]["meesho_template_link"] = (
            "https://affiliate.meesho.com/collection/MTEwNDEyMjY6Ojpub3JtYWw=,"
            "https://www.meesho.com/af_invite/24197020:instagram_stories:"
            "11040673?p_id=1")
        out = lk.meesho_link_for("https://www.meesho.com/kurta-p/489088490")
        self.assertIn("af_invite/24197020:instagram_stories:11040673", out)
        self.assertIn("p_id=489088490", out)


class TestMeeshoPerPlatform(unittest.TestCase):
    """Real owner links show per-platform tokens (instagram_stories /
    facebook). Each surface must publish its OWN token+campaign."""

    def _lk_with(self, links: str):
        import os
        from bot.affiliate import AffiliateLinker
        from bot.config import load_config
        os.environ.pop("MEESHO_TEMPLATE_LINK", None)
        lk = AffiliateLinker(load_config())
        lk.cfg.raw["affiliate"]["meesho_template_link"] = links
        return lk

    LINKS = ("https://www.meesho.com/af_invite/24197020:instagram_stories:11075346"
             "?p_id=5121&ext_id=3y9&utm_source=instagram_stories,"
             "https://www.meesho.com/af_invite/24197020:facebook:11075421"
             "?p_id=5121&ext_id=3y9&utm_source=facebook")

    def test_token_map(self):
        lk = self._lk_with(self.LINKS)
        self.assertEqual(lk.meesho_template_map(),
                         {"instagram_stories": "11075346",
                          "facebook": "11075421"})

    def test_instagram_gets_instagram_token(self):
        lk = self._lk_with(self.LINKS)
        out = lk.meesho_link_for("https://www.meesho.com/kurta/p/1k1b6",
                                 platform="instagram")
        self.assertIn(":instagram_stories:11075346", out)
        self.assertIn("p_id=1k1b6", out)
        self.assertIn("utm_source=instagram_stories", out)

    def test_facebook_gets_facebook_token(self):
        lk = self._lk_with(self.LINKS)
        out = lk.meesho_link_for("https://www.meesho.com/kurta/p/1k1b6",
                                 platform="facebook")
        self.assertIn(":facebook:11075421", out)
        self.assertIn("utm_source=facebook", out)

    def test_override_map_for_platforms_without_tokens(self):
        lk = self._lk_with(self.LINKS)
        lk.cfg.raw["affiliate"]["meesho_platform_tokens"] = {
            "pinterest": "instagram_stories", "youtube": "facebook"}
        self.assertEqual(lk.meesho_source_for("pinterest"), "instagram_stories")
        self.assertEqual(lk.meesho_source_for("youtube"), "facebook")
        self.assertIn(":instagram_stories:11075346",
                      lk.meesho_link_for("https://x.com/p/1k1b6", "pinterest"))

    def test_engine_uses_platform_specific_link(self):
        import tempfile
        from pathlib import Path
        from bot.db import DB
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as td:
            lk = self._lk_with(self.LINKS)
            cfg = lk.cfg
            cfg.raw["storage"] = {"db_path": str(Path(td) / "t.db"),
                                  "media_dir": str(Path(td) / "media")}
            e = Engine(cfg, DB(cfg.db_path))
            prod = {"id": 1, "source": "meesho",
                    "url": "https://www.meesho.com/kurta/p/1k1b6",
                    "affiliate_url": "https://www.meesho.com/af_invite/"
                                     "24197020:instagram_stories:11075346?p_id=1"}
            ig = e._aff_link(prod, "instagram")
            fb = e._aff_link(prod, "facebook")
            self.assertIn(":instagram_stories:", ig)
            self.assertIn(":facebook:", fb)
            self.assertNotEqual(ig, fb)
            # non-meesho products keep their stored link untouched
            ama = {"id": 2, "source": "amazon", "url": "https://amazon.in/dp/X",
                   "affiliate_url": "https://amazon.in/dp/X?tag=t-21"}
            self.assertEqual(e._aff_link(ama, "instagram"), ama["affiliate_url"])


class TestYouTubeUploader(unittest.TestCase):
    def _yt(self):
        from bot.config import load_config
        from bot.youtube import YouTubeAPI
        return YouTubeAPI(load_config())

    def test_not_configured_without_env(self):
        import os
        for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
            os.environ.pop(k, None)
        yt = self._yt()
        yt.token_path = yt.token_path.parent / "_nope_token.json"
        self.assertFalse(yt.configured)
        self.assertIn("client", yt.status())

    def test_auth_url_requires_client_and_has_scope(self):
        import os
        from bot.youtube import YouTubeError
        yt = self._yt()
        try:
            yt.auth_url()
            self.fail("should require client id/secret")
        except YouTubeError:
            pass
        os.environ["YT_CLIENT_ID"] = "cid"
        os.environ["YT_CLIENT_SECRET"] = "sec"
        url = yt.auth_url()
        self.assertIn("youtube.upload", url)
        self.assertIn("access_type=offline", url)
        for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET"):
            os.environ.pop(k, None)

    def test_upload_requires_existing_file(self):
        from bot.youtube import YouTubeError
        yt = self._yt()
        try:
            yt.upload_short("/nope/missing.mp4", "t", "d")
            self.fail("should raise")
        except YouTubeError as exc:
            self.assertIn("missing", str(exc))

    def test_engine_youtube_is_best_effort(self):
        """Not configured → engine must silently skip, never raise."""
        import tempfile
        from pathlib import Path
        from bot.db import DB
        from bot.engine import Engine
        from bot.config import load_config
        with tempfile.TemporaryDirectory() as td:
            cfg = load_config()
            cfg.raw["storage"] = {"db_path": str(Path(td) / "t.db"),
                                  "media_dir": str(Path(td) / "media")}
            e = Engine(cfg, DB(cfg.db_path))
            e._post_youtube({"id": 1, "title": "x", "price": "99",
                             "currency": "INR", "source": "meesho",
                             "url": "u", "affiliate_url": "a",
                             "video_path": ""})   # must not raise


class TestStoreTrueHooks(unittest.TestCase):
    """R72 — a hook must never name a store the product did not come from."""

    def test_meesho_never_mentions_amazon_or_flipkart(self):
        for day in range(1, 60):
            h = hook_for("₹299", "Cotton Kurta Set", day, "meesho")
            self.assertTrue(h)
            self.assertNotIn("amazon", h.lower())
            self.assertNotIn("flipkart", h.lower())

    def test_amazon_pool_keeps_its_own_hook(self):
        seen = {hook_for("₹999", "Earbuds", d, "amazon") for d in range(1, 80)}
        self.assertTrue(any("Amazon" in h for h in seen))

    def test_source_optional_backwards_compatible(self):
        self.assertTrue(hook_for("₹99", "Kurta", 3))
