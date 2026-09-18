"""Concurrency & claim-safety tests.

The money-critical invariant in this repo: **one product is posted exactly
once**, no matter how many processes/threads/buttons are in play, and a
claimed product is NEVER stranded in `status='posting'`.

Two autopilots (or the scheduler + a dashboard "Post now" click) posting the
same product is a duplicate-pin spam signal — exactly what gets accounts
limited — so these tests are the account-safety net.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from bot.config import Config
from bot.db import DB
from bot.engine import Engine


def _cfg(tmp: str, **posting) -> Config:
    media = Path(tmp) / "media"
    media.mkdir(parents=True, exist_ok=True)
    raw = {
        "design": {"brand_name": "T", "width": 1000, "height": 1500},
        "storage": {"media_dir": str(media), "db_path": str(Path(tmp) / "t.db")},
        "posting": {"platform_order": ["pinterest"], "pins_per_product": 1,
                    "manual_gap_seconds": 0, **posting},
        "keyword_mining": {"live": False},
        "keywords": {"live": False},
    }
    return Config(raw=raw)


GOOD_DESC = ("Beautiful women kurta set designer for daily wear, office and "
             "party — soft fabric, easy wash, best price today. #ad")


def _warm_keyword_cache(db: DB) -> None:
    """Pre-fill the autocomplete cache so tests never touch the network."""
    import json
    import time as _t
    with db._conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS keywords (
                         term TEXT PRIMARY KEY,
                         suggestions TEXT NOT NULL,
                         ts REAL NOT NULL)""")
        for term in ("women kurta", "women"):
            c.execute("INSERT OR REPLACE INTO keywords(term, suggestions, ts) "
                      "VALUES(?,?,?)",
                      (term, json.dumps(["women kurta set designer",
                                         "women kurta design"]), _t.time()))


def _seed(db: DB, tmp: str, n: int = 6, prefix: str = "race") -> str:
    _warm_keyword_cache(db)
    img = Path(tmp) / "media" / "p.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    if not img.exists():
        Image.new("RGB", (1000, 1500), "white").save(img)
    for i in range(n):
        db.add_product(
            source="meesho", url=f"https://www.meesho.com/{prefix}{i}/p/1k1b{100 + i}",
            affiliate_url="https://www.meesho.com/af_invite/24197020:"
                          f"instagram_stories:11075346?p_id=1k1b{100 + i}",
            title=f"Women Kurta Set Designer {i}", price="599", currency="INR",
            image_url="https://cdn.example/1.jpg", image_path=str(img),
            pin_image=str(img), seo_text=GOOD_DESC, score=9 - i, status="queued")
    return str(img)


class FakePinterest:
    """Records what was posted; never touches the network."""

    configured = True
    posts: list = []

    def __init__(self, *a, **k):
        pass

    def ensure_board(self, name, desc=""):
        return "board-1"

    def ensure_section(self, board_id, name, desc=""):
        return "section-1"

    def upload_image(self, path):
        return "image-1"

    def create_image_pin(self, **kw):
        FakePinterest.posts.append(kw.get("title", ""))
        return {"id": "pin-1"}

    def create_carousel_pin(self, **kw):
        FakePinterest.posts.append(kw.get("title", ""))
        return {"id": "pin-1"}


