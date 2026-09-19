"""R56: brand-naming engine — score a name, remember the collisions, verify live."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bot import naming
from bot.config import Config
from bot.main import cmd_name


def _cfg(**raw) -> Config:
    base = {"storage": {"db_path": "/tmp/naming.db", "media_dir": "/tmp/naming"},
            "dashboard": {"password": "", "secret_key": "t"}}
    base.update(raw)
    return Config(raw=base)


class _Resp:
    def __init__(self, status=200, text=""):
        self.status_code, self.text = status, text


class TestScore(unittest.TestCase):
    def test_coined_pick_scores_top(self):
        res = naming.score("Gharvana")
        self.assertGreaterEqual(res["score"], 85)
        self.assertEqual(res["grade"], "🏆 FINAL pick")
        self.assertEqual(res["syllables"], 3)

    def test_spam_coded_names_lose_trust_points(self):
        res = naming.score("LootZone Deals")
        self.assertTrue(any("Spam-coding" in r for r in res["risks"]))
        self.assertLess(res["score"], 70)

    def test_numbers_are_a_risk(self):
        self.assertTrue(any("Numbers" in r for r in naming.score("Ghar1")["risks"]))

    def test_long_names_lose_points(self):
        self.assertTrue(naming.score("SuperHomeKitchenDeals")["risks"])

    def test_home_root_is_rewarded(self):
        with_root = naming.score("Gharvana")["score"]
        without = naming.score("Vanya")["score"]
        self.assertGreater(with_root, without)

    def test_hard_clusters_are_flagged(self):
        self.assertTrue(any("cluster" in r.lower()
                            for r in naming.score("Shtrkhome")["risks"]))

    def test_known_collisions_are_named(self):
        for taken in ("NestBazaar", "NestKart", "Nestora", "Aangan", "Grihika"):
            res = naming.score(taken)
            self.assertTrue(any("already in use" in r.lower()
                                for r in res["risks"]), taken)

    def test_weak_words_cost_distinctiveness(self):
        strong = naming.score("Gharvana")["score"]
        weak = naming.score("Gharstore")["score"]
        self.assertGreater(strong, weak)

    def test_empty_name_is_zero(self):
        self.assertEqual(naming.score("")["score"], 0)
        self.assertEqual(naming.score("   ")["grade"], "❌")

    def test_known_collision_cannot_grade_strong(self):
        for taken in ("SuperDeals", "NestBazaar", "Dropvana", "Pickora",
                      "Haulvana"):
            res = naming.score(taken)
            self.assertLessEqual(res["score"], 60, taken)
            self.assertIn("already in use", res["grade"], taken)

    def test_new_collisions_are_remembered(self):
        for key in ("superdeals", "dropvana", "pickora", "haulvana"):
            self.assertIn(key, naming.KNOWN_USED)

    def test_promo_words_cost_points(self):
        self.assertGreater(naming.score("Gharvana")["score"],
                           naming.score("SuperHome")["score"])

    def test_grade_bands(self):
        self.assertIn("🏆", naming.score("Gharvana")["grade"])
        self.assertIn("❌", naming.score("Loot Free Cheap")["grade"])


class TestDealsFormula(unittest.TestCase):
    def test_name_field_options_fit_and_carry_deals(self):
        for cand in naming.name_field_options("Gharvana"):
            self.assertLessEqual(len(cand), naming.NAME_FIELD_MAX, cand)
            self.assertTrue(cand.startswith("Gharvana"), cand)
        first = naming.name_field_options("Gharvana")[0]
        self.assertIn("Deals", first)
        self.assertIn("Home", first)

    def test_name_field_options_empty_for_empty_brand(self):
        self.assertEqual(naming.name_field_options(""), [])
        self.assertEqual(naming.name_field_options("   "), [])

    def test_formula_talks_about_superdeals_and_the_fix(self):
        text = "\n".join(naming.deals_formula("Gharvana"))
        self.assertIn("SuperDeals", text)
        self.assertIn("PROMO PHRASE", text)
        self.assertIn("NAME field", text)
        self.assertIn("Gharvana | Home Deals & Finds", text)

    def test_report_includes_the_formula(self):
        text = "\n".join(naming.report("Gharvana", _cfg()))
        self.assertIn("DEALS POSITIONING", text)


class TestBlends(unittest.TestCase):
    def test_blends_are_clean_and_meaningful(self):
        got = naming.blends(20)
        self.assertTrue(got)
        for cand in got:
            self.assertGreaterEqual(cand["score"], 70, cand)
            self.assertLessEqual(len(cand["name"]), 12, cand)
            self.assertTrue(cand["meaning"].strip())
            self.assertNotIn(cand["name"].lower(), naming.KNOWN_USED)

    def test_blends_sorted_by_score_and_unique(self):
        got = naming.blends(20)
        scores = [c["score"] for c in got]
        self.assertEqual(scores, sorted(scores, reverse=True))
        names = [c["handle"] for c in got]
        self.assertEqual(len(names), len(set(names)))

    def test_blends_respect_limit(self):
        self.assertLessEqual(len(naming.blends(3)), 3)


class TestDomainProbe(unittest.TestCase):
    def _patch(self, resp=None, exc=None):
        import requests

        def fake_get(url, **kwargs):
            if exc:
                raise exc
            return resp

        old = requests.get
        requests.get = fake_get
        self.addCleanup(lambda: setattr(requests, "get", old))

    def test_serving_domain(self):
        self._patch(resp=_Resp(200))
        self.assertEqual(naming.probe_domain("example.com")[0], "serving")

    def test_not_serving_domain_says_not_serving(self):
        self._patch(resp=_Resp(404))
        state, detail = naming.probe_domain("nothing.in")
        self.assertEqual(state, "not-serving")
        self.assertNotIn("free", detail.lower())

    def test_dns_failure_is_not_serving(self):
        import requests
        self._patch(exc=requests.ConnectionError("dns"))
        self.assertEqual(naming.probe_domain("gharvana.in")[0], "not-serving")

    def test_unknown_error_is_unknown(self):
        self._patch(exc=ValueError("weird"))
        self.assertEqual(naming.probe_domain("gharvana.in")[0], "unknown")

    def test_bad_host_is_unknown(self):
        self.assertEqual(naming.probe_domain("")[0], "unknown")
        self.assertEqual(naming.probe_domain("localhost")[0], "unknown")


class TestReport(unittest.TestCase):
    def test_offline_report_answers_the_question(self):
        text = "\n".join(naming.report("Gharvana", _cfg()))
        self.assertIn("100/100", text)
        self.assertIn("@gharvana", text)
        self.assertIn("Gharvana | Home & Kitchen", text)
        self.assertIn("python -m bot brand", text)
        self.assertIn("python -m bot handle", text)
        self.assertIn("--live", text)          # tells how to verify for real
        self.assertIn("already in use", text)  # collision memory
        self.assertIn("Coined (ownable) options", text)

    def test_live_report_probes_handles_and_domains(self):
        import requests

        def fake_get(url, **kwargs):
            if "pinterest.com" in url or "instagram.com" in url:
                return _Resp(404)
            return _Resp(404)          # domains: not serving

        old = requests.get
        requests.get = fake_get
        self.addCleanup(lambda: setattr(requests, "get", old))

        text = "\n".join(naming.report("Gharvana", _cfg(), live=True))
        self.assertIn("LIVE CHECK", text)
        self.assertIn("FREE on both", text)
        self.assertIn("gharvana.com", text)
        self.assertIn("gharvana.in", text)

    def test_report_never_raises_on_empty_name(self):
        text = "\n".join(naming.report("", _cfg()))
        self.assertIn("BRAND DECISION", text)


class TestCli(unittest.TestCase):
    def test_named_and_default_output(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = Config(raw={"storage": {"db_path": f"{tmp}/t.db",
                                          "media_dir": f"{tmp}/m"},
                              "brand": {"display_name": "Gharvana | Home & Kitchen"},
                              "dashboard": {"password": "", "secret_key": "t"}})
            (tmp / "m").mkdir(parents=True, exist_ok=True)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_name(cfg, ["Gharvana"]), 0)
            self.assertIn("BRAND DECISION", buf.getvalue())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_name(cfg, []), 0)     # uses config brand
            self.assertIn("Gharvana", buf.getvalue())

    def test_live_flag_is_recognised_without_network(self):
        import requests

        def boom(url, **kwargs):
            raise requests.ConnectionError("offline")

        old = requests.get
        requests.get = boom
        self.addCleanup(lambda: setattr(requests, "get", old))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(cmd_name(_cfg(), ["Gharvana", "--live"]), 0)
        self.assertIn("LIVE CHECK", buf.getvalue())

    def test_dispatch_and_help_are_wired(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn('if cmd in ("name", "naming", "brand-name")', src)
        self.assertIn("python -m bot name", src)

    def test_real_config_has_a_healthy_configured_brand(self):
        """Invariant, not a hardcoded name: whatever is configured must be sane."""
        import yaml
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        data = yaml.safe_load(repo.read_text())
        display = data["brand"]["display_name"]
        strip = data["design"]["brand_name"]
        handle = data["brand"]["handle"]
        self.assertTrue(display.startswith(strip))          # strip inside name
        self.assertTrue(strip)                              # artwork word set
        self.assertTrue(handle and handle.islower())        # handle normalised
        self.assertLessEqual(len(handle), 30)
        self.assertNotIn(handle, naming.KNOWN_USED)         # not a known mess
        self.assertGreaterEqual(naming.score(strip)["score"], 70)
        self.assertTrue(display.startswith(f"{strip} |"))   # keyword field used
        self.assertLessEqual(len(display), 30)
        self.assertIn(strip, data["brand"]["bio"])


if __name__ == "__main__":
    unittest.main()
