"""Radar (usefulness scoring) + playbook (2026 content rules) tests.

Radar decides WHICH products deserve the account's posting slots, so a bug
here quietly fills the queue with junk. Playbook decides what the captions
say, so a bug here posts a broken hook to YouTube/Instagram.
Both are deterministic and offline by design — these tests lock that in.
"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from bot import playbook as pb
from bot import radar
from bot.config import Config
from bot.db import DB


class TestUsefulness(unittest.TestCase):
    def test_problem_solver_beats_random(self):
        good, _ = radar.usefulness(
            {"title": "Kitchen Storage Organizer Rack Foldable", "price": "399"})
        meh, _ = radar.usefulness({"title": "Random Plastic Toy Big",
                                   "price": "1999"})
        self.assertGreater(good, meh)
        self.assertGreaterEqual(good, 55)

    def test_impulse_price_boost(self):
        base = {"title": "Women Kurta Set Designer"}
        cheap, _ = radar.usefulness({**base, "price": "599"})
        rich, _ = radar.usefulness({**base, "price": "9999"})
        self.assertGreater(cheap, rich)

    def test_repeat_purchase_scores(self):
        serum, _ = radar.usefulness({"title": "Vitamin C Face Serum 30ml",
                                     "price": "449"})
        self.assertGreaterEqual(serum, 50)

    def test_festival_offseason_is_penalised(self):
        import datetime as _dt
        if radar._season_ahead("christmas santa cap xmas tree", 45):
            self.skipTest("festival is currently within 45 days")
        off, _ = radar.usefulness({"title": "Christmas Santa Cap", "price": "149"})
        self.assertLess(off, 40)

    def test_social_proof_rewards(self):
        base = {"title": "Cotton Bedsheet Double King", "price": "699"}
        plain, _ = radar.usefulness(base)
        loved, _ = radar.usefulness(base, rating=4.4, reviews=5200)
        self.assertGreater(loved, plain)

    def test_never_raises_on_junk(self):
        for junk in ({}, {"title": ""}, {"title": "x", "price": None},
                     {"title": "y", "price": "abc"}, None):
            score, why = radar.usefulness(junk or {})
            self.assertIsInstance(score, int)
            self.assertIsInstance(why, list)
            self.assertLessEqual(score, 100)

    def test_rank_sorted_and_explained(self):
        rows = radar.rank([
            {"id": 1, "title": "Random Plastic Toy Big", "price": "1999"},
            {"id": 2, "title": "Kitchen Storage Organizer Rack", "price": "399"},
            {"id": 3, "title": "Women Kurta Set Designer", "price": "599"},
        ])
        self.assertEqual(rows[0]["id"], 2)
        self.assertTrue(rows[0]["why"])
        scores = [r["usefulness"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_top_picks_respects_threshold(self):
        picks = radar.top_picks([
            {"id": 1, "title": "Kitchen Storage Organizer Rack", "price": "399"},
            {"id": 2, "title": "Random Plastic Toy Big", "price": "1999"},
        ], n=5, min_score=55)
        ids = [p["id"] for p in picks]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)


class TestRadarView(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(raw={
            "storage": {"db_path": f"{self.tmp}/t.db", "media_dir": f"{self.tmp}/m"},
            "radar": {"min_score": 40},
        })
        self.db = DB(self.cfg.db_path)

    def test_view_empty_db(self):
        view = radar.radar_view(self.cfg, self.db)
        self.assertEqual(view["queued"], [])
        self.assertTrue(view["notes"])

    def test_view_ranks_queue(self):
        self.db.add_product(source="meesho", url="u1", affiliate_url="a",
                            title="Kitchen Storage Organizer Rack", price="399")
        self.db.add_product(source="meesho", url="u2", affiliate_url="a",
                            title="Random Plastic Toy Big", price="1999")
        view = radar.radar_view(self.cfg, self.db)
        self.assertEqual(len(view["queued"]), 2)
        self.assertIn("organizer", view["queued"][0]["title"].lower())

    def test_view_never_raises_without_db(self):
        class Broken:
            def all_products(self, limit=100):
                raise RuntimeError("db gone")
        view = radar.radar_view(self.cfg, Broken())
        self.assertEqual(view["best"], [])
        self.assertTrue(any("db read failed" in n for n in view["notes"]))

    def test_hunt_survives_blocked_network(self):
        """Discovery failing must return [] — never break the autopilot."""
        class FakeEngine:
            class scraper:
                @staticmethod
                def discover_products(*a, **k):
                    raise RuntimeError("blocked")
                @staticmethod
                def polite_wait():
                    pass

            class db:
                @staticmethod
                def url_exists(url):
                    return False

                @staticmethod
                def log(*a, **k):
                    pass
        added = radar.radar_hunt(self.cfg, FakeEngine(), n=2)
        self.assertEqual(added, [])


class TestPlaybook(unittest.TestCase):
    def test_hook_never_empty(self):
        for title in ("", "x", "Kitchen Storage Organizer Rack",
                      "!!!", "Women Kurta Set Designer"):
            line = pb.hook_line(title, "₹499", seed=1)
            self.assertTrue(line.strip())

    def test_hook_is_deterministic_with_seed(self):
        a = pb.hook_line("Makeup Holder Box", "₹299", seed=7)
        b = pb.hook_line("Makeup Holder Box", "₹299", seed=7)
        self.assertEqual(a, b)

    def test_pain_detection(self):
        self.assertTrue(pb.pain_for("Kitchen Storage Rack"))
        self.assertEqual(pb.pain_for("Random Widget"), "")

    def test_shorts_script_caps_at_three_products(self):
        items = [{"title": f"Product {i}", "price": "499", "source": "meesho"}
                 for i in range(6)]
        plan = pb.shorts_script(items, seed=3)
        self.assertEqual(plan["max_products"], 3)
        self.assertEqual(len(plan["beats"]), 3)
        self.assertTrue(plan["hook"])
        self.assertTrue(plan["pinned_comment"])
        self.assertTrue(3 <= len(plan["hashtags"]) <= 5)

    def test_shorts_script_empty_is_safe(self):
        plan = pb.shorts_script([], seed=1)
        self.assertEqual(plan["beats"], [])
        self.assertEqual(plan["hook"], "")

    def test_ig_carousel_hook_first_and_save_cta(self):
        items = [{"title": f"Item {i}", "price": "599"} for i in range(5)]
        plan = pb.ig_carousel_plan(items, seed=2)
        self.assertEqual(plan["slides"][0], plan["slide1"])
        self.assertIn("#ad", plan["caption"])
        self.assertIn("Save", plan["caption"])
        self.assertGreaterEqual(plan["slide_count"], 3)

    def test_ig_carousel_slide_target(self):
        items = [{"title": f"Item {i}", "price": "599"} for i in range(10)]
        plan = pb.ig_carousel_plan(items, seed=4)
        lo, hi = pb.IG_CAROUSEL_SLIDES
        self.assertLessEqual(plan["slide_count"], hi + 1)

    def test_best_windows(self):
        self.assertTrue(pb.in_best_window("pinterest", 21))
        self.assertTrue(pb.in_best_window("instagram", 12))
        self.assertTrue(pb.in_best_window("youtube", 18))
        self.assertTrue(pb.in_best_window("unknown-platform", 15))  # default
        self.assertFalse(pb.in_best_window("pinterest", 3))

    def test_onscreen_text_short_lines(self):
        cards = pb.onscreen_text("Kitchen Storage Organizer Rack", "₹399")
        self.assertTrue(cards)
        self.assertTrue(all(len(c) <= 30 for c in cards))

    def test_title_line_always_fits_youtube(self):
        """Regression: hook titles used to reach 103 chars -> 400 upload fail."""
        long_title = ("Every time you hunt for the same thing every morning you "
                      "lose time you never get back premium quality extra large")
        for title in (long_title, "x", "", "Kitchen Storage Organizer Rack"):
            line = pb.title_line(title, "₹399", "meesho")
            self.assertLessEqual(len(line) + len(" #Shorts"), 100, line)

    def test_report_mentions_core_rules(self):
        text = pb.report()
        for token in ("3 products", "Carousel", "hook"):
            self.assertIn(token.lower(), text.lower())


class TestEngineUsesPlaybook(unittest.TestCase):
    """The wiring must survive: hooks/hashtags reach the posted caption."""

    def test_youtube_description_built_from_playbook(self):
        from bot.engine import Engine
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(raw={
            "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "posting": {"platform_order": ["pinterest"]},
            "youtube": {"enabled": True},
        })
        Path(tmp / "m").mkdir(parents=True, exist_ok=True)
        db = DB(cfg.db_path)
        eng = Engine(cfg, db)

        posted = {}

        class FakeYT:
            enabled = True
            configured = True

            def __init__(self, *a, **k):
                pass

            def upload_short(self, video, title, desc, tags=None):
                posted["title"] = title
                posted["desc"] = desc
                posted["tags"] = tags
                return "vid-1"

            def comment_on_video(self, vid, text):
                posted["comment"] = text
                return "c-1"

        import bot.youtube as yt_mod
        orig = yt_mod.YouTubeAPI
        yt_mod.YouTubeAPI = FakeYT
        try:
            video = Path(tmp) / "m" / "reel.mp4"
            video.write_bytes(b"\x00" * 2048)
            eng._post_youtube({
                "id": 7, "title": "Kitchen Storage Organizer Rack Foldable",
                "price": "399", "currency": "INR", "source": "meesho",
                "video_path": str(video),
                "affiliate_url": "https://www.meesho.com/af_invite/x?p_id=1k1b6",
            })
        finally:
            yt_mod.YouTubeAPI = orig
        self.assertTrue(posted.get("title", "").strip())
        self.assertIn("kitchen", posted.get("title", "").lower())
        # +8 for the uploader's " #Shorts" suffix must stay inside 100 chars
        self.assertLessEqual(len(posted.get("title", "")) + 8, 100)
        self.assertIn("under", posted.get("title", "").lower())
        self.assertIn("Buy here", posted.get("desc", ""))
        self.assertTrue(3 <= len(posted.get("tags", [])) <= 8)
        self.assertIn("comment", posted)
        self.assertIn("p_id=1k1b6", posted.get("comment", ""))


if __name__ == "__main__":
    unittest.main()


class TestHookLearning(unittest.TestCase):
    """Clicks must actually steer tomorrow's hooks (explore/exploit)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(raw={
            "storage": {"db_path": f"{self.tmp}/t.db", "media_dir": f"{self.tmp}/m"},
            "posting": {"platform_order": ["pinterest"]},
        })
        Path(self.tmp / "m").mkdir(parents=True, exist_ok=True)
        self.db = DB(self.cfg.db_path)

    def _seed_posts(self, hook: str, n: int, clicks: int) -> None:
        for i in range(n):
            pid = self.db.add_product(
                source="meesho", url=f"https://m/{hook}{i}/p/1k1b{i}",
                affiliate_url="a", title=f"Item {hook} {i}", price="599",
                status="posted")
            self.db.update_product(pid, hook=hook)
            for _ in range(clicks):
                self.db.log_click(pid, "ua")

    def test_performance_aggregates_clicks(self):
        self._seed_posts("pas", 3, 5)
        self._seed_posts("list", 3, 1)
        perf = self.db.hook_performance(min_samples=3)
        self.assertEqual(perf["pas"]["clicks"], 15)
        self.assertEqual(perf["pas"]["cpc"], 5.0)
        self.assertLess(perf["list"]["cpc"], perf["pas"]["cpc"])

    def test_min_samples_ignores_lucky_single(self):
        self._seed_posts("pov", 1, 40)
        perf = self.db.hook_performance(min_samples=3)
        self.assertNotIn("pov", perf)

    def test_pick_archetype_explores_then_exploits(self):
        import random as _r
        rng = _r.Random(11)
        counts = {}
        for _ in range(400):
            a = pb.pick_archetype({"pas": {"posts": 10, "clicks": 80, "cpc": 8.0}},
                                  rng)
            counts[a] = counts.get(a, 0) + 1
        self.assertGreater(counts.get("pas", 0), 150)          # exploits
        self.assertTrue(counts.get("list", 0) > 0)             # still explores
        self.assertTrue(counts.get("pov", 0) > 0)

    def test_pick_archetype_never_raises(self):
        for perf in (None, {}, {"pas": {}}, {"weird": {"cpc": "abc"}}):
            self.assertIn(pb.pick_archetype(perf, __import__("random").Random(1)),
                          pb.ARCHETYPES)

    def test_engine_picks_and_records_hook(self):
        from bot.engine import Engine
        eng = Engine(self.cfg, self.db)
        hook = eng._pick_hook()
        self.assertIn(hook, ("pas", "list", "pov", "auto"))

    def test_hook_column_migrates_on_old_db(self):
        import sqlite3
        old = Path(self.tmp) / "old.db"
        c = sqlite3.connect(old)
        c.execute("""CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     source TEXT DEFAULT '', url TEXT DEFAULT '',
                     affiliate_url TEXT DEFAULT '', title TEXT DEFAULT '',
                     price TEXT DEFAULT '', currency TEXT DEFAULT 'INR',
                     image_url TEXT DEFAULT '', image_path TEXT DEFAULT '',
                     pin_image TEXT DEFAULT '', video_url TEXT DEFAULT '',
                     status TEXT DEFAULT 'queued', error TEXT DEFAULT '',
                     created_at TEXT DEFAULT '')""")
        c.commit(); c.close()
        db = DB(old)
        cols = [r[1] for r in sqlite3.connect(old).execute("PRAGMA table_info(products)")]
        self.assertIn("hook", cols)
        self.assertIn("claim_ts", cols)


