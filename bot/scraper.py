"""Product scraper.

Strategy (most robust first):
1. JSON-LD `Product` schema  (Amazon/Meesho/Flipkart all embed it)
2. OpenGraph meta tags       (og:title, og:image, product:price)
3. Site-specific CSS selectors as fallback

Anti-bot etiquette: real browser headers, configurable delay & retries,
short timeouts. If a site hard-blocks (Amazon does this sometimes), add the
product via CSV/dashboard instead — the bot never crashes on it.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("pindrop.scraper")

# Professional UA rotation pool (real desktop browser strings). A single
# static UA gets fingerprinted & throttled fast by Amazon/Flipkart anti-bot.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

DOMAIN_SOURCES = {
    "amazon": ("amazon.in", "amazon.com", "amazon.co.uk", "amazon.ae", "amzn.in", "amzn.to"),
    "meesho": ("meesho.com", "affiliate.meesho.com"),
    "flipkart": ("flipkart.com", "fkrt.it"),
}


def normalize_image_url(url: str) -> str:
    """Ask the CDN for the FULL-SIZE version of the SAME photo.

    Thumbnails make pixelated pins, so: Amazon → ._SL1500_., Flipkart →
    image/832/832/, Meesho → drop the resize query string. Only well-known
    patterns are touched; callers keep the original URL as a fallback.
    """
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if "media-amazon.com" in u or "images-amazon.com" in u:
        u = re.sub(r"\._[^_.]+_\.", "._SL1500_.", u)
    if "flixcart.com" in u:
        u = re.sub(r"/image/\d+/\d+/", "/image/832/832/", u)
    if "images.meesho.com" in u:
        base, _, q = u.partition("?")
        if q and re.search(r"(width|height|resize|quality)=", q, re.I):
            u = base
        u = re.sub(r"_(\d{2,4})x(\d{2,4})(?=\.(?:jpe?g|png|webp))", "", u)
    return u


def photo_key(url: str) -> str:
    """Identity of a photo ignoring CDN size variants (dedupe key)."""
    u = (url or "").strip().lower().split("?")[0]
    if u.startswith("//"):
        u = "https:" + u
    u = re.sub(r"\._[^_.]+_\.", ".", u)
    u = re.sub(r"/image/\d+/\d+/", "/image/", u)
    u = re.sub(r"_(\d{2,4})x(\d{2,4})(?=\.(?:jpe?g|png|webp))", "", u)
    return re.sub(r"^https?://", "", u)


def human_int(text) -> int:
    """'1,36,104' / '13.6k' / '1.2L' -> int (Indian comma grouping handled)."""
    if isinstance(text, int):
        return text
    s = str(text or "").strip().lower().replace(",", "").replace(" ", "")
    m = re.match(r"(\d+(?:\.\d+)?)\s*([kmkl]?)", s)
    if not m:
        return 0
    val = float(m.group(1))
    mult = {"k": 1_000, "m": 1_000_000, "l": 100_000}.get(m.group(2), 1)
    return int(val * mult)


def detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for src, domains in DOMAIN_SOURCES.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return src
    return "other"


@dataclass
class Product:
    url: str
    title: str = ""
    price: str = ""
    mrp: str = ""                 # list price → % OFF badge (conversion trigger)
    currency: str = "INR"
    image_url: str = ""
    images: list = field(default_factory=list)   # full gallery (multiple pins!)
    video_url: str = ""
    rating: float = 0.0        # ★ average when the page exposes it
    reviews: int = 0           # rating/review count → trending signal
    category: str = ""
    description: str = ""
    source: str = field(default="other")

    @property
    def discount_pct(self) -> int:
        try:
            p = float(re.sub(r"[^\d.]", "", self.price.replace(",", "")) or 0)
            m = float(re.sub(r"[^\d.]", "", self.mrp.replace(",", "")) or 0)
            if m and p and m > p:
                return int(round((m - p) / m * 100))
        except ValueError:
            pass
        return 0

    @property
    def ok(self) -> bool:
        return bool(self.title and (self.image_url or self.images))


class Scraper:
    def __init__(self, cfg):
        self.cfg = cfg
        # consecutive failed fetches — lets autopilot/radar give up quickly
        # when the network (or a store) is unreachable instead of grinding
        self.net_failures = 0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": cfg.get("scraping.user_agent") or random.choice(USER_AGENTS),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self._last_html = ""

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _extract_json_array(html: str, key: str) -> str | None:
        """Bracket-balanced extraction of the JSON array after `key:` —
        immune to nested arrays that break naive regex."""
        for pat in (f"'{key}':", f"'{key}' :", f'"{key}":'):
            i = html.find(pat)
            while i != -1:
                j = html.find("[", i)
                if j != -1 and j - i < 80:
                    depth = 0
                    for k in range(j, min(len(html), j + 400_000)):
                        if html[k] == "[":
                            depth += 1
                        elif html[k] == "]":
                            depth -= 1
                            if depth == 0:
                                return html[j:k + 1]
                i = html.find(pat, i + 1)
        return None

    def _fetch(self, url: str, retries: int | None = None) -> str | None:
        """GET a page. `retries=None` → config default; pass 0 to
        fast-fail (used for speculative discovery so a dead store costs ~1s,
        not ~12s of backoff, while product pages keep full retries)."""
        if retries is None:
            retries = self.cfg.get_int("scraping.max_retries", 2)
        timeout = self.cfg.get_int("scraping.timeout_seconds", 25)
        for attempt in range(retries + 1):
            try:
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    self.net_failures = 0
                    return resp.text
                log.warning("HTTP %s for %s (attempt %d)", resp.status_code, url, attempt + 1)
            except requests.RequestException as exc:
                log.warning("Fetch error %s: %s", url, exc)
            time.sleep(2 * (attempt + 1) + random.random() * 2)
        self.net_failures += 1
        return None

    @property
    def net_down(self) -> bool:
        """True when the last few fetches all failed (store/network unreachable)."""
        return self.net_failures >= 2

    def polite_wait(self) -> None:
        delay = self.cfg.get_float("scraping.delay_seconds", 4.0)
        time.sleep(delay + random.random() * 2)

    # ------------------------------------------------------------ scrapers
    def scrape(self, url: str) -> Product:
        """Return a Product; check .ok before using."""
        prod = Product(url=url, source=detect_source(url))
        html = self._fetch(url)
        if not html:
            return prod
        self._last_html = html
        soup = BeautifulSoup(html, "lxml")

        self._from_jsonld(soup, prod)
        if not prod.title:
            self._from_opengraph(soup, prod)
        if not prod.title:
            self._site_specific(soup, prod)
        self._collect_images(soup, prod)
        self._collect_videos(soup, prod)
        self._collect_mrp(soup, prod)
        return prod

    # -- gallery images (multiple pins per product) -----------------------
    def _collect_images(self, soup: BeautifulSoup, prod: Product) -> None:
        imgs: list[str] = []

        seen_keys: set[str] = set()

        def push(u: str) -> None:
            """HI-RES first, original as fallback, exactly one entry per shot.

            Without the key check a gallery yields 4 thumbnails + 4 originals
            of the same dress → duplicate pins (spam signal) and pixelated
            designs. With it: one entry per photo, the big one.
            """
            u = (u or "").strip()
            if not u:
                return
            for cand in (normalize_image_url(u), u):
                if not cand.startswith("http") or ".svg" in cand:
                    continue
                key = photo_key(cand)
                if key in seen_keys or cand in imgs:
                    continue
                seen_keys.add(key)
                imgs.append(cand)

        # PRO SOURCE #1: Amazon 'colorImages' JS blob — the REAL hiRes gallery
        # (same data Amazon's own viewer uses; survives lazy-loading)
        blob = self._extract_json_array(self._last_html, "initial")
        if blob:
            try:
                items = json.loads(blob)
                # guard: must look like Amazon's gallery payload
                if items and isinstance(items[0], dict) and \
                        ("hiRes" in items[0] or "large" in items[0]):
                    for item in items:
                        hi = item.get("hiRes") or item.get("large") or ""
                        push(hi)
                        if not prod.video_url:
                            for v in (item.get("videos") or []):
                                if v.get("videoUrl"):
                                    prod.video_url = v["videoUrl"]
                                    break
            except (json.JSONDecodeError, TypeError):
                pass
        # PRO SOURCE #2: Meesho product JSON
        for mm in re.finditer(r'"images"\s*:\s*\[(.*?)\]', self._last_html):
            for u in re.findall(r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', mm.group(1)):
                push(u)

        if prod.image_url:
            push(prod.image_url)
        # JSON-LD image arrays were captured per node; capture all here too
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in self._iter_nodes(data):
                img = node.get("image")
                if isinstance(img, list):
                    for i in img:
                        push(i if isinstance(i, str) else i.get("url", ""))
                elif isinstance(img, str):
                    push(img)
        # all og:image entries
        for tag in soup.find_all("meta", attrs={"property": "og:image"}):
            push(tag.get("content", ""))
        # schema.org itemprop images
        for tag in soup.find_all("img", attrs={"itemprop": "image"}):
            push(tag.get("src") or tag.get("data-src", ""))
        # Amazon gallery thumbnails → full-size
        for tag in soup.select("#altImages img, .imageThumbnail img"):
            src = tag.get("src", "")
            if src:
                push(re.sub(r"\._[^_]+_\.", "._SL1500_.", src))
        # Flipkart gallery
        for tag in soup.select("._396cs4 img, ._20bN7y img"):
            push(tag.get("src") or tag.get("data-src", ""))
        # generic large product-zone images
        for tag in soup.find_all("img"):
            try:
                w = int(tag.get("width", 0) or 0)
            except ValueError:
                w = 0
            if w >= 400:
                push(tag.get("src") or tag.get("data-src", ""))

        prod.images = imgs[: self.cfg.get_int("scraping.max_images", 3)]
        if not prod.image_url and prod.images:
            prod.image_url = prod.images[0]

    # -- product videos -----------------------------------------------------
    def _collect_videos(self, soup: BeautifulSoup, prod: Product) -> None:
        if not prod.video_url:
            # Meesho embeds the reel URL in JSON — grab it directly
            m = re.search(r'"videoUrl"\s*:\s*"(https?://[^"]+)"', self._last_html)
            if m:
                prod.video_url = m.group(1).replace("\\u002F", "/")
        if not prod.video_url:
            for tag in soup.find_all("meta", attrs={"property": re.compile(r"^og:video")}):
                u = (tag.get("content") or "").strip()
                if u.startswith("http"):
                    prod.video_url = u
                    break
        if not prod.video_url:
            v = soup.find("video")
            if v:
                prod.video_url = (v.get("src") or "").strip()
                if not prod.video_url:
                    s = v.find("source")
                    if s:
                        prod.video_url = (s.get("src") or "").strip()

    # -- strategy 1: JSON-LD ---------------------------------------------
    def _from_jsonld(self, soup: BeautifulSoup, prod: Product) -> None:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in self._iter_nodes(data):
                if node.get("@type") == "Product" or (
                    isinstance(node.get("@type"), list) and "Product" in node["@type"]
                ):
                    prod.title = prod.title or str(node.get("name", "")).strip()
                    offers = node.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price") or offers.get("lowPrice") or ""
                    if price:
                        prod.price = str(price)
                        prod.currency = offers.get("priceCurrency", prod.currency)
                    high = offers.get("highPrice") or offers.get("maxPrice") or ""
                    if high:
                        prod.mrp = prod.mrp or str(high)
                    img = node.get("image")
                    if isinstance(img, list):
                        img = img[0] if img else ""
                    if isinstance(img, dict):
                        img = img.get("url", "")
                    if img:
                        prod.image_url = prod.image_url or str(img)
                    prod.description = prod.description or str(node.get("description", ""))[:400]
                    agg = node.get("aggregateRating") or {}
                    if isinstance(agg, list):
                        agg = agg[0] if agg else {}
                    if isinstance(agg, dict):
                        try:
                            if not prod.rating:
                                prod.rating = float(agg.get("ratingValue") or 0)
                        except (TypeError, ValueError):
                            pass
                        if not prod.reviews:
                            prod.reviews = human_int(
                                agg.get("reviewCount") or agg.get("ratingCount") or 0)
                    if not prod.video_url:
                        video = node.get("video")
                        if isinstance(video, dict):
                            prod.video_url = str(video.get("contentUrl", "")) or str(
                                video.get("embedUrl", "")
                            )

    @staticmethod
    def _iter_nodes(data):
        if isinstance(data, dict):
            yield data
            if "@graph" in data:
                yield from Scraper._iter_nodes(data["@graph"])
        elif isinstance(data, list):
            for item in data:
                yield from Scraper._iter_nodes(item)

    # -- strategy 2: OpenGraph -------------------------------------------
    def _from_opengraph(self, soup: BeautifulSoup, prod: Product) -> None:
        def meta(prop: str) -> str:
            tag = soup.find("meta", attrs={"property": prop}) or soup.find(
                "meta", attrs={"name": prop}
            )
            return (tag.get("content", "") or "").strip() if tag else ""

        prod.title = prod.title or meta("og:title")
        prod.image_url = prod.image_url or meta("og:image")
        prod.description = prod.description or meta("og:description")
        if not prod.price:
            for prop in ("product:price:amount", "og:price:amount"):
                val = meta(prop)
                if val:
                    prod.price = val
                    prod.currency = meta("product:price:currency") or prod.currency
                    break
        if not prod.video_url:
            prod.video_url = meta("og:video:url")

    # -- strategy 3: site-specific ----------------------------------------
    def _site_specific(self, soup: BeautifulSoup, prod: Product) -> None:
        if prod.source == "amazon":
            t = soup.select_one("#productTitle")
            if t:
                prod.title = t.get_text(strip=True)
            if not prod.price:
                p = soup.select_one(".a-price .a-offscreen")
                if p:
                    prod.price = p.get_text(strip=True)
            if not prod.image_url:
                img = soup.select_one("#landingImage") or soup.select_one("#imgBlkFront")
                if img:
                    prod.image_url = img.get("data-old-hires") or img.get("src", "")
        elif prod.source == "flipkart":
            t = soup.select_one("h1 span, ._35KyD6, .B_NuCI")
            if t:
                prod.title = t.get_text(strip=True)
            if not prod.price:
                p = soup.select_one("._30jeq3, ._1_WHN1, .Nx9bqj")
                if p:
                    prod.price = p.get_text(strip=True)
        elif prod.source == "meesho":
            t = soup.select_one("h1")
            if t:
                prod.title = t.get_text(strip=True)
        self._social_proof(soup, prod)

    def _social_proof(self, soup: BeautifulSoup, prod: Product) -> None:
        """Real ★ rating + rating-count = the trending signal.

        Meesho prints "136104 Ratings", Amazon uses #acrCustomerReviewText,
        Flipkart ._3LWZlK / ._2_R_DZ. We only ever read what the page
        shows — never invent social proof. 0 stays 0.
        """
        if prod.rating or prod.reviews:
            return
        if not prod.reviews:
            rc = soup.select_one("#acrCustomerReviewText, ._2_R_DZ")
            if rc:
                prod.reviews = human_int(re.sub(r"[^\d,]", "", rc.get_text()))
        if not prod.rating:
            pop = soup.select_one("#acrPopover, ._3LWZlK, .XQDdHH")
            if pop:
                m = re.search(r"([0-5](?:\.\d)?)\s*(?:out of|★|$)",
                              (pop.get("title") or "") + " " + pop.get_text(strip=True))
                if m:
                    try:
                        prod.rating = float(m.group(1))
                    except ValueError:
                        pass
        text = soup.get_text(" ", strip=True)
        if not prod.rating:
            m = re.search(r"([0-5]\.\d)\s*★?\s*[\d,]+\s*(?:Ratings|ratings)", text)
            if m:
                prod.rating = float(m.group(1))
        if not prod.reviews:
            m = re.search(r"([\d,]{2,})\s*(?:Ratings|ratings|Reviews|reviews)", text)
            if m:
                prod.reviews = human_int(m.group(1))

    # -- MRP / list price (for % OFF badges) -----------------------------
    def _collect_mrp(self, soup: BeautifulSoup, prod: Product) -> None:
        if not prod.mrp:
            tag = soup.select_one("#listPrice, .a-text-price .a-offscreen, ._3yOZfI")
            if tag:
                prod.mrp = tag.get_text(strip=True)
        if not prod.mrp:
            m = re.search(r"M\.?R\.?P\.?[:\s]*₹\s*([\d,]+)", soup.get_text(" ", strip=True))
            if m:
                prod.mrp = m.group(1)

    # ------------------------------------------------------------ download
    def discover_products(self, source: str = "amazon", limit: int = 6,
                          query: str = "") -> list[str]:
        """AUTOPILOT: hunt trending product URLs by themselves.

        With `query` → scrapes the store's SEARCH results for that winning
        niche (winner-clone mode). Without → bestseller/deal listing pages.
        Returns [] politely when the network blocks us.
        """
        from urllib.parse import quote_plus
        if query and query.startswith("http"):
            # trending/collection SEED URLs (bot/trends.MEESHO_TRENDING)
            urls = {source or "meesho": query}
        elif query:
            urls = {
                "amazon": f"https://www.amazon.in/s?k={quote_plus(query)}",
                "flipkart": f"https://www.flipkart.com/search?q={quote_plus(query)}",
                "meesho": f"https://www.meesho.com/search?q={quote_plus(query)}",
            }
        else:
            urls = {
                "amazon": "https://www.amazon.in/gp/bestsellers/electronics",
                "flipkart": "https://www.flipkart.com/mobiles/pr?sid=tyy,4io",
                "meesho": "https://www.meesho.com/women-ethnic-wear/pl/1k1b6",
            }
        patterns = {
            "amazon": re.compile(r"/dp/([A-Z0-9]{10})"),
            "flipkart": re.compile(r"\?pid=([A-Z0-9]+)"),
            "meesho": re.compile(r"/p/([a-z0-9]+)"),
        }
        page = urls.get(source)
        if not page:
            return []
        html = self._fetch(page, retries=0)
        if not html:
            return []
        found: list[str] = []
        for m in patterns[source].finditer(html):
            if source == "amazon":
                u = f"https://www.amazon.in/dp/{m.group(1)}"
            elif source == "flipkart":
                u = f"https://www.flipkart.com/item/p?pid={m.group(1)}"
            else:
                u = f"https://www.meesho.com/product/p/{m.group(1)}"
            if u not in found:
                found.append(u)
            if len(found) >= limit:
                break
        if found:
            log.info("Discovered %d %s products", len(found), source)
        return found

    def download_image_url(self, url: str, dest_dir, name_hint: str = "",
                           min_side: int = 300) -> str:
        """Download a PRODUCT PHOTO — and prove it really is one.

        A blocked/404 CDN answers with an HTML error page (or a 1×1 pixel);
        saving that as a product photo puts a broken image on a pin. So the
        bytes must decode with PIL, be big enough, and be unique (sha1) —
        otherwise we return '' and the caller tries the next photo.
        """
        if not url:
            return ""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.warning("Image download failed for %s: %s", url, exc)
            return ""
        ctype = (resp.headers.get("content-type") or "").lower()
        data = resp.content or b""
        if ctype and not ctype.startswith("image/"):
            log.warning("Image download rejected (content-type %s): %s", ctype, url)
            return ""
        try:
            from PIL import Image          # lazy: the scraper must import w/o PIL
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                w, h = im.size
                fmt = (im.format or "JPEG").upper()
        except Exception as exc:  # noqa: BLE001 — not an image / half-downloaded
            log.warning("Image download rejected (undecodable, %d bytes): %s",
                        len(data), url)
            return ""
        if min(w, h) < min_side:
            log.warning("Image download rejected (too small %dx%d): %s", w, h, url)
            return ""
        digest = hashlib.sha1(data).hexdigest()[:12]
        ext = {"PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}.get(fmt, ".jpg")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name_hint)[:50].strip("_") or "img"
        path = dest_dir / f"{safe}_{digest}{ext}"
        if not path.exists():                     # same photo twice → same file
            path.write_bytes(data)
        log.debug("Image ok %dx%d %s", w, h, path.name)
        return str(path)

    # -- cross-store enrichment: same product, watermark-free media -------
    SEARCH_URLS = {
        "amazon": ("https://www.amazon.in/s?k={q}", r'href="(/[^"]*?/dp/[A-Z0-9]{10}[^"]*)"'),
        "flipkart": ("https://www.flipkart.com/search?q={q}", r'href="(/[^"]*?/p/[^"?]+)'),
        "meesho": ("https://www.meesho.com/search?q={q}",
                   r'href="(/[^"?]*?/p/[a-z0-9]+)'),
    }
    HOSTS = {"amazon": "https://www.amazon.in",
             "flipkart": "https://www.flipkart.com",
             "meesho": "https://www.meesho.com"}

    def enrich_media(self, prod: "Product") -> "Product":
        """You never make media: if the gallery is thin or videoless, hunt
        the SAME product on the other stores and merge their official,
        watermark-free gallery (store policy = clean images) + brand video.
        Polite: one enrichment pass, waits between requests.
        """
        if len(prod.images) >= 3 and prod.video_url:
            return prod
        q = " ".join(re.sub(r"[^A-Za-z0-9 ]+", " ", prod.title).split()[:6])
        if not q:
            return prod
        for store, (tpl, link_re) in self.SEARCH_URLS.items():
            if store == prod.source:
                continue
            self.polite_wait()
            html = self._fetch(tpl.format(q=quote(q)))
            if not html:
                continue
            m = re.search(link_re, html)
            if not m:
                continue
            other = self.scrape(self.HOSTS[store] + m.group(1))
            if not other.ok:
                continue
            added = 0
            for u in other.images:
                if u not in prod.images:
                    prod.images.append(u)
                    added += 1
            if not prod.video_url and other.video_url:
                prod.video_url = other.video_url
            if added or other.video_url:
                log.info("🔍 Cross-store enriched from %s: +%d images%s",
                         store, added, " +video" if other.video_url else "")
                break
        prod.images = prod.images[: self.cfg.get_int("scraping.max_images", 3) + 2]
        return prod

    def download_video(self, url: str, dest_dir, max_mb: int = 120) -> str:
        """Stream-download a product video locally; returns saved path or ''."""
        if not url:
            return ""
        try:
            with self.session.get(url, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if "video" not in ctype and "octet-stream" not in ctype:
                    log.warning("Not a video content-type: %s", ctype)
                    return ""
                ext = ".mp4"
                if "quicktime" in ctype:
                    ext = ".mov"
                elif "webm" in ctype:
                    ext = ".webm"
                path = dest_dir / f"video_{int(time.time()*1000)}{ext}"
                total = 0
                with open(path, "wb") as fh:
                    for chunk in resp.iter_content(1 << 20):
                        total += len(chunk)
                        if total > max_mb * 1024 * 1024:
                            log.warning("Video too large (> %dMB), aborted", max_mb)
                            fh.close()
                            path.unlink(missing_ok=True)
                            return ""
                        fh.write(chunk)
            return str(path)
        except requests.RequestException as exc:
            log.warning("Video download failed for %s: %s", url, exc)
            return ""
