"""Unit tests for the critical engines (affiliate links, SEO, DB, designer).

Run:  .venv/bin/python -m pytest tests/ -q      (or  python -m unittest style below)
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.affiliate import AffiliateLinker, price_label  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.db import DB  # noqa: E402
from bot.engine import build_seo_text  # noqa: E402
from bot.scraper import detect_source  # noqa: E402


def make_cfg(**over) -> Config:
    raw = {
        "affiliate": {
            "amazon_tag": "mydeals-21",
            "meesho_affid": "MEESH123",
            "flipkart_affid": "",
            "earnkaro_prefix": "https://ekaro.in/enkr20240101s123456",
            "cuelinks_template": "",
            "generic_template": "",
            "default_wrapper": "earnkaro",
        },
        "seo": {"hashtags": True, "max_hashtags": 6, "extra_hashtags": ["#deals"],
                "description_template": "{title} | {price} | {hashtags}"},
    }
    raw.update(over)
    return Config(raw=raw)


class TestSourceDetect(unittest.TestCase):
    def test_sources(self):
        self.assertEqual(detect_source("https://www.amazon.in/dp/B0123456789"), "amazon")
        self.assertEqual(detect_source("https://amzn.in/B0123456789"), "amazon")
        self.assertEqual(detect_source("https://www.meesho.com/x/p/a1"), "meesho")
        self.assertEqual(detect_source("https://www.flipkart.com/p?pid=ABC"), "flipkart")
        self.assertEqual(detect_source("https://shop.example.com/x"), "other")


class TestAffiliate(unittest.TestCase):
    def setUp(self):
        self.l = AffiliateLinker(make_cfg())

    def test_amazon_tag_added(self):
        url = "https://www.amazon.in/dp/B08N2Z7R1L?ref=sr_1_1"
        out, net = self.l.convert(url, utm=False)
        self.assertEqual(net, "amazon")
        self.assertEqual(out, "https://www.amazon.in/dp/B08N2Z7R1L?tag=mydeals-21")

    def test_utm_tracking_added(self):
        out, _ = self.l.convert("https://www.amazon.in/dp/B08N2Z7R1L")
        self.assertIn("utm_source=pinterest", out)
        self.assertIn("tag=mydeals-21", out)

    def test_amazon_gp_product(self):
        out, _ = self.l.convert("https://www.amazon.in/gp/product/B0ABCDEFGH/")
        self.assertIn("/dp/B0ABCDEFGH", out)
        self.assertIn("tag=mydeals-21", out)

    def test_amazon_old_tag_replaced(self):
        out, _ = self.l.convert("https://www.amazon.in/dp/B08N2Z7R1L?tag=someone-else")
        self.assertEqual(out.count("tag="), 1)
        self.assertIn("tag=mydeals-21", out)

    def test_meesho_affid(self):
        out, net = self.l.convert("https://www.meesho.com/cool-kurta/p/xyz1")
        self.assertEqual(net, "meesho")
        self.assertIn("affid=MEESH123", out)
        self.assertIn("utm_source=affiliate", out)

    def test_other_wrapped_earnkaro(self):
        out, net = self.l.convert("https://shop.example.com/product/42")
        self.assertEqual(net, "wrapped")
        self.assertTrue(out.startswith("https://ekaro.in/enkr20240101s123456?url="))
        self.assertIn("https%3A%2F%2Fshop.example.com%2Fproduct%2F42", out)


class TestPriceLabel(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(price_label("₹1,099"), "₹1,099")
        self.assertEqual(price_label("1099.00", "INR"), "₹1,099")
        self.assertEqual(price_label("$49.99", "USD"), "USD 49.99")
        self.assertEqual(price_label(""), "")


class TestSEO(unittest.TestCase):
    def test_description(self):
        cfg = make_cfg()
        txt = build_seo_text(cfg, "Wireless Bluetooth Earbuds", "1099", "INR", "amazon")
        self.assertIn("Wireless Bluetooth Earbuds", txt)
        self.assertIn("₹1,099", txt)
        self.assertTrue(any(h in txt for h in ("#viral", "#trending", "#deals")))
        self.assertIn("#ad #affiliate", txt)     # mandatory disclosure
        self.assertNotIn("##", txt)              # no malformed hashtags


class TestDB(unittest.TestCase):
    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(Path(tmp) / "t.db")
            pid = db.add_product(source="amazon", url="https://a.in/dp/X", title="T",
                                 affiliate_url="https://a.in/dp/X?tag=x", seo_text="s")
            self.assertTrue(db.url_exists("https://a.in/dp/X"))
            self.assertEqual(len(db.pending_products()), 1)
            db.update_product(pid, status="posted")
            self.assertEqual(db.stats()["posted"], 1)
            db.log("INFO", "hello")
            self.assertEqual(db.recent_logs()[0]["message"], "hello")
            db.add_post(product_id=pid, pin_id="123", status="posted")
            self.assertEqual(db.recent_posts()[0]["title"], "T")


class TestDesigner(unittest.TestCase):
    def test_pin_generated(self):
        from PIL import Image, ImageDraw
        from bot.pin_designer import PinDesigner
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(raw={"design": {"brand_name": "Test", "width": 500, "height": 750}})
            img = Image.new("RGB", (400, 400), (200, 30, 30))
            ImageDraw.Draw(img).ellipse([50, 50, 350, 350], fill=(250, 200, 100))
            src = Path(tmp) / "p.jpg"
            img.save(src)
            out = Path(tmp) / "pin.jpg"
            PinDesigner(cfg).create(str(src), "Sample Product Title For Testing", "₹999", out, "amazon")
            self.assertTrue(out.exists())
            with Image.open(out) as im:
                self.assertEqual(im.size, (500, 750))


if __name__ == "__main__":
    unittest.main(verbosity=2)
