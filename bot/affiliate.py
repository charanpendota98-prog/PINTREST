"""Affiliate link engine.

Converts any product URL into YOUR monetized link:

  amazon.*   -> adds/replaces your Amazon Associates ?tag=
  meesho     -> appends your Meesho affid / campaign params
  flipkart   -> Flipkart affiliate param, or wrapped via EarnKaro/Cuelinks
  other      -> wrapped via EarnKaro > Cuelinks > generic template

Priority: amazon > meesho > flipkart > configured default_wrapper.
"""
from __future__ import annotations

import logging
import os
import random
import re
import string
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from .scraper import detect_source

log = logging.getLogger("pindrop.affiliate")

ASIN_RE = re.compile(r"(?:/dp/|/gp/product/|/gp/aw/d/|/product/)([A-Z0-9]{10})")
FLIPKART_PID_RE = re.compile(r"pid=([A-Z0-9]+)")


class AffiliateLinker:
    def __init__(self, cfg):
        self.cfg = cfg

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
        """Every share link the owner has pasted (comma/newline separated)."""
        raw = (os.getenv("MEESHO_TEMPLATE_LINK", "") or
               self.cfg.get("affiliate.meesho_template_link", "") or "").strip()
        return [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]

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

    def meesho_link_for(self, url: str) -> str:
        """Build the exact link the bot would publish for this product URL.

        Faithful by design: the af_invite base + every parameter from YOUR
        latest share link are copied verbatim; only p_id (this product) and
        ext_id (fresh click id) change. Nothing is invented.
        """
        pid = self.meesho_product_id(url)
        pub, src, camps = self.meesho_ids
        template = self.meesho_template_links[-1] if self.meesho_template_links else ""
        m = re.search(r"(https?://[^?\s]*af_invite/[^?\s]+)", template)
        if m:
            base = m.group(1)
            tparams = [(k, v) for k, v in
                       parse_qsl(urlparse(template).query)
                       if k not in ("p_id", "ext_id")]
            if pid:
                tparams.append(("p_id", pid))
            tparams.append(("ext_id", "".join(
                random.choices(string.ascii_lowercase + string.digits, k=6))))
            # your source token stays visible as utm_source (Meesho report
            # reads the af_invite path token; this keeps it consistent)
            if src and not any(k == "utm_source" for k, _ in tparams):
                tparams.append(("utm_source", src))
            return f"{base}?{urlencode(tparams)}"
        if pub and camps and pid:
            ext = "".join(random.choices(string.ascii_lowercase + string.digits,
                                         k=6))
            return (f"https://www.meesho.com/af_invite/{pub}:{src}:{camps[-1]}"
                    f"?p_id={pid}&ext_id={ext}&utm_source={src}")
        return ""

    def meeshoize(self, url: str) -> str:
        if self.MEESHO_MONETIZED.search(url):
            return url  # your generated link, passed through untouched
        # DIRECT Meesho affiliate: build af_invite with YOUR publisher +
        # campaign IDs and the product's p_id — commission lands in YOUR
        # Meesho account, no middleman. Verbatim template params preserved.
        built = self.meesho_link_for(url)
        if built:
            return built
        if self.meesho_template_links:
            log.warning(
                "MEESHO LINK WARNING: could not parse your af_invite link "
                "(no publisher/campaign IDs found) — paste a fresh share link "
                "from affiliate.meesho.com. Falling back to affid parameter.")
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
                utm: bool = True) -> tuple[str, str]:
        """Returns (affiliate_url, network_name)."""
        src = source or detect_source(url)
        if src == "amazon":
            out = self.amazonize(url)
        elif src == "meesho":
            if self.MEESHO_MONETIZED.search(url):
                return url, "meesho"  # user-generated link: zero rewriting
            out = self.meeshoize(url)
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
