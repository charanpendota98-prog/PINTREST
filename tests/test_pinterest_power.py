"""Pinterest power-layer tests: media upload, carousel, sections, analytics,
trends, rich-pin meta and the engine wiring around them — all mocked, no
network. These are the 'top-level advanced' features the owner asked for."""
import json
import tempfile
import unittest
from pathlib import Path

from bot.config import load_config
from bot.db import DB
from bot.pinterest_api import PinterestAPI, PinterestError


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestPinterestMediaUpload(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.cfg.raw["pinterest"]["access_token"] = "tok"
        self.api = PinterestAPI(self.cfg)
        self.tmp = tempfile.TemporaryDirectory()
        self.img = Path(self.tmp.name) / "pin.jpg"
        self.img.write_bytes(b"\xff\xd8\xff fake jpeg bytes")
        self.vid = Path(self.tmp.name) / "reel.mp4"
        self.vid.write_bytes(b"\x00\x00\x00 fake mp4")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_request(self, method, path, **kw):
        self.calls.append((method, path, kw))
        if path == "/media" and method == "POST":
            return {"media_id": "M123", "upload_url": "https://s3/put",
                    "upload_parameters": {"key": "k", "sig": "s"}}
        if path.startswith("/media/M123"):
            return {"status": "succeeded"}
        if path == "/pins":
            return {"id": "PIN1", "board_id": kw["json"]["board_id"]}
        raise AssertionError(f"unexpected {method} {path}")

    def test_upload_media_v5_flow(self):
        import bot.pinterest_api as mod
        orig_post, orig_put = mod.requests.post, mod.requests.put
        mod.requests.post = lambda url, **kw: FakeResp(204)
        mod.requests.put = lambda url, **kw: FakeResp(204)
        try:
            self.api._request = self._fake_request
            mid = self.api.upload_media(str(self.img), "image")
        finally:
            mod.requests.post, mod.requests.put = orig_post, orig_put
        self.assertEqual(mid, "M123")
        self.assertIn(("POST", "/media", {"json": {"media_type": "image"}}),
                      [(m, p, k) for m, p, k in self.calls])

    def test_register_refused_falls_back_for_video(self):
        def boom(method, path, **kw):
            if path == "/media":
                raise PinterestError("403 not available")
            if path == "/videos":
                raise PinterestError("legacy also refused")
            raise AssertionError(path)
        self.api._request = boom
        with self.assertRaises(PinterestError):
            self.api.upload_media(str(self.vid), "video")

    def test_create_image_pin_prefers_uploaded_image_id(self):
        self.api._request = self._fake_request
        self.api.upload_image = lambda p: "M123"      # pretend upload worked
        pin = self.api.create_image_pin("B1", "https://link", "T" * 130, "desc",
                                        image_path=str(self.img))
        self.assertEqual(pin["id"], "PIN1")
        body = [k["json"] for m, p, k in self.calls if p == "/pins"][0]
        self.assertEqual(body["media_source"],
                         {"source_type": "image_id", "media_id": "M123"})
        # first item's title is trimmed by the API layer
        self.assertEqual(len(body["title"]), 100)

    def test_create_image_pin_base64_fallback(self):
        self.cfg.raw["pinterest"]["upload_images"] = False
        self.api._request = self._fake_request
        self.api.create_image_pin("B1", "https://link", "T", "d",
                                  image_path=str(self.img))
        body = [k["json"] for m, p, k in self.calls if p == "/pins"][0]
        self.assertEqual(body["media_source"]["source_type"], "image_base64")
        self.assertTrue(body["media_source"]["data"])

    def test_carousel_pin_body(self):
        self.api._request = self._fake_request
        items = [{"url": f"https://cdn/{i}.jpg", "title": f"T{i}"}
                 for i in range(3)]
        self.api.create_carousel_pin("B1", items, "https://link", "Title", "Desc")
        body = [k["json"] for m, p, k in self.calls if p == "/pins"][0]
        ms = body["media_source"]
        self.assertEqual(ms["source_type"], "multiple_image_urls")
        self.assertEqual(len(ms["items"]), 3)
        self.assertEqual(ms["items"][0]["link"], "https://link")

    def test_carousel_needs_two_images(self):
        self.api._request = self._fake_request
        with self.assertRaises(PinterestError):
            self.api.create_carousel_pin("B1", [{"url": "u"}], "l", "t", "d")

    def test_video_pin_passes_alt_and_section(self):
        self.api._request = self._fake_request
        self.api.create_video_pin("B1", "M9", "link", "t", "d",
                                  alt_text="alt", board_section_id="S1")
        body = [k["json"] for m, p, k in self.calls if p == "/pins"][0]
        self.assertEqual(body["media_source"],
                         {"source_type": "video_id", "media_id": "M9"})
        self.assertEqual(body["alt_text"], "alt")
        self.assertEqual(body["board_section_id"], "S1")

    def test_schedule_guard_max_14_days(self):
        from datetime import datetime, timedelta, timezone
        self.api._request = self._fake_request
        with self.assertRaises(PinterestError):
            self.api.create_image_pin(
                "B1", "l", "t", "d", image_path=str(self.img),
                scheduled_for=datetime.now(timezone.utc) + timedelta(days=20))

    def test_sections_created_once(self):
        def fake(method, path, **kw):
            if path.endswith("/sections") and method == "GET":
                return {"items": []}
            if path.endswith("/sections") and method == "POST":
                return {"id": "SEC1", "name": kw["json"]["name"]}
            raise AssertionError(path)
        self.api._request = fake
        self.assertEqual(self.api.ensure_section("B1", "Kurtas"), "SEC1")

    def test_sections_failure_is_silent(self):
        def fake(method, path, **kw):
            raise PinterestError("403 no section access")
        self.api._request = fake
        self.assertEqual(self.api.ensure_section("B1", "Kurtas"), "")

    def test_pin_analytics_parses_both_shapes(self):
        def fake(method, path, **kw):
            if "summary_metrics" in (kw.get("params") or {}) or True:
                return {"IMPRESSION": 1200, "SAVE": 30, "PIN_CLICK": 12,
                        "OUTBOUND_CLICK": 5,
                        "summary_metrics": [
                            {"metric_type": "SAVE", "value": 31}]}
        self.api._request = fake
        m = self.api.pin_analytics("P1", days=7)
        self.assertEqual(m["impression"], 1200)
        self.assertEqual(m["outbound_click"], 5)
        self.assertEqual(m["save"], 31)      # summary_metrics override

    def test_trends_top_parses(self):
        def fake(method, path, **kw):
            self.assertIn("/trends/keywords/IN/top/growing", path)
            return {"trends": [{"keyword": "korean dress"},
                               {"keyword": "home decor"}]}
        self.api._request = fake
        out = self.api.trends_top(region="IN", trend_type="growing")
        self.assertEqual([t["keyword"] for t in out],
                         ["korean dress", "home decor"])


class TestEnginePinterestPower(unittest.TestCase):
    def _engine(self, tmp):
        from bot.engine import Engine
        cfg = load_config()
        cfg.raw["storage"] = {"db_path": str(Path(tmp) / "t.db"),
                              "media_dir": str(Path(tmp) / "media")}
        cfg.raw["pinterest"]["access_token"] = "tok"
        return Engine(cfg, DB(cfg.db_path))

    def test_gallery_urls_dedup_and_cap(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._engine(td)
            prod = {"images": "https://a/1.jpg,https://a/2.jpg",
                    "image_url": "https://a/1.jpg"}
            urls = e._gallery_urls(prod)
            self.assertEqual(urls, ["https://a/1.jpg", "https://a/2.jpg"])
            prod2 = {"images": ",".join(f"https://a/{i}.jpg" for i in range(9)),
                     "image_url": ""}
            self.assertEqual(len(e._gallery_urls(prod2)), 5)

    def test_sections_off_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._engine(td)
            self.assertEqual(e._section_for("B1", {"title": "Kurta"}), "")

    def test_pin_performance_disabled_and_unconfigured(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._engine(td)
            e.cfg.raw["pinterest"]["analytics"] = False
            self.assertEqual(e.pin_performance()["checked"], 0)
            e.cfg.raw["pinterest"]["analytics"] = True
            e.api.ensure_access_token = lambda: ""   # not configured
            self.assertEqual(e.pin_performance().get("checked"), 0)

    def test_pin_performance_stores_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            e = self._engine(td)
            pid = e.db.add_product(source="meesho", url="u", affiliate_url="a",
                                   title="Women Kurta", status="posted")
            e.db.add_post(product_id=pid, board_id="b")
            e.db.update_post(1, status="posted", pin_id="PP1",
                             posted_at="2020-01-01T00:00:00+00:00")
            type(e.api).configured = property(lambda self: True)
            e.api.pin_analytics = lambda pin_id, days=7: {
                "impression": 900, "save": 20, "pin_click": 9,
                "outbound_click": 4}
            res = e.pin_performance(limit=5)
            self.assertEqual(res["checked"], 1)
            m = e.db.latest_pin_metrics("PP1")
            self.assertEqual(m["impressions"], 900)
            self.assertEqual(m["outbound"], 4)
            self.assertIn(pid, e.db.engagement_by_product())

    def test_trends_cache_fallback_is_safe(self):
        from bot.trends import cached_keywords
        with tempfile.TemporaryDirectory() as td:
            cfg = load_config()
            cfg.raw["storage"] = {"db_path": str(Path(td) / "t.db"),
                                  "media_dir": str(Path(td) / "media")}
            cfg.raw["trends"] = {"live": False}
            self.assertEqual(cached_keywords(cfg), [])

    def test_landing_rich_pin_meta(self):
        from bot.dashboard import LANDING_HTML
        for key in ("product:price:amount", "product:price:currency",
                    "og:availability", "og:url", "twitter:card"):
            self.assertIn(key, LANDING_HTML)
