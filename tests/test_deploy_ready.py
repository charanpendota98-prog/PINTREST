"""Deploy-readiness regression tests: panel lock + preflight + money pages.

These exist because a deploy that leaves the admin panel open (or the money
path locked) is worse than no deploy at all.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from bot.config import load_config
from bot.dashboard import (PUBLIC_EXACT, PUBLIC_PREFIX, create_app,
                           resolve_dashboard_password, resolve_dashboard_secret)
from bot.db import DB

PW = "s3cret-panel-pw"


def _cfg(tmp: Path, password: str = ""):
    cfg = load_config()
    cfg.raw["storage"] = {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/media"}
    Path(cfg.media_dir).mkdir(parents=True, exist_ok=True)
    cfg.raw.setdefault("dashboard", {}).update(
        {"host": "127.0.0.1", "port": 5000, "password": password,
         "secret_key": "test-secret"})
    return cfg


class TestPanelLock(unittest.TestCase):
    """Admin routes must be locked; money pages must stay public."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ.pop("DASHBOARD_PASSWORD", None)
        self.cfg = _cfg(self.tmp, PW)
        self.db = DB(self.cfg.db_path)
        self.db.add_product(source="meesho", url="https://m/p/1k1b6",
                            affiliate_url="https://m/af_invite/x?p_id=1k1b6",
                            title="Women Kurta", price="499")
        self.c = create_app(self.cfg, self.db).test_client()

    # ------------------------------------------------------------ locked
    def test_admin_pages_redirect_to_login(self):
        for path in ("/", "/deals/today-x"):
            r = self.c.get(path)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/login", r.headers.get("Location", ""))

    def test_every_api_route_401_without_login(self):
        for path in ("/api/status", "/api/products", "/api/posts", "/api/logs",
                     "/api/analytics"):
            self.assertEqual(self.c.get(path).status_code, 401, path)

    def test_mutations_blocked_without_login(self):
        for method, path in (("post", "/api/post"), ("post", "/api/add"),
                             ("post", "/api/add-manual"),
                             ("post", "/api/products/1/skip"),
                             ("delete", "/api/products/1")):
            r = getattr(self.c, method)(path, json={})
            self.assertEqual(r.status_code, 401, f"{method} {path}")

    def test_unauth_api_returns_clean_json(self):
        body = self.c.get("/api/status").get_json()
        self.assertFalse(body["ok"])
        self.assertIn("login", body)

    # ------------------------------------------------------------ public
    def test_money_pages_stay_public(self):
        self.assertEqual(self.c.get("/healthz").status_code, 200)
        self.assertEqual(self.c.get("/deals/today").status_code, 200)
        r = self.c.get("/go/1")                 # bridge landing
        self.assertIn(r.status_code, (200, 302))
        self.assertEqual(self.c.get("/login").status_code, 200)

    def test_subscribe_and_media_public(self):
        r = self.c.post("/subscribe/1", data={"email": "buyer@example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/media/missing.jpg").status_code, 404)

    def test_public_lists_are_sane(self):
        self.assertIn("/go/", PUBLIC_PREFIX)
        self.assertIn("/healthz", PUBLIC_EXACT)
        self.assertNotIn("/", PUBLIC_EXACT)     # the panel root is NOT public

    # ------------------------------------------------------------- login
    def test_login_unlocks_everything(self):
        self.assertEqual(self.c.post("/login", data={"password": PW}).status_code, 302)
        self.assertEqual(self.c.get("/api/status").status_code, 200)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_wrong_password_does_not_unlock(self):
        self.c.post("/login", data={"password": "nope"})
        self.assertEqual(self.c.get("/api/status").status_code, 401)

    def test_header_token_works_for_scripts(self):
        r = self.c.get("/api/status", headers={"X-Dashboard-Token": PW})
        self.assertEqual(r.status_code, 200)

    def test_query_token_logs_in_then_sticks(self):
        self.assertEqual(self.c.get(f"/?token={PW}").status_code, 200)
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_logout_relocks(self):
        self.c.post("/login", data={"password": PW})
        self.c.get("/logout")
        self.assertEqual(self.c.get("/api/status").status_code, 401)

    def test_brute_force_is_rate_limited(self):
        codes = [self.c.post("/login", data={"password": f"x{i}"}).status_code
                 for i in range(7)]
        self.assertIn(429, codes)
        self.assertEqual(codes[-1], 429)

    def test_no_password_means_open_mode(self):
        cfg = _cfg(self.tmp / "open")
        c = create_app(cfg, DB(cfg.db_path)).test_client()
        self.assertEqual(c.get("/").status_code, 200)
        self.assertEqual(c.get("/api/status").status_code, 200)

    def test_env_var_locks_a_real_deployment(self):
        """Deploy safety net: DASHBOARD_PASSWORD alone must lock the panel."""
        os.environ["DASHBOARD_PASSWORD"] = "env-only-pw"
        try:
            cfg = _cfg(self.tmp / "envlock")       # config password empty
            c = create_app(cfg, DB(cfg.db_path)).test_client()
            self.assertEqual(c.get("/api/status").status_code, 401)
            self.assertEqual(c.get("/").status_code, 302)
            self.assertEqual(c.get("/deals/today").status_code, 200)  # money page
            c.post("/login", data={"password": "env-only-pw"})
            self.assertEqual(c.get("/api/status").status_code, 200)
        finally:
            os.environ.pop("DASHBOARD_PASSWORD", None)