class TestRadarSurfaces(unittest.TestCase):
    """/api/radar must show the brain, and never 500 on an empty install."""

    def _client(self, seed=False):
        from bot.dashboard import create_app
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(raw={
            "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"},
            "radar": {"min_score": 40},
        })
        Path(tmp / "m").mkdir(parents=True, exist_ok=True)
        db = DB(cfg.db_path)
        if seed:
            for i, (hook, clicks) in enumerate(
                    [("pas", 6), ("pas", 5), ("pas", 4), ("list", 1), ("list", 2),
                     ("list", 0)]):
                pid = db.add_product(
                    source="meesho", url=f"u{i}", affiliate_url="a",
                    title=f"Kitchen Storage Organizer Rack {i}", price="399",
                    status="posted")
                db.update_product(pid, hook=hook)
                for _ in range(clicks):
                    db.log_click(pid, "ua")
            db.add_product(source="meesho", url="q1", affiliate_url="a",
                           title="Random Plastic Toy", price="1999")
        return create_app(cfg, db).test_client()

    def test_radar_api_empty_install(self):
        r = self._client().get("/api/radar")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["best"], [])
        self.assertTrue(body["notes"])

    def test_radar_api_reports_hooks_and_best(self):
        body = self._client(seed=True).get("/api/radar").get_json()
        self.assertIn("pas", body["hooks"])
        self.assertGreater(body["hooks"]["pas"]["cpc"], body["hooks"]["list"]["cpc"])
        self.assertTrue(body["best"])
        self.assertLessEqual(body["best"][0]["usefulness"], 100)
        self.assertTrue(body["best"][0]["why"])

    def test_dashboard_renders_radar_tab(self):
        html = self._client().get("/").data.decode()
        self.assertIn('data-tab="radar"', html)
        self.assertIn("refreshRadar", html)


