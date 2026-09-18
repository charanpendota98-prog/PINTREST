"""Pin-to-pin robustness: EVERY frontend page & API endpoint must respond
without a 5xx crash — the owner demanded 'frontend & backend em fail avvodu'."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from bot.config import Config
from bot.dashboard import create_app
from bot.db import DB


def make_cfg(tmp: str) -> Config:
    return Config(raw={
        "design": {"brand_name": "T", "width": 500, "height": 750},
        "storage": {"media_dir": str(Path(tmp) / "media"),
                    "db_path": str(Path(tmp) / "t.db")},
        "link": {"bridge": False, "public_base": "", "landing": True,
                 "whatsapp_share": False},
        "affiliate": {"amazon_tag": "t-21", "meesho_affid": "",
                      "meesho_template_link": "", "meesho_collection_link": "",
                      "earnkaro_prefix": "", "cuelinks_template": "",
                      "generic_template": ""},
        "seo": {"max_hashtags": 4,
                "description_template": "{title} | {price} | {hashtags}"},
        "instagram": {"enabled": False, "triggers": {"link": "x"}},
        "facebook": {"enabled": False},
        "roundup": {"enabled": True, "count": 3},
    })


class TestAllRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = make_cfg(cls.tmp.name)
        cls.db = DB(cls.cfg.db_path)
        img = Path(cls.tmp.name) / "media" / "pin_demo.jpg"
        img.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (700, 900), "white").save(img)
        pid = cls.db.add_product(
            source="amazon", url="https://www.amazon.in/dp/B0T1",
            affiliate_url="https://www.amazon.in/dp/B0T1?tag=t-21",
            title="Test Kurta Set Women", price="499", currency="INR",
            image_url="https://x/i.jpg", image_path=str(img),
            pin_image=str(img), seo_text="test seo #ad", score=5, discount=20)
        cls.db.add_post(product_id=pid, board_id="b")
        cls.db.update_post(1, status="posted", pin_id="P1")
        cls.db.log_click(pid, "ua")
        cls.app = create_app(cls.cfg, cls.db).test_client()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def get_ok(self, path, html=False):
        r = self.app.get(path)
        self.assertLess(r.status_code, 500, f"{path} → {r.status_code}")
        return r

    def test_frontend_pages(self):
        for path in ["/", "/deals/today", "/go/1", "/go/999999"]:
            r = self.get_ok(path)
            self.assertIn(r.status_code, (200, 404))

    def test_go_landing_has_schema(self):
        r = self.app.get("/go/1")
        self.assertIn(b"schema.org", r.data)
        self.assertIn(b"og:title", r.data)

    def test_api_reads(self):
        for path in ["/api/status", "/api/products", "/api/posts",
                     "/api/logs", "/api/analytics"]:
            r = self.app.get(path)
            self.assertEqual(r.status_code, 200, path)
            json.loads(r.data)  # must be valid JSON

    def test_subscribe(self):
        r = self.app.post("/subscribe/1", data={"email": "a@b.co"})
        self.assertLess(r.status_code, 500)

    def test_upload_audio_video(self):
        wav = io.BytesIO(b"RIFFfakewavdata")
        r = self.app.post("/api/upload-audio",
                          data={"file": (wav, "t.wav")},
                          content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.data)
        mp4 = io.BytesIO(b"\x00fakevideo")
        r = self.app.post("/api/upload-video",
                          data={"file": (mp4, "t.mp4")},
                          content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200, r.data)
        # wrong type rejected cleanly
        r = self.app.post("/api/upload-audio",
                          data={"file": (io.BytesIO(b"x"), "t.exe")},
                          content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_add_manual_requires_fields(self):
        r = self.app.post("/api/add-manual",
                          data=json.dumps({"title": "x"}),
                          content_type="application/json")
        self.assertEqual(r.status_code, 400)  # clean JSON error, no crash

    def test_skip_and_post_guard(self):
        r = self.app.post("/api/products/1/skip")
        self.assertEqual(r.status_code, 200)
        r = self.app.post("/api/post", data=json.dumps({"count": 1}),
                          content_type="application/json")
        # no pinterest creds → clean 400, never 500
        self.assertEqual(r.status_code, 400, r.data)

    def test_unknown_route_json(self):
        r = self.app.get("/nope/nothing")
        self.assertEqual(r.status_code, 404)
        json.loads(r.data)

    def test_media_missing_file(self):
        r = self.app.get("/media/does_not_exist.jpg")
        self.assertIn(r.status_code, (404, 200))
        self.assertLess(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
