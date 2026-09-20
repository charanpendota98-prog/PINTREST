"""R52: Pinterest website claiming — token parse, injection, public file route."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot import claim
from bot.config import Config, load_config
from bot.db import DB

TOKEN = "abc123TOKENxyz"


def _cfg(tmp: Path, token: str = "") -> Config:
    raw = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
           "dashboard": {"password": "", "secret_key": "t"}}
    if token:
        raw["pinterest"] = {"domain_verify_token": token}
    cfg = Config(raw=raw)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestParseToken(unittest.TestCase):
    def test_raw_token(self):
        self.assertEqual(claim.parse_token(TOKEN), TOKEN)
        self.assertEqual(claim.parse_token(f"  {TOKEN}  "), TOKEN)

    def test_meta_tag_and_html_file(self):
        tag = f'<meta name="p:domain_verify" content="{TOKEN}">'
        self.assertEqual(claim.parse_token(tag), TOKEN)
        self.assertEqual(claim.parse_token(
            f'<meta name="p:domain_verify" content="{TOKEN}" />'), TOKEN)
        blob = f'<html><head>{tag}</head><body>hi</body></html>'
        self.assertEqual(claim.parse_token(blob), TOKEN)

    def test_junk_is_rejected_loudly(self):
        for junk in ("", "   ", "not a token!!", "short", "<html>nope</html>",
                     None, 123):
            self.assertEqual(claim.parse_token(junk), "", junk)


class TestHelpers(unittest.TestCase):
    def test_meta_and_file(self):
        self.assertIn("p:domain_verify", claim.meta_tag(TOKEN))
        self.assertIn(TOKEN, claim.meta_tag(TOKEN))
        self.assertEqual(claim.verify_filename(TOKEN),
                         f"pinterest-{TOKEN}.html")
        content = claim.verify_file_content(TOKEN)
        self.assertIn("p:domain_verify", content)
        self.assertIn(TOKEN, content)
        self.assertEqual(claim.meta_tag(""), "")
        self.assertEqual(claim.verify_file_content(""), "")

    def test_inject_adds_once_and_only_with_token(self):
        base = "<!DOCTYPE html><html><head><title>x</title></head><body>yo</body></html>"
        once = claim.inject(base, TOKEN)
        self.assertIn("p:domain_verify", once)
        twice = claim.inject(once, TOKEN)
        self.assertEqual(twice.count("p:domain_verify"), 1)   # idempotent
        self.assertEqual(claim.inject(base, ""), base)
        self.assertEqual(claim.inject("", TOKEN), "")


class TestSave(unittest.TestCase):
    def test_save_keeps_comments_and_reparses(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text(
                "# top comment\n"
                "pinterest:\n"
                "  board_name: Best Deals  # keep me\n"
                "other: 1  # and me\n")
            cfg = load_config(cfg_file)
            res = claim.save(cfg, f'<meta name="p:domain_verify" content="{TOKEN}">')
            self.assertTrue(res["saved"])
            self.assertEqual(res["token"], TOKEN)
            text = cfg_file.read_text()
            self.assertIn("# top comment", text)
            self.assertIn("# keep me", text)
            self.assertIn("# and me", text)
            import yaml
            data = yaml.safe_load(text)
            self.assertEqual(data["pinterest"]["domain_verify_token"], TOKEN)
            self.assertEqual(data["pinterest"]["board_name"], "Best Deals")
            self.assertEqual(data["other"], 1)

    def test_save_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("pinterest:\n  board_name: B\n")
            cfg = load_config(cfg_file)
            claim.save(cfg, TOKEN, path=cfg_file)
            claim.save(cfg, TOKEN, path=cfg_file)
            self.assertEqual(cfg_file.read_text().count("domain_verify_token"), 1)

    def test_bad_token_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("pinterest:\n  board_name: B\n")
            cfg = load_config(cfg_file)
            res = claim.save(cfg, "garbage input !!!", path=cfg_file)
            self.assertFalse(res["saved"])
            self.assertIn("error", res)
            self.assertNotIn("domain_verify_token", cfg_file.read_text())

    def test_token_of(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self.assertEqual(claim.token_of(_cfg(tmp)), "")
            self.assertEqual(claim.token_of(_cfg(tmp, TOKEN)), TOKEN)

    def test_lines_guide_before_and_after(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            before = "\n".join(claim.lines(_cfg(tmp)))
            self.assertIn("Claimed accounts", before)
            self.assertIn("python -m bot claim", before)
            cfg = _cfg(tmp, TOKEN)
            cfg.raw["link"] = {"public_base": "https://pin.example.com"}
            after = "\n".join(claim.lines(cfg))
            self.assertIn("already injected", after)
            self.assertIn("https://pin.example.com/pinterest-", after)


class TestDashboardIntegration(unittest.TestCase):
    def _client(self, tmp: Path, token: str = "", password: str = ""):
        from bot.dashboard import create_app
        cfg = _cfg(tmp, token)
        if password:
            cfg.raw["dashboard"]["password"] = password
        return create_app(cfg, DB(cfg.db_path)).test_client()

    def test_file_route_public_and_token_checked(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._client(Path(d), TOKEN, password="secret123")
            r = c.get(f"/pinterest-{TOKEN}.html")      # no login needed
            self.assertEqual(r.status_code, 200)
            self.assertIn("p:domain_verify", r.data.decode())
            self.assertEqual(c.get("/pinterest-wrongtoken123.html").status_code,
                             404)
            self.assertEqual(c.get("/pinterest-abc.html").status_code, 404)

    def test_meta_tag_on_public_pages(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            c = self._client(tmp, TOKEN, password="secret123")
            self.assertIn("p:domain_verify", c.get("/login").data.decode())
            self.assertIn("p:domain_verify",
                          c.get("/deals/today").data.decode())
            db = DB(tmp / "t.db")
            pid = db.add_product(source="meesho", url="https://m/x/p/1k1b6",
                                 affiliate_url="https://m/x?affid",
                                 title="Kitchen Storage Organizer Rack",
                                 price="399", status="posted")
            landing = c.get(f"/go/{pid}")
            self.assertEqual(landing.status_code, 200)
            self.assertIn("p:domain_verify", landing.data.decode())

    def test_no_token_means_no_tag_anywhere(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._client(Path(d))
            self.assertNotIn("p:domain_verify", c.get("/").data.decode())
            self.assertNotIn("p:domain_verify",
                             c.get("/deals/today").data.decode())
            self.assertEqual(c.get("/pinterest-abc123TOKENxyz.html").status_code,
                             404)

    def test_two_apps_do_not_leak_tokens(self):
        """Regression guard: constants must not be rebound per app."""
        with tempfile.TemporaryDirectory() as d1, \
                tempfile.TemporaryDirectory() as d2:
            with_token = self._client(Path(d1), TOKEN)
            without = self._client(Path(d2))
            self.assertIn("p:domain_verify",
                          with_token.get("/deals/today").data.decode())
            self.assertNotIn("p:domain_verify",
                             without.get("/deals/today").data.decode())


class TestCli(unittest.TestCase):
    def test_cli_claim_view_save_and_bad_input(self):
        import contextlib
        import io

        from bot.main import cmd_claim
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("pinterest:\n  board_name: B\n")
            cfg = load_config(cfg_file)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_claim(cfg, []), 0)       # instructions
            self.assertIn("Claimed accounts", buf.getvalue())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_claim(cfg, [TOKEN]), 0)
            self.assertIn(TOKEN, cfg_file.read_text())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_claim(cfg, ["bad input !!"]), 2)

    def test_cli_never_touches_repo_config(self):
        import contextlib
        import io

        from bot.main import cmd_claim
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        before = repo.read_text()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("pinterest:\n  board_name: B\n")
            cfg = load_config(cfg_file)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_claim(cfg, [TOKEN])
        self.assertEqual(repo.read_text(), before)


if __name__ == "__main__":
    unittest.main()
