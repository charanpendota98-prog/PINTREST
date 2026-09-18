"""Flask control-panel dashboard.

Run:  python -m bot dashboard
Then open the printed URL (works over the sandbox live-preview proxy too —
all URLs are relative).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from .db import DB
from .engine import Engine
from .notify import Notifier
from .pinterest_api import PinterestAPI, PinterestError

log = logging.getLogger("pindrop.dashboard")
ROOT = Path(__file__).resolve().parent.parent

# High-converting mini landing page (warm-up between pin and affiliate link)
LANDING_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — {{ brand }}</title>
<style>
 body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#faf7f2;color:#222}
 .wrap{max-width:520px;margin:0 auto;background:#fff;min-height:100vh;box-shadow:0 0 40px rgba(0,0,0,.08)}
 .top{background:#E60023;color:#fff;text-align:center;padding:10px;font-weight:700;letter-spacing:1px}
 img.hero{width:100%;display:block}
 .body{padding:22px}
 h1{font-size:20px;line-height:1.35;margin:0 0 12px}
 .price{font-size:34px;font-weight:800;color:#E60023}
 .off{display:inline-block;background:#ffc400;color:#111;font-weight:800;border-radius:8px;
     padding:4px 12px;margin-left:10px;font-size:18px;vertical-align:middle}
 ul{padding-left:20px;line-height:1.9;color:#444}
 a.buy{display:block;text-align:center;background:#E60023;color:#fff;font-size:20px;font-weight:800;
     padding:18px;border-radius:14px;text-decoration:none;margin:18px 0;
     box-shadow:0 6px 18px rgba(230,0,35,.35)}
 a.buy:active{transform:scale(.98)}
 a.wa{display:block;text-align:center;background:#25D366;color:#fff;font-size:16px;
     font-weight:800;padding:13px;border-radius:14px;text-decoration:none;margin:0 0 16px}
 .disc{color:#999;font-size:11.5px;text-align:center;padding:10px}
 .urg{background:#fff3cd;border:1px solid #ffe08a;color:#7a5c00;border-radius:10px;
     padding:10px;text-align:center;font-weight:600;font-size:14px}
</style></head><body><div class="wrap">
<div class="top">🔥 {{ brand }} — VERIFIED DEAL</div>
<img class="hero" src="{{ img }}" alt="{{ title }}">
<div class="body">
  <h1>{{ title }}</h1>
  <div><span class="price">{{ price }}</span>
  {% if disc >= 15 %}<span class="off">{{ disc }}% OFF</span>{% endif %}</div>
  <div class="urg" style="margin-top:12px">⏳ Limited stock at this price — selling fast!</div>
  <ul>
    <li>✅ Best price verified by {{ brand }}</li>
    <li>🚚 Fast delivery & easy returns</li>
    <li>💯 Secure checkout on the official store</li>
  </ul>
  <a class="buy" rel="nofollow sponsored" href="{{ buy }}">🛒 GRAB THE DEAL →</a>
  <a class="wa" href="https://wa.me/?text={{ wa }}" target="_blank" rel="noopener">
     💬 Share this deal on WhatsApp (family groups = free sales!)</a>
  <form method="post" action="/subscribe/{{ pid }}">
    <input type="email" name="email" required placeholder="Your email — get daily best deals free"
      style="width:100%;padding:13px;border:1px solid #ddd;border-radius:10px;font-size:15px">
    <button style="width:100%;margin-top:8px;padding:12px;border:none;border-radius:10px;
      background:#222;color:#fff;font-weight:700;font-size:15px">🔔 Send Me Daily Deals</button>
  </form>
  <div class="disc">As an affiliate partner we may earn from qualifying purchases.
  Price can change anytime — check the store for the live price.</div>
</div></div></body></html>"""


