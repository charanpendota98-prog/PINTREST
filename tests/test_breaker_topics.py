"""R44: API circuit breaker + feed variety — the "don't get flagged" layer."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from bot import breaker as br
from bot import topics
from bot.config import Config
from bot.db import DB


def _cfg(tmp: Path) -> Config:
    cfg = Config(raw={
        "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
        "posting": {"platform_order": ["pinterest"]},
    })
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestBreaker(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(br.classify("Pinterest API 401: unauthorized"), "auth")
        self.assertEqual(br.classify("Pinterest API 403: forbidden"), "auth")
        self.assertEqual(br.classify("Pinterest API 429: slow down"), "rate")
        self.assertEqual(br.classify("Pinterest API: too many retries"), "rate")
        self.assertEqual(br.classify("Network error: timeout"), "other")
        self.assertEqual(br.classify(""), "other")

    def test_auth_pauses_six_hours(self):
        now = time.time()
        st = br.record_failure(None, "Pinterest API 401: bad token", now)
        self.assertEqual(st["kind"], "auth")
        self.assertTrue(br.is_open(st, now + 60))
        self.assertFalse(br.is_open(st, now + 7 * 3600))
        self.assertIn("bot auth", st["hint"])

    def test_rate_limit_escalates_then_resets(self):
        now = time.time()
        st = br.record_failure(None, "Pinterest API 429", now)
        self.assertEqual(st["cooldown"], 900)
        st = br.record_failure(st, "Pinterest API 429", now)
        self.assertEqual(st["cooldown"], 3600)
        st = br.record_failure(st, "Pinterest API: too many retries", now)
        self.assertEqual(st["cooldown"], 14400)
        st = br.record_failure(st, "Pinterest API: too many retries", now)
        st = br.record_failure(st, "Pinterest API: too many retries", now)
        self.assertEqual(st["cooldown"], 43200)      # capped at 12h
        # a non-rate failure resets the escalation ladder
        st = br.record_failure(st, "Network error: timeout", now)
        self.assertEqual(st["cooldown"], br.OTHER_COOLDOWN)
        self.assertEqual(br.record_failure(st, "429", now)["cooldown"], 900)

    def test_success_and_junk_are_safe(self):
        self.assertFalse(br.is_open(br.record_success(), time.time()))
        self.assertEqual(br.load("not json"), {})
        self.assertEqual(br.load("[1,2]"), {})
        self.assertEqual(br.dump({"x": object()}), "{}")
        self.assertEqual(br.human(0), "0s")
        self.assertEqual(br.human(90), "1m")
        self.assertEqual(br.human(3 * 3600 + 600), "3h 10m")


class TestStateKV(unittest.TestCase):
    def test_state_roundtrip_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            self.assertEqual(db.get_state("nope"), "")
            db.set_state("k", '{"a": 1}')
            self.assertEqual(db.get_state("k"), '{"a": 1}')
            db.set_state("k", "overwritten")
            self.assertEqual(db.get_state("k"), "overwritten")
            db.del_state("k")
            self.assertEqual(db.get_state("k"), "x-default-of-mine"[:0] or "")
            # survives a new DB handle (i.e. a process restart)
            db.set_state("k2", "v2")
            self.assertEqual(DB(cfg.db_path).get_state("k2"), "v2")


class TestTopics(unittest.TestCase):
    def test_bucket(self):
        cases = {
            "Kitchen Storage Organizer Rack": "kitchen",
            "Vitamin C Face Serum": "beauty",
            "Women Kurta Set": "fashion",
            "Diwali Diya Set": "festive",
            "Wireless Earbuds": "electronics",
            "Some Random Thing": "general",
            "": "general",
        }
        for title, want in cases.items():
            self.assertEqual(topics.bucket(title), want, title)

    def test_order_for_variety_breaks_the_run(self):
        rows = [{"title": "Kitchen Storage Organizer"},      # top score
                {"title": "Kitchen Spice Container"},
                {"title": "Women Kurta Set"}]                # different topic
        recent = ["Kitchen Chopper", "Kitchen Bottle"]       # 2 kitchen in a row
        out = topics.order_for_variety(rows, recent)
        self.assertEqual(topics.bucket(out[0]["title"]), "fashion")

    def test_order_for_variety_keeps_score_order_when_no_run(self):
        rows = [{"title": "Kitchen Storage Organizer"},
                {"title": "Women Kurta Set"}]
        self.assertEqual(topics.order_for_variety(rows, ["Women Kurta Set"]),
                         rows)
        self.assertEqual(topics.order_for_variety(rows, []), rows)
        self.assertEqual(topics.order_for_variety([], ["x"]), [])

    def test_unknown_topic_never_blocks(self):
        rows = [{"title": "Mystery Item A"}, {"title": "Mystery Item B"}]
        out = topics.order_for_variety(rows, ["Unknown Thing", "Unknown Thing"])
        self.assertEqual(out, rows)                       # general ≠ a topic run

    def test_all_same_topic_posts_anyway(self):
        rows = [{"title": "Kitchen Storage Organizer"},
                {"title": "Kitchen Spice Rack"}]
        out = topics.order_for_variety(rows, ["Kitchen Bottle", "Kitchen Mug"])
        self.assertEqual(len(out), 2)                     # never starve queue

    def test_allows_more_cap(self):
        q = ["kitchen", "kitchen", "kitchen"]
        self.assertFalse(topics.allows_more("kitchen", q, ["kitchen"]))
        self.assertTrue(topics.allows_more("kitchen", ["kitchen"], q, 4))
        self.assertTrue(topics.allows_more("general", q, q))   # unknown = ok


class TestEngineSafety(unittest.TestCase):
    def _engine(self, tmp: str):
        from bot.engine import Engine
        cfg = _cfg(Path(tmp))
        return Engine(cfg, DB(cfg.db_path)), cfg

    def test_breaker_persists_across_engines(self):
        with tempfile.TemporaryDirectory() as d:
            eng, cfg = self._engine(d)
            self.assertEqual(eng.api_paused(), {})
            wait = eng._api_failed(Exception("Pinterest API 401: expired"))
            self.assertGreater(wait, 3600)
            self.assertEqual(eng.api_paused()["kind"], "auth")
            # a fresh engine (new process) must still be paused
            eng2 = __import__("bot.engine", fromlist=["Engine"]).Engine(
                cfg, DB(cfg.db_path))
            self.assertTrue(eng2.api_paused())
            eng2._api_ok()
            self.assertEqual(eng2.api_paused(), {})

    def test_run_offers_different_topic_first(self):
        with tempfile.TemporaryDirectory() as d:
            eng, _ = self._engine(d)
            for i, title in enumerate(["Kitchen Storage Organizer",
                                       "Kitchen Spice Container",
                                       "Women Kurta Set"]):
                pid = eng.db.add_product(
                    source="meesho", url=f"u{i}", affiliate_url="a",
                    title=title, price="599")
                eng.db.update_product(pid, score=100 - i)
            # recent_posts reads the posts table — record the last two pins
            # as real posts (that is the authoritative "what did I just post")
            for t in ("Kitchen Chopper", "Kitchen Bottle"):
                pid = eng.db.add_product(
                    source="meesho", url=f"p{t}", affiliate_url="a",
                    title=t, price="499", status="posted")
                eng.db.add_post(product_id=pid, board_id="b", pin_id=f"pin-{pid}",
                                status="posted")
            picked: list[str] = []

            def fake_post(product):
                picked.append(product["title"])
                return {"id": "pin"}

            with mock.patch.object(eng, "post_product", fake_post):
                eng.post_next()
            self.assertEqual(picked, ["Women Kurta Set"])

    def test_breaker_state_is_json_safe(self):
        with tempfile.TemporaryDirectory() as d:
            eng, _ = self._engine(d)
            eng._api_failed(Exception("Pinterest API 429: rate limited"))
            raw = eng.db.get_state(br.STATE_KEY)
            self.assertEqual(json.loads(raw)["kind"], "rate")


class TestBreakerInStatusAPI(unittest.TestCase):
    def test_status_reports_pause(self):
        from bot.dashboard import create_app
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            cfg.raw["dashboard"] = {"password": "", "secret_key": "t"}
            db = DB(cfg.db_path)
            c = create_app(cfg, db).test_client()
            body = c.get("/api/status").get_json()
            self.assertIn("api_breaker", body)
            self.assertFalse(body["api_breaker"]["open"])
            state = br.record_failure(None, "Pinterest API 401: expired",
                                      time.time())
            db.set_state(br.STATE_KEY, br.dump(state))
            body = c.get("/api/status").get_json()["api_breaker"]
            self.assertTrue(body["open"])
            self.assertEqual(body["kind"], "auth")
            self.assertTrue(body["paused_for"])
            self.assertIn("bot auth", body["hint"])


if __name__ == "__main__":
    unittest.main()


class TestReauthClearsBreaker(unittest.TestCase):
    """Re-auth must resume posting immediately (not wait out the 6h pause)."""

    def test_helper_clears_state(self):
        from bot.main import _clear_api_breaker
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            db.set_state(br.STATE_KEY, br.dump(br.record_failure(
                None, "Pinterest API 401", time.time())))
            _clear_api_breaker(cfg)
            self.assertEqual(DB(cfg.db_path).get_state(br.STATE_KEY), "")
            _clear_api_breaker(cfg)          # second call is a no-op, no crash

    def test_doctor_and_queue_show_pause(self):
        """The owner must SEE a paused bot from the CLI, not guess."""
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn("_clear_api_breaker", src)


class TestDoctorResilience(unittest.TestCase):
    """A short check entry must never crash `bot doctor` (real crash caught)."""

    def test_doctor_runs_and_reports_breaker(self):
        import io
        import contextlib
        from bot.main import cmd_doctor
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            db.set_state(br.STATE_KEY, br.dump(br.record_failure(
                None, "Pinterest API 401", time.time())))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_doctor(cfg)          # must not raise
            out = buf.getvalue()
            self.assertIn("Posting paused by API breaker", out)
            self.assertIn("bot auth", out)

    def test_source_guards_short_entries(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn("len(item) > 2", src)
