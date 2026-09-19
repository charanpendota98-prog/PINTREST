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


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


class TestAvailabilityCheck(unittest.TestCase):
    """The ladder probe must be honest: free / taken / unknown, never guessed."""

    def _patch(self, mapping):
        import requests
        calls = []

        def fake_get(url, timeout=None, headers=None):
            calls.append(url)
            for key, resp in mapping.items():
                if key in url:
                    return resp
            return _Resp(500, "")

        old = requests.get
        requests.get = fake_get
        self.addCleanup(lambda: setattr(requests, "get", old))
        return calls

    def test_free_when_404_on_both(self):
        self._patch({"pinterest.com": _Resp(404), "instagram.com": _Resp(404)})
        res = handles.check_handle("pindropdealshome")
        self.assertEqual(res["verdict"], "free_both")
        self.assertEqual(res["pinterest"]["detail"], "404")

    def test_taken_when_profile_loads(self):
        self._patch({"pinterest.com": _Resp(200, "<html>user profile</html>"),
                     "instagram.com": _Resp(200, "<html>profile</html>")})
        self.assertEqual(handles.check_handle("pindropdeals")["verdict"], "taken")

    def test_not_found_marker_beats_status_200(self):
        self._patch({"pinterest.com": _Resp(
            200, "<html>Sorry! We couldn't find that page</html>"),
            "instagram.com": _Resp(404)})
        self.assertEqual(handles.check_handle("gharfinds")["verdict"], "free_both")

    def test_blocked_is_unknown_not_free(self):
        self._patch({"pinterest.com": _Resp(429), "instagram.com": _Resp(404)})
        res = handles.check_handle("pindropdealshome")
        self.assertEqual(res["verdict"], "partial")     # never claims free
        self.assertIn("blocked", res["pinterest"]["detail"])

    def test_taken_on_one_platform_is_enough(self):
        """Pinterest unreadable (429) but Instagram taken → the handle IS taken."""
        self._patch({"pinterest.com": _Resp(429),
                     "instagram.com": _Resp(200, "profile")})
        self.assertEqual(handles.check_handle("pindropdealshome")["verdict"],
                         "taken")

    def test_network_error_is_unknown(self):
        import requests

        def boom(*a, **k):
            raise requests.ConnectionError("offline")

        old = requests.get
        requests.get = boom
        self.addCleanup(lambda: setattr(requests, "get", old))
        res = handles.check_handle("pindropdealshome")
        self.assertEqual(res["verdict"], "unknown")
        self.assertIn("network", res["pinterest"]["detail"])

    def test_short_handle_never_probed(self):
        calls = self._patch({})
        self.assertEqual(handles.check_handle("ab")["verdict"], "invalid")
        self.assertEqual(calls, [])

    def test_check_lines_picks_first_free_and_stops_claiming(self):
        self._patch({"pinterest.com/pindrop_deals/": _Resp(404),
                     "instagram.com/pindrop_deals/": _Resp(404),
                     "pinterest.com/pindropdealshome/": _Resp(404),
                     "instagram.com/pindropdealshome/": _Resp(404)})
        text = "\n".join(handles.check_lines(["pindrop_deals", "pindropdealshome"],
                                             limit=2))
        self.assertIn("FREE on both", text)
        self.assertIn("Pick: pindrop_deals", text)

    def test_check_lines_says_so_when_nothing_is_full_free(self):
        self._patch({"pinterest.com": _Resp(200, "profile"),
                     "instagram.com": _Resp(429)})
        text = "\n".join(handles.check_lines(["pindropdealshome"], limit=1))
        self.assertIn("full-free dorakaledu", text)

    def test_cli_check_uses_the_probe(self):
        self._patch({"pinterest.com": _Resp(404), "instagram.com": _Resp(404)})
        import contextlib
        import io
        from bot.config import Config
        cfg = Config(raw={"storage": {"db_path": "/tmp/n.db",
                                      "media_dir": "/tmp/n"}})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cmd_handle(cfg, ["check"]), 0)
        out = buf.getvalue()
        self.assertIn("LIVE AVAILABILITY CHECK", out)
        self.assertIn("FREE on both", out)


class TestVerdict(unittest.TestCase):
    def test_good_handle_reads_positively(self):
        text = "\n".join(handles.verdict("pindropdealshome"))
        self.assertIn("Brand word undi", text)
        self.assertIn("Numbers ledu", text)
        self.assertIn("Instagram", text)

    def test_bad_handle_shows_errors_only(self):
        text = "\n".join(handles.verdict("pin-drop"))
        self.assertIn("BLOCK" if False else "\u26d4", text)
        self.assertNotIn("Brand word undi", text)

    def test_missing_brand_word_is_flagged(self):
        text = "\n".join(handles.verdict("homedealsdrop"))
        self.assertIn("Brand word", text)

    def test_number_suffix_loses_the_cleanliness_line(self):
        text = "\n".join(handles.verdict("pindropdeals01"))
        self.assertNotIn("Numbers ledu", text)


if __name__ == "__main__":
    unittest.main()
