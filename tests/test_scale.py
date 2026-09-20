"""R48: scale engine — honest target math, auto-scale rails, store mix."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot import scale
from bot.config import Config
from bot.db import DB


def _cfg(tmp: Path, **extra) -> Config:
    raw = {
        "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
        "money": {"click_to_order": 0.02, "aov": 599, "confirm_days": 45,
                  "rates": {"meesho": 8, "amazon": 3, "flipkart": 5}},
        "target": {"monthly_commission": 100000, "months": 6,
                   "auto_scale": False, "ceiling_per_day": 30},
        "posting": {"pins_per_day": 8, "max_per_day": 25},
    }
    raw.update(extra)
    cfg = Config(raw=raw)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


def _post(db, clicks=0, days_ago=1, source="meesho"):
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    pid = db.add_product(source=source, url=f"u{when}{clicks}{source}",
                         affiliate_url="a", title="Kitchen Storage Organizer",
                         price="599", status="posted")
    db.add_post(product_id=pid, board_id="b", pin_id="p", status="posted",
                posted_at=when)
    for _ in range(clicks):
        db.log_click(pid, "ua")
    return pid


class TestFunnelMath(unittest.TestCase):
    def test_needs_are_monthly_not_divided_by_months(self):
        """Real bug guarded: dividing by the ramp months made ₹1L look 6x easier."""
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            f = scale.funnel(cfg)
            # 100000 / (599 * 6.2%) = ~2693 orders; /2% = ~134.6k clicks
            self.assertAlmostEqual(f["orders_per_month"], 2692.7, delta=5)
            self.assertAlmostEqual(f["clicks_per_month"], 134633, delta=400)
            self.assertAlmostEqual(f["clicks_per_day"], 4487.8, delta=20)
            self.assertEqual(f["ramp_months"], 6)     # shown as a runway only

    def test_target_override(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            self.assertAlmostEqual(scale.funnel(cfg, 50000)["clicks_per_day"],
                                   2243.9, delta=20)

    def test_blend_rate_uses_real_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), money={"rates": {"meesho": 12, "amazon": 12,
                                                 "flipkart": 12}})
            self.assertAlmostEqual(scale.blend_rate(cfg), 12.0, delta=0.01)

    def test_scenarios_match_funnel(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            f = scale.funnel(cfg)
            row = [r for r in scale.scenarios(cfg) if r["target"] == 100000][0]
            self.assertAlmostEqual(row["clicks_per_day"]["2%"],
                                   f["clicks_per_day"], delta=1)


class TestRunRateAndGap(unittest.TestCase):
    def test_measured_run_rate(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            for _ in range(10):
                _post(db, clicks=5, days_ago=1)
            rr = scale.run_rate(db, cfg, days=30)
            self.assertEqual(rr["posts"], 10)
            self.assertEqual(rr["clicks"], 50)
            self.assertAlmostEqual(rr["clicks_per_post"], 5.0)
            self.assertGreater(rr["monthly_projection"], 0)

    def test_gap_and_recommendation(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            g = scale.gap(cfg, db)
            self.assertEqual(g["percent"], 0.0)
            self.assertGreater(g["gap"], 0)
            rec = scale.recommend_posts_per_day(cfg, db)
            self.assertGreaterEqual(rec["suggested"], 1)
            self.assertLessEqual(rec["suggested"], rec["ceiling"])

    def test_recommendation_respects_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), target={"ceiling_per_day": 12,
                                        "monthly_commission": 100000},
                       posting={"pins_per_day": 8, "max_per_day": 25})
            db = DB(cfg.db_path)
            # measured 1 click per post → needs a huge volume → clamp at 12
            for _ in range(6):
                _post(db, clicks=1, days_ago=1)
            rec = scale.recommend_posts_per_day(cfg, db, base=8)
            self.assertEqual(rec["ceiling"], 12)
            self.assertEqual(rec["suggested"], 12)

    def test_no_data_keeps_configured_volume(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            rec = scale.recommend_posts_per_day(cfg, DB(cfg.db_path))
            self.assertEqual(rec["suggested"], 8)
            self.assertIn("no click data", rec["reason"])

    def test_eta_needs_growth(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            _post(db, clicks=10, days_ago=3)          # only one week of data
            self.assertIsNone(scale.eta_months(cfg, db))
            _post(db, clicks=50, days_ago=1)          # + prior week → growth
            _post(db, clicks=5, days_ago=10)
            eta = scale.eta_months(cfg, db)
            self.assertTrue(eta is None or eta >= 0)


class TestAutoScaleRails(unittest.TestCase):
    def test_off_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            self.assertEqual(scale.apply_autoscale(db, cfg), 0)
            self.assertEqual(scale.effective_per_day(db, cfg, 8), 8)

    def test_on_persists_and_is_ceiling_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), target={"auto_scale": True, "ceiling_per_day": 10,
                                        "monthly_commission": 100000})
            db = DB(cfg.db_path)
            for _ in range(6):
                _post(db, clicks=1, days_ago=1)
            applied = scale.apply_autoscale(db, cfg)
            self.assertEqual(applied, 10)                  # clamped
            self.assertEqual(scale.effective_per_day(db, cfg, 8), 10)
            # safety wins: with auto-scale ON the ceiling caps even a higher
            # manually configured volume (documented, logged as a change)
            self.assertEqual(scale.effective_per_day(db, cfg, 25), 10)

    def test_never_scales_below_configured(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), target={"auto_scale": True})
            db = DB(cfg.db_path)
            db.set_state(scale.STATE_KEY, "2")
            self.assertEqual(scale.effective_per_day(db, cfg, 8), 8)

    def test_junk_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), target={"auto_scale": True})
            db = DB(cfg.db_path)
            db.set_state(scale.STATE_KEY, "not-a-number")
            self.assertEqual(scale.effective_per_day(db, cfg, 8), 8)


class TestStoreMix(unittest.TestCase):
    def test_one_store_cannot_own_the_queue(self):
        self.assertFalse(scale.mix_ok("meesho",
                                      ["meesho"] * 5 + ["amazon"]))
        self.assertTrue(scale.mix_ok("meesho", ["meesho", "amazon", "flipkart"]))
        self.assertTrue(scale.mix_ok("meesho", ["meesho", "meesho"]))  # tiny q
        self.assertTrue(scale.mix_ok("", ["meesho"] * 5))
        # all one store → nothing better available → allow it
        self.assertTrue(scale.mix_ok("meesho", ["meesho"] * 6))

    def test_mix_report(self):
        rep = scale.mix_report([{"source": "meesho"}, {"source": "meesho"},
                                {"source": "amazon"}])
        self.assertEqual(rep["counts"]["meesho"], 2)
        self.assertAlmostEqual(rep["share"]["meesho"], 0.667, delta=0.01)
        self.assertEqual(scale.mix_report([])["counts"], {})


class TestScaleSurfaces(unittest.TestCase):
    def test_lines_are_honest(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            text = "\n".join(scale.lines(cfg, DB(cfg.db_path)))
            self.assertIn("TARGET", text)
            self.assertIn("not promises", text)
            self.assertIn("clicks/day", text)

    def test_cli_scale_runs(self):
        import io
        import contextlib
        from bot.main import cmd_scale
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_scale(cfg, []), 0)
            self.assertIn("TARGET", buf.getvalue())

    def test_api_scale(self):
        from bot.dashboard import create_app
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg.raw["dashboard"] = {"password": "", "secret_key": "t"}
            c = create_app(cfg, DB(cfg.db_path)).test_client()
            body = c.get("/api/scale").get_json()
            self.assertTrue(body["ok"])
            self.assertIn("target_monthly", body)
            self.assertTrue(body["lines"])
            self.assertIn("recommend", body)
            html = c.get("/").data.decode()
            self.assertIn("scTarget", html)

    def test_never_raises_on_broken_db(self):
        class Broken:
            def oldest_activity(self):
                raise RuntimeError("gone")

            def get_state(self, *a, **k):
                raise RuntimeError("gone")

        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            try:
                scale.gap(cfg, Broken())
            except Exception:
                self.fail("scale.gap must not raise on a broken db")


if __name__ == "__main__":
    unittest.main()
