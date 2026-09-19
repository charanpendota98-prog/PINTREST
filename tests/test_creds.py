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


class TestMeeshoCollectionLink(unittest.TestCase):
    """R66b: the owner's own collection link is honoured, verbatim, from .env."""

    OWNER = "https://affiliate.meesho.com/collection/MTEwNDEyMjY6Ojo6Ojpub3JtYWw="

    def test_owner_link_is_accepted(self):
        res = creds.validate_meesho_collection(self.OWNER)
        self.assertTrue(res["ok"])
        self.assertEqual(res["link"], self.OWNER)

    def test_earnkaro_wrapped_collection_is_refused(self):
        res = creds.validate_meesho_collection(
            "https://earnkaro.com/go?url=affiliate.meesho.com/collection/x")
        self.assertFalse(res["ok"])

    def test_random_url_is_refused_with_fix(self):
        res = creds.validate_meesho_collection("https://example.com/deals")
        self.assertFalse(res["ok"])
        self.assertIn("affiliate.meesho.com", res["fix"])

    def test_saved_into_env_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("# keep me\nMEESHO_TEMPLATE_LINK=x\n")
            out = creds.apply_credentials([("MEESHO_COLLECTION_LINK", self.OWNER)],
                                          path=env)
            self.assertTrue(out["results"][0]["ok"])
            text = env.read_text()
            self.assertIn(f"MEESHO_COLLECTION_LINK={self.OWNER}", text)
            self.assertIn("# keep me", text)

    def test_status_board_lists_the_collection_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            creds.save_env({"MEESHO_COLLECTION_LINK": self.OWNER}, path=env)
            text = "\n".join(creds.status_lines())
        self.assertIn("Meesho collection", text)


class TestMeeshoPlatformOverride(unittest.TestCase):
    """R67: each Meesho surface has its OWN token; Pinterest has none."""

    # owner's real links (R34/R38 recovering campaigns + R67 fresh ones)
    LINKS = ("https://www.meesho.com/af_invite/24197020:instagram_stories:11075346,"
             "https://www.meesho.com/af_invite/24197020:facebook:11075421,"
             "https://www.meesho.com/af_invite/"
             "24197020:instagram_product_tag:11173806?p_id=1&ext_id=a,"
             "https://www.meesho.com/af_invite/"
             "24197020:instagram_product_tag:11173869?p_id=1&ext_id=a,"
             "https://www.meesho.com/af_invite/24197020:facebook:11173912,"
             "https://www.meesho.com/af_invite/"
             "24197020:youtube_long_form:11173971,"
             "https://www.meesho.com/af_invite/"
             "24197020:instagram_stories:11174107")

    def _linker(self):
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def __init__(self, d):
                self.d = d

            def get(self, key, default=None):
                return self.d.get(key, default)

        cfg = Cfg({"affiliate.meesho_template_link": self.LINKS,
                   "affiliate.meesho_platform_tokens": {
                       "pinterest": "instagram_stories",
                       "instagram": "instagram_product_tag",
                       "instagram_stories": "instagram_stories",
                       "youtube": "youtube_long_form"}})
        return AffiliateLinker(cfg)

    def test_each_platform_gets_its_own_token(self):
        lk = self._linker()
        self.assertEqual(lk.meesho_source_for("instagram"), "instagram_product_tag")
        self.assertEqual(lk.meesho_source_for("instagram_stories"), "instagram_stories")
        self.assertEqual(lk.meesho_source_for("facebook"), "facebook")
        self.assertEqual(lk.meesho_source_for("youtube"), "youtube_long_form")

    def test_newest_campaign_per_token_wins(self):
        lk = self._linker()
        ig = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "instagram")
        self.assertIn(":instagram_product_tag:11173869", ig)   # not 11173806
        fb = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "facebook")
        self.assertIn(":facebook:11173912", fb)                # not 11075421
        st = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "instagram_stories")
        self.assertIn(":instagram_stories:11174107", st)       # not 11075346

    def test_youtube_uses_the_long_form_token(self):
        lk = self._linker()
        link = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "youtube")
        self.assertIn("24197020:youtube_long_form:11173971", link)
        self.assertIn("utm_source=youtube_long_form", link)

    def test_pinterest_uses_the_override(self):
        lk = self._linker()
        self.assertEqual(lk.meesho_source_for("pinterest"), "instagram_stories")
        link = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "pinterest")
        self.assertIn("24197020:instagram_stories:11174107", link)

    def test_unknown_surface_still_lands_on_the_owner_account(self):
        lk = self._linker()
        link = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", "telegram")
        self.assertIn("/af_invite/24197020:", link)

    def test_stories_token_present_without_override(self):
        # even if the override map is empty, 'instagram' must not steal the
        # story surface's own token name when asked for it explicitly
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def __init__(self, d):
                self.d = d

            def get(self, key, default=None):
                return self.d.get(key, default)

        lk = AffiliateLinker(Cfg({"affiliate.meesho_template_link": self.LINKS}))
        self.assertEqual(lk.meesho_source_for("instagram_stories"), "instagram_stories")
        self.assertEqual(lk.meesho_source_for("youtube"), "youtube_long_form")

    def test_publisher_id_never_changes(self):
        lk = self._linker()
        for platform in ("instagram", "facebook", "pinterest", "youtube"):
            link = lk.meesho_link_for("https://www.meesho.com/x/p/1k1b6", platform)
            self.assertIn("/af_invite/24197020:", link, platform)


