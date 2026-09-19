"""R63 tests: navigation helper + token capability proof."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import requests

from bot import appform, tokencheck
from bot.config import Config
from bot.main import cmd_app, cmd_token_check


def _cfg(tmp: Path, **raw) -> Config:
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"},
            "design": {"brand_name": "Gharvanaa"},
            "pinterest": {"redirect_uri": "http://localhost:8888/callback"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class _FakeAPI:
    """Stand-in for PinterestAPI: records what the checker asked it to do."""

    def __init__(self, *, configured=True, read_ok=True, boards_ok=True,
                 write_ok=True, app_secret="s"):
        self.app_id = "1613412"
        self.app_secret = app_secret
        self.auth_mode = "trial token (dashboard)"
        self._configured = configured
        self._read_ok = read_ok
        self._boards_ok = boards_ok
        self._write_ok = write_ok
        self.created: list[str] = []
        self.deleted: list[str] = []

    # --- attribute expected by tokencheck / api module
    @property
    def configured(self):
        return self._configured

    def user_account(self):
        if not self._read_ok:
            raise RuntimeError("401 unauthorized")
        return {"username": "gharvanaa", "account_type": "BUSINESS",
                "follower_count": 12, "board_count": 3, "pin_count": 4}

    def list_boards(self):
        if not self._boards_ok:
            raise RuntimeError("403 forbidden")
        return [{"id": "1", "name": "Home & Kitchen"}, {"id": "2", "name": "Deals"}]

    def create_board(self, name, description=""):
        if not self._write_ok:
            raise RuntimeError("403 forbidden: insufficient scope")
        self.created.append(name)
        return {"id": "999", "name": name}

    def _request(self, method, path, **kwargs):
        if method == "DELETE":
            self.deleted.append(path)
            return {}
        return {}


def _patch_api(fake):
    from bot import pinterest_api
    old = pinterest_api.PinterestAPI
    pinterest_api.PinterestAPI = lambda cfg: fake
    return lambda: setattr(pinterest_api, "PinterestAPI", old)


class TestWhereHelper(unittest.TestCase):
    def test_click_path_is_complete(self):
        text = "\n".join(appform.where_lines(_cfg(Path("/tmp"))))
        self.assertIn("developers.pinterest.com", text)
        self.assertIn("My apps", text)
        self.assertIn("Manage", text)
        self.assertIn("Configure", text)
        self.assertIn("http://localhost:8888/callback", text)
        self.assertIn("Generate token", text)
        self.assertIn("pins:write", text)
        self.assertIn("token-check", text)

    def test_reads_app_id_from_env_when_present(self):
        import os
        old = os.environ.get("PINTEREST_APP_ID")
        os.environ["PINTEREST_APP_ID"] = "1613412"
        self.addCleanup(lambda: os.environ.pop("PINTEREST_APP_ID", None)
                        if old is None else os.environ.update(
                            {"PINTEREST_APP_ID": old}))
        text = "\n".join(appform.where_lines(_cfg(Path("/tmp"))))
        self.assertIn("apps/1613412/", text)
        self.assertNotIn("(App ID 1613412)\n   →", "  " + text)

    def test_never_raises_without_config(self):
        self.assertIn("APP PAGE", "\n".join(appform.where_lines()))

    def test_cli_where_flag(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_app(cfg, ["--where"]), 0)
            self.assertIn("APP PAGE EKKADA", buf.getvalue())

    def test_sheet_reminds_the_navigation_command(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        self.assertIn("app --where", text)


class TestTokenCheck(unittest.TestCase):
    def test_no_credentials_is_explained(self):
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp")), )).replace(
            "❌ Credentials", "❌")
        fake = _FakeAPI(configured=False)
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp"))))
        self.assertIn("PINTEREST_ACCESS_TOKEN", text)
        self.assertIn("PINTEREST_APP_ID", text)

    def test_read_success_reports_account_and_boards(self):
        fake = _FakeAPI()
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp"))))
        self.assertIn("READ works", text)
        self.assertIn("@gharvanaa", text)
        self.assertIn("boards:read works", text)
        self.assertIn("Home & Kitchen", text)
        self.assertIn("--write-test", text)      # offers the write proof

    def test_read_failure_is_explained_with_the_fix(self):
        fake = _FakeAPI(read_ok=False)
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp"))))
        self.assertIn("READ failed", text)
        self.assertIn("401", text)
        self.assertIn("Generate token", text)

    def test_write_blocked_is_reported_honestly_with_next_steps(self):
        fake = _FakeAPI(write_ok=False)
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp")), write_test=True))
        self.assertIn("WRITE BLOCKED", text)
        self.assertIn("auth-url", text)
        self.assertIn("pins:write", text)
        self.assertEqual(fake.created, [])       # board not created

    def test_write_test_creates_then_deletes_the_board(self):
        fake = _FakeAPI()
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp")), write_test=True))
        self.assertIn("boards:write WORKS", text)
        self.assertIn("delete ayyindi", text)
        self.assertEqual(fake.created, [tokencheck.TEST_BOARD])
        self.assertEqual(fake.deleted, ["/boards/999"])

    def test_delete_failure_tells_the_owner_to_clean_up(self):
        fake = _FakeAPI()
        fake._request = lambda method, path, **k: (_ for _ in ()).throw(
            RuntimeError("403"))
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp")), write_test=True))
        self.assertIn("delete avvaledu", text)
        self.assertIn(tokencheck.TEST_BOARD, text)

    def test_boards_read_failure_is_a_warning_not_a_lie(self):
        fake = _FakeAPI(boards_ok=False)
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp"))))
        self.assertIn("READ works", text)
        self.assertIn("boards:read failed", text)

    def test_path_reminder_is_always_present(self):
        fake = _FakeAPI()
        self.addCleanup(_patch_api(fake))
        text = "\n".join(tokencheck.verify(_cfg(Path("/tmp"))))
        self.assertIn("PATH REMINDER", text)
        self.assertIn("app --upgrade", text)

    def test_cli_write_test_flag(self):
        fake = _FakeAPI()
        self.addCleanup(_patch_api(fake))
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_token_check(_cfg(Path(d)), ["--write-test"]), 0)
            self.assertIn("WRITE TEST", buf.getvalue())

    def test_cli_defaults_to_read_only(self):
        fake = _FakeAPI()
        self.addCleanup(_patch_api(fake))
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_token_check(_cfg(Path(d)), [])
            self.assertIn("READ works", buf.getvalue())
            self.assertEqual(fake.created, [])

    def test_dispatch_and_help_wired(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn('if cmd in ("token-check", "tokencheck", "whoami")', src)
        self.assertIn("python -m bot token-check", src)
        self.assertIn("python -m bot app --where", src)


if __name__ == "__main__":
    unittest.main()