class TestPasswordResolution(unittest.TestCase):
    """Deploy must never end up locked-out OR wide-open."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ.pop("DASHBOARD_PASSWORD", None)

    def tearDown(self):
        os.environ.pop("DASHBOARD_PASSWORD", None)

    def test_env_wins(self):
        self.cfg = _cfg(self.tmp, "from-config")
        os.environ["DASHBOARD_PASSWORD"] = "from-env"
        self.assertEqual(resolve_dashboard_password(self.cfg), "from-env")

    def test_config_used_when_set(self):
        self.assertEqual(resolve_dashboard_password(_cfg(self.tmp, "cfg-pw")), "cfg-pw")

    def test_autogenerated_once_and_stable(self):
        cfg = _cfg(self.tmp)
        first = resolve_dashboard_password(cfg)
        self.assertGreaterEqual(len(first), 12)
        self.assertTrue((self.tmp / "dashboard_password.txt").exists())
        self.assertEqual(resolve_dashboard_password(cfg), first)

    def test_auto_false_does_not_create(self):
        cfg = _cfg(self.tmp / "noauto")
        (self.tmp / "noauto").mkdir(parents=True, exist_ok=True)
        self.assertEqual(resolve_dashboard_password(cfg, auto=False), "")
        self.assertFalse((self.tmp / "noauto" / "dashboard_password.txt").exists())

    def test_secret_persists_across_restarts(self):
        cfg = _cfg(self.tmp / "sec")
        (self.tmp / "sec").mkdir(parents=True, exist_ok=True)
        cfg.raw["dashboard"]["secret_key"] = ""      # as on a fresh install
        first = resolve_dashboard_secret(cfg)
        self.assertGreaterEqual(len(first), 32)
        cfg2 = _cfg(self.tmp / "sec")
        cfg2.raw["dashboard"]["secret_key"] = ""
        self.assertEqual(resolve_dashboard_secret(cfg2), first)


class TestDeployPreflight(unittest.TestCase):
    """`bot deploy-check` must run on any machine and give a verdict."""

    def test_preflight_reports_and_never_crashes(self):
        import contextlib
        import io
        from bot.main import cmd_deploy_check
        cfg = _cfg(Path(tempfile.mkdtemp()))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_deploy_check(cfg)
        out = buf.getvalue()
        self.assertIn(code, (0, 1))
        self.assertIn("DEPLOY PREFLIGHT", out)
        self.assertIn("Money path", out)

    def test_dashboard_pass_command_works(self):
        import contextlib
        import io
        from bot.main import cmd_dashboard_pass
        cfg = _cfg(Path(tempfile.mkdtemp()))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cmd_dashboard_pass(cfg)
        self.assertEqual(code, 0)
        self.assertIn("Dashboard login", buf.getvalue())


class TestPageRoutesStillServe(unittest.TestCase):
    """Unlocking must not break any page the owner uses."""

    def test_all_pages_ok_when_logged_in(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = _cfg(tmp, PW)
        db = DB(cfg.db_path)
        db.add_product(source="meesho", url="https://m/p/1k1b7",
                       affiliate_url="https://m/af_invite/x?p_id=1k1b7",
                       title="Kitchen Rack", price="399", status="posted")
        c = create_app(cfg, db).test_client()
        c.post("/login", data={"password": PW})
        for path in ("/", "/deals/today", "/go/1", "/api/status",
                     "/api/products", "/api/posts", "/api/logs", "/api/analytics"):
            r = c.get(path)
            self.assertLess(r.status_code, 500, path)


if __name__ == "__main__":
    unittest.main()


class TestSingleInstanceLock(unittest.TestCase):
    """Two autopilots must never post the same product twice (ban + money risk)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp)
        (self.tmp / "locks").mkdir(parents=True, exist_ok=True)

    def test_acquire_release_roundtrip(self):
        from bot.lock import acquire, lock_path, release
        lk = acquire(self.cfg, "scheduler", heartbeat=False)
        self.assertTrue(lk.exists())
        self.assertEqual(lk, lock_path(self.cfg, "scheduler"))
        release(lk)
        self.assertFalse(lk.exists())

    def test_stale_lock_dead_pid_is_recovered(self):
        from bot.lock import acquire, lock_path, release
        lp = lock_path(self.cfg, "scheduler")
        lp.write_text('{"pid": 999999, "token": "ghost", "cmd": "bot run"}')
        lk = acquire(self.cfg, "scheduler", heartbeat=False)
        self.assertNotEqual(lp.read_text(), '{"pid": 999999, "token": "ghost", "cmd": "bot run"}')
        release(lk)

    def test_frozen_holder_is_taken_over(self):
        """Alive pid + stale heartbeat = frozen twin -> new instance proceeds."""
        import os
        import time
        from bot.lock import acquire, lock_path, release
        lp = lock_path(self.cfg, "scheduler")
        lp.write_text(f'{{"pid": {os.getpid()}, "token": "old", "cmd": "bot run"}}')
        old = time.time() - 600
        os.utime(lp, (old, old))
        import json
        import os as _os
        lk = acquire(self.cfg, "scheduler", heartbeat=False, stale_after=120)
        self.assertEqual(json.loads(lp.read_text())["pid"], _os.getpid())
        release(lk)

    def test_corrupt_lock_never_blocks(self):
        from bot.lock import acquire, lock_path, release
        locked = lock_path(self.cfg, "scheduler")
        locked.write_text("{ this is not json")
        lk = acquire(self.cfg, "scheduler", heartbeat=False)
        self.assertTrue(lk.exists())
        release(lk)

    def test_live_twin_is_refused(self):
        """The real thing: a second OS process holding the lock blocks us."""
        import subprocess
        import time
        from bot.config import load_config
        from bot.lock import AlreadyRunning, acquire, release
        # NOT .resolve(): that follows the venv symlink to system python
        py = Path(".venv/bin/python").absolute()
        # the twin must use THIS temp storage, else it fights the real install
        script = self.tmp / "twin.py"
        script.write_text(
            "import time, sys\n"
            f"sys.path.insert(0, {str(Path.cwd())!r})\n"
            "from bot.config import Config\n"
            "from bot.lock import acquire\n"
            f"cfg = Config(raw={{'storage': {{'db_path': {str(self.tmp / 't.db')!r},"
            f" 'media_dir': {str(self.tmp / 'media')!r}}}}})\n"
            "acquire(cfg, 'scheduler')\n"
            "print('HOLDING', flush=True)\n"
            "time.sleep(25)\n")
        proc = subprocess.Popen([str(py), str(script)], cwd=str(Path.cwd()),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(), "HOLDING",
                             "twin failed to take the lock")
            with self.assertRaises(AlreadyRunning):
                acquire(self.cfg, "scheduler", wait=0.3)
        finally:
            proc.kill()
            proc.wait()
        time.sleep(0.5)
        lk = acquire(self.cfg, "scheduler", wait=2.0, heartbeat=False)
        self.assertTrue(lk.exists())          # dead twin -> we take over
        release(lk)


