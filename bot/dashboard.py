"""Flask control-panel dashboard.

Run:  python -m bot dashboard
Then open the printed URL (works over the sandbox live-preview proxy too —
all URLs are relative).
"""
from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
import time
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template_string, request,
                   send_file, send_from_directory, session)

from .db import DB
from .engine import Engine
from .notify import Notifier
from .pinterest_api import PinterestAPI, PinterestError

log = logging.getLogger("pindrop.dashboard")
ROOT = Path(__file__).resolve().parent.parent

# ── Pages that MUST stay public: they are the money path (pins → landing →
#    affiliate link). Everything else is the admin panel and is password-locked.
PUBLIC_EXACT = {"/login", "/logout", "/healthz", "/favicon.ico", "/deals/today"}
PUBLIC_PREFIX = ("/go/", "/subscribe/", "/media/")

LOGIN_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PinDrop Pro — login</title></head>
<body style="font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
 background:#0f1117;color:#e8eaed;display:flex;align-items:center;
 justify-content:center;min-height:100vh;margin:0">
<form method="post" action="/login" style="background:#171a21;padding:34px 30px;
 border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.5);width:320px">
  <div style="font-size:34px;text-align:center">📌</div>
  <h2 style="margin:6px 0 4px;text-align:center;font-size:19px">PinDrop Pro panel</h2>
  <p style="margin:0 0 18px;text-align:center;color:#9aa0a6;font-size:12px">
     Owner-only area. Your bot keeps posting 24×7 regardless.</p>
  {% if err %}<p style="color:#ff6b6b;font-size:13px;margin:0 0 12px">{{ err }}</p>{% endif %}
  <input name="password" type="password" placeholder="Panel password" autofocus
   style="width:100%;box-sizing:border-box;padding:12px;border-radius:9px;
   border:1px solid #2a2f3a;background:#0f1117;color:#e8eaed;font-size:14px">
  <button style="width:100%;margin-top:12px;padding:12px;border:0;border-radius:9px;
   background:#e60023;color:#fff;font-size:14px;font-weight:600;cursor:pointer">
   Unlock</button>
  <p style="margin:14px 0 0;color:#5f6368;font-size:11px;text-align:center">
   Forgot it? On your server run <code>python -m bot dashboard-pass</code></p>
</form></body></html>"""


def resolve_dashboard_secret(cfg) -> str:
    """Stable session key so the owner isn't logged out on every restart."""
    env = (os.environ.get("DASHBOARD_SECRET") or "").strip()
    if env:
        return env
    cur = str(cfg.get("dashboard.secret_key", "") or "").strip()
    if cur:
        return cur
    path = Path(cfg.db_path).parent / "dashboard_secret.txt"
    try:
        if path.exists():
            saved = path.read_text().strip()
            if saved:
                cfg.raw.setdefault("dashboard", {})["secret_key"] = saved
                return saved
        fresh = secrets.token_hex(24)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh + "\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        cfg.raw.setdefault("dashboard", {})["secret_key"] = fresh
        return fresh
    except OSError:
        return secrets.token_hex(24)


def resolve_dashboard_password(cfg, auto: bool = True,
                               source: dict | None = None) -> str:
    """Password for the admin panel — env > config > auto-generated file.

    Deployments must NEVER leave the panel open on a public IP: when nothing
    is configured we mint a strong password once, store it (chmod 600) and
    keep reusing it so the owner can always find it with `bot dashboard-pass`.

    `source` (optional dict) comes back with {"from": env|config|file|generated|""}
    so callers can report exactly where the password lives — never guess.
    """
    def _done(value: str, whence: str) -> str:
        if source is not None:
            source["from"] = whence
        return value

    env = (os.environ.get("DASHBOARD_PASSWORD") or "").strip()
    if env:
        return _done(env, "env")
    pw = str(cfg.get("dashboard.password", "") or "").strip()
    if pw:
        return _done(pw, "config")
    path = Path(cfg.db_path).parent / "dashboard_password.txt"
    try:
        if path.exists():
            saved = path.read_text().strip()
            if saved:
                if auto:
                    cfg.raw.setdefault("dashboard", {})["password"] = saved
                return _done(saved, "file")
        if not auto:
            return _done("", "")
        fresh = secrets.token_urlsafe(12)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh + "\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        cfg.raw.setdefault("dashboard", {})["password"] = fresh
        return _done(fresh, "generated")
    except OSError:
        return _done("", "")

