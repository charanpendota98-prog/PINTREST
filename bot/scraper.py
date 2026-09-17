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

import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("pindrop.scraper")

DOMAIN_SOURCES = {
    "amazon": ("amazon.in", "amazon.com", "amazon.co.uk", "amazon.ae", "amzn.in", "amzn.to"),
    "meesho": ("meesho.com",),
    "flipkart": ("flipkart.com", "fkrt.it"),
}


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
    currency: str = "INR"
    image_url: str = ""
    video_url: str = ""
    category: str = ""
    description: str = ""
    source: str = field(default="other")

    @property
    def ok(self) -> bool:
        return bool(self.title and self.image_url)


class Scraper:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": cfg.get("scraping.user_agent"),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    # ------------------------------------------------------------- helpers
    def _fetch(self, url: str) -> str | None:
        retries = int(self.cfg.get("scraping.max_retries", 2))
        timeout = int(self.cfg.get("scraping.timeout_seconds", 25))
        for attempt in range(retries + 1):
            try:
                resp = self.session.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp.text
                log.warning("HTTP %s for %s (attempt %d)", resp.status_code, url, attempt + 1)
            except requests.RequestException as exc:
                log.warning("Fetch error %s: %s", url, exc)
            time.sleep(2 * (attempt + 1) + random.random() * 2)
        return None

    def polite_wait(self) -> None:
        delay = float(self.cfg.get("scraping.delay_seconds", 4.0))
        time.sleep(delay + random.random() * 2)

    # ------------------------------------------------------------ scrapers
    def scrape(self, url: str) -> Product:
        """Return a Product; check .ok before using."""
        prod = Product(url=url, source=detect_source(url))
        html = self._fetch(url)
        if not html:
            return prod
        soup = BeautifulSoup(html, "lxml")

        self._from_jsonld(soup, prod)
        if not prod.title:
            self._from_opengraph(soup, prod)
        if not prod.title:
            self._site_specific(soup, prod)
        return prod

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
                    img = node.get("image")
                    if isinstance(img, list):
                        img = img[0] if img else ""
                    if isinstance(img, dict):
                        img = img.get("url", "")
                    if img:
                        prod.image_url = prod.image_url or str(img)
                    prod.description = prod.description or str(node.get("description", ""))[:400]
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

    # ------------------------------------------------------------ download
    def download_image(self, prod: Product, dest_dir) -> str:
        """Download product image locally; returns saved path or ''."""
        if not prod.image_url:
            return ""
        try:
            resp = self.session.get(prod.image_url, timeout=30)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            ext = ".jpg" if "png" not in ctype else ".png"
            if "webp" in ctype:
                ext = ".webp"
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", prod.title)[:60].strip("_") or "img"
            path = dest_dir / f"{safe}_{int(time.time())}{ext}"
            path.write_bytes(resp.content)
            return str(path)
        except requests.RequestException as exc:
            log.warning("Image download failed for %s: %s", prod.image_url, exc)
            return ""
