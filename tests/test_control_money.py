"""R45: owner control, money health, earnings, report — all new surfaces."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from bot import control, earnings, health, report
from bot.config import Config
from bot.db import DB


def _cfg(tmp: Path, **extra) -> Config:
    raw = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
           "posting": {"max_per_day": 5, "quiet_hours": "0-6"},
           "money": {"click_to_order": 0.02, "aov": 599, "confirm_days": 45},
           "dashboard": {"password": "", "secret_key": "t"}}
    raw.update(extra)
    cfg = Config(raw=raw)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


def _post(db, source="meesho", clicks=0, posted_at="2026-09-18T10:00:00",
          status="posted"):
    pid = db.add_product(source=source, url=f"u{time.time()}{clicks}",
                         affiliate_url="a", title="Kitchen Storage Organizer",
                         price="599", status=status)
    db.add_post(product_id=pid, board_id="b", pin_id="p", status=status,
                posted_at=posted_at)
    for _ in range(clicks):
        db.log_click(pid, "ua")
    return pid


class TestQuietHours(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(control.parse_quiet_hours("0-6"), (0, 6))
        self.assertEqual(control.parse_quiet_hours("23-7"), (23, 7))
        self.assertEqual(control.parse_quiet_hours("5-5"), (0, 0))   # disabled
        self.assertEqual(control.parse_quiet_hours(""), (0, 0))
        self.assertEqual(control.parse_quiet_hours("junk"), (0, 0))

    def test_in_quiet_hours(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            self.assertTrue(control.in_quiet_hours(cfg, 2))
            self.assertTrue(control.in_quiet_hours(cfg, 0))
            self.assertFalse(control.in_quiet_hours(cfg, 6))
            self.assertFalse(control.in_quiet_hours(cfg, 14))

    def test_wrapping_window(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), posting={"quiet_hours": "23-7"})
            self.assertTrue(control.in_quiet_hours(cfg, 23))
            self.assertTrue(control.in_quiet_hours(cfg, 3))
            self.assertFalse(control.in_quiet_hours(cfg, 12))


class TestKillSwitch(unittest.TestCase):
    def test_pause_resume_persist(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            self.assertEqual(control.is_paused(db), {})
            control.pause(db, "bad batch")
            state = control.is_paused(db)
            self.assertTrue(state["paused"])
            self.assertEqual(state["reason"], "bad batch")
            # survives a fresh handle (process restart)
            self.assertTrue(control.is_paused(DB(cfg.db_path)))
            self.assertTrue(control.resume(DB(cfg.db_path)))
            self.assertEqual(control.is_paused(db), {})
            self.assertFalse(control.resume(db))       # nothing to resume

    def test_auto_resume_after_until(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            control.pause(db, "short", until_ts=time.time() + 60)
            self.assertTrue(control.is_paused(db))
            self.assertEqual(control.is_paused(db, now=time.time() + 120), {})
            self.assertEqual(db.get_state(control.PAUSE_KEY), "")  # cleaned up

    def test_human_pause(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            control.pause(db, "selling spree", until_ts=time.time() + 600)
            self.assertIn("selling spree", control.human_pause(control.is_paused(db)))
            self.assertEqual(control.human_pause({}), "")


class TestDailyCapAndGate(unittest.TestCase):
    def test_daily_cap(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            for _ in range(5):
                _post(db)
            capped, posted, cap = control.cap_reached(db, cfg)
            self.assertEqual((posted, cap), (5, 5))
            self.assertTrue(capped)

    def test_cap_disabled_when_zero(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), posting={"max_per_day": 0})
            db = DB(cfg.db_path)
            _post(db)
            self.assertFalse(control.cap_reached(db, cfg)[0])

    def test_pending_posts_do_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            _post(db, status="pending")
            self.assertEqual(control.posts_today(db), 0)

    def test_gate_priority(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), posting={"max_per_day": 5, "quiet_hours": "0-6"})
            db = DB(cfg.db_path)
            self.assertEqual(control.gate(db, cfg, 12), "")        # free
            self.assertIn("quiet hours", control.gate(db, cfg, 3))
            control.pause(db, "owner nap")
            self.assertIn("paused by owner", control.gate(db, cfg, 12))
            control.resume(db)
            for _ in range(5):
                _post(db)
            self.assertIn("daily cap", control.gate(db, cfg, 12))

    def test_gate_never_raises_on_broken_db(self):
        class Broken:
            def get_state(self, *a, **k):
                raise RuntimeError("db gone")

            def count_posts_since(self, *a, **k):
                raise RuntimeError("db gone")

            def recent_posts(self, *a, **k):
                raise RuntimeError("db gone")
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            try:
                control.gate(Broken(), cfg, 12)
            except RuntimeError:
                self.fail("gate must never raise")


class _FakeResp:
    def __init__(self, status=200, url="https://www.meesho.com/x"):
        self.status_code = status
        self.url = url


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc = resp, exc
        self.calls = 0

    def get(self, url, **kw):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.resp


class TestLinkHealth(unittest.TestCase):
    def _cfg_with_tag(self, tmp):
        return _cfg(tmp, affiliate={"meesho_affid": "af_invite123"})

    def test_alive_and_tagged(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg_with_tag(Path(d))
            s = _FakeSession(_FakeResp(200, "https://www.meesho.com/x?af_invite123"))
            r = health.check_link(cfg, "https://meesho.com/x", session=s)
            self.assertTrue(r["ok"] and r["monetized"])
            self.assertEqual(r["note"], "")

    def test_alive_but_untagged_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg_with_tag(Path(d))
            s = _FakeSession(_FakeResp(200, "https://www.meesho.com/x"))
            r = health.check_link(cfg, "https://meesho.com/x", session=s)
            self.assertTrue(r["ok"])
            self.assertFalse(r["monetized"])
            self.assertIn("tracking token missing", r["note"])

    def test_dead_link(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg_with_tag(Path(d))
            s = _FakeSession(_FakeResp(404, "https://meesho.com/gone"))
            r = health.check_link(cfg, "https://meesho.com/gone", session=s)
            self.assertFalse(r["ok"])
            self.assertIn("404", r["note"])

    def test_network_error_and_junk_url(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg_with_tag(Path(d))
            s = _FakeSession(exc=RuntimeError("dns fail"))
            r = health.check_link(cfg, "https://meesho.com/x", session=s)
            self.assertFalse(r["ok"])
            self.assertIn("check failed", r["note"])
            self.assertEqual(health.check_link(cfg, "not-a-url")["note"],
                             "not a http(s) link")

    def test_summary(self):
        rows = [{"ok": True, "monetized": True}, {"ok": True, "monetized": False},
                {"ok": False, "monetized": False}]
        self.assertEqual(health.summary(rows),
                         "1/3 links healthy, 1 unreachable, 1 untagged")
        self.assertEqual(health.summary([]), "no links to check")

    def test_audit_links_queued_first(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = self._cfg_with_tag(Path(d))
            db = DB(cfg.db_path)
            db.add_product(source="meesho", url="https://m/1", affiliate_url="https://m/1?af_invite123",
                           title="Posted one", status="posted")
            db.add_product(source="meesho", url="https://m/2", affiliate_url="https://m/2?af_invite123",
                           title="Queued one", status="queued")
            s = _FakeSession(_FakeResp(200, "https://m/?af_invite123"))
            rows = health.audit_links(cfg, db, limit=2, session=s)
            self.assertEqual(rows[0]["title"], "Queued one")

    def test_secrets_audit(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            p = tmp / ".env"
            p.write_text("X=1")
            os.chmod(p, 0o644)
            findings = health.audit_secrets(cfg, root=tmp)
            env = [f for f in findings if f["file"] == ".env"][0]
            self.assertTrue(env["exists"])
            self.assertFalse(env["ok"])                 # world readable = bad
            self.assertIn("chmod 600", env["note"])
            os.chmod(p, 0o600)
            findings = health.audit_secrets(cfg, root=tmp)
            self.assertTrue([f for f in findings if f["file"] == ".env"][0]["ok"])
            self.assertTrue(all(f["ok"] for f in findings if f["exists"]))
            self.assertFalse(health.secrets_ok([{"ok": False}]))


class TestEarnings(unittest.TestCase):
    def test_math_is_transparent(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            est = earnings.estimate(cfg, [{"source": "meesho", "clicks": 50}])
            self.assertEqual(est["clicks"], 50)
            self.assertAlmostEqual(est["orders"], 1.0)
            self.assertAlmostEqual(est["commission"], 47.92, places=2)
            self.assertEqual(est["per_network"]["meesho"]["rate"], 8.0)
            self.assertIn("Estimate only", est["disclaimer"])

    def test_rate_override_and_unknown_network(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), money={"rates": {"meesho": 12, "mystore": 4}})
            est = earnings.estimate(cfg, [{"source": "meesho", "clicks": 100},
                                          {"source": "mystore", "clicks": 100}])
            self.assertEqual(est["per_network"]["meesho"]["rate"], 12.0)
            self.assertEqual(est["per_network"]["mystore"]["rate"], 4.0)

    def test_zero_clicks_and_junk_rows(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            est = earnings.estimate(cfg, [{"source": "meesho", "clicks": 0},
                                          None, {}])
            self.assertEqual(est["clicks"], 0)
            self.assertEqual(est["commission"], 0.0)

    def test_window_uses_posted_at(self):
        """regression: posts table has posted_at, not created_at (real bug)."""
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            _post(db, clicks=7, posted_at="2026-09-18T10:00:00")
            rows = earnings.click_rows_since(db, days=30)
            self.assertTrue(rows)
            self.assertEqual(earnings.estimate(cfg, rows)["clicks"], 7)


class TestReport(unittest.TestCase):
    def test_lines_include_real_numbers(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            _post(db, clicks=9, posted_at="2026-09-18T10:00:00")
            out = "\n".join(report.lines(cfg, db, days=30))
            self.assertIn("LAST 30 DAYS", out)
            self.assertIn("pins posted: 1", out)
            self.assertIn("clicks: 9", out)
            self.assertIn("ESTIMATE", out)

    def test_no_fake_best_hour_on_zero_clicks(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            _post(db, clicks=0)
            out = "\n".join(report.lines(cfg, db, days=7))
            self.assertNotIn("best hour", out)

    def test_empty_db_never_raises(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            self.assertTrue(report.lines(cfg, db, days=7))
            self.assertIsInstance(report.build(cfg, db), dict)

    def test_telegram_is_optional(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            self.assertFalse(report.send_telegram(cfg, "hello"))

    def test_paused_flag(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            control.pause(db, "test")
            self.assertTrue(report.build(cfg, db)["paused"])


class TestMoneyPanelAPI(unittest.TestCase):
    def _client(self, tmp: Path):
        from bot.dashboard import create_app
        cfg = _cfg(tmp)
        return create_app(cfg, DB(cfg.db_path)).test_client()

    def test_control_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._client(Path(d))
            body = c.get("/api/control").get_json()
            self.assertFalse(body["paused"])
            self.assertEqual(body["daily"]["cap"], 5)
            self.assertTrue(c.post("/api/control", json={"action": "pause",
                                                         "reason": "demo"}).get_json()["paused"])
            self.assertTrue(c.get("/api/control").get_json()["paused"])
            self.assertFalse(c.post("/api/control",
                                    json={"action": "resume"}).get_json()["paused"])
            self.assertEqual(c.post("/api/control",
                                    json={"action": "nuke"}).status_code, 400)

    def test_earnings_and_report_endpoints(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            c = self._client(tmp)
            db = DB(Config(raw={"storage": {"db_path": f"{tmp}/t.db"}}).db_path)
            _post(db, clicks=50)
            e = c.get("/api/earnings").get_json()
            self.assertTrue(e["ok"])
            self.assertEqual(e["clicks"], 50)
            self.assertGreater(e["commission"], 0)
            r = c.get("/api/report?days=30").get_json()
            self.assertTrue(r["ok"])
            self.assertTrue(r["lines"])

    def test_links_status_shape(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._client(Path(d))
            st = c.get("/api/links/status").get_json()
            self.assertIn("running", st)
            self.assertIn("results", st)

    def test_money_tab_in_ui(self):
        with tempfile.TemporaryDirectory() as d:
            html = self._client(Path(d)).get("/").data.decode()
            self.assertIn('data-tab="money"', html)
            self.assertIn("refreshMoney", html)
            self.assertIn("checkLinks", html)


if __name__ == "__main__":
    unittest.main()


class TestReadiness(unittest.TestCase):
    """`bot ready` — the honest "what is left for YOU" answer."""

    def test_items_and_summary_shape(self):
        from bot import ready
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            s = ready.summary(cfg)
            self.assertIn("percent", s)
            self.assertTrue(0 <= s["percent"] <= 100)
            self.assertTrue(s["you_must_do"])
            self.assertTrue(s["automatic"])
            keys = {i["key"] for i in s["items"]}
            self.assertIn("pinterest_token", keys)
            self.assertIn("money", keys)

    def test_every_unfinished_item_has_instructions(self):
        from bot import ready
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            for item in ready.summary(cfg)["you_must_do"]:
                self.assertTrue(item["how"].strip(), item["key"])
                self.assertGreater(item["minutes"], 0)

    def test_optional_platforms_are_not_required(self):
        from bot import ready
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            you = {i["key"] for i in ready.summary(cfg)["you_must_do"]}
            for opt in ("instagram", "facebook", "youtube"):
                self.assertNotIn(opt, you)      # never block a launch on these

    def test_ready_when_pinterest_and_money_present(self):
        from bot import ready
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg.raw["affiliate"] = {"amazon_tag": "mytag-21"}
            (tmp / ".env").write_text("X=1")
            os.chmod(tmp / ".env", 0o600)
            with unittest.mock.patch.dict(os.environ, {
                    "PINTEREST_APP_ID": "app-id-123",
                    "PINTEREST_APP_SECRET": "secret-xyz"}):
                items = {i["key"]: i["done"] for i in ready.checks(cfg)}
            self.assertTrue(items["pinterest_app"])
            self.assertTrue(items["money"])
            self.assertFalse(items["pinterest_token"])   # still needs the click

    def test_lines_are_printable_and_mention_deploy(self):
        from bot import ready
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            text = "\n".join(ready.lines(cfg))
            self.assertIn("YOU DO (one time only)", text)
            self.assertIn("BOT DOES", text)
            self.assertIn("deploy.sh", text)

    def test_automatic_list_covers_the_core_promises(self):
        from bot import ready
        text = " ".join(ready.automatic_lines()).lower()
        for promise in ("affiliate link", "qa gate", "hunts top products",
                        "circuit breaker", "self-audit"):
            self.assertIn(promise, text)

    def test_never_raises_on_odd_config(self):
        from bot import ready
        cfg = Config(raw={"storage": {"db_path": "/nonexistent/x.db"}})
        self.assertIsInstance(ready.summary(cfg), dict)


class TestSetupTabAPI(unittest.TestCase):
    def test_ready_endpoint_and_ui(self):
        from bot.dashboard import create_app
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            html_client = create_app(cfg, DB(cfg.db_path)).test_client()
            r = html_client.get("/api/ready").get_json()
            self.assertTrue(r["ok"])
            self.assertIn("you_must_do", r)
            self.assertGreater(len(r["automatic"]), 5)
            html = html_client.get("/").data.decode()
            self.assertIn('data-tab="setup"', html)
            self.assertIn("refreshReady", html)


class TestSelfAudit(unittest.TestCase):
    def test_self_audit_logs_something(self):
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            eng = Engine(cfg, DB(cfg.db_path))
            eng._self_audit()                    # must not raise on empty db
            logs = eng.db.recent_logs(limit=10)
            self.assertTrue(any("self-audit" in str(r.get("message", ""))
                                for r in logs))

    def test_self_audit_reports_pause(self):
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            db = DB(cfg.db_path)
            eng = Engine(cfg, db)
            control.pause(db, "audit test")
            eng._self_audit()
            logs = " ".join(str(r.get("message", ""))
                            for r in db.recent_logs(limit=20))
            self.assertIn("PAUSED", logs)