class TestAtomicClaim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _cfg(self.tmp)
        self.db = DB(self.cfg.db_path)
        _warm_keyword_cache(self.db)

    def test_claim_is_exclusive(self):
        _seed(self.db, self.tmp, n=1)
        pid = self.db.all_products(limit=1)[0]["id"]
        self.assertTrue(self.db.claim_product(pid))
        self.assertFalse(self.db.claim_product(pid), "second claim must fail")
        self.assertEqual(self.db.all_products(limit=1)[0]["status"], "posting")

    def test_stale_claim_recovered_fresh_claim_kept(self):
        _seed(self.db, self.tmp, n=2)
        rows = self.db.all_products(limit=5)
        fresh, stale = rows[0]["id"], rows[1]["id"]
        self.db.claim_product(fresh)
        self.db.claim_product(stale)
        self.db.update_product(stale, claim_ts="2000-01-01T00:00:00+00:00")
        rescued = self.db.release_stale_claims(older_than_minutes=20)
        self.assertEqual(rescued, 1)
        by_id = {r["id"]: r for r in self.db.all_products(limit=5)}
        self.assertEqual(by_id[fresh]["status"], "posting")   # in-flight kept
        self.assertEqual(by_id[stale]["status"], "queued")    # stale rescued

    def test_engine_startup_rescues_stranded_rows(self):
        _seed(self.db, self.tmp, n=1)
        pid = self.db.all_products(limit=1)[0]["id"]
        self.db.claim_product(pid)
        self.db.update_product(pid, claim_ts="2000-01-01T00:00:00+00:00")
        Engine(self.cfg, self.db)          # construction runs the rescue
        self.assertEqual(self.db.all_products(limit=1)[0]["status"], "queued")


class TestNoDoublePost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = _cfg(self.tmp)
        self.db = DB(self.cfg.db_path)
        FakePinterest.posts = []
        self.engine = Engine(self.cfg, self.db)
        self.engine.api = FakePinterest()

    def test_post_product_twice_posts_once(self):
        _seed(self.db, self.tmp, n=1)
        product = self.db.all_products(limit=1)[0]
        first = self.engine.post_product(product)
        second = self.engine.post_product(dict(product))   # stale dict, same id
        self.assertIsNotNone(first)
        self.assertIsNone(second, "second worker must not post a duplicate")
        self.assertEqual(len(FakePinterest.posts), 1)
        self.assertEqual(len(self.db.recent_posts(limit=10)), 1)

    def test_batch_posts_each_product_once(self):
        _seed(self.db, self.tmp, n=4)
        pins = self.engine.post_batch(4, human_gaps=False, quick_gap=0)
        self.assertEqual(len(pins), 4)
        rows = self.db.recent_posts(limit=20)
        pids = [r["product_id"] for r in rows]
        self.assertEqual(len(pids), len(set(pids)), "duplicate post rows!")

    def test_claim_released_when_pinterest_fails(self):
        """No credentials -> clean failure, row back in the queue, no strand."""
        _seed(self.db, self.tmp, n=1)
        real = Engine(self.cfg, self.db)     # real (unconfigured) PinterestAPI
        from bot.pinterest_api import PinterestError
        with self.assertRaises(PinterestError):
            real.post_next()
        row = self.db.all_products(limit=1)[0]
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["claim_ts"], "")

    def test_claim_released_on_unexpected_error(self):
        """A raw bug in the API client must not strand the product forever."""
        _seed(self.db, self.tmp, n=1)

        class Boom(FakePinterest):
            def ensure_board(self, name, desc=""):
                raise RuntimeError("simulated SDK bug")

        self.engine.api = Boom()
        with self.assertRaises(RuntimeError):
            self.engine.post_next()
        row = self.db.all_products(limit=1)[0]
        self.assertEqual(row["status"], "queued")
        self.assertEqual(row["claim_ts"], "")
        self.assertEqual(len(self.db.recent_posts(limit=5)), 0)

    def test_quick_batch_is_fast(self):
        """Manual posting must not sleep the 40-minute human gap."""
        _seed(self.db, self.tmp, n=3)
        t0 = time.time()
        self.engine.post_batch(3, human_gaps=False, quick_gap=0)
        self.assertLess(time.time() - t0, 5, "manual batch waited like autopilot")


