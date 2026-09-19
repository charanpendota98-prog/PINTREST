"""R61: the 'Connect app' answer sheet + --site saving."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from bot import appform
from bot.config import Config, load_config
from bot.main import cmd_app


def _cfg(tmp: Path, **raw) -> Config:
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"},
            "design": {"brand_name": "Gharvanaa"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestSheet(unittest.TestCase):
    def test_every_form_field_is_answered(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        for needle in ("App icon", "App name", "Company name",
                       "Company website", "Privacy policy", "App purpose",
                       "Developer purpose", "Use cases", "Audience",
                       "Reads Pins and/or Boards", "reCAPTCHA"):
            self.assertIn(needle, text, needle)

    def test_choices_are_the_minimal_honest_ones(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        self.assertIn("Personal API access (single, personal use)", text)
        self.assertIn("Only me", text)
        self.assertIn("Businesses", text)
        self.assertIn("Yes, mine", text)
        self.assertIn("select cheyyakandi", text)   # what NOT to tick

    def test_purpose_text_says_it_is_internal_and_own_account_only(self):
        text = appform.PURPOSE_TEXT.lower()
        self.assertIn("own", text)
        self.assertIn("does not access other users", text)
        self.assertIn("does not run ads", text)

    def test_scopes_are_the_minimal_set(self):
        for scope in ("pins:write", "boards:write", "user_accounts:read"):
            self.assertIn(scope, appform.SCOPES)

    def test_placeholders_warn_before_submitting(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        self.assertIn("<VPS-IP>", text)
        self.assertIn("submit cheyyaku", text)

    def test_configured_site_gives_real_urls_and_a_curl_check(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), link={"public_base": "https://gharvanaa.in"})
            text = "\n".join(appform.lines(cfg))
            self.assertIn("https://gharvanaa.in/about", text)
            self.assertIn("https://gharvanaa.in/privacy", text)
            self.assertNotIn("<VPS-IP>", text)
            self.assertIn("curl", text)

    def test_trailing_slash_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), link={"public_base": "https://gharvanaa.in/"})
            site, privacy = appform.urls(cfg)
            self.assertEqual(site, "https://gharvanaa.in/about")
            self.assertEqual(privacy, "https://gharvanaa.in/privacy")

    def test_brand_name_flows_into_app_and_company_name(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), design={"brand_name": "Gharvanaa"})
            text = "\n".join(appform.lines(cfg))
            self.assertIn("Gharvanaa Deals Publisher", text)

    def test_never_raises_on_broken_config(self):
        class Boom:
            def get(self, *a, **k):
                raise RuntimeError("bad config")
        text = "\n".join(appform.lines(Boom()))
        self.assertIn("CONNECT APP", text)


class TestSaveSite(unittest.TestCase):
    def test_saves_and_keeps_comments_and_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("# top\nlink:\n  public_base: \"\"  # host the dashboard here\n"
                         "  bridge: false\nbrand:\n  handle: gharvanaa\n")
            cfg = load_config(f)
            res = appform.save_site(cfg, "https://gharvanaa.in/")
            self.assertTrue(res["saved"])
            text = f.read_text()
            self.assertIn("# top", text)
            self.assertIn("# host the dashboard here", text)
            data = yaml.safe_load(text)
            self.assertEqual(data["link"]["public_base"], "https://gharvanaa.in")
            self.assertFalse(data["link"]["bridge"])
            self.assertEqual(data["brand"]["handle"], "gharvanaa")

    def test_rejects_junk_urls(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\n")
            cfg = load_config(f)
            for bad in ("", "gharvanaa.in", "ftp://x.com", "https://"):
                res = appform.save_site(cfg, bad)
                self.assertFalse(res["saved"], bad)
            self.assertEqual(yaml.safe_load(f.read_text())["link"]["public_base"],
                             "")

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\n")
            cfg = load_config(f)
            appform.save_site(cfg, "https://a.in")
            appform.save_site(cfg, "https://b.in")
            text = f.read_text()
            self.assertEqual(text.count("public_base:"), 1)
            self.assertIn("https://b.in", text)


class TestCli(unittest.TestCase):
    def test_prints_sheet_and_saves_site(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\nbrand:\n  handle: gharvanaa\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_app(cfg, ["--site", "https://gharvanaa.in"]), 0)
            out = buf.getvalue()
            self.assertIn("Site saved", out)
            self.assertIn("https://gharvanaa.in/about", out)
            self.assertEqual(yaml.safe_load(f.read_text())["link"]["public_base"],
                             "https://gharvanaa.in")

    def test_equals_form_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_app(cfg, ["--site=https://x.in"])
            self.assertIn("https://x.in", f.read_text())

    def test_bad_site_reports_and_still_prints_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_app(cfg, ["--site", "nope"]), 0)
            self.assertIn("❌", buf.getvalue())
            self.assertIn("CONNECT APP", buf.getvalue())

    def test_repo_config_untouched(self):
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        before = repo.read_text()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("link:\n  public_base: \"\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_app(cfg, ["--site", "https://x.in"])
        self.assertEqual(repo.read_text(), before)

    def test_dispatch_and_help(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn('if cmd in ("app", "app-form", "appform")', src)
        self.assertIn("python -m bot app", src)


class TestUpgradePack(unittest.TestCase):
    """R62: the standard-access request is the gate to PUBLIC pins."""

    def test_explains_why_trial_is_not_enough(self):
        text = "\n".join(appform.upgrade_lines(_cfg(Path("/tmp"))))
        self.assertIn("visible only to the user", text)
        self.assertIn("Standard", text)
        self.assertIn("public", text.lower())

    def test_scope_justification_covers_every_requested_scope(self):
        text = "\n".join(appform.upgrade_lines(_cfg(Path("/tmp"))))
        for scope in ("boards:read", "boards:write", "pins:read", "pins:write",
                      "user_accounts:read"):
            self.assertIn(scope, text, scope)

    def test_uses_the_configured_urls(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), link={"public_base": "https://gharvanaa.in"})
            text = "\n".join(appform.upgrade_lines(cfg))
            self.assertIn("https://gharvanaa.in/about", text)
            self.assertIn("https://gharvanaa.in/privacy", text)

    def test_pre_submit_checklist_is_present(self):
        text = "\n".join(appform.upgrade_lines(_cfg(Path("/tmp"))))
        self.assertIn("BEFORE YOU SUBMIT", text)
        self.assertIn("deploy.sh", text)
        self.assertIn("bot doctor", text)

    def test_never_raises_without_config(self):
        self.assertIn("STANDARD ACCESS", "\n".join(appform.upgrade_lines()))

    def test_main_sheet_points_at_it(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        self.assertIn("bot app --upgrade", text)


class TestTrialToken(unittest.TestCase):
    """R62: the dashboard trial token must be usable before app approval."""

    def _api(self, tmp, **env):
        import os
        from bot.pinterest_api import PinterestAPI
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None
                                 else os.environ.update({k: v})
                                 for k, v in old.items()])
        cfg = _cfg(tmp)
        cfg.raw["pinterest"] = {"redirect_uri": "http://localhost:8888/callback"}
        return PinterestAPI(cfg)

    def test_trial_token_makes_the_api_configured(self):
        with tempfile.TemporaryDirectory() as d:
            api = self._api(Path(d), PINTEREST_ACCESS_TOKEN="tok-123",
                            PINTEREST_APP_ID="1613412")
            self.assertTrue(api.configured)
            self.assertEqual(api.ensure_access_token(), "tok-123")
            self.assertEqual(api.auth_mode, "trial token (dashboard)")

    def test_oauth_still_wins_when_a_refresh_token_exists(self):
        with tempfile.TemporaryDirectory() as d:
            api = self._api(Path(d), PINTEREST_ACCESS_TOKEN="tok-123",
                            PINTEREST_REFRESH_TOKEN="refresh-abc")
            self.assertEqual(api.auth_mode, "oauth refresh token")

    def test_no_credentials_reports_not_connected(self):
        with tempfile.TemporaryDirectory() as d:
            api = self._api(Path(d))
            self.assertFalse(api.configured)
            self.assertEqual(api.auth_mode, "not connected")

    def test_doctor_and_ready_know_about_the_trial_token(self):
        src_main = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        src_ready = (Path(__file__).resolve().parents[1] / "bot" / "ready.py").read_text()
        self.assertIn("trial token in .env", src_main)
        self.assertIn("trial token in .env", src_ready)

    def test_env_example_documents_the_trial_token(self):
        env = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
        self.assertIn("PINTEREST_ACCESS_TOKEN", env)
        self.assertIn("Trial", env)

class TestPendingState(unittest.TestCase):
    """R64: a greyed-out field is Pinterest's lock, not the owner's mistake."""

    def test_says_what_is_locked_and_what_is_not(self):
        text = "\n".join(appform.pending_lines(_cfg(Path("/tmp"))))
        self.assertIn("App secret", text)
        self.assertIn("Redirect URLs", text)
        self.assertIn("cheyyaledu", text)           # it is not their mistake
        self.assertIn("Generate token", text)        # what they CAN do now

    def test_lists_the_immediate_work_that_is_not_blocked(self):
        text = "\n".join(appform.pending_lines(_cfg(Path("/tmp"))))
        for needle in ("PINTEREST_ACCESS_TOKEN", "token-check", "Amazon tag",
                       "deploy"):
            self.assertIn(needle, text, needle)

    def test_unlock_steps_are_in_order(self):
        text = "\n".join(appform.pending_lines(_cfg(Path("/tmp"))))
        self.assertIn("auth-url", text)
        self.assertIn("app --upgrade", text)
        self.assertLess(text.index("auth-url"), text.index("--upgrade"))

    def test_order_does_not_block_the_workflow(self):
        text = "\n".join(appform.pending_lines(_cfg(Path("/tmp"))))
        self.assertIn("Order mukhyam kaadu", text)

    def test_where_helper_explains_the_greyed_field(self):
        text = "\n".join(appform.where_lines(_cfg(Path("/tmp"))))
        self.assertIn("GREY", text)
        self.assertIn("app --pending", text)

    def test_cli_pending_flag(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_app(cfg, ["--pending"]), 0)
            self.assertIn("TRIAL ACCESS PENDING", buf.getvalue())

    def test_sheet_mentions_the_pending_state(self):
        text = "\n".join(appform.lines(_cfg(Path("/tmp"))))
        self.assertIn("Trial", text)

    def test_help_lists_pending(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn("python -m bot app --pending", src)


if __name__ == "__main__":
    unittest.main()
