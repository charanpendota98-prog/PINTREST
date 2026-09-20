"""IG carousel list post — money path, faked APIs (once a day, hook first)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.config import Config
from bot.db import DB
from bot.engine import Engine
from bot.instagram import InstagramError


class _FakeIG:
    enabled = True
    configured = True

    def __init__(self):
        self.posted: list[tuple[list[str], str]] = []
        self.hosting_ok = True

    def upload_imgbb(self, path: str) -> str:
        return f"https://img/{Path(path).name}" if self.hosting_ok else ""

    def upload_catbox(self, path: str) -> str:
        return f"https://cat/{Path(path).name}" if self.hosting_ok else ""

    def post_carousel(self, urls: list[str], caption: str) -> str:
        self.posted.append((list(urls), caption))
        return "media-123"


class _FakeDesigner:
    def design_roundup(self, items, title, out_path) -> str:
        Path(out_path).write_bytes(b"jpg")
        return str(out_path)


class TestIgListPost(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(raw={
            "storage": {"db_path": f"{self.tmp}/t.db",
                        "media_dir": f"{self.tmp}/m"},
            "instagram": {"list_count": 6, "enabled": True},
            "posting": {"platform_order": ["instagram"]},
        })
        (self.tmp / "m").mkdir(parents=True, exist_ok=True)
        self.db = DB(self.cfg.db_path)
        self.eng = Engine(self.cfg, self.db)
        self.ig = _FakeIG()
        self.eng.ig = self.ig
        self.eng.designer = _FakeDesigner()

    def _seed(self, n: int, with_images: bool = True) -> None:
        titles = ["Kitchen Storage Organizer Rack", "Women Kurta Set Cotton",
                  "Vitamin C Face Serum 30ml", "Diwali Diya Decoration Set",
                  "Wireless Earbuds Pro", "Silicone Spatula Set"]
        for i in range(n):
            img = self.tmp / f"p{i}.jpg"
            img.write_bytes(b"jpg")
            pid = self.db.add_product(
                source="meesho", url=f"u{i}", affiliate_url="a",
                title=titles[i % len(titles)], price="599",
                status="posted")
            if with_images:
                self.db.update_product(pid, image_path=str(img))

    def test_posts_once_with_hook_first_and_disclosure(self):
        self._seed(6)
        media = self.eng.post_ig_list()
        self.assertEqual(media, "media-123")
        urls, caption = self.ig.posted[0]
        self.assertGreaterEqual(len(urls), 3)             # hook + products
        self.assertTrue(urls[0].startswith("https://"))   # slide 1 hosted hook
        self.assertIn("#ad", caption.lower())             # affiliate disclosure
        self.assertLessEqual(len(caption), 2200)

    def test_second_call_same_day_is_skipped(self):
        self._seed(6)
        self.eng.post_ig_list()
        self.assertIsNone(self.eng.post_ig_list())        # once a day
        self.assertEqual(len(self.ig.posted), 1)

    def test_too_few_products_skips(self):
        self._seed(2)
        self.assertIsNone(self.eng.post_ig_list())
        self.assertEqual(self.ig.posted, [])

    def test_hosting_failure_is_reported_not_raised(self):
        self._seed(6)
        self.ig.hosting_ok = False
        self.assertIsNone(self.eng.post_ig_list())
        self.assertEqual(self.ig.posted, [])

    def test_instagram_api_error_never_propagates(self):
        self._seed(6)

        def boom(urls, caption):
            raise InstagramError("graph api down")

        self.ig.post_carousel = boom
        self.assertIsNone(self.eng.post_ig_list())        # logged, not raised

    def test_products_without_images_are_ignored(self):
        self._seed(6, with_images=False)
        self.assertIsNone(self.eng.post_ig_list())


if __name__ == "__main__":
    unittest.main()