def create_app(cfg, db: DB | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    db = db or DB(cfg.db_path)
    engine = Engine(cfg, db)
    media_dir = cfg.media_dir

    def _api_check(fn):
        """Wrapper: run heavy work in a thread-safe way and report errors."""
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except (ValueError, PinterestError) as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
        wrapper.__name__ = fn.__name__
        return wrapper

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return send_from_directory(ROOT / "templates", "index.html")

    @app.get("/go/<int:pid>")
    def go(pid: int):
        """Your own-domain bridge link: Pinterest → landing → affiliate URL.

        Landing pages convert 3-8× better than raw affiliate links (they warm
        the buyer, show the deal, handle disclosure) AND keep Pinterest from
        flagging affiliate short-domains. Every view is click-tracked.
        """
        from flask import redirect, render_template_string
        rows = [p for p in db.all_products(limit=2000) if p["id"] == pid]
        if not rows:
            return jsonify({"ok": False, "error": "unknown product"}), 404
        p = rows[0]
        db.log_click(pid, request.headers.get("User-Agent", ""))
        if not cfg.get("link.landing", True):
            return redirect(p["affiliate_url"], code=302)

        from urllib.parse import quote
        from .affiliate import price_label
        price = price_label(p["price"], p["currency"]) or "Best Price"
        disc = int(p.get("discount", 0) or 0)
        public = str(cfg.get("link.public_base", "")).rstrip("/")
        wa = quote(f"🔥 Deal alert! {p['title']} — only {price}"
                   f"{' (' + str(disc) + '% OFF)' if disc >= 15 else ''} 👉 "
                   f"{public}/go/{pid}")
        return render_template_string(LANDING_HTML,
                                      title=p["title"], price=price,
                                      disc=disc, img=f"/media/{p['pin_image'].split('/')[-1]}",
                                      buy=p["affiliate_url"], pid=pid, wa=wa,
                                      brand=cfg.get("design.brand_name", "Deal Drops"))

    @app.post("/subscribe/<int:pid>")
    def subscribe(pid: int):
        """Email capture on landing pages — build YOUR buyer list (gold)."""
        email = (request.form.get("email") or "").strip()
        ok = bool(email) and db.add_subscriber(email)
        from flask import render_template_string
        return render_template_string(
            "<html><body style='font-family:sans-serif;text-align:center;padding-top:60px'>"
            "<h2>{{ msg }}</h2><p>You'll get the best deals daily. 🔥</p></body></html>",
            msg="✅ You're on the list!" if ok else "Already subscribed — you're in!",
        )

    @app.get("/media/<path:name>")
    def media(name: str):
        return send_file(media_dir / name)

    # ------------------------------------------------------------------ api
    @app.get("/api/status")
    def status():
        api = PinterestAPI(cfg)
        stats = db.stats()
        account = None
        if api.configured:
            try:
                acc = api.user_account()
                account = {
                    "username": acc.get("username"),
                    "followers": acc.get("follower_count", 0),
                    "monthly_views": acc.get("monthly_views", 0),
                }
            except PinterestError as exc:
                account = {"error": str(exc)[:200]}
        from .instagram import InstagramAPI, InstagramError as IGE
        ig = InstagramAPI(cfg)
        ig_info = {"enabled": ig.enabled, "configured": ig.configured}
        if ig.enabled and ig.configured:
            try:
                info = ig.check()
                ig_info["username"] = info.get("username")
            except IGE as exc:
                ig_info["error"] = str(exc)[:150]
        return jsonify({
            "ok": True,
            "credentials_ok": api.configured,
            "amazon_tag": bool(cfg.amazon_tag),
            "earnkaro": bool(cfg.get("affiliate.earnkaro_prefix")),
            "cuelinks": bool(cfg.get("affiliate.cuelinks_template")),
            "meesho": bool(cfg.get("affiliate.meesho_affid")),
            "board": cfg.get("pinterest.board_name"),
            "instagram": ig_info,
            "telegram": Notifier().enabled,
            "subscribers": db.subscriber_count(),
            "account": account,
            "stats": stats,
        })

    @app.get("/api/products")
    def products():
        return jsonify(db.all_products(limit=300))

    @app.get("/api/posts")
    def posts():
        return jsonify(db.recent_posts(limit=200))

    @app.get("/api/logs")
    def logs():
        return jsonify(db.recent_logs(limit=150))

    @app.post("/api/add")
    @_api_check
    def add():
        data = request.get_json(force=True, silent=True) or {}
        urls = [u.strip() for u in str(data.get("urls", "")).splitlines() if u.strip()]
        results = []
        for url in urls:
            try:
                pid = engine.ingest_url(url)
                results.append({"url": url, "ok": pid > 0, "id": pid if pid > 0 else None,
                                "note": "duplicated" if pid == -1 else "queued"})
            except ValueError as exc:
                results.append({"url": url, "ok": False, "error": str(exc)})
        engine.scraper.polite_wait()
        return jsonify({"ok": True, "results": results})

    @app.get("/api/analytics")
    def analytics():
        """Pin-to-pin performance: every stage, every number, one screen."""
        hours = {int(k): v for k, v in db.click_hours().items()}
        top = sorted(db.recent_posts(limit=500), key=lambda r: r.get("clicks", 0),
                     reverse=True)[:10]
        return jsonify({
            "clicks_total": sum(db.click_counts().values()),
            "clicks_by_hour": [hours.get(h, 0) for h in range(24)],
            "templates_ctr": db.template_clicks(),
            "subscribers": db.subscriber_count(),
            "top_pins": [{"title": r["title"][:60], "clicks": r.get("clicks", 0),
                          "source": r.get("source", "")} for r in top],
        })

    @app.post("/api/upload-video")
    def upload_video():
        """YOUR videos in, automation out: upload product videos/reels once,
        the bot posts them as video pins + IG reels automatically."""
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "no file"}), 400
        if not f.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
            return jsonify({"ok": False, "error": "only mp4/mov/webm/mkv"}), 400
        vdir = ROOT / "data" / "videos"
        vdir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in f.filename if c.isalnum() or c in "._-")[:80]
        f.save(vdir / safe)
        db.log("INFO", f"🎬 Video added by user: {safe} — will be posted automatically")
        return jsonify({"ok": True, "file": safe})

    @app.post("/api/upload-audio")
    def upload_audio():
        """Manual step for YOU: upload trending audio once.
        The bot then mixes it into every reel automatically."""
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "no file"}), 400
        if not f.filename.lower().endswith((".mp3", ".m4a", ".wav", ".aac")):
            return jsonify({"ok": False, "error": "only mp3/m4a/wav/aac"}), 400
        music_dir = ROOT / str(cfg.get("video.music_dir", "data/music"))
        music_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in f.filename if c.isalnum() or c in "._-")[:80]
        dest = music_dir / safe
        f.save(dest)
        db.log("INFO", f"🎵 Audio added by user: {safe} — reels will use it automatically")
        return jsonify({"ok": True, "file": safe})

    @app.post("/api/add-manual")
    @_api_check
    def add_manual():
        """Add a product without scraping — user provides the details directly."""
        data = request.get_json(force=True, silent=True) or {}
        url = str(data.get("product_url", "")).strip()
        title = str(data.get("title", "")).strip()
        price = str(data.get("price", "")).strip()
        mrp = str(data.get("mrp", "")).strip()
        image_url = str(data.get("image_url", "")).strip()
        video_url = str(data.get("video_url", "")).strip()
        if not url or not title or not image_url:
            raise ValueError("product_url, title and image_url are required")
        if db.url_exists(url):
            return jsonify({"ok": False, "error": "This URL is already in the system"})

        from .affiliate import AffiliateLinker, price_label
        from .engine import build_seo_text
        from .pin_designer import PinDesigner
        from .scraper import detect_source
        import time

        src = detect_source(url)
        linker = AffiliateLinker(cfg)
        aff_url, network = linker.convert(url, src)
        prod = type("P", (), {"image_url": image_url, "title": title,
                              "price": price, "currency": "INR"})()
        img_path = engine.scraper.download_image(prod, cfg.media_dir)
        if not img_path:
            raise ValueError("Could not download the image — check the image URL")
        video_path = ""
        if video_url:
            video_path = engine.scraper.download_video(video_url, cfg.media_dir)
        pin_path = cfg.media_dir / f"pin_{int(time.time()*1000)}.jpg"
        from .scraper import Product as ProdModel
        disc = ProdModel(url=url, price=price, mrp=mrp).discount_pct
        PinDesigner(cfg).create(img_path, title, price_label(price), pin_path,
                                network, discount=disc)
        seo = build_seo_text(cfg, title, price, "INR", network, discount=disc)
        from .trends import score_product
        pid = db.add_product(source=src, url=url, affiliate_url=aff_url, title=title,
                             price=price, image_url=image_url, image_path=img_path,
                             pin_image=str(pin_path), video_url=video_url,
                             video_path=video_path, seo_text=seo,
                             score=score_product(title, price, src),
                             discount=disc, template="")
        db.log("INFO", f"Manually queued product #{pid}: {title[:60]}")
        return jsonify({"ok": True, "id": pid})

    @app.post("/api/post")
    @_api_check
    def post_now():
        data = request.get_json(force=True, silent=True) or {}
        count = max(1, min(int(data.get("count", 1)), 25))
        api = PinterestAPI(cfg)
        if not api.configured:
            raise ValueError(
                "Pinterest credentials missing. Fill .env (PINTEREST_APP_ID, "
                "PINTEREST_APP_SECRET) and run: python -m bot auth"
            )
        posted = engine.post_batch(count)
        return jsonify({"ok": True, "posted": len(posted)})

    @app.post("/api/products/<int:pid>/skip")
    @_api_check
    def skip(pid: int):
        db.update_product(pid, status="skipped")
        return jsonify({"ok": True})

    @app.delete("/api/products/<int:pid>")
    @_api_check
    def delete(pid: int):
        db.update_product(pid, status="skipped")
        return jsonify({"ok": True})

    return app


def serve(cfg) -> None:  # pragma: no cover - long running
    app = create_app(cfg)
    host = cfg.get("dashboard.host", "0.0.0.0")
    port = int(cfg.get("dashboard.port", 5000))
    print(f"\n🖥  Dashboard: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False, threaded=True)
