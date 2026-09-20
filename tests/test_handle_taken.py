"""R58: when the brand handle is taken — variants, spelling options, auto-pick."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import yaml

from bot import handles, naming
from bot.config import Config, load_config
from bot.main import cmd_handle, cmd_name


class _Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


def _fake_requests(mapping):
    """Patch requests.get with URL-substring routing (returns a cleanup fn)."""
    import requests

    def fake_get(url, timeout=None, headers=None):
        for key, resp in mapping.items():
            if key in url:
                return resp
        return _Resp(404)

    old = requests.get
    requests.get = fake_get
    return lambda: setattr(requests, "get", old)


def _cfg(tmp: Path, **raw) -> Config:
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestSpellingVariants(unittest.TestCase):
    def test_variants_keep_the_sound_and_pass_the_rules(self):
        got = naming.spelling_variants("Gharvana")
        self.assertTrue(got)
        handles_ = [v["handle"] for v in got]
        self.assertIn("gharvanaa", handles_)
        self.assertIn("gharvanah", handles_)
        for v in got:
            self.assertTrue(handles.validate_handle(v["handle"])["ok"], v)
            self.assertNotEqual(v["handle"], "gharvana")     # never the base
            self.assertTrue(v["why"])

    def test_no_unpronounceable_variants(self):
        for v in naming.spelling_variants("Gharvana"):
            self.assertLessEqual(naming._clusters(v["handle"]), 0, v)
            self.assertLessEqual(len(v["handle"]), 14, v)

    def test_known_collision_is_excluded(self):
        self.assertNotIn("nestor", [v["handle"] for v in
                                    naming.spelling_variants("Nestor")])

    def test_empty_input(self):
        self.assertEqual(naming.spelling_variants(""), [])
        self.assertEqual(naming.spelling_variants("123"), [])


class TestTakenPlan(unittest.TestCase):
    def test_plan_is_actionable(self):
        text = "\n".join(naming.taken_plan("Gharvana"))
        self.assertIn("HANDLE TAKEN", text)
        self.assertIn("@gharvanahome", text)                 # brand + niche first
        self.assertIn("--pick", text)                        # one-command path
        self.assertIn("@gharvanadeals", text)
        self.assertIn("gharvanaa", text)                     # spelling option
        self.assertNotIn("@gharvana ", text)                 # base not re-offered

    def test_plan_excludes_the_base_from_fresh_names(self):
        text = "\n".join(naming.taken_plan("Gharvana"))
        section = text.split("3️⃣")[1]
        self.assertNotIn("(@gharvana)", section)

    def test_plan_never_offers_a_trailing_underscore(self):
        text = "\n".join(naming.taken_plan("Gharvana"))
        self.assertNotIn("gharvana_ ", text)
        self.assertIn("gharvana_home", text)

    def test_plan_for_an_empty_brand_still_works(self):
        text = "\n".join(naming.taken_plan(""))
        self.assertIn("HANDLE TAKEN", text)

    def test_live_report_adds_the_plan_when_taken(self):
        cleanup = _fake_requests({
            "pinterest.com": _Resp(200, "user profile"),
            "instagram.com": _Resp(200, "profile"),
        })
        self.addCleanup(cleanup)
        text = "\n".join(naming.report("Gharvana", _cfg(Path("/tmp")), live=True))
        self.assertIn("taken", text)
        self.assertIn("HANDLE TAKEN", text)      # plan shown automatically

    def test_live_report_skips_the_plan_when_free(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(404),
                                  "instagram.com": _Resp(404)})
        self.addCleanup(cleanup)
        out = naming.report("Gharvana", _cfg(Path("/tmp")), live=True)
        text = "\n".join(out)
        self.assertIn("FREE on both", text)
        self.assertNotIn("🚨", text)


class TestPickFirstFree(unittest.TestCase):
    def test_picks_first_free_and_reports_skips(self):
        cleanup = _fake_requests({
            "pinterest.com/gharvanahome/": _Resp(200, "profile"),
            "instagram.com/gharvanahome/": _Resp(200, "profile"),
            "pinterest.com/gharvanadeals/": _Resp(404),
            "instagram.com/gharvanadeals/": _Resp(404),
        })
        self.addCleanup(cleanup)
        res = handles.pick_first_free(["gharvanahome", "gharvanadeals"])
        self.assertEqual(res["picked"], "gharvanadeals")
        self.assertEqual(res["skipped"], ["gharvanahome"])

    def test_no_pick_when_nothing_is_free_on_both(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(200, "profile"),
                                  "instagram.com": _Resp(429)})
        self.addCleanup(cleanup)
        self.assertEqual(handles.pick_first_free(["gharvanahome"])["picked"], "")

    def test_short_candidates_are_ignored(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(404),
                                  "instagram.com": _Resp(404)})
        self.addCleanup(cleanup)
        res = handles.pick_first_free(["ab", "gharvanahq"])
        self.assertEqual(res["picked"], "gharvanahq")

    def test_empty_input_is_safe(self):
        self.assertEqual(handles.pick_first_free([])["picked"], "")


class TestCliPick(unittest.TestCase):
    def test_check_pick_saves_the_winner(self):
        cleanup = _fake_requests({
            "pinterest.com/gharvanahome/": _Resp(200, "profile"),
            "instagram.com/gharvanahome/": _Resp(200, "profile"),
            "pinterest.com/gharvanadeals/": _Resp(404),
            "instagram.com/gharvanadeals/": _Resp(404),
        })
        self.addCleanup(cleanup)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"Gharvana | Home Deals\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["check", "--pick",
                                                  "gharvanahome",
                                                  "gharvanadeals"]), 0)
            out = buf.getvalue()
            self.assertIn("Picked + saved", out)
            self.assertIn("gharvanadeals", out)
            self.assertEqual(yaml.safe_load(f.read_text())["brand"]["handle"],
                             "gharvanadeals")

    def test_check_pick_with_nothing_free_says_so(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(200, "profile"),
                                  "instagram.com": _Resp(200, "profile")})
        self.addCleanup(cleanup)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"X | Home\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_handle(cfg, ["check", "--pick",
                                                  "gharvanahome"]), 0)
            self.assertIn("dorakaledu", buf.getvalue())
            self.assertNotIn("handle:", f.read_text())

    def test_check_without_pick_saves_nothing(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(404),
                                  "instagram.com": _Resp(404)})
        self.addCleanup(cleanup)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"X | Home\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_handle(cfg, ["check", "gharvanahome"])
            self.assertNotIn("handle:", f.read_text())

    def test_name_next_uses_the_configured_brand(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp, brand={"display_name": "Gharvana | Home Deals & Finds"},
                       design={"brand_name": "Gharvana"})
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_name(cfg, ["--next"]), 0)
            out = buf.getvalue()
            self.assertIn("HANDLE TAKEN", out)
            self.assertIn("gharvanahome", out)

    def test_name_next_accepts_an_explicit_brand(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_name(cfg, ["Grihika", "--next"]), 0)
            self.assertIn("grihikahome", buf.getvalue())

    def test_repo_config_untouched_by_pick(self):
        cleanup = _fake_requests({"pinterest.com": _Resp(404),
                                  "instagram.com": _Resp(404)})
        self.addCleanup(cleanup)
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        before = repo.read_text()
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            f = tmp / "config.yaml"
            f.write_text("brand:\n  display_name: \"X | Home\"\n")
            cfg = load_config(f)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_handle(cfg, ["check", "--pick", "gharvanahq"])
        self.assertEqual(repo.read_text(), before)

    def test_help_lists_the_next_command(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn("python -m bot name --next", src)
        self.assertIn('"--pick"', src)


if __name__ == "__main__":
    unittest.main()
