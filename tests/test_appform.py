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


if __name__ == "__main__":
    unittest.main()
