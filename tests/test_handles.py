"""R53c: handle rules, ranked fallbacks (pindropdeals is taken), and saving."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from bot import handles
from bot.config import Config, load_config
from bot.main import cmd_handle


def _cfg(tmp: Path, **raw) -> Config:
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestRules(unittest.TestCase):
    def test_pinterest_rules_enforced(self):
        for bad in ("ab", "a" * 31, "pin drop", "pin-drop", "pin.drop",
                    "12345678", "", "   "):
            self.assertFalse(handles.validate_handle(bad)["ok"], bad)

    def test_valid_handles_pass(self):
        for good in ("pindrop_deals", "pindropdealsindia", "thepindropdeals",
                     "pindropdeals01", "gharfinds"):
            self.assertTrue(handles.validate_handle(good)["ok"], good)

    def test_at_prefix_and_case_normalised(self):
        res = handles.validate_handle("  @PinDrop_Deals ")
        self.assertTrue(res["ok"])
        self.assertEqual(res["handle"], "pindrop_deals")

    def test_reserved_and_number_suffix_warn(self):
        self.assertTrue(handles.validate_handle("pinterest_home")["warnings"])
        self.assertTrue(handles.validate_handle("pindropdeals1")["warnings"])
        self.assertTrue(handles.validate_handle("pin__drop")["warnings"])

    def test_digits_only_message_mentions_pinterest(self):
        self.assertIn("Pinterest", " ".join(
            handles.validate_handle("98765432")["errors"]))

    def test_clean_handle_strips_rejected_chars(self):
        self.assertEqual(handles.clean_handle("Pin Drop.Deals-HQ!"),
                         "pindropdealshq")


class TestIdeas(unittest.TestCase):
    def test_ranked_and_clean(self):
        ideas = handles.handle_ideas()
        self.assertGreaterEqual(len(ideas), 8)
        self.assertTrue(all(i["ok"] for i in ideas))
        self.assertEqual(ideas[0]["handle"], "pindrop_deals")   # closest first
        self.assertEqual(ideas[-1]["handle"], "pindropdeals01")  # numbers last
        self.assertEqual(len({i["handle"] for i in ideas}), len(ideas))

    def test_no_handle_over_30_chars(self):
        for idea in handles.handle_ideas("A Very Long Brand Name Indeed", "Home"):
            self.assertLessEqual(len(idea["handle"]), handles.HANDLE_MAX)

    def test_every_idea_has_a_reason(self):
        for idea in handles.handle_ideas():
            self.assertTrue(idea["why"].strip())

    def test_plan_c_is_fresh_and_valid(self):
        for h in handles.plan_c():
            self.assertTrue(handles.validate_handle(h)["ok"], h)

    def test_niche_word_shows_up(self):
        got = [i["handle"] for i in handles.handle_ideas("PinDrop Deals", "Home")]
        self.assertIn("pindropdealshome", got)


class TestSaveHandle(unittest.TestCase):
    def _file(self, tmp: Path, body: str) -> Path:
        f = tmp / "config.yaml"
        f.write_text(body)
        return f

    def test_saves_inside_existing_block_and_keeps_comments(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "# top\npinterest:\n  board_name: B  # keep\n"
                                "brand:\n  display_name: \"X\"\n  bio: \"Y\"\n")
            cfg = load_config(f)
            res = handles.save_handle(cfg, "pindrop_deals")
            self.assertTrue(res["saved"])
            text = f.read_text()
            self.assertEqual(text.count("\nbrand:"), 1)      # no duplicate block
            self.assertIn("# top", text)
            self.assertIn("# keep", text)
            data = yaml.safe_load(text)
            self.assertEqual(data["brand"]["handle"], "pindrop_deals")
            self.assertEqual(data["brand"]["display_name"], "X")
            self.assertEqual(data["pinterest"]["board_name"], "B")

    def test_brand_block_last_in_file(self):
        """Regression: brand block at EOF used to append a second brand block."""
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "pinterest:\n  board_name: B\n\nbrand:\n"
                                "  display_name: \"X\"\n")
            cfg = load_config(f)
            handles.save_handle(cfg, "thepindropdeals")
            text = f.read_text()
            self.assertEqual(text.count("\nbrand:"), 1)
            self.assertEqual(yaml.safe_load(text)["brand"]["handle"],
                             "thepindropdeals")

    def test_no_brand_block_at_all(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "pinterest:\n  board_name: B\n")
            cfg = load_config(f)
            handles.save_handle(cfg, "gharfinds")
            self.assertEqual(yaml.safe_load(f.read_text())["brand"]["handle"],
                             "gharfinds")

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "brand:\n  display_name: \"X\"\n")
            cfg = load_config(f)
            handles.save_handle(cfg, "pindrop_deals")
            handles.save_handle(cfg, "pindropdealsindia")
            text = f.read_text()
            self.assertEqual(text.count("handle:"), 1)
            self.assertEqual(yaml.safe_load(text)["brand"]["handle"],
                             "pindropdealsindia")

    def test_bad_handle_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "brand:\n  display_name: \"X\"\n")
            cfg = load_config(f)
            res = handles.save_handle(cfg, "pin-drop")
            self.assertFalse(res["saved"])
            self.assertNotIn("handle:", f.read_text())

    def test_cli_exit_codes_and_output(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = self._file(tmp, "brand:\n  display_name: \"X\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["pindrop_deals"]), 0)
            out = buf.getvalue()
            self.assertIn("Saved handle: pindrop_deals", out)
            self.assertIn("already taken", out)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["pin-drop"]), 2)
            self.assertIn("⛔", buf.getvalue())

    def test_cli_never_touches_repo_config(self):
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        before = repo.read_text()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"X\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_handle(cfg, ["gharfinds"])
        self.assertEqual(repo.read_text(), before)

    def test_real_config_keeps_single_brand_block(self):
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        text = repo.read_text()
        self.assertEqual(text.count("\nbrand:"), 1)
        self.assertTrue(text.count("#") >= 80)      # comments still intact
        data = yaml.safe_load(text)
        self.assertTrue(data["brand"]["handle"])


class TestAdvice(unittest.TestCase):
    def test_advice_explains_order_and_rules(self):
        text = "\n".join(handles.advice())
        self.assertIn("already taken", text)
        self.assertIn("pindrop_deals", text)
        self.assertIn("python -m bot handle", text)
        self.assertIn("3-30", text)
        self.assertIn("Instagram", text)

    def test_advice_never_raises_on_broken_config(self):
        class Boom:
            def get(self, *a, **k):
                raise RuntimeError("bad config")
        self.assertIn("PINTEREST / INSTAGRAM HANDLE",
                      "\n".join(handles.advice(Boom())))

    def test_advice_echoes_a_bad_candidate(self):
        text = "\n".join(handles.advice(None, "pin-drop"))
        self.assertIn("⛔", text)


class TestWiring(unittest.TestCase):
    def test_profile_form_uses_saved_handle(self):
        from bot import brand
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), brand={"display_name": "PinDrop Deals | Home",
                                       "handle": "pindrop_deals"})
            self.assertIn("Username   → pindrop_deals",
                          "\n".join(brand.profile_form(cfg)))

    def test_profile_form_hints_when_handle_unset(self):
        from bot import brand
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d), brand={"display_name": "PinDrop Deals | Home"})
            self.assertIn("python -m bot handle",
                          "\n".join(brand.profile_form(cfg)))

    def test_onboard_mentions_the_taken_username(self):
        from bot import onboard
        self.assertIn("already taken", "\n".join(onboard.lines()))

    def test_help_lists_handle_command(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn("python -m bot handle", src)
        self.assertIn('if cmd in ("handle", "handles")', src)


if __name__ == "__main__":
    unittest.main()