class TestMeeshoLinkCorrectness(unittest.TestCase):
    """R68: deep-probe findings — never build a product-less link, and survive
    HTML-escaped pastes (`&amp;` is how browsers/WhatsApp deliver links)."""

    PRODUCT = "https://www.meesho.com/women-kurta/p/1k1b6"
    TEMPLATE = ("https://www.meesho.com/af_invite/"
                "24197020:instagram_stories:11174107"
                "?p_id=82595628&ext_id=1d6b70&utm_source=instagram_stories")

    def _linker(self, template=None):
        import os
        from unittest import mock
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def __init__(self, d):
                self.d = d

            def get(self, key, default=None):
                return self.d.get(key, default)

        env = mock.patch.dict(os.environ, {"MEESHO_TEMPLATE_LINK": template or ""})
        env.start()
        self.addCleanup(env.stop)
        return AffiliateLinker(Cfg({"affiliate.meesho_template_link": template or ""}))

    def test_no_product_id_never_builds_an_af_invite_link(self):
        lk = self._linker(self.TEMPLATE)
        for bad in ("https://www.meesho.com/search?q=kurta",
                    "https://www.meesho.com/",
                    "https://www.meesho.com/women-kurta/p/"):
            self.assertEqual(lk.meesho_link_for(bad, "instagram"), "", bad)

    def test_real_product_url_still_builds_with_pid(self):
        lk = self._linker(self.TEMPLATE)
        out = lk.meesho_link_for(self.PRODUCT, "instagram")
        self.assertIn("p_id=1k1b6", out)
        self.assertIn("24197020:instagram_stories:11174107", out)
        # R69: BOTH ids are the product's own code — Meesho resolves the
        # landing page from ext_id, a random one 404s.
        self.assertIn("ext_id=1k1b6", out)

    def test_html_escaped_link_is_normalised_not_shredded(self):
        escaped = self.TEMPLATE.replace("&", "&amp;")
        lk = self._linker(escaped)
        links = lk.meesho_template_links
        self.assertEqual(len(links), 1, links)          # one link, not three
        self.assertNotIn("&amp;", links[0])
        self.assertEqual(len(lk.meesho_template_links), 1)
        built = lk.meesho_link_for(self.PRODUCT, "instagram")
        self.assertIn("p_id=1k1b6", built)
        self.assertNotIn("amp;", built)

    def test_qa_gate_quarantines_a_pid_less_af_invite_link(self):
        import tempfile
        from pathlib import Path
        from PIL import Image
        from unittest import mock
        from bot.config import load_config
        from bot.db import DB
        from bot import qa

        with mock.patch.dict("os.environ" and __import__("os").environ,
                             {"AMAZON_TAG": ""}, clear=False):
            cfg = load_config()
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            db = DB(f"{tmp.name}/t.db")
            img = Path(tmp.name) / "p.jpg"
            _pin_like(img)
            prod = {"id": 1, "source": "meesho",
                    "title": "Floral Printed Kurta Set for Women"}
            seo_t = "Floral Printed Kurta Set for Women | best deal 2026"
            seo_d = ("Floral printed kurta set for women — soft rayon, all sizes. "
                     "Grab this offer today from Meesho! #ad")
            ok, issues = qa.qa_pin(
                cfg, db, prod, seo_t, seo_d, str(img),
                "https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
                "?ext_id=abc123&utm_source=instagram_stories")
            self.assertFalse(ok)
            self.assertTrue(any("p_id" in i for i in issues), issues)

            ok2, issues2 = qa.qa_pin(
                cfg, db, prod, seo_t, seo_d, str(img),
                "https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
                "?p_id=1k1b6&ext_id=abc123&utm_source=instagram_stories")
            self.assertFalse(any("p_id" in i for i in issues2), issues2)


