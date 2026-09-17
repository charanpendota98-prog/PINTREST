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
from .pinterest_api import PinterestAPI, PinterestError

log = logging.getLogger("pindrop.dashboard")
ROOT = Path(__file__).resolve().parent.parent


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
        """Your own-domain bridge link: Pinterest → /go/12 → affiliate URL.

        Why top affiliates do this: your domain is never flagged as a known
        affiliate short-link, it builds account trust, and every click is
        counted so you know EXACTLY which pin makes money.
        """
        from flask import redirect
        rows = [p for p in db.all_products(limit=2000) if p["id"] == pid]
        if not rows:
            return jsonify({"ok": False, "error": "unknown product"}), 404
        db.log_click(pid, request.headers.get("User-Agent", ""))
        return redirect(rows[0]["affiliate_url"], code=302)

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

    @app.post("/api/add-manual")
    @_api_check
    def add_manual():
        """Add a product without scraping — user provides the details directly."""
        data = request.get_json(force=True, silent=True) or {}
        url = str(data.get("product_url", "")).strip()
        title = str(data.get("title", "")).strip()
        price = str(data.get("price", "")).strip()
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
        PinDesigner(cfg).create(img_path, title, price_label(price), pin_path, network)
        seo = build_seo_text(cfg, title, price, "INR", network)
        from .trends import score_product
        pid = db.add_product(source=src, url=url, affiliate_url=aff_url, title=title,
                             price=price, image_url=image_url, image_path=img_path,
                             pin_image=str(pin_path), video_url=video_url,
                             video_path=video_path, seo_text=seo,
                             score=score_product(title, price, src))
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