class TestHuntIsTimeBounded(unittest.TestCase):
    """A dead store must never stall the run loop (real bug: 200s hunts)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = Config(raw={
            "storage": {"db_path": f"{self.tmp}/t.db", "media_dir": f"{self.tmp}/m"},
            "radar": {"min_score": 40, "budget_seconds": 30},
            "autopilot": {"discover_limit": 4},
        })
        Path(self.tmp / "m").mkdir(parents=True, exist_ok=True)
        self.db = DB(self.cfg.db_path)

    def test_dead_network_aborts_within_a_few_calls(self):
        """net_down after 2 failures → hunt gives up, does not grind all niches."""
        calls = {"n": 0}

        class DeadScraper:
            net_failures = 0

            @property
            def net_down(self):
                return self.net_failures >= 2

            def discover_products(self, store, limit=4, query=""):
                calls["n"] += 1
                self.net_failures += 1
                return []

        class Eng:
            scraper = DeadScraper()
            db = self.db

            def ingest_url(self, url, prefetched=None):
                return 0

        import time as _t
        t0 = _t.monotonic()
        added = radar.radar_hunt(self.cfg, Eng(), n=2)
        self.assertEqual(added, [])
        self.assertLessEqual(calls["n"], 3)              # stopped early
        self.assertLess(_t.monotonic() - t0, 5.0)        # no backoff grind

    def test_budget_stops_a_slow_but_alive_store(self):
        class SlowScraper:
            net_failures = 0
            net_down = False

            def discover_products(self, store, limit=4, query=""):
                import time as _t
                _t.sleep(0.35)
                return []

        class Eng:
            scraper = SlowScraper()
            db = self.db

        import time as _t
        t0 = _t.monotonic()
        radar.radar_hunt(self.cfg, Eng(), n=2, budget_seconds=1)
        self.assertLess(_t.monotonic() - t0, 3.0)

    def test_discovery_uses_fast_fail_fetch(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "scraper.py").read_text()
        self.assertIn("_fetch(page, retries=0)", src)    # no 12s backoff in discovery
        self.assertIn("def net_down", src)


class TestRadarHuntJob(unittest.TestCase):
    """Panel "Hunt now": background, guarded, never hangs the browser."""

    def _client(self):
        from bot.dashboard import create_app
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(raw={
            "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"},
            "radar": {"min_score": 40, "hunt_count": 2, "budget_seconds": 5},
        })
        Path(tmp / "m").mkdir(parents=True, exist_ok=True)
        return create_app(cfg, DB(cfg.db_path)).test_client()

    def test_hunt_runs_in_background_and_reports(self):
        import bot.radar as R
        calls = {"n": 0}

        def fake_hunt(cfg, engine, n=3, min_score=40):
            calls["n"] += 1
            return [{"title": "Kitchen Storage Organizer", "usefulness": 62,
                     "product_id": 1}]

        orig = R.radar_hunt
        R.radar_hunt = fake_hunt
        try:
            c = self._client()
            r = c.post("/api/radar/hunt")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json()["running"])
            for _ in range(40):
                st = c.get("/api/radar/hunt/status").get_json()
                if not st["running"]:
                    break
                time.sleep(0.05)
            self.assertFalse(st["running"])
            self.assertEqual(st["added"], 1)
            self.assertEqual(st["best"], 62)
            self.assertEqual(calls["n"], 1)
        finally:
            R.radar_hunt = orig

    def test_double_click_does_not_start_twice(self):
        import bot.radar as R
        started = {"n": 0}

        def slow_hunt(cfg, engine, n=3, min_score=40):
            started["n"] += 1
            time.sleep(0.4)
            return []

        orig = R.radar_hunt
        R.radar_hunt = slow_hunt
        try:
            c = self._client()
            first = c.post("/api/radar/hunt").get_json()
            second = c.post("/api/radar/hunt").get_json()
            self.assertTrue(first["running"])
            self.assertTrue(second["running"])           # second click acknowledged
            self.assertIn("already", second["message"].lower())
            for _ in range(40):
                if not c.get("/api/radar/hunt/status").get_json()["running"]:
                    break
                time.sleep(0.05)
            self.assertEqual(started["n"], 1)
        finally:
            R.radar_hunt = orig

    def test_hunt_failure_is_reported_not_raised(self):
        import bot.radar as R

        def boom(*a, **k):
            raise RuntimeError("stores exploded")

        orig = R.radar_hunt
        R.radar_hunt = boom
        try:
            c = self._client()
            c.post("/api/radar/hunt")
            for _ in range(40):
                st = c.get("/api/radar/hunt/status").get_json()
                if not st["running"]:
                    break
                time.sleep(0.05)
            self.assertIn("stores exploded", st["error"])
        finally:
            R.radar_hunt = orig
