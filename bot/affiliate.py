"""Affiliate link engine.

Converts any product URL into YOUR monetized link:

  amazon.*   -> adds/replaces your Amazon Associates ?tag=
  meesho     -> appends your Meesho affid / campaign params
  flipkart   -> Flipkart affiliate param, or wrapped via EarnKaro/Cuelinks
  other      -> wrapped via EarnKaro (API token = real profit link) >
                Cuelinks > generic template

Priority: amazon > meesho > flipkart > configured default_wrapper.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from .scraper import detect_source

# R69: Meesho serves the mobile page (with the SSR product title we grep in
# the live landing check); desktop UA gets a thinner shell.
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 13; SM-A536E) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")

log = logging.getLogger("pindrop.affiliate")

ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/)([A-Z0-9]{10})")
FLIPKART_PID_RE = re.compile(r"pid=([A-Z0-9]+)")


class AffiliateLinker:
    def __init__(self, cfg, converter=None):
        self.cfg = cfg
        # `converter(url) -> monetized_url | None` — the EarnKaro API call.
        # Injected only at publishing call sites (see from_cfg) so that tests
        # and read-only checks never touch the network.
        self._converter = converter

    @classmethod
    def from_cfg(cls, cfg):
        """Linker with the live EarnKaro converter attached (when usable)."""
        try:
            from .earnkaro import build_converter
            return cls(cfg, converter=build_converter(cfg))
        except Exception:  # noqa: BLE001 — never let money-wiring break a run
            return cls(cfg)

    # ------------------------------------------------------------- config
    @property
    def amazon_tag(self) -> str:
        return (self.cfg.amazon_tag or "").strip()

    @property
    def meesho_affid(self) -> str:
        return (os.getenv("MEESHO_AFFID", "") or
                self.cfg.get("affiliate.meesho_affid", "") or "").strip()

    @property
    def flipkart_affid(self) -> str:
        return (os.getenv("FLIPKART_AFFID", "") or
                self.cfg.get("affiliate.flipkart_affid", "") or "").strip()

    @property
    def earnkaro_prefix(self) -> str:
        return (os.getenv("EARNKARO_PREFIX", "") or
                self.cfg.get("affiliate.earnkaro_prefix", "") or "").strip()

    @property
    def earnkaro_api_token(self) -> str:
        return (os.getenv("EARNKARO_API_TOKEN", "") or
                os.getenv("EARNKARO_TOKEN", "") or
                self.cfg.get("affiliate.earnkaro_api_token", "") or "").strip()

    @property
    def cuelinks_template(self) -> str:
        return (os.getenv("CUELINKS_TEMPLATE", "") or
                self.cfg.get("affiliate.cuelinks_template", "") or "").strip()

    @property
    def generic_template(self) -> str:
        return (self.cfg.get("affiliate.generic_template", "") or "").strip()

    # ------------------------------------------------------------ wrappers
    def amazonize(self, url: str) -> str:
        """Clean amazon URL to canonical /dp/ASIN and attach your tag."""
        if not self.amazon_tag:
            return url
        parsed = urlparse(url)
        m = ASIN_RE.search(parsed.path)
        if m:
            clean = f"https://{parsed.netloc}/dp/{m.group(1)}"
            return f"{clean}?tag={self.amazon_tag}"
        # no ASIN found (search/landing page) -> keep path, swap tag
        params = [(k, v) for k, v in parse_qsl(parsed.query) if k != "tag"]
        params.append(("tag", self.amazon_tag))
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(params), "")
        )

    # Links Meesho's affiliate site generates for YOU (af_invite / collection
    # / links already carrying p_id+ext_id tracking). They're ALREADY
    # monetized — rewriting them would break Meesho's own tracking.
    MEESHO_MONETIZED = re.compile(
        r"af_invite|affiliate\.meesho\.com|affid=|ext_id=|/collection/")

    @property
    def meesho_template_links(self) -> list[str]:
        """Every share link the owner has pasted (comma/newline separated).

        R68: links arrive HTML-escaped (`&amp;`) when copied from a browser,
        WhatsApp or a screenshot. `&amp;` contains a `;`, so splitting on `;`
        used to shred ONE link into three broken pieces. Normalise the entity
        first, and never split on `;`.
        """
        raw = (os.getenv("MEESHO_TEMPLATE_LINK", "") or
               self.cfg.get("affiliate.meesho_template_link", "") or "").strip()
        raw = (raw.replace("&amp;", "&").replace("&#38;", "&")
                  .replace("\u0026", "&").replace("&quot;", ""))
        return [p.strip() for p in re.split(r"[,\n\r]+", raw) if p.strip()]

    @property
    def meesho_ids(self) -> tuple[str, str, list[str]]:
        """Your Meesho publisher + source-token + ALL campaign IDs.

        Meesho rotates campaign IDs per product/campaign — so paste links
        over time (comma/newline separated in MEESHO_TEMPLATE_LINK); the bot
        learns every campaign and builds new links with the LATEST one.
        """
        pub = src = ""
        camps: list[str] = []
        for lnk in self.meesho_template_links:
            m = re.search(r"af_invite/([^:/?]+):([^:/?]+):([^:/?&]+)", lnk)
            if not m:
                continue
            pub, src = m.group(1), m.group(2)
            if m.group(3) not in camps:
                camps.append(m.group(3))
        return pub, src, camps

    @staticmethod
    def meesho_product_id(url: str) -> str:
        """Real Meesho product IDs are ALPHANUMERIC short codes.

        Handles every shape Meesho actually serves:
          /women-kurta-set/p/1k1b6        ← standard
          /women-kurta-set-p-1k1b6        ← search-result style (-p-<id>)
          /product/p/1k1b6
          ?p_id=1k1b6                     ← already-tagged links
        """
        parsed = urlparse(url)
        # matches: /p/<id>, -p/<id>, -p-<id>  (all shapes Meesho serves)
        m = re.search(r"[-/]p[-/]([A-Za-z0-9_-]{3,})", parsed.path)
        if not m:
            for k, v in parse_qsl(parsed.query):
                if k in ("p_id", "product_id", "pid") and v:
                    return v.strip()
            return ""
        return m.group(1).strip().strip("-")

    def meesho_health(self) -> dict:
        """Diagnostics for `bot doctor` / `bot meesho` — honest status."""
        links = self.meesho_template_links
        pub, src, camps = self.meesho_ids
        return {
            "links_pasted": len(links),
            "parsed": bool(pub and camps),
            "publisher": pub,
            "source_token": src,
            "campaigns": camps,
            "affid_fallback": bool(self.meesho_affid),
            "ready": bool((pub and camps) or self.meesho_affid),
        }

    # platform → the source tokens Meesho generates for that platform.
    # (Meesho's "Get commission link" screen lets you pick Instagram Story,
    #  Facebook Post, etc — each comes with its OWN token + campaign id.)
    PLATFORM_TOKENS = {
        # "Get commission link" lo Meesho isthe token per surface. Feed posts
        # (the bot's main IG surface) use the PRODUCT-TAG token, stories keep
        # their own token, YouTube uses the long-form token.
        "pinterest": ("pinterest", "pinterest_stories", "pinterest_ideas"),
        "instagram": ("instagram_product_tag", "instagram_product",
                      "instagram_feed", "instagram", "instagram_reels",
                      "instagram_stories", "instagram_story"),
        "instagram_stories": ("instagram_stories", "instagram_story"),
        "instagram_product_tag": ("instagram_product_tag", "instagram_product"),
        "facebook": ("facebook", "facebook_post", "facebook_stories"),
        "youtube": ("youtube_long_form", "youtube_shorts", "youtube_videos",
                    "youtube"),
    }

    def meesho_template_map(self) -> dict[str, str]:
        """{source_token: latest campaign id} from every pasted link."""
        out: dict[str, str] = {}
        for lnk in self.meesho_template_links:
            m = re.search(r"af_invite/[^:/?]+:([^:/?]+):([^:/?&]+)", lnk)
            if m:
                out[m.group(1)] = m.group(2)   # later paste wins = newest
        return out

    def meesho_source_for(self, platform: str = "") -> str:
        """Pick the right source token for the platform being posted to.

        Attribution matters: a Pinterest pin tagged 'facebook' muddies the
        Meesho report. Falls back to the newest token when that platform has
        no link yet (commission still lands — publisher id is unchanged).
        """
        m = self.meesho_template_map()
        if not m:
            return ""
        # 1) explicit override: affiliate.meesho_platform_tokens:
        #      {pinterest: instagram_stories}   (Meesho has no Pinterest token)
        override = (self.cfg.get("affiliate.meesho_platform_tokens") or {})
        if isinstance(override, dict):
            forced = str(override.get(platform.lower(), "") or "").strip()
            if forced and forced in m:
                return forced
        # 2) exact platform token
        for tok in self.PLATFORM_TOKENS.get(platform.lower(), ()):
            if tok in m:
                return tok
        # 3) partial match (e.g. 'instagram_stories_2')
        for tok in m:
            if any(k in tok for k in self.PLATFORM_TOKENS.get(
                    platform.lower(), ())):
                return tok
        # 4) newest token the owner pasted (commission is unaffected —
        #    publisher id is the same; only the report label differs)
        newest = ""
        for lnk in reversed(self.meesho_template_links):
            mm = re.search(r"af_invite/[^:/?]+:([^:/?]+):", lnk)
            if mm:
                newest = mm.group(1)
                break
        return newest or list(m)[-1]

    def meesho_link_for(self, url: str, platform: str = "") -> str:
        """Build the exact link the bot would publish for this product URL.

        Faithful by design: the af_invite base + every parameter from YOUR
        matching share link are copied verbatim; only p_id and ext_id change —
        and BOTH are set to this product's own code. Nothing is invented.

        R69 (live-verified): Meesho resolves the landing page by looking the
        code up on /s/p/<code>, and it reads that code from `ext_id`. A
        RANDOM ext_id therefore 404s ("Not Found page") or, by collision,
        drops the visitor on a completely different product's page. The
        product's own code (what your "Get Commission Link" link carries as
        ext_id) is the only correct value.
        """
        pid = self.meesho_product_id(url)
        pub, src, camps = self.meesho_ids
        token = self.meesho_source_for(platform) or src
        template = ""
        for lnk in reversed(self.meesho_template_links):
            if token and f":{token}:" in lnk:
                template = lnk
                break
        if not template:
            template = self.meesho_template_links[-1] if self.meesho_template_links else ""
        if not pid:
            # R68: NO product id = the click lands on a generic Meesho page.
            # An af_invite with no p_id is monetized-but-worthless, and the
            # leak gate cannot see the difference — so never build one.
            log.warning("MEESHO LINK: no product id (p_id) in '%s' — af_invite "
                        "link ni build cheyyaledu (generic page ki vellipoyedi).",
                        url[:90])
            return ""
        m = re.search(r"(https?://[^?\s]*af_invite/[^?\s]+)", template)
        if m:
            base = m.group(1)
            tparams = [(k, v) for k, v in
                       parse_qsl(urlparse(template).query)
                       if k not in ("p_id", "ext_id")]
            tparams.append(("p_id", pid))
            # R69: ext_id decides the LANDING PAGE (Meesho -> /s/p/<code>).
            # It must be the product's own code, never a random click id.
            tparams.append(("ext_id", pid))
            # source token stays visible as utm_source (Meesho's report reads
            # the af_invite path token; this keeps the two consistent)
            has_utm = any(k == "utm_source" for k, _ in tparams)
            if has_utm:
                tparams = [(k, token if k == "utm_source" and token else v)
                           for k, v in tparams]
            elif token:
                tparams.append(("utm_source", token))
            return f"{base}?{urlencode(tparams)}"
        if pub and camps and pid:
            tok = token or src
            return (f"https://www.meesho.com/af_invite/{pub}:{tok}:{camps[-1]}"
                    f"?p_id={pid}&ext_id={pid}&utm_source={tok}")
        return ""

    def meesho_landing_ok(self, link: str, timeout: int = 8):
        """LIVE check: does this built Meesho link really open the product?

        Returns True (lands on a product page), False (definitive failure —
        Meesho's "Not Found page", or /s/p with no code) or None (couldn't
        tell: network/robot-blocking — never quarantine on a None).

        This is the check that R69 taught us we needed: a link can look
        perfectly monetized and still 404 on the Meesho side.
        """
        if "af_invite/" not in link:
            return None
        try:
            import requests
            r = requests.get(
                link, timeout=timeout, allow_redirects=True,
                headers={"User-Agent": MOBILE_UA,
                         "Accept-Language": "en-IN,en;q=0.9"})
        except Exception as e:                                   # noqa: BLE001
            log.warning("MEESHO LANDING: check cheyyalekapoyam (%s) — link ni "
                        "nammakam tho vadilestunnam.", str(e)[:90])
            return None
        final = r.url or ""
        if re.search(r"/s/p(\?|$)", final):
            return False                       # no code in the share route
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text or "", re.S | re.I)
        title = (m.group(1) if m else "").strip().lower()
        if "not found" in title:
            return False
        if r.status_code >= 400:
            return None                        # blocked/ratelimited ≠ broken
        return True

    def meeshoize(self, url: str, platform: str = "") -> str:
        if self.MEESHO_MONETIZED.search(url):
            return url  # your generated link, passed through untouched
        # DIRECT Meesho affiliate: build af_invite with YOUR publisher +
        # campaign IDs and the product's p_id — commission lands in YOUR
        # Meesho account, no middleman. Verbatim template params preserved.
        built = self.meesho_link_for(url, platform=platform)
        if built:
            return built
        if self.meesho_template_links:
            is_collection = any("affiliate.meesho.com/collection/" in l
                                for l in self.meesho_template_links)
            log.warning(
                "MEESHO LINK WARNING: could not parse your af_invite link "
                "(no publisher/campaign IDs found)%s — open any Meesho product "
                "→ Share → copy link (af_invite format) → paste in .env. "
                "Falling back to affid parameter for now.",
                " [you pasted a COLLECTION link — it cannot build per-product "
                "links]" if is_collection else "")
        elif not self.meesho_affid:
            log.warning("MEESHO LINK WARNING: no MEESHO_TEMPLATE_LINK and no "
                        "MEESHO_AFFID set — Meesho links are NOT monetized yet. "
                        "Paste your af_invite link in .env (see `bot meesho`).")
        # fallbacks: raw reseller affid param, then aggregator
        if self.meesho_affid:
            parsed = urlparse(url)
            params = [
                (k, v)
                for k, v in parse_qsl(parsed.query)
                if k not in ("affid", "utm_source", "source")
            ]
            params += [("utm_source", "affiliate"), ("affid", self.meesho_affid)]
            return urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(params), "")
            )
        wrapped = self._wrap(url)
        return wrapped if wrapped != url else url

    def flipkartize(self, url: str) -> str:
        """Use Flipkart affiliate id if present, else fall through to wrapper."""
        if self.flipkart_affid:
            parsed = urlparse(url)
            params = [(k, v) for k, v in parse_qsl(parsed.query) if k != "affid"]
            params.append(("affid", self.flipkart_affid))
            return urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, "", urlencode(params), "")
            )
        return self._wrap(url, skip_source="flipkart")

    def _wrap_earnkaro(self, url: str) -> str:
        """Monetize via the EarnKaro API, else the (legacy) static prefix.

        The API hands back a REAL per-product profit link for the owner's own
        account; the prefix convention can only ever guess. Order: API → prefix.
        """
        if self._converter is not None:
            try:
                got = self._converter(url)
            except Exception as e:  # noqa: BLE001 — network hiccup != crash
                log.warning("earnkaro conversion failed: %s", e)
                got = None
            if got:
                return got
        if not self.earnkaro_prefix:
            return ""
        sep = "&" if "?" in self.earnkaro_prefix else "?"
        return f"{self.earnkaro_prefix}{sep}url={quote(url, safe='')}"

    def _wrap_cuelinks(self, url: str) -> str:
        if not self.cuelinks_template or "{url}" not in self.cuelinks_template:
            return ""
        return self.cuelinks_template.replace("{url}", quote(url, safe=""))

    def _wrap_generic(self, url: str) -> str:
        if not self.generic_template or "{url}" not in self.generic_template:
            return ""
        return self.generic_template.replace("{url}", quote(url, safe=""))

    def _wrap(self, url: str, skip_source: str = "") -> str:
        """Wrap via the first wrapper that is configured."""
        order = [self.cfg.get("affiliate.default_wrapper", "earnkaro")]
        for name in ("earnkaro", "cuelinks", "generic"):
            if name not in order:
                order.append(name)
        for name in order:
            if name == "earnkaro":
                wrapped = self._wrap_earnkaro(url)
            elif name == "cuelinks":
                wrapped = self._wrap_cuelinks(url)
            else:
                wrapped = self._wrap_generic(url)
            if wrapped:
                return wrapped
        return url  # nothing configured -> original link (better than nothing)

    def is_monetized(self, url: str, source: str = "") -> bool:
        """Commission-leak guard: does this link actually carry tracking?
        A pin with an untracked link = clicks that pay nobody."""
        markers = ("tag=", "affid=", "af_invite", "ekaro.in", "cuelinks",
                   "earnkaro", "url=")
        return any(mk in url for mk in markers)

    # --------------------------------------------------------------- main
    @staticmethod
    def _add_utm(url: str, source: str) -> str:
        """Track which platform drives sales (Pinterest vs IG) in analytics."""
        if url.startswith("http") and "utm_source" not in url:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}utm_source=pinterest&utm_medium=social&utm_campaign=pindrop_{source}"
        return url

    def convert(self, url: str, source: str | None = None,
                utm: bool = True, platform: str = "") -> tuple[str, str]:
        """Returns (affiliate_url, network_name).

        `platform` (pinterest/instagram/facebook/youtube) picks the matching
        Meesho source token + campaign so your Meesho report stays clean.
        """
        src = source or detect_source(url)
        if src == "amazon":
            out = self.amazonize(url)
        elif src == "meesho":
            if self.MEESHO_MONETIZED.search(url):
                return url, "meesho"  # user-generated link: zero rewriting
            out = self.meeshoize(url, platform=platform)
        elif src == "flipkart":
            out = self.flipkartize(url)
        else:
            out, src2 = self._wrap(url), "wrapped"
            return (self._add_utm(out, src) if utm else out), src2
        return (self._add_utm(out, src) if utm else out), src


def price_label(price: str, currency: str = "INR") -> str:
    """Normalize a scraped price for display."""
    if not price:
        return ""
    cleaned = re.sub(r"[^\d.]", "", price.replace(",", ""))
    if not cleaned:
        return price.strip()
    try:
        val = float(cleaned)
    except ValueError:
        return price.strip()
    symbol = "₹" if currency.upper() == "INR" else f"{currency} "
    return f"{symbol}{val:,.0f}" if val == int(val) else f"{symbol}{val:,.2f}"
