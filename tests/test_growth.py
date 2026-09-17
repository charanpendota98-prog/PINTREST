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
