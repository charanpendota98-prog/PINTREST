"""R54: trailing/leading underscore is legal but looks generated — polish it."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bot import handles
from bot.config import Config, load_config
from bot.main import cmd_handle


def _cfg(tmp: Path) -> Config:
    cfg = Config(raw={"storage": {"db_path": f"{tmp}/t.db",
                                  "media_dir": f"{tmp}/m"},
                      "dashboard": {"password": "", "secret_key": "t"}})
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestPolish(unittest.TestCase):
    def test_trailing_underscore_is_flagged_with_a_fix(self):
        check = handles.validate_handle("pindrop_deals_")
        self.assertTrue(check["ok"])                 # legal on Pinterest
        self.assertTrue(check["warnings"])           # but not clean
        self.assertIn("pindrop_deals", check["warnings"][0])

    def test_leading_underscore_is_flagged(self):
        check = handles.validate_handle("_pindropdeals")
        self.assertTrue(check["ok"])
        self.assertIn("pindropdeals", " ".join(check["warnings"]))

    def test_double_underscore_suggests_single(self):
        got = handles.polish("pin__drop__deals")
        self.assertIn("pin_drop_deals", got)
        self.assertTrue(all("__" not in c for c in got))

    def test_polish_variants_are_all_valid(self):
        for cand in handles.polish("pindrop_deals_"):
            self.assertTrue(handles.validate_handle(cand)["ok"], cand)
            self.assertNotIn(cand, ("", "pindrop_deals_", None))

    def test_polish_is_empty_for_a_clean_handle(self):
        self.assertEqual(handles.polish("pindrop_deals"), [])
        self.assertEqual(handles.polish(""), [])
        self.assertEqual(handles.polish("!!!"), [])

    def test_polish_never_repeats_candidates(self):
        got = handles.polish("pin_drop_deals_")
        self.assertEqual(len(got), len(set(got)))

    def test_verdict_prints_cleaner_variants(self):
        text = "\n".join(handles.verdict("pindrop_deals_"))
        self.assertIn("🔧 Cleaner variants", text)
        self.assertIn("pindrop_deals", text)

    def test_clean_handle_gets_no_variant_suggestion(self):
        text = "\n".join(handles.verdict("pindropdeals_home"))
        self.assertNotIn("🔧 Cleaner variants", text)


class TestLadderWithSeparator(unittest.TestCase):
    def test_intentional_separator_variant_is_near_the_top(self):
        ideas = [i["handle"] for i in handles.handle_ideas()]
        self.assertIn("pindropdeals_home", ideas)
        self.assertLess(ideas.index("pindropdeals_home"), 3)
        self.assertLess(ideas.index("pindropdeals_home"),
                        ideas.index("pindropdeals01"))

    def test_every_ladder_idea_still_valid_and_short(self):
        for idea in handles.handle_ideas("Some Long Brand Name Here", "Home"):
            self.assertTrue(idea["ok"], idea["handle"])
            self.assertLessEqual(len(idea["handle"]), handles.HANDLE_MAX)


class TestCliPolish(unittest.TestCase):
    def test_saving_a_rough_handle_reports_the_cleaner_one(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"X\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["pindrop_deals_"]), 0)
            out = buf.getvalue()
            self.assertIn("Cleaner alternative", out)
            self.assertIn("pindrop_deals", out)

    def test_check_accepts_the_owners_own_candidates(self):
        import requests

        class _Resp:
            def __init__(self, status, text=""):
                self.status_code, self.text = status, text

        seen: list[str] = []

        def fake_get(url, timeout=None, headers=None):
            seen.append(url)
            return _Resp(404)

        old = requests.get
        requests.get = fake_get
        self.addCleanup(lambda: setattr(requests, "get", old))

        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["check", "pindrop_deals_",
                                                  "pindropdeals_home"]), 0)
        self.assertIn("pindropdeals_home", buf.getvalue())
        self.assertEqual(len(seen), 4)          # 2 candidates x 2 platforms
        self.assertTrue(all("pindropdeals_home" in u or "pindrop_deals_" in u
                            for u in seen))

    def test_check_with_bad_input_never_crashes(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["check", "!", "x"]), 0)
        self.assertIn("AVAILABILITY", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
