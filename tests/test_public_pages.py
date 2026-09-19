"""R60: public /about, /privacy and /terms pages (app-review forms need them)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.config import Config
from bot.db import DB


def _client(tmp: Path, **raw):
    from bot.dashboard import create_app
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"},
            "brand": {"handle": "gharvanaa"},
            "design": {"brand_name": "Gharvanaa"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return create_app(cfg, DB(cfg.db_path)).test_client()


class TestPublicPages(unittest.TestCase):
    def test_pages_are_public_and_200(self):
        with tempfile.TemporaryDirectory() as d:
            c = _client(Path(d))
            for path in ("/about", "/privacy", "/terms"):
                r = c.get(path)
                self.assertEqual(r.status_code, 200, path)
                self.assertIn("Gharvanaa", r.data.decode(), path)

    def test_about_carries_company_facts_the_form_asks(self):
        with tempfile.TemporaryDirectory() as d:
            body = _client(Path(d)).get("/about").data.decode()
            self.assertIn("pinterest.com/gharvanaa/", body)
            self.assertIn('rel="me"', body)
            self.assertIn("affiliate", body.lower())
            self.assertIn("no extra cost", body)          # honest disclosure
            self.assertIn("Gharvanaa", body)

    def test_privacy_is_truthful_about_data(self):
        with tempfile.TemporaryDirectory() as d:
            body = _client(Path(d)).get("/privacy").data.decode()
            self.assertIn("no selling", body.lower())
            self.assertIn("Unsubscribe", body)
            self.assertIn("session cookie", body)
            self.assertIn("not directed to children", body)

    def test_terms_cover_the_essentials(self):
        with tempfile.TemporaryDirectory() as d:
            body = _client(Path(d)).get("/terms").data.decode()
            self.assertIn("Prices", body)
            self.assertIn("affiliate", body.lower())
            self.assertIn("third-party", body.lower())

    def test_contact_email_shows_when_configured(self):
        with tempfile.TemporaryDirectory() as d:
            c = _client(Path(d), brand={"handle": "gharvanaa",
                                        "contact_email": "hello@gharvanaa.in"})
            for path in ("/about", "/privacy", "/terms"):
                self.assertIn("hello@gharvanaa.in", c.get(path).data.decode(),
                              path)

    def test_contact_falls_back_to_pinterest_without_email(self):
        with tempfile.TemporaryDirectory() as d:
            body = _client(Path(d)).get("/about").data.decode()
            self.assertIn("Reach us on Pinterest", body)
            self.assertNotIn("mailto:", body)

    def test_no_handle_no_broken_links(self):
        with tempfile.TemporaryDirectory() as d:
            c = _client(Path(d), brand={"handle": ""}, design={"brand_name": "X"})
            body = c.get("/about").data.decode()
            self.assertNotIn("https://www.pinterest.com//", body)
            self.assertNotIn("https://www.instagram.com//", body)
            self.assertEqual(c.get("/about").status_code, 200)

    def test_domain_token_is_injected_into_new_pages_too(self):
        with tempfile.TemporaryDirectory() as d:
            c = _client(Path(d), pinterest={"domain_verify_token": "abc123TOKENxyz"})
            for path in ("/about", "/privacy", "/terms"):
                self.assertIn("p:domain_verify", c.get(path).data.decode(), path)

    def test_footers_link_the_public_pages(self):
        with tempfile.TemporaryDirectory() as d:
            from bot.dashboard import create_app
            tmp = Path(d)
            cfg = Config(raw={"storage": {"db_path": f"{tmp}/t.db",
                                          "media_dir": f"{tmp}/m"},
                              "dashboard": {"password": "", "secret_key": "t"}})
            db = DB(cfg.db_path)
            pid = db.add_product(source="meesho", url="https://m/x/p/1k1b6",
                                 affiliate_url="https://m/x?affid",
                                 title="Kitchen Storage Organizer Rack",
                                 price="399", status="posted")
            c = create_app(cfg, db).test_client()
            for page in (c.get(f"/go/{pid}").data.decode(),
                         c.get("/deals/today").data.decode()):
                self.assertIn('href="/about"', page)
                self.assertIn('href="/privacy"', page)

    def test_allowlist_marks_the_pages_public(self):
        from bot.dashboard import PUBLIC_EXACT
        for path in ("/about", "/privacy", "/terms"):
            self.assertIn(path, PUBLIC_EXACT)

    def test_pages_never_500_on_broken_config(self):
        class Boom:
            def get(self, *a, **k):
                raise RuntimeError("bad config")
        from bot.dashboard import create_app
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = Boom()
            cfg.db_path = f"{tmp}/t.db"          # property used by create_app
            (tmp / "m").mkdir(parents=True, exist_ok=True)
            try:
                c = create_app(cfg, DB(cfg.db_path)).test_client()
                for path in ("/about", "/privacy", "/terms"):
                    self.assertLess(c.get(path).status_code, 500, path)
            except Exception as exc:            # create_app may refuse outright
                self.assertIn("config", str(exc).lower())


if __name__ == "__main__":
    unittest.main()
