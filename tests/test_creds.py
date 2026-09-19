"""R65: credential intake — validate, classify and save .env safely."""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from bot import creds
from bot.main import cmd_creds


def _read(path: Path) -> str:
    return path.read_text()


class TestAmazonTag(unittest.TestCase):
    def test_owner_tag_is_valid(self):
        res = creds.validate_amazon_tag("mama086-21")
        self.assertTrue(res["ok"])
        self.assertEqual(res["tag"], "mama086-21")
        self.assertNotIn("warn", res)

    def test_quotes_and_spaces_are_stripped(self):
        self.assertEqual(creds.validate_amazon_tag("  'mama086-21' ")["tag"],
                         "mama086-21")

    def test_wrong_shapes_are_refused(self):
        for bad in ("", "mama086", "mama086-", "-21", "mama 086-21", "a-2"):
            self.assertFalse(creds.validate_amazon_tag(bad)["ok"], bad)

    def test_non_india_region_warns_but_accepts(self):
        res = creds.validate_amazon_tag("mama086-20")
        self.assertTrue(res["ok"])
        self.assertIn("warn", res)


class TestEarnkaro(unittest.TestCase):
    OWNER_REFERRAL = "https://earnkaro.com?r=5478322&fname=Charan Pendota"

    def test_owner_link_is_a_referral_not_a_prefix(self):
        res = creds.classify_earnkaro(self.OWNER_REFERRAL)
        self.assertEqual(res["kind"], "referral")
        self.assertFalse(res["ok"])
        self.assertEqual(res["ref"], "5478322")
        self.assertIn("commission raadu", res["reason"])
        self.assertIn("ekaro.in", res["fix"])

    def test_deeplink_prefix_is_accepted(self):
        for good in ("https://ekaro.in/enkr20260101s123456",
                     "https://ekaro.in/enkr20260101s123456/",
                     "https://earnkaro.com/deal/abc123"):
            res = creds.classify_earnkaro(good)
            self.assertTrue(res["ok"], good)
            self.assertEqual(res["kind"], "prefix")
            self.assertTrue(res["prefix"])

    def test_already_converted_product_link_is_explained(self):
        res = creds.classify_earnkaro("https://ekaro.in/link?url=https%3A%2F%2Fm.com")
        self.assertFalse(res["ok"])
        self.assertIn("already-converted", res["reason"])

    def test_unrelated_url_is_refused(self):
        res = creds.classify_earnkaro("https://example.com/abc")
        self.assertEqual(res["kind"], "unknown")
        self.assertFalse(res["ok"])

    def test_empty(self):
        self.assertEqual(creds.classify_earnkaro("")["kind"], "empty")


class TestMeesho(unittest.TestCase):
    def test_owner_af_invite_accepted(self):
        res = creds.validate_meesho(
            "https://www.meesho.com/af_invite/PUB:instagram_stories:C1?p_id=1")
        self.assertTrue(res["ok"])

    def test_middleman_wrapped_link_is_refused(self):
        res = creds.validate_meesho("https://ekaro.in/enkr123?url=meesho.com/x")
        self.assertFalse(res["ok"])
        self.assertIn("middleman", res["error"])

    def test_junk_refused(self):
        self.assertFalse(creds.validate_meesho("https://example.com")["ok"])