def _mp_worker(db_path: str, media: str, tag: int, out) -> None:
    """Top-level (picklable) worker for the multi-process race test."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    cfg = _cfg(str(Path(db_path).parent))
    cfg.raw["storage"] = {"db_path": db_path, "media_dir": media}
    db = DB(db_path)
    _warm_keyword_cache(db)
    engine = Engine(cfg, db)
    engine.api = FakePinterest()
    posted = []
    for _ in range(3):
        try:
            pin = engine.post_next()
            if pin:
                posted.append(pin.get("id"))
        except Exception:                     # noqa: BLE001
            break
    out.put((tag, len(posted)))


class TestMultiProcessRace(unittest.TestCase):
    """Five OS processes raid one queue: every product posted exactly once."""

    def test_race_has_no_duplicates(self):
        try:
            ctx = mp.get_context("fork")
        except ValueError:                    # pragma: no cover - non-posix
            self.skipTest("fork start method unavailable")
        tmp = tempfile.mkdtemp()
        cfg = _cfg(tmp)
        db = DB(cfg.db_path)
        media = _seed(db, tmp, n=6)
        db.log("INFO", "race seed ready")

        out = ctx.Queue()
        procs = [ctx.Process(target=_mp_worker,
                             args=(cfg.db_path, media, i, out))
                 for i in range(5)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=90)
        results = []
        while not out.empty():
            results.append(out.get())
        db2 = DB(cfg.db_path)
        rows = db2.recent_posts(limit=50)
        pids = [r["product_id"] for r in rows]
        self.assertEqual(len(pids), len(set(pids)),
                         f"a product was posted twice! results={results}")
        self.assertEqual(len(pids), 6, f"expected exactly 6 posts, got {len(pids)}")
        stranded = [p for p in db2.all_products(limit=20)
                    if p["status"] == "posting"]
        self.assertEqual(stranded, [], "product stranded in 'posting'")


if __name__ == "__main__":
    unittest.main()


class TestManualPostJob(unittest.TestCase):
    """Panel 'Post now' must never hang a browser tab and never double-burst."""

    def setUp(self):
        import bot.dashboard as dash
        self.dash = dash
        self.tmp = tempfile.mkdtemp()
        self.cfg = _cfg(self.tmp)
        self.cfg.raw.setdefault("dashboard", {}).update(
            {"password": "", "secret_key": "t"})
        self.db = DB(self.cfg.db_path)
        _warm_keyword_cache(self.db)
        _seed(self.db, self.tmp, n=3)
        import bot.engine as eng
        self._dash_api, self._eng_api = dash.PinterestAPI, eng.PinterestAPI
        dash.PinterestAPI = eng.PinterestAPI = FakePinterest   # no network
        self.app = dash.create_app(self.cfg, self.db)
        self.c = self.app.test_client()

    def tearDown(self):
        import bot.engine as eng
        self.dash.PinterestAPI = self._dash_api
        eng.PinterestAPI = self._eng_api

    def _wait(self, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            st = self.c.get("/api/post/status").get_json()
            if not st.get("running"):
                return st
            time.sleep(0.1)
        return {"running": True, "timeout": True}

    def test_post_now_returns_immediately(self):
        t0 = time.time()
        r = self.c.post("/api/post", json={"count": 2})
        elapsed = time.time() - t0
        self.assertEqual(r.status_code, 200)
        self.assertLess(elapsed, 2.0, "panel click blocked the browser")
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertIn("background", body["message"])
        st = self._wait()
        self.assertEqual(st["done"], 2)
        self.assertFalse(st["error"])

    def test_second_click_does_not_start_second_burst(self):
        self.c.post("/api/post", json={"count": 3})
        second = self.c.post("/api/post", json={"count": 3}).get_json()
        self.assertIn("not started", second["message"])
        st = self._wait()
        self.assertEqual(st["done"], 3)
        pids = [r["product_id"] for r in self.db.recent_posts(limit=20)]
        self.assertEqual(len(pids), len(set(pids)), "double burst posted twice!")

    def test_status_endpoint_shape(self):
        st = self.c.get("/api/post/status").get_json()
        self.assertTrue(st["ok"])
        for key in ("running", "done", "total", "error"):
            self.assertIn(key, st)

    def test_count_validation(self):
        self.assertEqual(self.c.post("/api/post", json={"count": "junk"}).status_code, 400)
        self.c.post("/api/post", json={"count": 999})      # clamped, not a crash
        st = self._wait()
        self.assertLessEqual(st.get("done", 0), 10)