class TestMeeshoLandingCheck(unittest.TestCase):
    """R69: the only check that would have caught the ext_id bug — asking
    Meesho what the link actually opens."""

    def _linker(self):
        import os
        from unittest import mock
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def get(self, key, default=None):
                return default

        env = mock.patch.dict(os.environ, {"MEESHO_TEMPLATE_LINK": ""})
        env.start()
        self.addCleanup(env.stop)
        return AffiliateLinker(Cfg())

    def test_landing_true_false_and_unknown(self):
        from unittest import mock

        class Resp:
            def __init__(self, url, text, code=200):
                self.url, self.text, self.status_code = url, text, code

        lk = self._linker()
        link = "https://www.meesho.com/af_invite/24197020:facebook:1?p_id=1k1b6&ext_id=1k1b6"
        with mock.patch("requests.get", return_value=Resp(
                "https://www.meesho.com/s/p/1k1b6", "<title>Kurti | Meesho</title>")):
            self.assertTrue(lk.meesho_landing_ok(link))
        with mock.patch("requests.get", return_value=Resp(
                "https://www.meesho.com/s/p/zzzzzz", "<title>Not Found page</title>")):
            self.assertFalse(lk.meesho_landing_ok(link))
        with mock.patch("requests.get", return_value=Resp(
                "https://www.meesho.com/s/p", "<title>Not Found page</title>")):
            self.assertFalse(lk.meesho_landing_ok(link))
        with mock.patch("requests.get", side_effect=Exception("no net")):
            self.assertIsNone(lk.meesho_landing_ok(link))     # fail-open
        # never touches the network for a non-Meesho link
        self.assertIsNone(lk.meesho_landing_ok("https://www.amazon.in/dp/B0?tag=x"))

    def test_qa_quarantines_a_definitively_broken_landing(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from PIL import Image
        from bot.config import load_config
        from bot.db import DB
        from bot import qa

        cfg = load_config()
        cfg.raw.setdefault("link", {})["verify_meesho_landing"] = True
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = DB(f"{tmp.name}/t.db")
        img = Path(tmp.name) / "p.jpg"
        Image.new("RGB", (800, 1200), "white").save(img)
        prod = {"id": 1, "source": "meesho", "title": "Floral Printed Kurta Set"}
        seo_t = "Floral Printed Kurta Set | best deal 2026"
        seo_d = ("Floral printed kurta set — soft rayon, all sizes. Grab today! #ad")

        class Resp:
            def __init__(self, url, text, code=200):
                self.url, self.text, self.status_code = url, text, code

        link = ("https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
                "?p_id=1k1b6&ext_id=1k1b6&utm_source=instagram_stories")
        with mock.patch("requests.get", return_value=Resp(
                "https://www.meesho.com/s/p/zzzzzz", "<title>Not Found page</title>")):
            ok, issues = qa.qa_pin(cfg, db, prod, seo_t, seo_d, str(img), link)
        self.assertFalse(ok)
        self.assertTrue(any("landing FAILED" in i for i in issues), issues)

        with mock.patch("requests.get", side_effect=Exception("no net")):
            ok2, issues2 = qa.qa_pin(cfg, db, prod, seo_t, seo_d, str(img), link)
        self.assertFalse(any("landing FAILED" in i for i in issues2), issues2)


class TestMeeshoPasteHygiene(unittest.TestCase):
    def test_html_escaped_paste_is_cleaned_before_saving(self):
        escaped = ("https://www.meesho.com/af_invite/24197020:facebook:11173912"
                   "?p_id=82595628&amp;ext_id=1d6b70&amp;utm_source=facebook")
        res = creds.validate_meesho(escaped)
        self.assertTrue(res["ok"])
        self.assertNotIn("&amp;", res["link"])
        self.assertIn("&ext_id=1d6b70", res["link"])


class TestMeeshoLandingProbeDetail(unittest.TestCase):
    """R70: the probe must explain WHY (ad-blocker vs real 404)."""

    def test_probe_reports_final_url_and_title(self):
        from unittest import mock
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def get(self, key, default=None):
                return default

        class Resp:
            url = "https://www.meesho.com/s/p/35pwo2?product_id=35pwo2"
            text = "<html><title>Black Embroidered Rayon Kurti | Meesho</title></html>"
            status_code = 200

        with mock.patch("requests.get", return_value=Resp()):
            pr = AffiliateLinker(Cfg()).meesho_landing_probe(
                "https://www.meesho.com/af_invite/24197020:facebook:1?p_id=35pwo2&ext_id=35pwo2")
        self.assertTrue(pr["ok"])
        self.assertIn("/s/p/35pwo2", pr["url"])
        self.assertIn("Kurti", pr["title"])
        self.assertEqual(pr["reason"], "lands on a product page")

    def test_probe_never_claims_a_verdict_when_offline(self):
        from unittest import mock
        from bot.affiliate import AffiliateLinker

        class Cfg:
            amazon_tag = ""

            def get(self, key, default=None):
                return default

        with mock.patch("requests.get", side_effect=Exception("dns")):
            pr = AffiliateLinker(Cfg()).meesho_landing_probe(
                "https://www.meesho.com/af_invite/24197020:facebook:1?p_id=1&ext_id=1")
        self.assertIsNone(pr["ok"])
        self.assertIn("dns", pr["reason"])


def _pin_like(path, size=(1000, 1500)):
    """Non-blank stand-in for a DESIGNED pin (QA rejects blank media now)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle((60, 60, size[0] - 60, size[1] - 420), fill=(38, 38, 58))
    d.rectangle((80, size[1] - 320, size[0] - 80, size[1] - 160),
                fill=(200, 30, 60))
    im.save(path)


class TestMeeshoAttribution(unittest.TestCase):
    """R73 — the owner's phone test showed Meesho carrying the affiliate id in
    `c=<publisher>:<token>:<campaign>`; a landing WITHOUT it = leak risk."""

    def test_attribution_markers(self):
        from bot.affiliate import AffiliateLinker as L
        link = ("https://www.meesho.com/af_invite/24197020:instagram_stories:"
                "11174107?utm_source=instagram_stories&p_id=21cuip&ext_id=21cuip")
        self.assertTrue(L.meesho_attribution_ok(
            "https://www.meesho.com/s/p/21cuip?c=24197020:instagram_stories:11174107", link))
        self.assertTrue(L.meesho_attribution_ok(
            "https://www.meesho.com/s/p/1d6b70?pid=meesho_affiliate_portal&x=1", link))
        self.assertFalse(L.meesho_attribution_ok(
            "https://www.meesho.com/s/p/21cuip?product_id=21cuip", link))
        self.assertFalse(L.meesho_attribution_ok("", link))

    def test_probe_reports_attribution_field(self):
        from bot.affiliate import AffiliateLinker
        probe = AffiliateLinker.meesho_landing_probe
        # offline sandbox: probe must fail open and still carry the field
        import bot.config as C
        cfg = C.Config(raw={"affiliate": {"meesho_affid": "24197020"}})
        out = AffiliateLinker(cfg).meesho_landing_probe(
            "https://www.meesho.com/af_invite/24197020:instagram_stories:11174107"
            "?p_id=21cuip&ext_id=21cuip", timeout=1)
        self.assertIn("attributed", out)


class TestTelegramControl(unittest.TestCase):
    """R74 — phone nunchi machine ni control cheyyadam (two-way Telegram)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        from bot.config import Config
        from bot.db import DB
        self.cfg = Config(raw={
            "storage": {"db_path": f"{self.tmp.name}/t.db", "media_dir": f"{self.tmp.name}/m"},
            "affiliate": {"amazon_tag": "x-21", "meesho_affid": "24197020"}})
        self.db = DB(self.cfg.get("storage.db_path"))

    def tearDown(self):
        self.tmp.cleanup()

    def _ctl(self):
        from bot.tgcontrol import TelegramControl
        return TelegramControl(self.cfg, db=self.db)

    def test_parse_command(self):
        from bot.tgcontrol import parse_command
        self.assertEqual(parse_command("/link https://x y"), ("link", ["https://x", "y"]))
        self.assertEqual(parse_command("/Deals@GharvanaaBot 3"), ("deals", ["3"]))
        self.assertEqual(parse_command("hello"), ("hello", []))
        self.assertEqual(parse_command(""), ("", []))

    def test_help_and_unknown(self):
        ctl = self._ctl()
        self.assertIn("/status", ctl.reply("/help"))
        self.assertIn("Teliyani command", ctl.reply("/nonsense"))

    def test_status_reports_queue_and_pauses(self):
        self.db.add_product(url="https://x/p/1", title="t", source="meesho")
        out = self._ctl().reply("/status")
        self.assertIn("queue 1", out)
        self.assertIn("running", out)

    def test_pause_and_resume_from_phone(self):
        ctl = self._ctl()
        self.assertIn("Paused", ctl.reply("/pause 2"))
        from bot import control
        self.assertTrue(control.is_paused(self.db).get("paused"))
        self.assertIn("resumed", ctl.reply("/resume").lower())
        self.assertFalse(control.is_paused(self.db).get("paused"))

    def test_post_requires_a_url(self):
        self.assertIn("Usage", self._ctl().reply("/post"))
        self.assertIn("http", self._ctl().reply("/post notaurl"))

    def test_deals_lists_posted_products_with_links(self):
        pid = self.db.add_product(url="https://www.meesho.com/kurti/p/35pwo2",
                                  title="Black Kurti", source="meesho",
                                  affiliate_url="https://www.meesho.com/af_invite/x")
        self.db.update_product(pid, status="posted")
        out = self._ctl().reply("/deals 3")
        self.assertIn("Black Kurti", out)
        self.assertIn("af_invite", out)

    def test_link_command_builds_surface_links(self):
        import os
        from bot.config import load_config
        old = os.environ.get("MEESHO_TEMPLATE_LINK")
        os.environ["MEESHO_TEMPLATE_LINK"] = (
            "https://www.meesho.com/af_invite/24197020:instagram_stories:11174107,"
            "https://www.meesho.com/af_invite/24197020:facebook:11173912")
        try:
            from bot.tgcontrol import TelegramControl
            ctl = TelegramControl(load_config(), db=self.db)
            out = ctl.reply("/link https://www.meesho.com/kurti-rayon/p/35pwo2")
            self.assertIn("ext_id=35pwo2", out)
        finally:
            if old is None:
                os.environ.pop("MEESHO_TEMPLATE_LINK", None)
            else:
                os.environ["MEESHO_TEMPLATE_LINK"] = old

    def test_surfaces_lists_five(self):
        out = self._ctl().reply("/surfaces")
        for name in ("Pinterest", "Instagram", "Facebook", "YouTube", "Telegram"):
            self.assertIn(name, out)

    def test_only_owner_chat_is_obeyed(self):
        import os
        from unittest import mock
        from bot.config import Config
        cfg = Config(raw={"storage": {"db_path": f"{self.tmp.name}/t2.db"}})
        with mock.patch.dict(os.environ, {"TELEGRAM_CHAT_ID": "999",
                                          "TELEGRAM_TOKEN": "tok"}):
            from bot.tgcontrol import TelegramControl
            ctl = TelegramControl(cfg, db=self.db)
            self.assertEqual(ctl.owner, "999")
            updates = {"ok": True, "result": [
                {"update_id": 5, "message": {"chat": {"id": 111}, "text": "/status"}},
                {"update_id": 6, "message": {"chat": {"id": 999}, "text": "/help"}},
            ]}
            class _Resp:
                status_code = 200
                def json(self):
                    return updates
            ctl.notify.token = "tok"
            with mock.patch("requests.get", return_value=_Resp()), \
                 mock.patch.object(ctl.notify, "send_to", return_value=True) as sent:
                n = ctl.poll_once(timeout=1)
            self.assertEqual(n, 1)                       # only the owner's
            self.assertEqual(sent.call_args.args[0], "999")


class TestPerSurfaceRecords(unittest.TestCase):
    """R74 — every surface a product was posted to is recorded."""

    def test_surface_counts(self):
        import tempfile
        from bot.db import DB
        with tempfile.TemporaryDirectory() as tmp:
            db = DB(f"{tmp}/t.db")
            pid = db.add_product(url="https://x/p/1", title="t", source="meesho")
            db.add_post(product_id=pid, status="posted", platform="instagram",
                        posted_at="2026-09-19T10:00:00")
            db.add_post(product_id=pid, status="posted", platform="telegram",
                        posted_at="2026-09-19T10:00:01")
            db.add_post(product_id=pid, status="posted")          # pinterest default
            counts = db.surface_counts()
            self.assertEqual(counts["instagram"], 1)
            self.assertEqual(counts["telegram"], 1)
            self.assertEqual(counts["pinterest"], 1)

    def test_deal_card_carries_real_numbers(self):
        from bot.notify import Notifier
        n = Notifier()
        n.token, n.deals_channel = "tok", "@ch"
        calls = {}

        class _Resp:
            status_code = 200
        def fake_post(url, data=None, timeout=None, **kw):
            calls.update(data or {})
            return _Resp()
        import bot.notify as mod
        orig = mod.requests.post
        mod.requests.post = fake_post
        try:
            ok = n.deal("Black Kurti", "₹200", "https://l", "https://img",
                        discount=40, rating=4.0, reviews=136104, source="meesho")
        finally:
            mod.requests.post = orig
        self.assertTrue(ok)
        cap = calls.get("caption", "")
        self.assertIn("40% OFF", cap)
        self.assertIn("4.0★", cap)
        self.assertIn("1.36L ratings", cap)
        self.assertIn("Meesho", cap)

    def test_deal_returns_false_when_not_configured(self):
        from bot.notify import Notifier
        self.assertFalse(Notifier().deal("t", "₹1", "https://l"))


class TestTelegramControlAutostart(unittest.TestCase):
    """R74 — no extra process: the scheduler starts the control listener."""

    def test_no_token_means_no_thread(self):
        import os
        from unittest import mock
        import tempfile
        from bot.config import Config
        from bot.db import DB
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(raw={"storage": {"db_path": f"{tmp}/t.db",
                                          "media_dir": f"{tmp}/m"}})
            cfg.raw.setdefault("storage", {})
            import pathlib
            pathlib.Path(cfg.media_dir).mkdir(parents=True, exist_ok=True)
            eng = Engine(cfg)
            with mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": ""}):
                eng._start_telegram_control()
            self.assertFalse(getattr(eng, "_tg_started", False))

    def test_token_starts_one_thread_only(self):
        import os
        from unittest import mock
        import tempfile
        from bot.config import Config
        from bot.engine import Engine
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(raw={"storage": {"db_path": f"{tmp}/t.db",
                                          "media_dir": f"{tmp}/m"}})
            import pathlib
            pathlib.Path(cfg.media_dir).mkdir(parents=True, exist_ok=True)
            eng = Engine(cfg)
            with mock.patch.dict(os.environ, {"TELEGRAM_TOKEN": "tok",
                                              "TELEGRAM_CHAT_ID": "1"}), \
                 mock.patch("bot.tgcontrol.TelegramControl.serve",
                            return_value=None):
                eng._start_telegram_control()
                eng._start_telegram_control()          # second call = no-op
            self.assertTrue(eng._tg_started)