class TestApply(unittest.TestCase):
    def test_valid_saved_invalid_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            env = tmp / ".env"
            env.write_text("# secrets\nAMAZON_TAG=\nEARNKARO_PREFIX=\n")
            res = creds.apply_credentials(
                [("AMAZON_TAG", "mama086-21"),
                 ("EARNKARO_PREFIX", "https://earnkaro.com?r=5478322")], env)
            kinds = {r["key"]: r["ok"] for r in res["results"]}
            self.assertTrue(kinds["AMAZON_TAG"])
            self.assertFalse(kinds["EARNKARO_PREFIX"])
            text = _read(env)
            self.assertIn("AMAZON_TAG=mama086-21", text)
            self.assertIn("# secrets", text)          # comments preserved
            self.assertNotIn("earnkaro.com?r=", text)

    def test_existing_comment_on_the_line_survives(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=old-21  # my tag\n")
            creds.save_env({"AMAZON_TAG": "mama086-21"}, env)
            text = _read(env)
            self.assertIn("mama086-21", text)
            self.assertIn("# my tag", text)
            self.assertEqual(text.count("AMAZON_TAG="), 1)

    def test_missing_file_is_created_from_the_example(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / ".env.example").write_text("# example\nAMAZON_TAG=\n")
            env = tmp / ".env"
            res = creds.save_env({"AMAZON_TAG": "mama086-21"}, env)
            self.assertTrue(res["saved"])
            self.assertIn("# example", _read(env))
            self.assertIn("AMAZON_TAG=mama086-21", _read(env))

    def test_file_permissions_are_locked_down(self):
        if os.name == "nt":
            self.skipTest("posix permissions only")
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=\n")
            creds.save_env({"AMAZON_TAG": "mama086-21"}, env)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_unknown_key_is_refused_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=\n")
            res = creds.apply_credentials([("SECRET_HACK", "x")], env)
            self.assertFalse(res["results"][0]["ok"])
            self.assertNotIn("SECRET_HACK", _read(env))

    def test_passthrough_tokens_are_saved(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("PINTEREST_ACCESS_TOKEN=\n")
            res = creds.apply_credentials(
                [("PINTEREST_ACCESS_TOKEN", "tok-abc")], env)
            self.assertTrue(res["results"][0]["ok"])
            self.assertIn("PINTEREST_ACCESS_TOKEN=tok-abc", _read(env))

    def test_empty_values_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=\n")
            res = creds.apply_credentials([("AMAZON_TAG", "   ")], env)
            self.assertEqual(res["results"], [])
            self.assertFalse(res["saved"]["saved"])


class TestStatus(unittest.TestCase):
    def _clean_env(self):
        keys = ("AMAZON_TAG", "MEESHO_TEMPLATE_LINK", "EARNKARO_PREFIX",
                "MEESHO_AFFID", "PINTEREST_APP_ID", "PINTEREST_ACCESS_TOKEN")
        old = {k: os.environ.get(k) for k in keys}
        for k in keys:
            os.environ.pop(k, None)
        def restore():
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)

    def test_reports_each_credential(self):
        self._clean_env()
        os.environ["AMAZON_TAG"] = "mama086-21"
        text = "\n".join(creds.status_lines())
        self.assertIn("mama086-21", text)
        self.assertIn("Amazon pins: tag 'mama086-21'", text)

    def test_missing_meesho_warns_about_the_middleman(self):
        self._clean_env()
        text = "\n".join(creds.status_lines())
        self.assertIn("middleman", text)
        self.assertIn("affiliate.meesho.com", text)

    def test_never_raises_on_broken_config(self):
        self._clean_env()

        class Boom:
            def get(self, *a, **k):
                raise RuntimeError("bad config")

        self.assertIn("CREDENTIALS STATUS", "\n".join(creds.status_lines(Boom())))


class TestCli(unittest.TestCase):
    def test_cli_saves_and_explains(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=\n")
            import bot.creds as c
            old = c.env_path
            c.env_path = lambda: env
            self.addCleanup(lambda: setattr(c, "env_path", old))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_creds(None, ["--amazon", "mama086-21",
                                                  "--earnkaro",
                                                  "https://earnkaro.com?r=5478322"]), 0)
            out = buf.getvalue()
            self.assertIn("AMAZON_TAG saved", out)
            self.assertIn("NOT saved", out)
            self.assertIn("referral", out)
            self.assertIn("mama086-21", env.read_text())

    def test_cli_equals_form(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=\n")
            import bot.creds as c
            old = c.env_path
            c.env_path = lambda: env
            self.addCleanup(lambda: setattr(c, "env_path", old))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_creds(None, ["--amazon=mama086-21"])
            self.assertIn("mama086-21", env.read_text())

    def test_status_only_mode_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("AMAZON_TAG=keep-21\n")
            import bot.creds as c
            old = c.env_path
            c.env_path = lambda: env
            self.addCleanup(lambda: setattr(c, "env_path", old))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_creds(None, [])
            self.assertEqual(env.read_text(), "AMAZON_TAG=keep-21\n")

    def test_dispatch_and_help_wired(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn('if cmd in ("creds", "credentials", "keys")', src)
        self.assertIn("python -m bot creds", src)

class TestQaReadsTheEnvTag(unittest.TestCase):
    """R65: the QA revenue-leak check must see the tag that lives in .env.

    Before this fix it read only `affiliate.amazon_tag` from config.yaml, so with
    the owner's tag in .env the Amazon check silently passed everything.
    """

    def _run(self, link, source, wrapper="earnkaro"):
        import os
        import tempfile
        from unittest import mock
        from PIL import Image
        from bot.config import Config
        from bot.db import DB
        from bot.qa import qa_pin
        tmp = Path(tempfile.mkdtemp())
        (tmp / "m").mkdir()
        img = tmp / "m" / "p.jpg"
        Image.new("RGB", (300, 400), "white").save(img)
        cfg = Config(raw={"storage": {"db_path": f"{tmp}/q.db",
                                      "media_dir": f"{tmp}/m"},
                          "design": {"brand_name": "Gharvanaa"},
                          "affiliate": {"amazon_tag": "",
                                        "default_wrapper": wrapper}})
        db = DB(cfg.db_path)
        desc = ("Verified deal khoj — kitchen storage organizer rack for home "
                "and office. Strong build, easy setup, limited stock." * 2)
        product = {"id": 1, "title": "Kitchen Storage Organizer Rack for Home",
                   "price": "399", "source": source, "affiliate_url": link,
                   "pin_image": "p.jpg"}
        with mock.patch.dict(os.environ, {"AMAZON_TAG": "mama086-21"}):
            ok, issues = qa_pin(cfg, db, product,
                                "Kitchen Storage Organizer Rack", desc,
                                str(img), link)
        return ok, issues

    def test_untagged_amazon_link_is_flagged_from_the_env_tag(self):
        ok, issues = self._run("https://www.amazon.in/dp/B08N2Z7R1L", "amazon")
        self.assertFalse(ok)
        self.assertTrue(any("affiliate tag" in i for i in issues), issues)

    def test_tagged_amazon_link_passes_the_tag_check(self):
        ok, issues = self._run(
            "https://www.amazon.in/dp/B08N2Z7R1L?tag=mama086-21", "amazon")
        self.assertFalse(any("affiliate tag" in i for i in issues), issues)

    def test_untracked_flipkart_link_is_quarantined(self):
        ok, issues = self._run("https://www.flipkart.com/x/p/itm1", "flipkart")
        self.assertFalse(ok)
        self.assertTrue(any("COMMISSION LEAK" in i for i in issues), issues)

    def test_earnkaro_wrapped_link_stops_the_leak_warning(self):
        ok, issues = self._run(
            "https://ekaro.in/enkr123?url=https%3A%2F%2Fwww.flipkart.com%2Fx",
            "flipkart")
        self.assertFalse(any("COMMISSION LEAK" in i for i in issues), issues)


if __name__ == "__main__":
    unittest.main()
