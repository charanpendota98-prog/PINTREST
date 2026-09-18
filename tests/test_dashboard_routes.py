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

    def test_dashboard_page_has_js_and_no_dupes(self):
        from pathlib import Path as P
        html = (P(__file__).resolve().parent.parent /
                "templates" / "index.html").read_text()
        self.assertIn("async function api(", html)
        # global fetch guard must exist (network error never breaks the UI)
        self.assertIn("catch(e){ return {ok:false, error:", html)

    def test_javascript_syntax_valid(self):
        """JS syntax must be valid — a duplicate `const` once killed the
        whole dashboard silently. node --check guards it forever."""
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path as P
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        html = (P(__file__).resolve().parent.parent /
                "templates" / "index.html").read_text()
        import re
        blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertTrue(blocks, "dashboard has no <script> block")
        with tempfile.NamedTemporaryFile("w", suffix=".js",
                                         delete=False) as fh:
            fh.write(blocks[-1])
            js_path = fh.name
        out = subprocess.run([node, "--check", js_path],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0,
                         f"JS syntax error: {out.stderr[:400]}")


if __name__ == "__main__":
    unittest.main()


class TestFrontendRobustness(unittest.TestCase):
    """Round-2 hardening: JS can never die, media can never 500,
    reels can never be silent."""

    def test_api_helper_never_throws(self):
        """The JS api() must catch both fetch and json failures."""
        from pathlib import Path as P
        html = (P(__file__).resolve().parent.parent /
                "templates" / "index.html").read_text()
        self.assertIn("catch(e){ return {ok:false, error:", html)
        self.assertEqual(html.count("const esc"), 1, "duplicate esc breaks JS")

    def test_broken_audio_falls_back_to_composed_bgm(self):
        import tempfile
        from pathlib import Path as P
        from bot.video_maker import music_usable, usable_or_auto_bgm
        with tempfile.TemporaryDirectory() as td:
            bad = P(td) / "corrupt.wav"
            bad.write_bytes(b"RIFFnot-really-audio")
            self.assertFalse(music_usable(str(bad)))
            cfg = make_cfg(td)
            fb = usable_or_auto_bgm(cfg, str(bad))
            self.assertTrue(fb, "no fallback BGM produced")
            self.assertTrue(music_usable(fb), "fallback BGM is not decodable")

    def test_pin_filename_is_seo_slug(self):
        """Pinterest indexes image filenames — must be keyword rich."""
        from bot.engine import Engine
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = make_cfg(td)
            e = Engine(cfg, DB(cfg.db_path))
            name = e.pin_filename("Women Floral Anarkali Kurta Set", "₹549")
            self.assertIn("women-floral-anarkali", name)
            self.assertIn("549", name)
            self.assertTrue(name.endswith(".jpg"))

    def test_landing_has_product_schema(self):
        from bot.dashboard import LANDING_HTML
        self.assertIn("og:title", LANDING_HTML)
        self.assertIn("schema.org", LANDING_HTML)
        self.assertIn("priceCurrency", LANDING_HTML)


class TestNoDummyPosting(unittest.TestCase):
    """Owner rule: NO dummy posting. Demo/sample data must be unpostable."""

    def test_looks_dummy_flags_seed_data(self):
        from bot.qa import looks_dummy
        for bad in ({"url": "https://www.meesho.com/x/p/demokurta"},
                    {"url": "https://www.flipkart.com/p/itmdemo123"},
                    {"url": "https://www.amazon.in/dp/B0CDEAR01"},
                    {"image_url": "https://example.com/img.jpg"},
                    {"title": "Sample Product"},  # normalised match
                    {"title": "Test Product Lorem"}):
            self.assertTrue(looks_dummy(bad), bad)

    def test_real_product_passes(self):
        from bot.qa import looks_dummy
        self.assertFalse(looks_dummy({
            "url": "https://www.meesho.com/women-kurta/p/8xk2m1",
            "title": "Women Yellow Floral Cotton Kurta Set",
            "image_url": "https://m.media-amazon.com/images/I/61abc.jpg"}))

    def test_qa_blocks_dummy_before_anything_else(self):
        from bot.qa import qa_pin
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = make_cfg(td)
            db = DB(cfg.db_path)
            ok, issues = qa_pin(cfg, db,
                                {"id": 1, "url": "https://x/p/demokurta",
                                 "title": "Demo Kurta Set", "source": "meesho"},
                                "Demo Kurta", "x" * 200,
                                str(Path(td) / "nope.jpg"), "https://x/y")
            self.assertFalse(ok)
            self.assertTrue(any("DUMMY PRODUCT" in i for i in issues), issues)

    def test_seed_demo_marks_status_demo(self):
        from pathlib import Path as P
        src = (P(__file__).resolve().parent.parent /
               "scripts" / "seed_demo.py").read_text()
        self.assertIn('status="demo"', src)

    def test_pending_queue_excludes_demo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            cfg = make_cfg(td)
            db = DB(cfg.db_path)
            db.add_product(source="meesho", url="u1", affiliate_url="a1",
                           title="t", status="demo")
            db.add_product(source="meesho", url="u2", affiliate_url="a2",
                           title="real one")
            pend = db.pending_products()
            self.assertEqual([p["url"] for p in pend], ["u2"])
