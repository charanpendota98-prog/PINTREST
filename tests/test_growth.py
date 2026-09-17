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
        self.assertTrue(all(p.startswith("#") for p in parts))
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