class TestMediaSafety(unittest.TestCase):
    """Hostile filenames must be a clean 404 — never a traceback or a leak."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp, "")          # unlocked: focus on the route
        (self.tmp / "secret.txt").write_text("TOP-SECRET")
        media = Path(self.cfg.media_dir)
        media.mkdir(parents=True, exist_ok=True)
        (media / "real.jpg").write_bytes(b"\xff\xd8\xff\xe0real")
        self.c = create_app(self.cfg, DB(self.cfg.db_path)).test_client()

    def test_hostile_paths_are_404_not_500(self):
        for path in ("/media/x%00.jpg", "/media/../../secret.txt",
                     "/media/..%2f..%2fsecret.txt", "/media//etc/passwd",
                     "/media/.env", "/media/nope.jpg", "/media/"):
            r = self.c.get(path)
            self.assertLess(r.status_code, 500, path)
            self.assertNotIn(b"TOP-SECRET", r.data, path)
            self.assertNotIn(b"root:", r.data, path)

    def test_real_media_served(self):
        r = self.c.get("/media/real.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"\xff\xd8"))


class TestReshareGuard(unittest.TestCase):
    """Winner rotation is locked: two workers must not re-share the same pin."""

    def test_second_reshare_worker_skips(self):
        import unittest.mock as mock
        from bot.engine import Engine
        from bot.lock import AlreadyRunning
        from bot.config import Config
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(raw={
            "design": {"brand_name": "T"},
            "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/media"},
            "posting": {"platform_order": ["pinterest"]},
        })
        (tmp / "media").mkdir(parents=True, exist_ok=True)
        db = DB(cfg.db_path)
        engine = Engine(cfg, db)
        with mock.patch("bot.lock.acquire",
                        side_effect=AlreadyRunning(4242, "bot run")):
            self.assertEqual(engine.reshare_winners(), 0)
        logs = [str(r["message"]) for r in db.recent_logs(limit=10)]
        self.assertTrue(any("reshare skipped" in m for m in logs),
                        f"no skip log: {logs[:3]}")

    def test_reshare_lock_is_released_after_run(self):
        """The lock must not leak — a later cycle has to be able to run."""
        from bot.engine import Engine
        from bot.config import Config
        from bot.lock import lock_path
        tmp = Path(tempfile.mkdtemp())
        cfg = Config(raw={
            "design": {"brand_name": "T"},
            "storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/media"},
            "posting": {"platform_order": ["pinterest"]},
        })
        (tmp / "media").mkdir(parents=True, exist_ok=True)
        db = DB(cfg.db_path)
        Engine(cfg, db).reshare_winners()          # no candidates: quick run
        self.assertFalse(lock_path(cfg, "reshare").exists(),
                         "reshare lock leaked")


if __name__ == "__main__":
    unittest.main()


class TestMoneyPathCompliance(unittest.TestCase):
    """Every clickable money surface must carry the tracked link + disclosure."""

    def setUp(self):
        from PIL import Image
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _cfg(self.tmp, "")
        self.cfg.raw.setdefault("link", {}).update(
            {"bridge": True, "landing": True, "public_base": "https://deals.example"})
        media = Path(self.cfg.media_dir)
        media.mkdir(parents=True, exist_ok=True)
        img = media / "pin_1.jpg"
        Image.new("RGB", (1000, 1500), "white").save(img)
        self.aff = ("https://www.meesho.com/af_invite/24197020:instagram_stories"
                    ":11075346?p_id=1k1b6")
        self.db = DB(self.cfg.db_path)
        self.pid = self.db.add_product(
            source="meesho", url="https://www.meesho.com/x/p/1k1b6",
            affiliate_url=self.aff, title="Women Kurta Set Designer",
            price="499", currency="INR", image_path=str(img),
            pin_image=str(img), status="posted", discount=45)
        self.c = create_app(self.cfg, self.db).test_client()

    def test_landing_has_tracked_link_and_disclosure(self):
        html = self.c.get(f"/go/{self.pid}").data.decode()
        self.assertIn("af_invite", html, "affiliate link missing on landing!")
        self.assertIn("#ad", html.lower(), "FTC disclosure missing")
        self.assertIn("nofollow", html, "sponsored/nofollow attribute missing")

    def test_deals_page_links_are_tracked_or_bridged(self):
        html = self.c.get("/deals/today").data.decode()
        self.assertTrue("/go/" in html or "af_invite" in html,
                        "deals page has no clickable money link")

    def test_clicks_are_counted(self):
        for _ in range(3):
            self.c.get(f"/go/{self.pid}")
        self.assertEqual(self.db.click_counts().get(self.pid), 3)

    def test_landing_off_redirects_directly(self):
        cfg = _cfg(Path(tempfile.mkdtemp()), "")
        cfg.raw.setdefault("link", {}).update({"landing": False})
        db = DB(cfg.db_path)
        pid = db.add_product(source="meesho", url="https://m/p/1k1b9",
                             affiliate_url=self.aff, title="Kurta", price="599")
        c = create_app(cfg, db).test_client()
        r = c.get(f"/go/{pid}")
        self.assertEqual(r.status_code, 302)
        self.assertIn("af_invite", r.headers.get("Location", ""))
