"""R66 tests — EarnKaro API client, cache, wiring and CLI.

No test ever touches the network: every HTTP call goes through a fake session,
every token is generated locally.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot import creds                      # noqa: E402
from bot import earnkaro as ek             # noqa: E402
from bot.affiliate import AffiliateLinker  # noqa: E402


def b64(obj) -> str:
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_jwt(payload=None, header=None) -> str:
    payload = {"_id": "6a6f90496dff9665696fc624", "earnkaro": "5478322",
               "iat": 1789820612} if payload is None else payload
    return f"{b64(header or {'alg': 'HS256', 'typ': 'JWT'})}.{b64(payload)}.sig"


class Cfg:
    """Minimal config stub — the bot's Config is overkill for these tests."""

    def __init__(self, amazon_tag="", data_dir=None, **kw):
        self.amazon_tag = amazon_tag
        if data_dir is not None:
            self.data_dir = pathlib.Path(data_dir)
        self.data = kw

    def get(self, key, default=None):
        return self.data.get(key, default)


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.url = "https://ekaro.in/enkr123"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self):
        return self.responses.pop(0) if self.responses else FakeResp(500, {})

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}),
                           "json": json, "timeout": timeout})
        item = self._next()
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, **kw):
        self.calls.append({"url": url, "get": True})
        item = self._next()
        if isinstance(item, Exception):
            raise item
        return item


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.cache = self.dir / "earnkaro_links.json"
        self.token = make_jwt()
        patcher = mock.patch.dict(os.environ, {
            "EARNKARO_API_TOKEN": self.token,
            "PINTREST_OFFLINE": "",
        }, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cfg(self, **kw) -> Cfg:
        return Cfg(data_dir=self.dir, **kw)

    def api(self, responses, **kw) -> ek.EarnKaroAPI:
        return ek.EarnKaroAPI(self.cfg(), session=FakeSession(responses),
                              cache_path=self.cache, sleep=lambda s: None, **kw)


# --------------------------------------------------------------- token shape
class TestTokenDecode(Base):
    def test_owner_token_decodes_to_his_account(self):
        info = ek.decode_token(make_jwt())
        self.assertTrue(info["ok"])
        self.assertEqual(info["earnkaro"], "5478322")
        self.assertEqual(info["issued"][:4], "2026")
        self.assertFalse(info["has_exp"])

    def test_missing_earnkaro_id_falls_back_to_object_id(self):
        info = ek.decode_token(make_jwt({"_id": "abc123"}))
        self.assertTrue(info["ok"])
        self.assertEqual(info["id"], "abc123")

    def test_garbage_token_refused(self):
        self.assertFalse(ek.decode_token("hello")["ok"])
        self.assertFalse(ek.decode_token("")["ok"])
        self.assertFalse(ek.decode_token("a.b")["ok"])

    def test_broken_payload_refused(self):
        self.assertFalse(ek.decode_token("aaa.!!!!.ccc")["ok"])

    def test_validate_token_ok_returns_value_and_note(self):
        out = ek.validate_token(make_jwt())
        self.assertTrue(out["ok"])
        self.assertIn("5478322", out["note"])
        self.assertEqual(out["value"], make_jwt())

    def test_validate_token_bad_returns_fix(self):
        out = ek.validate_token("not-a-jwt")
        self.assertFalse(out["ok"])
        self.assertIn("Token shape", out["error"])
        self.assertIn("creds", out["fix"])

    def test_validate_token_without_earnkaro_claim_refused(self):
        out = ek.validate_token(make_jwt({"sub": "x"}))
        self.assertFalse(out["ok"])

    def test_masked_token_never_leaks_full_secret(self):
        api = self.api([])
        self.assertNotIn(self.token, api.masked_token)
        self.assertIn("chars", api.masked_token)


# --------------------------------------------------------------- conversion
class TestConversion(Base):
    def test_happy_path_uses_confirmed_body_and_key(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr999",
                                                     "merchant": "Flipkart",
                                                     "commission_rate": "7%"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("https://www.flipkart.com/x/p/itm123")
        self.assertTrue(res["ok"])
        self.assertEqual(res["affiliate_url"], "https://ekaro.in/enkr999")
        self.assertEqual(res["merchant"], "Flipkart")
        self.assertEqual(res["rate"], "7%")
        call = sess.calls[0]
        self.assertEqual(call["url"], ek.API_URL)
        self.assertEqual(call["json"], {"url": "https://www.flipkart.com/x/p/itm123"})
        self.assertTrue(call["headers"]["Authorization"].startswith("Bearer ey"))

    def test_cache_hit_does_not_call_api_again(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert("https://www.ajio.com/p/1")
        second = api.convert("https://www.ajio.com/p/1")
        self.assertTrue(second["cached"])
        self.assertEqual(len(sess.calls), 1)

    def test_force_bypasses_cache(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}}),
                            FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr2"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert("https://www.ajio.com/p/1")
        again = api.convert("https://www.ajio.com/p/1", force=True)
        self.assertEqual(again["affiliate_url"], "https://ekaro.in/enkr2")
        self.assertEqual(len(sess.calls), 2)

    def test_alternate_response_shapes_are_understood(self):
        for payload in ({"data": {"converted_links": [{"converted_url": "https://ekaro.in/enkrA"}]}},
                        {"data": {"affiliate_url": "https://ekaro.in/enkrB"}},
                        {"shortUrl": "https://ekaro.in/enkrC"},
                        {"data": {"converted_url": "https://ekaro.in/enkrD"}}):
            with self.subTest(payload=payload):
                api = self.api([FakeResp(200, payload)])
                res = api.convert("https://www.myntra.com/p/2")
                self.assertTrue(res["ok"], res)
                self.assertTrue(res["affiliate_url"].startswith("https://ekaro.in/enkr"))

    def test_body_shape_fallback_remembers_what_worked(self):
        sess = FakeSession([FakeResp(200, {"message": "url required"}),          # shape 1
                            FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr5"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("https://www.nykaa.com/p/3")
        self.assertTrue(res["ok"])
        self.assertEqual(sess.calls[1]["json"],
                         {"url": "https://www.nykaa.com/p/3",
                          "convert_option": "convert_only"})
        self.assertEqual(api.shape_state["shape"], "url+convert")

    def test_remembered_shape_is_tried_first(self):
        api1 = ek.EarnKaroAPI(self.cfg(), cache_path=self.cache)
        api1._remember_shape("deal+convert")
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr7"}})])
        api2 = ek.EarnKaroAPI(self.cfg(), session=sess,
                              cache_path=self.cache, sleep=lambda s: None)
        api2.convert("https://www.croma.com/p/4")
        self.assertIn("deal", sess.calls[0]["json"])

    def test_401_is_terminal_and_explains_refresh(self):
        sess = FakeSession([FakeResp(401, {"message": "unauthorized"})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("https://www.ajio.com/p/9")
        self.assertFalse(res["ok"])
        self.assertIn("Token expire", res["reason"])
        self.assertEqual(len(sess.calls), 1)

    def test_429_retries_then_succeeds(self):
        sess = FakeSession([FakeResp(429, {}),
                            FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr8"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        self.assertTrue(api.convert("https://www.ajio.com/p/10")["ok"])
        self.assertEqual(len(sess.calls), 2)

    def test_network_error_never_raises(self):
        sess = FakeSession([ConnectionError("boom")] * 3)
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("https://www.ajio.com/p/11")
        self.assertFalse(res["ok"])
        self.assertIn("network", res["reason"])
        self.assertEqual(len(sess.calls), 2)   # one retry, then gave up

    def test_circuit_opens_after_network_death(self):
        sess = FakeSession([ConnectionError("boom")] * 3)
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert("https://www.ajio.com/p/11")
        calls_after_first = len(sess.calls)
        second = api.convert("https://www.croma.com/p/12")
        self.assertFalse(second["ok"])
        self.assertIn("reach avvatledu", second["reason"])
        self.assertEqual(len(sess.calls), calls_after_first)   # no new calls

    def test_non_json_error_page_is_handled(self):
        api = self.api([FakeResp(200, None, text="<html>oops</html>")] * len(ek.SHAPES))
        res = api.convert("https://www.ajio.com/p/12")
        self.assertFalse(res["ok"])
        self.assertTrue(res["reason"])

    def test_garbage_url_refused_without_calling_api(self):
        sess = FakeSession([])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("flipkart dot com")
        self.assertFalse(res["ok"])
        self.assertEqual(sess.calls, [])

    def test_existing_ekaro_link_is_never_rewritten(self):
        sess = FakeSession([])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert("https://ekaro.in/enkr20240101s999")
        self.assertTrue(res["ok"])
        self.assertIn("never rewritten", res["reason"])
        self.assertEqual(sess.calls, [])

    def test_missing_token_gives_exact_command(self):
        with mock.patch.dict(os.environ, {"EARNKARO_API_TOKEN": "",
                                          "EARNKARO_TOKEN": ""}, clear=False):
            api = ek.EarnKaroAPI(self.cfg(), session=FakeSession([]), cache_path=self.cache)
            res = api.convert("https://www.ajio.com/p/13")
        self.assertFalse(res["ok"])
        self.assertIn("creds --earnkaro-token", res["reason"])

    def test_offline_switch_blocks_calls(self):
        sess = FakeSession([])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache, offline=True)
        res = api.convert("https://www.ajio.com/p/14")
        self.assertFalse(res["ok"])
        self.assertIn("PINTREST_OFFLINE", res["reason"])
        self.assertEqual(sess.calls, [])

    def test_convert_many_reports_each(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}}),
                            FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr2"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.convert_many(["https://www.ajio.com/p/a", "https://www.croma.com/p/b"],
                               gap=0)
        self.assertEqual([r["ok"] for r in res], [True, True])


# -------------------------------------------------------------------- cache
class TestCache(Base):
    def test_cache_file_written_and_reusable_across_instances(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert("https://www.ajio.com/p/1")
        self.assertTrue(self.cache.exists())
        fresh = ek.EarnKaroAPI(self.cfg(), session=FakeSession([]), cache_path=self.cache)
        hit = fresh.convert("https://www.ajio.com/p/1")
        self.assertTrue(hit["cached"])
        self.assertEqual(hit["affiliate_url"], "https://ekaro.in/enkr1")

    def test_corrupt_cache_does_not_crash(self):
        self.cache.write_text("{not json")
        api = self.api([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}})])
        self.assertTrue(api.convert("https://www.ajio.com/p/2")["ok"])

    def test_cache_stats_counts_hosts(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}}),
                            FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr2"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert_many(["https://www.ajio.com/p/a", "https://www.ajio.com/p/b"], gap=0)
        stats = api.cache_stats()
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["hosts"]["www.ajio.com"], 2)

    def test_fragment_is_ignored_in_cache_key(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        api.convert("https://www.ajio.com/p/1#reviews")
        self.assertEqual(len(sess.calls), 1)
        self.assertTrue(api.convert("https://www.ajio.com/p/1")["cached"])


# -------------------------------------------------------- linker integration
class TestLinkerWiring(Base):
    def test_converter_is_used_for_non_direct_stores(self):
        lk = AffiliateLinker(Cfg(), converter=lambda url: "https://ekaro.in/enkrXYZ")
        link, network = lk.convert("https://www.myntra.com/kurta/123", "myntra")
        self.assertTrue(link.startswith("https://ekaro.in/enkrXYZ"), link)
        self.assertTrue(lk.is_monetized(link))

    def test_converter_failure_falls_back_to_prefix(self):
        cfg = Cfg(**{"affiliate.earnkaro_prefix": "https://ekaro.in/enkrPREFIX"})
        lk = AffiliateLinker(cfg, converter=lambda url: None)
        link, _ = lk.convert("https://www.myntra.com/kurta/123", "myntra")
        self.assertIn("enkrPREFIX", link)

    def test_converter_exception_never_breaks_publishing(self):
        def boom(url):
            raise ConnectionError("api down")
        cfg = Cfg(**{"affiliate.earnkaro_prefix": "https://ekaro.in/enkrPREFIX"})
        lk = AffiliateLinker(cfg, converter=boom)
        link, _ = lk.convert("https://www.myntra.com/kurta/123", "myntra")
        self.assertIn("enkrPREFIX", link)

    def test_no_converter_no_prefix_means_no_link_honestly(self):
        lk = AffiliateLinker(Cfg(), converter=lambda url: None)
        link, _ = lk.convert("https://www.myntra.com/kurta/123", "myntra")
        self.assertFalse(lk.is_monetized(link))

    def test_from_cfg_without_token_keeps_old_behaviour(self):
        with mock.patch.dict(os.environ, {"EARNKARO_API_TOKEN": "",
                                          "EARNKARO_TOKEN": ""}, clear=False):
            lk = AffiliateLinker.from_cfg(self.cfg())
        self.assertIsNone(lk._converter)

    def test_build_converter_none_without_token(self):
        with mock.patch.dict(os.environ, {"EARNKARO_API_TOKEN": "",
                                          "EARNKARO_TOKEN": ""}, clear=False):
            self.assertIsNone(ek.build_converter(self.cfg()))

    def test_build_converter_returns_callable_with_token(self):
        with mock.patch.object(ek.EarnKaroAPI, "convert",
                               return_value={"ok": True,
                                             "affiliate_url": "https://ekaro.in/enkrBUILT"}):
            conv = ek.build_converter(self.cfg())
            self.assertTrue(callable(conv))
            self.assertEqual(conv("https://www.ajio.com/p/1"), "https://ekaro.in/enkrBUILT")

    def test_built_converter_returns_none_on_failure(self):
        with mock.patch.object(ek.EarnKaroAPI, "convert",
                               return_value={"ok": False, "affiliate_url": ""}):
            conv = ek.build_converter(self.cfg())
            self.assertIsNone(conv("https://www.ajio.com/p/1"))

    def test_amazon_and_meesho_paths_are_untouched_by_the_api(self):
        lk = AffiliateLinker(Cfg(amazon_tag="mama086-21"),
                             converter=lambda url: "https://ekaro.in/SHOULD-NOT-HAPPEN")
        link, _ = lk.convert("https://www.amazon.in/dp/B08N2Z7R1L", "amazon")
        self.assertIn("tag=mama086-21", link)
        self.assertNotIn("enkr", link)


# ---------------------------------------------------------------- creds/CLI
class TestCredsAndCli(Base):
    def test_token_saved_through_creds(self):
        env = self.dir / ".env"
        env.write_text("# secrets\nAMAZON_TAG=mama086-21\n")
        res = creds.apply_credentials([("EARNKARO_API_TOKEN", make_jwt())], path=env)
        self.assertTrue(res["results"][0]["ok"])
        self.assertIn("EARNKARO_API_TOKEN", env.read_text())
        self.assertIn("AMAZON_TAG=mama086-21", env.read_text())

    def test_bad_token_not_saved(self):
        env = self.dir / ".env"
        env.write_text("")
        res = creds.apply_credentials([("EARNKARO_API_TOKEN", "nope")], path=env)
        self.assertFalse(res["results"][0]["ok"])
        self.assertNotIn("EARNKARO_API_TOKEN=", env.read_text())

    def test_status_board_shows_the_api_token(self):
        text = "\n".join(creds.status_lines())
        self.assertIn("EarnKaro API token", text)
        self.assertIn("5478322", text)

    def test_status_board_without_token_explains_capture(self):
        with mock.patch.dict(os.environ, {"EARNKARO_API_TOKEN": "",
                                          "EARNKARO_TOKEN": ""}, clear=False):
            text = "\n".join(creds.status_lines())
        self.assertIn("EarnKaro API token", text)
        self.assertIn("(not set)", text)

    def test_cli_status_without_token_prints_guidance(self):
        with mock.patch.dict(os.environ, {"EARNKARO_API_TOKEN": "",
                                          "EARNKARO_TOKEN": ""}, clear=False):
            with mock.patch("builtins.print") as pr:
                rc = ek.cli(Cfg(), ["status"])
        self.assertEqual(rc, 0)
        printed = " ".join(str(c) for c in pr.call_args_list)
        self.assertIn("EARNKARO", printed.upper())

    def test_cli_convert_without_url_is_usage_error(self):
        with mock.patch("builtins.print"):
            self.assertEqual(ek.cli(Cfg(), ["convert"]), 1)

    def test_cli_convert_prints_link(self):
        stub = mock.Mock()
        stub.convert.return_value = {"ok": True, "affiliate_url": "https://ekaro.in/enkrCLI",
                                     "merchant": "Myntra", "rate": "", "cached": False,
                                     "reason": "converted"}
        with mock.patch.object(ek, "EarnKaroAPI", lambda *a, **k: stub):
            with mock.patch("builtins.print") as pr:
                rc = ek.cli(Cfg(), ["convert", "https://www.myntra.com/p/1"])
        self.assertEqual(rc, 0)
        self.assertIn("https://ekaro.in/enkrCLI", " ".join(str(c) for c in pr.call_args_list))

    def test_cli_convert_failure_is_not_silent(self):
        stub = mock.Mock()
        stub.convert.return_value = {"ok": False, "affiliate_url": "", "reason": "boom"}
        with mock.patch.object(ek, "EarnKaroAPI", lambda *a, **k: stub):
            with mock.patch("builtins.print") as pr:
                rc = ek.cli(Cfg(), ["convert", "https://www.myntra.com/p/1"])
        self.assertEqual(rc, 1)
        self.assertIn("quarantine", " ".join(str(c) for c in pr.call_args_list))

    def test_cli_unknown_subcommand_prints_usage(self):
        with mock.patch("builtins.print"):
            self.assertEqual(ek.cli(Cfg(), ["wat"]), 1)

    def test_cli_bulk_missing_file(self):
        with mock.patch("builtins.print"):
            self.assertEqual(ek.cli(Cfg(), ["bulk", str(self.dir / "nope.txt")]), 1)

    def test_cli_bulk_converts_file(self):
        path = self.dir / "links.txt"
        path.write_text("https://www.ajio.com/p/1\n# comment\nhttps://www.croma.com/p/2\n")
        stub = mock.Mock()
        stub.convert_many.return_value = [
            {"ok": True, "url": "https://www.ajio.com/p/1",
             "affiliate_url": "https://ekaro.in/enkr1", "reason": ""},
            {"ok": False, "url": "https://www.croma.com/p/2", "affiliate_url": "",
             "reason": "boom"},
        ]
        stub.cache_stats.return_value = {"count": 1, "hosts": {}}
        with mock.patch.object(ek, "EarnKaroAPI", lambda *a, **k: stub):
            with mock.patch("builtins.print"):
                rc = ek.cli(Cfg(), ["bulk", str(path)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(stub.convert_many.call_args[0][0]), 2)


# ------------------------------------------------------------------ capture
class TestCaptureHelpers(Base):
    def test_extract_bearer_case_insensitive(self):
        self.assertEqual(ek.extract_bearer({"authorization": "Bearer abc.def.ghi"}),
                         "abc.def.ghi")
        self.assertEqual(ek.extract_bearer({"Authorization": "BEARER xyz"}).lower(),
                         "xyz")
        self.assertEqual(ek.extract_bearer({"Accept": "json"}), "")

    def test_extract_bearer_accepts_bare_jwt(self):
        tok = make_jwt()
        self.assertEqual(ek.extract_bearer({"Authorization": tok}), tok)

    def test_is_api_url_matches_earnkaro_hosts(self):
        self.assertTrue(ek.is_api_url("https://webapi.earnkaro.com/api/affiliate/link-converter"))
        self.assertTrue(ek.is_api_url("https://earnkaro.com/x"))
        self.assertFalse(ek.is_api_url("https://www.flipkart.com/x"))

    def test_howto_mentions_both_paths(self):
        text = "\n".join(ek.howto_lines())
        self.assertIn("earnkaro capture", text)
        self.assertIn("--earnkaro-token", text)
        self.assertIn("share cheyyakandi", text)

    def test_playwright_hint(self):
        self.assertIn("pip install playwright", ek.install_playwright_hint())

    def test_capture_without_playwright_gives_install_hint(self):
        real_import = __import__

        def fake_import(name, *a, **k):
            if name.startswith("playwright"):
                raise ImportError("no playwright")
            return real_import(name, *a, **k)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            res = ek.capture_with_browser(save=False)
        self.assertFalse(res["ok"])
        self.assertIn("pip install playwright", res["error"])


class TestStatusLines(Base):
    def test_status_shows_account_and_cache(self):
        api = self.api([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}})])
        api.convert("https://www.ajio.com/p/1")
        with mock.patch.object(ek.EarnKaroAPI, "cache_stats",
                               return_value={"count": 1, "hosts": {"www.ajio.com": 1}}):
            text = "\n".join(ek.status_lines(Cfg()))
        self.assertIn("EARNKARO API", text)
        self.assertIn("5478322", text)

    def test_probe_reports_redirect_when_link_comes_back(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}}),
                            FakeResp(200, {"ok": 1})])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.probe("https://www.flipkart.com/x/p/itm1")
        self.assertTrue(res["convert"]["ok"])
        self.assertTrue(res["redirect"]["checked"])

    def test_probe_survives_link_that_does_not_resolve(self):
        sess = FakeSession([FakeResp(200, {"data": {"shortUrl": "https://ekaro.in/enkr1"}}),
                            ConnectionError("no route")])
        api = ek.EarnKaroAPI(self.cfg(), session=sess, cache_path=self.cache,
                             sleep=lambda s: None)
        res = api.probe("https://www.flipkart.com/x/p/itm1")
        self.assertTrue(res["convert"]["ok"])
        self.assertEqual(res["redirect"]["status"], 0)

    def test_offline_flag_env_is_respected(self):
        with mock.patch.dict(os.environ, {"PINTREST_OFFLINE": "1"}, clear=False):
            self.assertTrue(ek.EarnKaroAPI(Cfg()).offline)
        with mock.patch.dict(os.environ, {"PINTREST_OFFLINE": "0"}, clear=False):
            self.assertFalse(ek.EarnKaroAPI(Cfg()).offline)


if __name__ == "__main__":
    unittest.main()


class TestSecretMasking(Base):
    def test_tokens_are_never_echoed_in_full(self):
        tok = make_jwt()
        masked = creds.mask("EARNKARO_API_TOKEN", tok)
        self.assertNotIn(tok, masked)
        self.assertIn("chars", masked)

    def test_non_secret_values_still_print(self):
        self.assertEqual(creds.mask("AMAZON_TAG", "mama086-21"), "mama086-21")
        self.assertEqual(creds.mask("EARNKARO_PREFIX", "https://ekaro.in/enkr1"),
                         "https://ekaro.in/enkr1")
