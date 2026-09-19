"""R53: the onboarding cheat-sheet command (every Pinterest screen answered)."""
from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from bot import onboard
from bot.config import Config, load_config
from bot.main import cmd_onboard


def _cfg(tmp: Path, **raw) -> Config:
    base = {"storage": {"db_path": f"{tmp}/t.db", "media_dir": f"{tmp}/m"},
            "dashboard": {"password": "", "secret_key": "t"}}
    base.update(raw)
    cfg = Config(raw=base)
    (tmp / "m").mkdir(parents=True, exist_ok=True)
    return cfg


class TestOnboardSheet(unittest.TestCase):
    def test_answers_every_screen_we_were_asked(self):
        text = "\n".join(onboard.lines())
        for answer in ("Content creator", "Home", "Increase online sales",
                       "Drive traffic to your site", "Create a Pin",
                       "Share ideas", "Claim your website", "Showcase your brand",
                       "Claim website", "domain_verify" if False else "Rich Pins",
                       "developers.pinterest.com"):
            self.assertIn(answer, text, answer)
        # the exact question the owner asked, answered
        self.assertIn("SKIP", text)
        self.assertIn("OPTIONAL", text)
        self.assertIn("REQUIRED", text)

    def test_only_two_things_are_required(self):
        required = [s for s in onboard.SCREENS if s[3] == "REQUIRED"]
        self.assertEqual(len(required), 2)
        self.assertIn("developer", required[1][0].lower())
        self.assertIn("business account", required[0][0].lower())

    def test_personalised_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = _cfg(tmp, brand={"display_name": "Ghar Finds | Home & Kitchen",
                                   "bio": "Home & kitchen finds under budget"},
                       link={"public_base": "https://shop.example.com"})
            text = "\n".join(onboard.lines(cfg))
            self.assertIn("Ghar Finds | Home & Kitchen", text)
            self.assertIn("Home & kitchen finds under budget", text)
            self.assertIn("https://shop.example.com", text)

    def test_never_raises_on_broken_config(self):
        class Boom:
            def get(self, *a, **k):
                raise RuntimeError("bad config")
        text = "\n".join(onboard.lines(Boom()))
        self.assertIn("Content creator", text)

    def test_wrap_respects_width(self):
        for line in onboard._wrap("word " * 60, 62):
            self.assertLessEqual(len(line), 62)

    def test_cli_prints_and_returns_zero(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(Path(d))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_onboard(cfg), 0)
            self.assertIn("Create a Pin", buf.getvalue())

    def test_cli_dispatch_alias(self):
        src = (Path(__file__).resolve().parents[1] / "bot" / "main.py").read_text()
        self.assertIn('if cmd in ("onboard", "onboarding")', src)

    def test_reads_real_config_without_crash(self):
        repo = Path(__file__).resolve().parents[1] / "config.yaml"
        text = "\n".join(onboard.lines(load_config(repo)))
        self.assertIn("ONBOARDING", text)


if __name__ == "__main__":
    unittest.main()
