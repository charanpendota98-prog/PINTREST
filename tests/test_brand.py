"""R50: brand/profile SEO — name rules, bio, boards, comment-safe config save."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot import brand
from bot.config import Config


def _cfg(tmp: Path) -> Config:
    raw = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
           "design": {"brand_name": "Deal Drops"}}
    cfg = Config(raw=raw)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestValidate(unittest.TestCase):
    def test_good_name(self):
        v = brand.validate("PinDrop Deals | Home & Kitchen")
        self.assertTrue(v["ok"])
        self.assertEqual(v["warnings"], [])
        self.assertLessEqual(len(v["name"]), 40)

    def test_empty_and_too_long(self):
        self.assertFalse(brand.validate("")["ok"])
        long_name = "X" * 70
        v = brand.validate(long_name)
        self.assertFalse(v["ok"])
        self.assertIn("65", v["errors"][0])

    def test_truncation_warning_only_above_40(self):
        v = brand.validate("A" * 30 + " | Home")      # 38 chars, has a niche
        self.assertEqual(v["warnings"], [])
        self.assertTrue(v["notes"])                   # gentle note, not a warning
        self.assertTrue(brand.validate("A" * 45 + " | Home")["warnings"])

    def test_spam_words_flagged(self):
        v = brand.validate("Cheap Loot Deals | Free Stuff")
        self.assertTrue(any("spam" in w for w in v["warnings"]))

    def test_keyword_niche_hint(self):
        v = brand.validate("MyBrandNameIsQuiteLong")     # >18 chars, no niche
        self.assertTrue(any("keyword" in w for w in v["warnings"]))
        short = brand.validate("Tiny")                   # short → gentle note
        self.assertEqual(short["warnings"], [])
        self.assertTrue(any("keyword" in n for n in short["notes"]))

    def test_never_raises_on_junk(self):
        for junk in (None, 123, [], {}):
            self.assertIn("ok", brand.validate(junk))


class TestPinStrip(unittest.TestCase):
    def test_strip_is_the_short_brand(self):
        self.assertEqual(brand.pin_strip("PinDrop Deals | Home & Kitchen"),
                         "PinDrop Deals")
        self.assertEqual(brand.pin_strip("Ghar Finds"), "Ghar Finds")
        self.assertEqual(brand.pin_strip(""), "")

    def test_strip_never_exceeds_pin_width(self):
        self.assertLessEqual(len(brand.pin_strip("A Very Long Brand Name "
                                                 "Indeed Here")), 28)


class TestBioAndBoards(unittest.TestCase):
    def test_bio_fits_the_field_and_has_keywords(self):
        bio = brand.bio_for("PinDrop Deals | Home & Kitchen")
        self.assertLessEqual(len(bio), brand.BIO_MAX)
        low = bio.lower()
        self.assertIn("home", low)
        self.assertIn("kitchen", low)

    def test_long_brand_falls_back_shorter(self):
        bio = brand.bio_for("Super Duper Long Brand Name Here | Niche")
        self.assertLessEqual(len(bio), brand.BIO_MAX)
        self.assertIn("home", bio.lower())        # keywords survive shortening

    def test_boards_are_keyword_titles_within_limit(self):
        boards = brand.board_plan()
        self.assertGreaterEqual(len(boards), 5)
        for b in boards:
            self.assertLessEqual(len(b["title"]), brand.BOARD_MAX)
            self.assertIn("₹", b["desc"])          # price language = buyer intent

    def test_suggestions_include_the_users_brand(self):
        groups = brand.display_suggestions("PinDrop Deals")
        first = list(groups)[0]
        self.assertIn("PinDrop Deals", first)
        self.assertLessEqual(len(groups[first][0]), 40)


class TestSave(unittest.TestCase):
    def test_save_updates_config_and_keeps_comments(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text(
                "# top comment\n"
                "design:\n"
                "  width: 1000\n"
                '  brand_name: "Deal Drops"  # strip on every pin\n'
                "other: 1  # keep me\n")
            res = brand.save(cfg, "PinDrop Deals | Home & Kitchen",
                             path=cfg_file)
            self.assertTrue(res["saved"])
            self.assertEqual(res["strip"], "PinDrop Deals")
            text = cfg_file.read_text()
            self.assertIn("# top comment", text)          # comments survive
            self.assertIn("# keep me", text)
            self.assertIn("# strip on every pin", text)   # inline comment kept
            self.assertIn("brand_name: PinDrop Deals", text)
            self.assertIn("display_name: \"PinDrop Deals | Home & Kitchen\"", text)
            self.assertIn("brand:", text)
            # and it still parses as YAML
            import yaml
            data = yaml.safe_load(text)
            self.assertEqual(data["design"]["brand_name"], "PinDrop Deals")
            self.assertEqual(data["brand"]["display_name"],
                             "PinDrop Deals | Home & Kitchen")
            self.assertLessEqual(len(data["brand"]["bio"]), brand.BIO_MAX)

    def test_save_updates_in_memory_config(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            brand.save(cfg, "Ghar Finds | Home & Kitchen",
                       path=tmp / "config.yaml")
            self.assertEqual(cfg.get("design.brand_name"), "Ghar Finds")
            self.assertEqual(cfg.get("brand.display_name"),
                             "Ghar Finds | Home & Kitchen")

    def test_invalid_name_is_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("design:\n  brand_name: Keep Me\n")
            res = brand.save(cfg, "X" * 70, path=cfg_file)
            self.assertFalse(res["saved"])
            self.assertIn("Keep Me", cfg_file.read_text())

    def test_second_save_replaces_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("design:\n  brand_name: Old\n")
            brand.save(cfg, "First Brand | Home", path=cfg_file)
            brand.save(cfg, "Second Brand | Kitchen", path=cfg_file)
            text = cfg_file.read_text()
            self.assertEqual(text.count("display_name:"), 1)
            self.assertIn("Second Brand | Kitchen", text)
            self.assertNotIn("First Brand", text)


class TestCliAndLines(unittest.TestCase):
    def test_lines_are_complete(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            text = "\n".join(brand.lines(cfg, "PinDrop Deals | Home & Kitchen"))
            for needle in ("BRAND & PROFILE SEO", "NAME IDEAS", "READY-TO-PASTE",
                           "Boards to create", "python -m bot brand"):
                self.assertIn(needle, text)

    def test_cli_brand_view_and_save(self):
        """Regression: this test used to write the REPO config.yaml (real bug).

        `brand.save` now targets `cfg.source_path`, so a temp config is safe.
        """
        import contextlib
        import io

        from bot.main import cmd_brand
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg_file = tmp / "config.yaml"
            cfg_file.write_text("design:\n  brand_name: Old\n")
            cfg.source_path = cfg_file                 # what load_config sets
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_brand(cfg, []), 0)      # view mode
            self.assertIn("BRAND & PROFILE SEO", buf.getvalue())

            repo_before = (Path(__file__).resolve().parents[1] / "config.yaml").read_text()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cmd_brand(cfg, ["Ghar Finds | Home & Kitchen"])
            self.assertEqual(code, 0)
            self.assertIn("Ghar Finds", cfg_file.read_text())      # temp written
            repo_after = (Path(__file__).resolve().parents[1] / "config.yaml").read_text()
            self.assertEqual(repo_before, repo_after)              # repo untouched

    def test_bad_name_exit_code(self):
        import contextlib
        import io

        from bot.main import cmd_brand
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp)
            cfg.source_path = tmp / "config.yaml"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cmd_brand(cfg, ["X" * 70])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class TestOnboardingGuidance(unittest.TestCase):
    """The Pinterest onboarding answers must stay documented (R51).

    The owner hit these screens live; the answers belong in the repo so nobody
    has to research them again.
    """

    def test_readme_documents_goals_and_focus(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
        self.assertIn("A few more details", readme)
        self.assertIn("Increase online sales", readme)
        self.assertIn("Drive traffic to your site", readme)   # outbound clicks
        self.assertIn("Brand focus", readme)
        self.assertIn("Content creator", readme)

    def test_wizard_and_ready_mention_them(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        ready = (Path(__file__).resolve().parents[1] / "bot" / "ready.py").read_text()
        for needle in ("A few more details", "Drive traffic to your site",
                       "Brand focus"):
            self.assertIn(needle, src)
        self.assertIn("Brand focus: Home", ready)