# High-converting mini landing page (warm-up between pin and affiliate link)
LANDING_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — {{ brand }}</title>
<meta property="og:title" content="{{ title }} — {{ price }}">
<meta property="og:type" content="product">
<meta property="og:description" content="Verified deal: {{ title }} at {{ price }}. Grab it before price jumps!">
<meta property="og:url" content="{{ page_url }}">
<meta property="og:image" content="{{ img }}">
<meta property="og:image:width" content="1000">
<meta property="og:image:height" content="1500">
<meta property="og:site_name" content="{{ brand }}">
<meta property="og:availability" content="instock">
<meta property="product:price:amount" content="{{ raw_price }}">
<meta property="product:price:currency" content="INR">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{{ img }}">
<meta name="description" content="{{ title }} at {{ price }} — verified deal, limited stock.">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"{{ title }}",
 "offers":{"@type":"Offer","price":"{{ raw_price }}","priceCurrency":"INR",
 "availability":"https://schema.org/InStock"}}
</script>
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
 a.more{display:block;text-align:center;background:#7b2ff7;color:#fff;font-size:15px;
     font-weight:800;padding:13px;border-radius:14px;text-decoration:none;margin:0 0 16px}
 .disc{color:#999;font-size:11.5px;text-align:center;padding:10px}
 .urg{background:#fff3cd;border:1px solid #ffe08a;color:#7a5c00;border-radius:10px;
     padding:10px;text-align:center;font-weight:600;font-size:14px}
</style></head><body><div class="wrap">
<div class="top">🔥 {{ brand }} — VERIFIED DEAL</div>
<img class="hero" src="{{ img }}" alt="{{ title }}" onerror="this.style.display='none'">
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
  <div style="color:#777;font-size:11.5px;margin:14px 0 -8px">
    #ad · affiliate link — we may earn a small commission, you pay nothing extra.</div>
  <a class="buy" rel="nofollow sponsored" href="{{ buy }}">🛒 GRAB THE DEAL →</a>
  {% if more %}<a class="more" rel="nofollow sponsored" href="{{ more }}">
     🛍️ Browse More Deals — full collection</a>{% endif %}
  {% if wa_on %}<a class="wa" href="https://wa.me/?text={{ wa }}" target="_blank" rel="noopener">
     💬 Share this deal on WhatsApp (family groups = free sales!)</a>{% endif %}
  <form method="post" action="/subscribe/{{ pid }}">
    <input type="email" name="email" required placeholder="Your email — get daily best deals free"
      style="width:100%;padding:13px;border:1px solid #ddd;border-radius:10px;font-size:15px">
    <button style="width:100%;margin-top:8px;padding:12px;border:none;border-radius:10px;
      background:#222;color:#fff;font-weight:700;font-size:15px">🔔 Send Me Daily Deals</button>
  </form>
  <div class="disc">As an affiliate partner we may earn from qualifying purchases.
  Price can change anytime — check the store for the live price.</div>
</div></div></body></html>"""


DEALS_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deals of the Day — {{ brand }}</title>
<style>
 body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:#faf7f2;color:#222}
 .wrap{max-width:560px;margin:0 auto;background:#fff;min-height:100vh;box-shadow:0 0 40px rgba(0,0,0,.08);padding:20px 16px}
 h1{color:#E60023;text-align:center;font-size:22px;margin:8px 0 2px}
 .sub{text-align:center;color:#888;font-size:13px;margin-bottom:18px}
 .card{display:flex;gap:12px;border:1px solid #eee;border-radius:14px;padding:10px;margin-bottom:12px;align-items:center}
 .card img{width:76px;height:76px;object-fit:cover;border-radius:10px}
 .card .t{font-size:14px;font-weight:600;line-height:1.3}
 .card .p{color:#E60023;font-weight:800;margin-top:4px}
 a.btn{background:#E60023;color:#fff;font-size:13px;font-weight:700;padding:8px 14px;border-radius:10px;text-decoration:none;white-space:nowrap}
 .disc{color:#999;font-size:11px;text-align:center;padding:12px}
</style></head><body><div class="wrap">
<h1>🔥 Deals of the Day</h1>
<div class="sub">{{ brand }} — hand-picked, price-checked, updated daily</div>
{% for p in deals %}
<div class="card">
  <img src="/media/{{ p.img }}" alt="{{ p.title }}" loading="lazy" onerror="this.parentNode.style.display='none'">
  <div style="flex:1"><div class="t">{{ p.title }}</div>
    <div class="p">{{ p.price }}{% if p.disc >= 15 %} · {{ p.disc }}% OFF{% endif %}</div></div>
  <a class="btn" rel="nofollow sponsored" href="{{ p.buy }}">GRAB →</a>
</div>
{% endfor %}
<div class="disc">As an affiliate partner we may earn from qualifying purchases.</div>
</div></body></html>"""


def create_app(cfg, db: DB | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 250MB uploads max
    db = db or DB(cfg.db_path)
    engine = Engine(cfg, db)
    media_dir = cfg.media_dir
    media_dir.mkdir(parents=True, exist_ok=True)

    # every error = clean JSON (frontend never breaks, no tracebacks)
    @app.errorhandler(404)
    def _nf(e):
        return jsonify({"ok": False, "error": "not found"}), 404

    @app.errorhandler(413)
    def _big(e):
        return jsonify({"ok": False, "error": "file too large (max 250MB)"}), 413

    @app.errorhandler(500)
    def _se(e):
        return jsonify({"ok": False, "error": "internal error"}), 500

    # ── owner lock: the panel is admin-only, the money pages stay public ──
    pw = str(cfg.get("dashboard.password", "") or "").strip()
    if not pw:
        pw = (os.environ.get("DASHBOARD_PASSWORD") or "").strip()
    secret = str(cfg.get("dashboard.secret_key", "") or "").strip()
    if not secret:
        secret = secrets.token_hex(24)          # per-run when not persisted
    app.secret_key = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 30 * 86400   # phone stays logged in
    _fails: dict = {}

    def _client_ip() -> str:
        fwd = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        return fwd or request.remote_addr or "?"

    def _authed() -> bool:
        if not pw:
            return True                          # local/dev mode (no lock)
        if hmac.compare_digest(str(session.get("pin_auth", "")), pw):
            return True
        if hmac.compare_digest(request.headers.get("X-Dashboard-Token", ""), pw):
            return True
        tok = request.args.get("token", "")
        if tok and hmac.compare_digest(tok, pw):
            session["pin_auth"] = pw             # ?token=… then clean URL
            return True
        return False

    @app.get("/healthz")
    def _healthz():
        """Public uptime probe — no data leak beyond 'alive'."""
        return jsonify({"ok": True, "service": "pindrop-dashboard",
                        "locked": bool(pw)})

    @app.route("/login", methods=["GET", "POST"])
    def _login():
        err = ""
        if request.method == "POST":
            ip = _client_ip()
            now = time.time()
            hits = [t for t in _fails.get(ip, []) if now - t < 300]
            if len(hits) >= 5:
                return render_template_string(
                    LOGIN_HTML, err="Too many attempts — wait 5 minutes."), 429
            given = (request.form.get("password") or "").strip()
            if pw and hmac.compare_digest(given, pw):
                _fails.pop(ip, None)
                session.permanent = True
                session["pin_auth"] = pw
                return redirect("/")
            if len(_fails) > 200:                # keep the brute-force map small
                _fails.clear()
                _fails[ip] = hits
            hits.append(now)
            _fails[ip] = hits
            err = "Wrong password."
        if not pw:
            return redirect("/")
        return render_template_string(LOGIN_HTML, err=err)

    @app.get("/logout")
    def _logout():
        session.pop("pin_auth", None)
        return redirect("/login")

    @app.before_request
    def _gate():
        if not pw:
            return None
        path = request.path
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX):
            return None
        if _authed():
            return None
        if path.startswith("/api/"):
            return jsonify({"ok": False, "error": "locked — login required",
                            "login": "/login"}), 401
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            return jsonify({"ok": False, "error": "locked"}), 401
        return redirect("/login")

    def _api_check(fn):
        """Wrapper: run heavy work in a thread-safe way and report errors.
        EVERY failure becomes clean JSON — the frontend never sees a crash."""
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except (ValueError, PinterestError) as exc:
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:  # noqa: BLE001 — never a raw 500 traceback
                db.log("ERROR", f"API error in {fn.__name__}: {exc}")
                return jsonify({"ok": False, "error": f"server error: {exc}"}), 500
        wrapper.__name__ = fn.__name__
        return wrapper

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def index():
        return send_from_directory(ROOT / "templates", "index.html")

    @app.get("/deals/today")
    def deals_today():
        """The Deals-of-the-Day page that roundup pins link to — every item
        carries its own tracked affiliate link."""
        from flask import render_template_string
        from .affiliate import price_label
        from .trends import score_product
        base = str(cfg.get("link.public_base", "") or "").rstrip("/")
        bridge = bool(cfg.get("link.bridge", False)) and base
        deals = []
        for p in sorted(db.all_products(limit=300),
                        key=lambda x: score_product(x["title"], x["price"],
                                                    x["source"]), reverse=True)[:10]:
            if not (p.get("pin_image") or p.get("image_path")):
                continue
            deals.append({
                "title": p["title"][:70],
                "price": price_label(p["price"], p["currency"]) or "Best price",
                "disc": int(p.get("discount", 0) or 0),
                "img": (p.get("pin_image") or p.get("image_path")).split("/")[-1],
                "buy": (f"{base}/go/{p['id']}" if bridge else p["affiliate_url"]),
            })
        return render_template_string(
            DEALS_HTML, deals=deals,
            brand=cfg.get("design.brand_name", "Deal Drops"))

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
        img_name = (p.get("pin_image") or "").split("/")[-1]
        rel = f"/media/{img_name}" if img_name else (p.get("image_url") or "")
        # Pinterest/Google need ABSOLUTE image + page URLs for rich results
        if rel.startswith("/") and public:
            hero = f"{public}{rel}"
            page_url = f"{public}/go/{pid}"
        else:
            hero, page_url = rel, f"/go/{pid}"
        return render_template_string(LANDING_HTML,
                                      title=p["title"], price=price,
                                      raw_price=re.sub(r"[^0-9.]", "", p["price"]) or "0",
                                      disc=disc, img=hero, page_url=page_url,
                                      buy=p["affiliate_url"], pid=pid, wa=wa,
                                      wa_on=bool(cfg.get("link.whatsapp_share", False)),
                                      more=str(cfg.get("affiliate.meesho_collection_link",
                                                       "") or ""),
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
        """Serve a generated pin/reel — strictly inside the media dir.

        Hostile filenames (null bytes, traversal, symlink tricks) must be a
        clean 404, never a traceback/500.
        """
        try:
            root = media_dir.resolve()
            p = (media_dir / name).resolve()
            inside = p == root or root in p.parents
        except (OSError, ValueError):        # null byte, bad encoding, …
            return jsonify({"ok": False, "error": "not found"}), 404
        if not inside or not p.is_file():
            return jsonify({"ok": False, "error": "not found"}), 404
        return send_file(p)

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
        # 🚧 circuit breaker: is posting paused (bad token / rate limit)?
        from . import breaker as _br
        br_state = _br.load(db.get_state(_br.STATE_KEY))
        br_open = _br.is_open(br_state, time.time())
        return jsonify({
            "ok": True,
            "api_breaker": {
                "open": br_open,
                "kind": br_state.get("kind", ""),
                "paused_for": _br.human(_br.remaining(br_state, time.time()))
                              if br_open else "",
                "hint": br_state.get("hint", "") if br_open else "",
                "fails": int(br_state.get("fails", 0) or 0),
            },
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

    # ---------------------------------------------- owner control (R45)
    @app.get("/api/control")
    @_api_check
    def control_get():
        """Pause state, daily count, quiet hours, and WHY posting is waiting."""
        from . import control as _ctl
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(cfg.get("timezone", "Asia/Kolkata"))
        now_hour = _dt.now(tz).hour
        capped, posted, cap = _ctl.cap_reached(db, cfg, tz=tz)
        state = _ctl.is_paused(db)
        return jsonify({
            "ok": True,
            "paused": bool(state),
            "reason": _ctl.human_pause(state) if state else "",
            "gate": _ctl.gate(db, cfg, now_hour, tz=tz),
            "daily": {"posted": posted, "cap": cap, "capped": capped},
            "quiet_hours": str(cfg.get("posting.quiet_hours", "")),
        })

    @app.post("/api/control")
    @_api_check
    def control_set():
        """Pause / resume the scheduler. The owner is always the boss."""
        from . import control as _ctl
        data = request.get_json(force=True, silent=True) or {}
        action = str(data.get("action", "")).lower()
        if action == "pause":
            state = _ctl.pause(db, str(data.get("reason", "") or "panel"))
            return jsonify({"ok": True, "paused": True,
                            "message": f"Paused — {state['reason']}"})
        if action == "resume":
            was = _ctl.resume(db)
            return jsonify({"ok": True, "paused": False,
                            "message": "Resumed" if was else "Was not paused"})
        raise ValueError("action must be 'pause' or 'resume'")

    @app.get("/api/report")
    @_api_check
    def report_api():
        """Real numbers for the period + honest estimate (same as bot report)."""
        from . import report as _rep
        try:
            days = max(1, min(int(request.args.get("days", 7)), 365))
        except (TypeError, ValueError):
            days = 7
        return jsonify({"ok": True, "lines": _rep.lines(cfg, db, days=days),
                        "days": days})

    @app.get("/api/earnings")
    @_api_check
    def earnings_api():
        """Honest estimate from real clicks + configurable assumptions."""
        from . import earnings as _earn
        try:
            days = max(1, min(int(request.args.get("days", 30)), 365))
        except (TypeError, ValueError):
            days = 30
        est = _earn.estimate(cfg, _earn.click_rows_since(db, days=days))
        return jsonify({"ok": True, "days": days, **est})

    _links_job: dict = {"running": False, "checked": 0, "broken": 0,
                        "started": "", "last": "", "error": "", "results": []}

    @app.post("/api/links/check")
    @_api_check
    def links_check():
        import threading
        data = request.get_json(force=True, silent=True) or {}
        try:
            limit = max(1, min(int(data.get("limit", 8)), 25))
        except (TypeError, ValueError):
            limit = 8
        if _links_job["running"]:
            return jsonify({"ok": True, "running": True,
                            "message": "Link check already running."})

        def _work(n: int) -> None:
            from . import health as _health
            _links_job.update({"running": True, "checked": 0, "broken": 0,
                               "started": time.strftime("%H:%M:%S"),
                               "last": "", "error": "", "results": []})
            try:
                results = _health.audit_links(cfg, db, limit=n)
                _links_job["checked"] = len(results)
                _links_job["broken"] = sum(1 for r in results
                                           if not (r["ok"] and r["monetized"]))
                _links_job["results"] = [
                    {"product_id": r.get("product_id"), "title": r["title"][:60],
                     "status": r["status"], "ok": r["ok"],
                     "monetized": r["monetized"], "note": r["note"]}
                    for r in results]
            except Exception as exc:  # noqa: BLE001 — job must always end
                _links_job["error"] = str(exc)[:200]
            finally:
                _links_job["running"] = False
                _links_job["last"] = time.strftime("%H:%M:%S")

        threading.Thread(target=_work, args=(limit,), daemon=True,
                         name="links-check").start()
        return jsonify({"ok": True, "running": True,
                        "message": f"Checking {limit} link(s) in the background…"})

    @app.get("/api/links/status")
    @_api_check
    def links_status():
        return jsonify({"ok": True, **_links_job})

    @app.get("/api/radar")
    @_api_check
    def radar_api():
        """🧭 What is genuinely worth posting right now (+ why), and which
        hook archetype is winning — the owner sees the bot's brain."""
        from . import radar as _radar
        view = _radar.radar_view(cfg, db, n=8)
        return jsonify({
            "ok": True,
            "best": [{"id": p["id"], "title": p["title"][:70],
                      "usefulness": p["usefulness"], "price": p.get("price", ""),
                      "why": p["why"][:3]} for p in view["best"]],
            "queued": [{"id": p["id"], "title": p["title"][:70],
                        "usefulness": p["usefulness"]} for p in view["queued"]],
            "notes": view["notes"],
            "hooks": db.hook_performance(),
            "min_score": cfg.get_int("radar.min_score", 40),
        })

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
        img_path = engine.scraper.download_image_url(image_url, cfg.media_dir, title)
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

    # Manual posting runs in the background: a browser tab must never hang for
    # hours, and a double-click must not spawn a second posting thread.
    _post_job: dict = {"running": False, "done": 0, "total": 0,
                       "started": "", "last": "", "error": ""}

    @app.post("/api/post")
    @_api_check
    def post_now():
        import threading
        data = request.get_json(force=True, silent=True) or {}
        try:
            count = max(1, min(int(data.get("count", 1)), 10))
        except (TypeError, ValueError):
            raise ValueError("count must be a number")
        api = PinterestAPI(cfg)
        if not api.configured:
            raise ValueError(
                "Pinterest credentials missing. Fill .env (PINTEREST_APP_ID, "
                "PINTEREST_APP_SECRET) and run: python -m bot auth"
            )
        if _post_job["running"]:
            return jsonify({"ok": True, "running": True, "queued": count,
                            "posted": _post_job["done"],
                            "message": "Posting is already running — this click "
                                       "was not started (no duplicate burst)."})

        def _work(n: int) -> None:
            _post_job.update({"running": True, "done": 0, "total": n,
                              "started": time.strftime("%H:%M:%S"),
                              "last": "", "error": ""})
            try:
                pins = engine.post_batch(
                    n, human_gaps=False,
                    quick_gap=max(0.0, cfg.get_float(
                        "posting.manual_gap_seconds", 6)))
                _post_job["done"] = len(pins)
                if not pins:
                    # never leave the owner with a silent "0 posted": say why
                    why = ""
                    for row in (db.recent_logs(limit=12) or []):
                        if str(row.get("level", "")).upper() in ("ERROR", "WARN"):
                            why = str(row.get("message", ""))[:220]
                            break
                    _post_job["error"] = why or ("nothing posted — check the "
                                                 "logs tab (queue empty or QA "
                                                 "quarantine)")
            except Exception as exc:  # noqa: BLE001 — job must always end
                _post_job["error"] = str(exc)[:200]
                db.log("ERROR", f"manual post job failed: {exc}")
            finally:
                _post_job["running"] = False
                _post_job["last"] = time.strftime("%H:%M:%S")

        threading.Thread(target=_work, args=(count,), daemon=True,
                         name="pin-post-now").start()
        return jsonify({"ok": True, "running": True, "queued": count,
                        "message": f"Posting {count} pin(s) in the background — "
                                   "this page can be closed."})

    @app.get("/api/post/status")
    @_api_check
    def post_status():
        return jsonify({"ok": True, **_post_job})

    # 🧭 Radar hunt in the background — one click finds the top useful
    # products. Bounded by radar.budget_seconds, so it can never hang a tab.
    _radar_job: dict = {"running": False, "added": 0, "best": 0,
                        "started": "", "last": "", "error": ""}

    @app.post("/api/radar/hunt")
    @_api_check
    def radar_hunt_now():
        import threading
        if _radar_job["running"]:
            return jsonify({"ok": True, "running": True,
                            "message": "Hunt already running — no duplicate start."})

        def _work() -> None:
            _radar_job.update({"running": True, "added": 0, "best": 0,
                               "started": time.strftime("%H:%M:%S"),
                               "last": "", "error": ""})
            try:
                from . import radar as _radar
                eng = engine
                added = _radar.radar_hunt(
                    cfg, eng, n=cfg.get_int("radar.hunt_count", 3),
                    min_score=cfg.get_int("radar.min_score", 40))
                _radar_job["added"] = len(added)
                _radar_job["best"] = added[0]["usefulness"] if added else 0
                if not added:
                    _radar_job["error"] = ("nothing added — stores unreachable "
                                           "or all candidates already queued")
            except Exception as exc:  # noqa: BLE001 — job must always end
                _radar_job["error"] = str(exc)[:200]
                db.log("ERROR", f"radar hunt job failed: {exc}")
            finally:
                _radar_job["running"] = False
                _radar_job["last"] = time.strftime("%H:%M:%S")

        threading.Thread(target=_work, daemon=True,
                         name="radar-hunt-now").start()
        return jsonify({"ok": True, "running": True,
                        "message": "Hunting top products in the background…"})

    @app.get("/api/radar/hunt/status")
    @_api_check
    def radar_hunt_status():
        return jsonify({"ok": True, **_radar_job})

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
    host = str(cfg.get("dashboard.host", "0.0.0.0"))
    port = cfg.get_int("dashboard.port", 5000)
    require = cfg.get_bool("dashboard.require_password", True)
    src: dict = {}
    pw = ""
    if require:
        pw = resolve_dashboard_password(cfg, source=src)
    resolve_dashboard_secret(cfg)
    from .lock import AlreadyRunning, acquire, release
    try:
        lk = acquire(cfg, "dashboard")
    except AlreadyRunning as exc:
        print(f"\n⏸  Dashboard already running — {exc}")
        print("   Open the one already serving "
              f"http://127.0.0.1:{port} (or stop it: pkill -f 'bot dashboard').\n")
        return
    app = create_app(cfg)
    print(f"\n🖥  Dashboard: http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
          f"   (VPS unte: http://<server-ip>:{port})")
    if pw:
        whence = {"env": "from .env", "config": "from config.yaml",
                  "file": "saved earlier", "generated": "just auto-created"}.get(
                      src.get("from", ""), "set")
        print(f"🔐 Panel password ({whence}): {pw}")
        if src.get("from") in ("file", "generated"):
            print(f"   Saved in {Path(cfg.db_path).parent / 'dashboard_password.txt'} "
                  "— change anytime with DASHBOARD_PASSWORD in .env")
        else:
            print("   Change it anytime via DASHBOARD_PASSWORD in .env "
                  "(or `python -m bot dashboard-pass`)")
        print("   Public money pages (/go/…, /deals/today, /subscribe/…) stay open.\n")
    else:
        print("⚠️  NO password — panel is OPEN to anyone who finds this port.")
        print("   Fix: put DASHBOARD_PASSWORD=… in .env or set "
              "dashboard.require_password: true\n")
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        release(lk)
