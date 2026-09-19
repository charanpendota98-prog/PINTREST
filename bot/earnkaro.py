"""EarnKaro deeplink API — convert ANY product URL into YOUR ekaro.in link.

Why this module exists
----------------------
The statically-pasted "deeplink prefix" (`ekaro.in/enkr…?url=<product>`) is a
convention the bot could never prove, and it only ever worked for one store at
a time. EarnKaro's own web API converts a URL into a *real* per-product profit
link — the same call the EarnKaro site and app make for you when you tap
"Create affiliate link".

Contract (independently confirmed in two public codebases):

    POST https://webapi.earnkaro.com/api/affiliate/link-converter
    Authorization: Bearer <JWT>          # payload {"_id", "earnkaro", "iat"}
    Content-Type: application/json
    body:  {"url": "<product url>"}
    resp:  {"data": {"shortUrl": "https://ekaro.in/enkr…"}}

The JWT is the owner's OWN EarnKaro session token, so every conversion is
credited to his own EarnKaro account — no middleman, no reseller API
(`ekaro-api.affiliaters.in` and friends are third parties and are refused).

Design rules baked in here
--------------------------
* never rewrite a link that is already monetized (owner-pasted Meesho links,
  existing ekaro.in deeplinks) — that would break tracking
* every conversion is cached in `data/earnkaro_links.json`: a product is
  converted once, and publishing still works if the API blips later
* adaptive request/response shapes + versioned cache: if EarnKaro changes
  internals, the next known shape is tried and the working one is remembered
* any failure returns no link at all → the QA gate quarantines that pin.
  A broken link is never posted, and an untracked link is never posted.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("pindrop.earnkaro")

# ---------------------------------------------------------------- constants
API_URL = "https://webapi.earnkaro.com/api/affiliate/link-converter"

# Request bodies we have seen EarnKaro-style APIs accept. The first one is the
# documented-by-observation shape; the rest are fallbacks if their contract
# shifts. The one that works is remembered in data/earnkaro_api_shape.json.
SHAPES: tuple[str, ...] = (
    "url",                 # {"url": url}                       ← confirmed
    "url+convert",         # {"url": url, "convert_option": "convert_only"}
    "deal+convert",        # {"deal": url, "convert_option": "convert_only"}
    "urls+convert",        # {"urls": [url], "convert_option": "convert_only"}
)

# Where the affiliate link can hide in a response. Order matters: the confirmed
# key first, then every variant seen in the wild.
LINK_PATHS: tuple[tuple, ...] = (
    ("data", "shortUrl"),
    ("data", "short_url"),
    ("data", "convertedUrl"),
    ("data", "converted_url"),
    ("data", "affiliate_url"),
    ("data", "affiliateUrl"),
    ("data", "dealUrl"),
    ("data", "deal_url"),
    ("data", "url"),
    ("shortUrl",),
    ("data", "links", 0, "url"),
    ("data", "converted_links", 0, "converted_url"),
    ("data", "converted_links", 0, "short_url"),
    ("data", "deals", 0, "affiliate_url"),
    ("data", 0, "shortUrl"),
)

MERCHANT_PATHS: tuple[tuple, ...] = (
    ("data", "merchant"), ("data", "store"), ("data", "storeName"),
    ("data", "deals", 0, "merchant"), ("data", "converted_links", 0, "merchant"),
)
RATE_PATHS: tuple[tuple, ...] = (
    ("data", "commission_rate"), ("data", "commissionRate"),
    ("data", "cashback"), ("data", "profit"), ("data", "rate"),
)

ALREADY_EKARO = re.compile(r"ekaro\.in|earnkaro\.com/\S", re.I)
RETRY_STATUS = (408, 429, 500, 502, 503, 504)
TOKEN_EXPIRED_HINT = (
    "Token expire/invalid ayindi. EarnKaro lo fresh token teesukondi → "
    "python -m bot creds --earnkaro-token '<new jwt>'  "
    "(yaa: python -m bot earnkaro capture)"
)


# ------------------------------------------------------------------- helpers
def _dig(payload, path: tuple):
    """Walk a nested dict/list by path, returning None instead of raising."""
    node = payload
    for key in path:
        try:
            if isinstance(key, int):
                if not isinstance(node, (list, tuple)) or len(node) <= key:
                    return None
                node = node[key]
            else:
                if not isinstance(node, dict):
                    return None
                node = node.get(key)
        except Exception:  # noqa: BLE001 — never let a weird payload crash a run
            return None
    return node


def _norm_url(url: str) -> str:
    """Cache key: the URL without its fragment. Nothing else is touched."""
    return str(url or "").split("#", 1)[0].strip()


def decode_token(token: str) -> dict:
    """Read the JWT payload WITHOUT verifying it (we cannot — unknown secret).

    We are not the security boundary here: the EarnKaro API is. We only read
    the payload so the bot can tell the owner WHICH account a token belongs to
    and how old it is.
    """
    tok = str(token or "").strip()
    if not tok:
        return {"ok": False, "reason": "token khali undi"}
    parts = tok.split(".")
    if len(parts) != 3:
        return {"ok": False, "reason": "JWT kaadu (3 parts undali)"}
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": "JWT payload chadavadam kudaraledu"}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "JWT payload object kaadu"}
    ident = str(payload.get("earnkaro") or payload.get("userId")
                or payload.get("_id") or "").strip()
    iat = payload.get("iat")
    try:
        iat = int(iat) if iat is not None else 0
    except (TypeError, ValueError):
        iat = 0
    age_days = None
    issued = ""
    if iat:
        age_days = round((time.time() - iat) / 86400.0, 1)
        issued = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(iat))
    return {"ok": True, "id": ident, "earnkaro": ident, "iat": iat,
            "age_days": age_days, "issued": issued,
            "has_exp": bool(payload.get("exp")), "payload": payload}


def validate_token(token: str) -> dict:
    """Validator used by `bot creds --earnkaro-token` (shape only, offline)."""
    info = decode_token(token)
    if not info.get("ok"):
        return {"ok": False, "error": f"Token shape thappu: {info.get('reason')}",
                "fix": "EarnKaro lo login ayyi token copy cheyyandi → "
                       "python -m bot creds --earnkaro-token '<jwt>'"}
    if not info.get("earnkaro"):
        return {"ok": False,
                "error": "JWT lo 'earnkaro' id ledu — idi EarnKaro token kaadu la undi.",
                "fix": "webapi.earnkaro.com request ki pampina Authorization "
                       "header value teesukondi."}
    note = (f"EarnKaro account id {info['earnkaro']} · issued {info['issued']}"
            f" ({info['age_days']}d old)")
    if info.get("age_days") is not None and info["age_days"] > 180:
        note += " — chala old; pani cheyyakapote fresh token teesukondi"
    return {"ok": True, "value": str(token).strip(), "note": note}


def extract_bearer(headers) -> str:
    """Pull 'Bearer <jwt>' out of a headers mapping (case-insensitive)."""
    if not headers:
        return ""
    for key, value in dict(headers).items():
        if str(key).lower() in ("authorization", "authorisation", "x-access-token",
                                "x-auth-token"):
            val = str(value or "").strip()
            if val.lower().startswith("bearer "):
                return val.split(" ", 1)[1].strip()
            if val.count(".") == 2 and len(val) > 40:  # bare JWT
                return val
    return ""


def is_api_url(url: str) -> bool:
    """Is this the EarnKaro web-API host (i.e. carries the real token)?"""
    try:
        host = (urlparse(str(url or "")).netloc or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return host.endswith("webapi.earnkaro.com") or host.endswith("earnkaro.com")


def _looks_like_link(value) -> bool:
    return isinstance(value, str) and value.startswith("http") and len(value) < 600


def _prefer_ekaro(links: list[str]) -> str:
    for lnk in links:
        if "ekaro" in lnk.lower() or "earnkaro" in lnk.lower():
            return lnk
    return links[0] if links else ""


# ------------------------------------------------------------------- client
class EarnKaroAPI:
    """Thin, honest client around EarnKaro's link-converter endpoint."""

    def __init__(self, cfg=None, session=None, endpoint: str | None = None,
                 cache_path: str | Path | None = None, timeout: int = 12,
                 sleep=time.sleep, offline: bool | None = None):
        self.cfg = cfg
        self._session = session
        self._endpoint = endpoint
        self._cache_path = Path(cache_path) if cache_path else None
        self.timeout = timeout
        self._sleep = sleep
        self._offline = offline
        self._cache: dict | None = None
        self._shape_state: dict | None = None
        # circuit breaker: once the network is provably down, stop stalling the
        # publish loop for every remaining product in this process
        self._net_down = ""
        self.calls = 0

    # ------------------------------------------------------------- config
    def _cfg_get(self, key: str, default=""):
        if self.cfg is None:
            return default
        try:
            return self.cfg.get(key, default)
        except Exception:  # noqa: BLE001
            return default

    @property
    def token(self) -> str:
        return (os.getenv("EARNKARO_API_TOKEN", "") or
                os.getenv("EARNKARO_TOKEN", "") or
                self._cfg_get("affiliate.earnkaro_api_token", "") or "").strip()

    @property
    def endpoint(self) -> str:
        return (self._endpoint or os.getenv("EARNKARO_API_URL", "") or
                self._cfg_get("affiliate.earnkaro_api_url", "") or API_URL).strip()

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def offline(self) -> bool:
        if self._offline is not None:
            return bool(self._offline)
        return str(os.getenv("PINTREST_OFFLINE", "")).strip() not in ("", "0", "false")

    @property
    def identity(self) -> dict:
        return decode_token(self.token)

    @property
    def masked_token(self) -> str:
        tok = self.token
        if not tok:
            return ""
        return f"{tok[:16]}…({len(tok)} chars)"

    # -------------------------------------------------------------- paths
    def _data_dir(self) -> Path:
        for attr in ("data_dir",):
            val = getattr(self.cfg, attr, None) if self.cfg is not None else None
            if val:
                return Path(val)
        db = getattr(self.cfg, "db_path", None) if self.cfg is not None else None
        if db:
            return Path(db).parent
        return Path(__file__).resolve().parent.parent / "data"

    @property
    def cache_path(self) -> Path:
        return self._cache_path or (self._data_dir() / "earnkaro_links.json")

    @property
    def shape_path(self) -> Path:
        return self._data_dir() / "earnkaro_api_shape.json"

    # -------------------------------------------------------------- cache
    def _read_json(self, path: Path) -> dict:
        try:
            if path.exists():
                data = json.loads(path.read_text())
                return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 — a corrupt cache must never break a run
            log.warning("earnkaro: could not read %s — starting fresh", path)
        return {}

    def _write_json(self, path: Path, data: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            log.warning("earnkaro: could not write %s (%s)", path, e)

    @property
    def cache(self) -> dict:
        if self._cache is None:
            self._cache = self._read_json(self.cache_path)
        return self._cache

    def cached(self, url: str) -> dict | None:
        return self.cache.get(_norm_url(url))

    def cache_stats(self) -> dict:
        links = self.cache
        hosts: dict[str, int] = {}
        for url, rec in links.items():
            hosts[urlparse(url).netloc.lower()] = hosts.get(urlparse(url).netloc.lower(), 0) + 1
        return {"count": len(links), "hosts": hosts}

    # --------------------------------------------------------- shape memory
    @property
    def shape_state(self) -> dict:
        if self._shape_state is None:
            self._shape_state = self._read_json(self.shape_path)
        return self._shape_state

    def _remember_shape(self, shape: str) -> None:
        self.shape_state["shape"] = shape
        self._write_json(self.shape_path, self.shape_state)

    def _shape_order(self) -> list[str]:
        good = str(self.shape_state.get("shape") or "")
        order = [good] if good in SHAPES else []
        order += [s for s in SHAPES if s not in order]
        return order

    def _body(self, shape: str, url: str) -> dict:
        if shape == "url":
            return {"url": url}
        if shape == "url+convert":
            return {"url": url, "convert_option": "convert_only"}
        if shape == "deal+convert":
            return {"deal": url, "convert_option": "convert_only"}
        return {"urls": [url], "convert_option": "convert_only"}

    # ------------------------------------------------------------ request
    def _client(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; PinDropPro/1.0)"}

    def _extract(self, payload) -> dict:
        if not isinstance(payload, dict):
            return {}
        links = []
        for path in LINK_PATHS:
            val = _dig(payload, path)
            if _looks_like_link(val):
                links.append(val)
        merchant = ""
        for path in MERCHANT_PATHS:
            val = _dig(payload, path)
            if isinstance(val, str) and val.strip():
                merchant = val.strip()
                break
        rate = ""
        for path in RATE_PATHS:
            val = _dig(payload, path)
            if val not in (None, "", [], {}):
                rate = str(val).strip()
                break
        msg = ""
        for path in (("message",), ("msg",), ("error",), ("data", "message")):
            val = _dig(payload, path)
            if isinstance(val, str) and val.strip():
                msg = val.strip()
                break
        link = _prefer_ekaro(links)
        return {"affiliate_url": link, "merchant": merchant, "rate": rate,
                "message": msg, "raw_keys": sorted(payload.keys())[:12]}

    def _post_once(self, body: dict) -> tuple[int, dict, str]:
        resp = self._client().post(self.endpoint, headers=self._headers(),
                                   json=body, timeout=self.timeout)
        self.calls += 1
        status = int(getattr(resp, "status_code", 0) or 0)
        payload, text = {}, ""
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001 — HTML error page, empty body, …
            payload = {}
            text = str(getattr(resp, "text", "") or "")[:200]
        return status, payload if isinstance(payload, dict) else {}, text

    def _post(self, url: str) -> dict:
        """Try each known body shape; retry the network-ish failures."""
        last = {"ok": False, "reason": "no attempt made", "status": 0}
        for shape in self._shape_order():
            body = self._body(shape, url)
            net_fail = ""
            for attempt in range(2):
                try:
                    status, payload, text = self._post_once(body)
                except Exception as e:  # noqa: BLE001 — timeout, DNS, TLS, …
                    net_fail = f"network: {type(e).__name__}: {str(e)[:120]}"
                    if attempt < 1:
                        self._sleep(2 ** attempt)
                        continue
                    break
                net_fail = ""
                if status in (401, 403):
                    return {"ok": False, "status": status, "shape": shape,
                            "reason": TOKEN_EXPIRED_HINT, "fatal": True}
                if status in RETRY_STATUS:
                    if attempt < 1:
                        self._sleep(2 ** attempt)
                        continue
                    # a 5xx/timeout is not a body-shape problem — stop guessing
                    return {"ok": False, "status": status, "shape": shape,
                            "reason": f"EarnKaro server error HTTP {status} — "
                                      "malli try cheyyandi"}
                got = self._extract(payload)
                if status == 200 and got.get("affiliate_url"):
                    self._remember_shape(shape)
                    return {"ok": True, "status": status, "shape": shape, **got}
                last = {"ok": False, "status": status, "shape": shape,
                        "reason": got.get("message") or text or
                                  f"HTTP {status}, link ravaledu",
                        "raw_keys": got.get("raw_keys", [])}
                break  # one answer per shape: 200-but-unusable → next shape
            if net_fail:
                # network is down — trying another body shape cannot help, and
                # every later product should fail fast instead of re-waiting
                self._net_down = net_fail
                return {"ok": False, "status": 0, "shape": shape, "reason": net_fail}
        return last

    # -------------------------------------------------------------- public
    def convert(self, url: str, force: bool = False) -> dict:
        """Convert one product URL into the owner's EarnKaro profit link.

        Returns a dict; `ok` False means NO link (never a fake one).
        """
        raw = str(url or "").strip()
        out = {"ok": False, "url": raw, "affiliate_url": "", "cached": False,
               "merchant": "", "rate": "", "reason": "", "status": 0}
        if not raw.startswith("http"):
            out["reason"] = "URL kaadu"
            return out
        if ALREADY_EKARO.search(raw):
            out.update(ok=True, affiliate_url=raw, merchant="earnkaro",
                       reason="already an EarnKaro deeplink — as-is (never rewritten)")
            return out
        hit = self.cached(raw)
        if hit and not force:
            out.update(ok=True, affiliate_url=hit.get("aff", ""), cached=True,
                       merchant=hit.get("merchant", ""), rate=hit.get("rate", ""),
                       reason="cache nunchi (API call ledu)")
            return out
        if not self.configured:
            out["reason"] = ("EarnKaro API token ledu → python -m bot creds "
                             "--earnkaro-token '<jwt>'")
            return out
        if self.offline:
            out["reason"] = "PINTREST_OFFLINE set — API call cheyyaledu"
            return out
        if self._net_down:
            out["reason"] = (f"EarnKaro reach avvatledu ({self._net_down[:60]}) — "
                             "skip (circuit open, malli process start aithe try)")
            return out

        res = self._post(raw)
        out["status"] = res.get("status", 0)
        if res.get("ok"):
            out.update(ok=True, affiliate_url=res["affiliate_url"],
                       merchant=res.get("merchant", ""), rate=res.get("rate", ""),
                       reason=f"converted via shape '{res.get('shape')}'")
            self.cache[_norm_url(raw)] = {
                "aff": res["affiliate_url"], "merchant": res.get("merchant", ""),
                "rate": res.get("rate", ""), "at": int(time.time()), "src": "api"}
            self._write_json(self.cache_path, self.cache)
            return out
        out["reason"] = res.get("reason") or "conversion failed"
        return out

    def convert_many(self, urls, force: bool = False, gap: float = 1.2) -> list[dict]:
        """Convert a list of URLs, politely paced (one call per URL)."""
        results = []
        for i, url in enumerate(urls):
            results.append(self.convert(url, force=force))
            if gap and i < len(urls) - 1 and not results[-1].get("cached"):
                self._sleep(gap)
        return results

    def probe(self, url: str = "") -> dict:
        """Live end-to-end proof: token → API → link → does it redirect?"""
        sample = url or "https://www.flipkart.com/apple-iphone-15-blue-128-gb/p/itm6ac6485515ae4"
        info = self.identity
        out = {"configured": self.configured, "endpoint": self.endpoint,
               "identity": info, "sample": sample,
               "convert": self.convert(sample, force=True),
               "redirect": {"checked": False, "final": "", "status": 0}}
        link = out["convert"].get("affiliate_url")
        if link and not self.offline:
            try:
                resp = self._client().get(link, timeout=self.timeout,
                                          allow_redirects=True, stream=True)
                out["redirect"] = {"checked": True,
                                   "status": int(getattr(resp, "status_code", 0) or 0),
                                   "final": str(getattr(resp, "url", "") or "")}
            except Exception as e:  # noqa: BLE001
                out["redirect"] = {"checked": True, "status": 0, "final": "",
                                   "error": f"{type(e).__name__}: {str(e)[:120]}"}
        return out


# ------------------------------------------------------------------ wiring
def build_converter(cfg):
    """Return a `url -> affiliate_url|None` callable, or None when unusable.

    Injected into AffiliateLinker at the *publishing* call sites only, so tests
    and read-only checks never touch the network.
    """
    api = EarnKaroAPI(cfg)
    if not api.configured or api.offline:
        return None

    def _convert(url: str) -> str | None:
        res = api.convert(url)
        return res.get("affiliate_url") or None

    return _convert


# --------------------------------------------------------------------- CLI
def status_lines(cfg=None) -> list[str]:
    api = EarnKaroAPI(cfg)
    info = api.identity
    stats = api.cache_stats()
    out = ["═" * 70, "🏷  EARNKARO API — every store → your own profit link", "═" * 70]
    if api.configured and info.get("ok"):
        out += [
            f"   ✅ token set      : {api.masked_token}",
            f"      account id     : {info.get('earnkaro') or '(unknown)'}",
            f"      issued         : {info.get('issued')} ({info.get('age_days')}d old)",
            f"      expires (exp)  : {'yes' if info.get('has_exp') else 'no exp claim (session token)'}",
            f"   ✅ endpoint       : {api.endpoint}",
            f"   ✅ cached links   : {stats['count']}"
            + (f"  {stats['hosts']}" if stats["hosts"] else ""),
            "",
            "   • Flipkart/Myntra/Ajio/Nykaa… prati product ippudu automatic ga",
            "     nee EarnKaro profit link ki convert avutundi (direct, no middleman).",
            "   • Live proof: python -m bot earnkaro probe",
        ]
    elif api.configured:
        out += [f"   ⚠️ token set kani shape doubtful: {info.get('reason')}",
                "   → fresh token: python -m bot earnkaro capture"]
    else:
        out += [
            "   ❌ token ledu → Flipkart/Myntra/Ajio links ki tracking ledu",
            "      (QA gate aa pins ni quarantine chestundi — untracked post avvadu).",
            "   → EarnKaro login ayyaka: python -m bot earnkaro capture",
            "     leda DevTools → webapi.earnkaro.com request → Authorization value:",
            "     python -m bot creds --earnkaro-token '<jwt>'",
        ]
    out.append("")
    return out


def howto_lines() -> list[str]:
    return [
        "═" * 70,
        "🔑 EARNKARO TOKEN — ela teesukovali / refresh cheyyali",
        "═" * 70,
        "",
        "  🥇 EASIEST (recommended):",
        "     python -m bot earnkaro capture",
        "     → browser open avutundi, EarnKaro lo login (OTP) cheyyandi,",
        "       'Make Link' page okkasari open cheyyandi — bot token ni",
        "       automatic ga pattukoni .env lo save chestundi (chmod 600).",
        "     (playwright kavali: pip install playwright && playwright install chromium)",
        "",
        "  🥈 MANUAL (2 nimushalu):",
        "     1) Chrome lo earnkaro.com → login → F12 → Network tab",
        "     2) Filter box lo 'webapi' type cheyyandi",
        "     3) 'Make Link' / profit link generate cheyyandi (page refresh kuda saripothundi)",
        "     4) aa request → Headers → Request Headers →",
        "        'Authorization: Bearer eyJhbGci…' value copy cheyyandi",
        "     5) python -m bot creds --earnkaro-token '<aa JWT>'",
        "",
        "  🔒 ee token nee account ki full access — evariki share cheyyakandi,",
        "     chat/screenshot lo pettakandi. .env git-lo commit avvadu (600).",
        "",
        "  ℹ️  Token pani cheyyakapote (401) bot eh cheptundi — appudu ee",
        "     rendu steps lo okkati chesi malli pettandi. Cache valla already",
        "     converted pins alage pani chestayi.",
        "",
    ]


def install_playwright_hint() -> str:
    return ("playwright ledu — install cheyyandi:\n"
            "   pip install playwright && playwright install chromium\n"
            "   tarvata: python -m bot earnkaro capture")


def capture_with_browser(save: bool = True, timeout_s: int = 600) -> dict:
    """Open a real browser, let the owner log in, capture the bearer token.

    Nothing is stored until a request to EarnKaro's API carries an
    Authorization header — i.e. until the owner is genuinely logged in.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": install_playwright_hint()}
    found: dict = {}

    def _on_request(req):
        try:
            if found.get("token"):
                return
            if is_api_url(req.url):
                tok = extract_bearer(req.headers)
                if tok:
                    found["token"] = tok
                    found["url"] = req.url
        except Exception:  # noqa: BLE001
            pass

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.on("request", _on_request)
            page.goto("https://earnkaro.com/login", wait_until="domcontentloaded")
            print("🌐 Browser open aindi — EarnKaro lo login cheyyandi (OTP),")
            print("   tarvata 'Make Link' page okkasari open cheyyandi.")
            print("   Token automatic ga pattukuntanu… (Ctrl+C tho aapochu)")
            waited = 0
            while not found.get("token") and waited < timeout_s:
                time.sleep(2)
                waited += 2
            browser.close()
    except KeyboardInterrupt:
        return {"ok": False, "error": "aapesaru (token ravaledu)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}

    tok = found.get("token") or ""
    if not tok:
        return {"ok": False,
                "error": "token dorakaledu — login ayyaka 'Make Link' page open "
                         "cheyyandi (network call eh token ni chupistundi)."}
    info = validate_token(tok)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "token shape thappu")}
    saved = None
    if save:
        from . import creds as _creds
        saved = _creds.save_env({"EARNKARO_API_TOKEN": tok})
        os.environ["EARNKARO_API_TOKEN"] = tok
    return {"ok": True, "token": tok, "note": info.get("note", ""), "saved": saved}


def cli(cfg, rest: list[str]) -> int:
    """`python -m bot earnkaro [status|convert|bulk|probe|howto|capture]`"""
    args = list(rest or [])
    sub = args[0].lower() if args and not args[0].startswith("-") else "status"
    tail = args[1:] if args and not args[0].startswith("-") else args
    force = any(f in ("--force", "-f") for f in tail)
    clean = [a for a in tail if not a.startswith("-")]
    api = EarnKaroAPI(cfg)

    if sub in ("status", "st"):
        print()
        print("\n".join(status_lines(cfg)))
        return 0

    if sub in ("howto", "token", "help", "refresh"):
        print()
        print("\n".join(howto_lines()))
        return 0

    if sub in ("capture", "login"):
        print()
        res = capture_with_browser(save=True)
        if res.get("ok"):
            print(f"✅ token pattukoni save chesanu — {res.get('note', '')}")
            print("   Ippudu check: python -m bot earnkaro probe")
        else:
            print(f"❌ {res.get('error')}")
            print()
            print("\n".join(howto_lines()))
            return 1
        return 0

    if sub in ("convert", "c", "one"):
        if not clean:
            print("\n   python -m bot earnkaro convert '<product url>' [--force]\n")
            return 1
        url = clean[0]
        res = api.convert(url, force=force)
        print()
        print(f"   input   : {url[:110]}")
        if res["ok"]:
            print(f"   ✅ link : {res['affiliate_url']}")
            print(f"   ℹ️  {res['reason']}"
                  + (f" · merchant {res['merchant']}" if res.get("merchant") else "")
                  + (f" · rate {res['rate']}" if res.get("rate") else ""))
            return 0
        print(f"   ❌ link ledu: {res['reason']}")
        print("   (untracked link post cheyyadam ledu — aa pin quarantine avutundi)")
        return 1

    if sub in ("bulk", "file", "warm"):
        if not clean:
            print("\n   python -m bot earnkaro bulk links.txt [--force]")
            print("   (file lo okka product URL per line)\n")
            return 1
        from pathlib import Path as _P
        path = _P(clean[0])
        if not path.exists():
            print(f"\n   ❌ file ledu: {path}\n")
            return 1
        urls = [ln.strip() for ln in path.read_text().splitlines()
                if ln.strip().startswith("http")]
        if not urls:
            print(f"\n   ❌ {path} lo product URLs levu\n")
            return 1
        res = api.convert_many(urls, force=force)
        ok = [r for r in res if r["ok"]]
        print()
        for r in res:
            mark = "✅" if r["ok"] else "❌"
            print(f"   {mark} {r['url'][:70]}")
            if r["ok"]:
                print(f"      → {r['affiliate_url']}")
            else:
                print(f"      {r['reason'][:110]}")
        print(f"\n   {len(ok)}/{len(res)} converted · cached: {api.cache_stats()['count']}")
        return 0 if ok else 1

    if sub in ("probe", "test", "live"):
        url = clean[0] if clean else ""
        print("\n   🔎 Live probe — token → API → link → redirect…\n")
        res = api.probe(url)
        info = res["identity"]
        print(f"   token      : {'✅ ' + (info.get('earnkaro') or 'set') if res['configured'] else '❌ not set'}")
        print(f"   endpoint   : {res['endpoint']}")
        print(f"   convert    : {'✅ ' + res['convert']['affiliate_url'] if res['convert']['ok'] else '❌ ' + str(res['convert'].get('reason'))[:120]}")
        if res["redirect"]["checked"]:
            print(f"   redirect   : status {res['redirect']['status']} → "
                  f"{res['redirect']['final'][:90] or '(none)'}")
        print()
        if res["convert"]["ok"]:
            print("   ✅ PROOF: ivvani live ga pani chestunnayi (nee account ki).")
            return 0
        print("   ⚠️  Live proof ravaledu. Sandbox/ee machine nunchi EarnKaro")
        print("      reach avvadam ledu — VPS/laptop lo malli run cheyyandi:")
        print("      python -m bot earnkaro probe")
        return 1

    print("\n   Usage: python -m bot earnkaro "
          "[status | convert <url> | bulk <file> | probe | capture | howto]\n")
    return 1
