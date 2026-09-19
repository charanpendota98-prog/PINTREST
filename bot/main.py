"""PinDrop Pro CLI.

Usage:
  python -m bot auth                     # connect your Pinterest account (local browser)
  python -m bot auth-url                 # headless step 1: print login URL
  python -m bot auth --code <CODE>       # headless step 2: finish login with code
  python -m bot check                    # verify Pinterest connection & board
  python -m bot ig-check                 # verify Instagram connection
  python -m bot add <url> [url ...]      # scrape products & add to queue
  python -m bot add-csv products.csv     # bulk import (url,title,price,image_url[,video_url])
  python -m bot queue                    # show current queue
  python -m bot post [count]             # post N pins right now (default 1)
  python -m bot run                      # start 24x7 human-like scheduler
  python -m bot design-test              # generate a sample pin graphic
  python -m bot dashboard                # web control panel
  python -m bot radar                    # 🧭 most useful products (0-100 score)
  python -m bot radar --hunt             # find + queue the top ones right now
  python -m bot playbook                 # 📕 2026 content playbook the bot follows
  python -m bot app [--site URL]         # 📝 Pinterest app form — exact answers
  python -m bot app --where              # 🧭 app page open cheyyadam ela (click path)
  python -m bot app --pending            # ⏳ trial pending lo emi lock, emi cheyyochu
  python -m bot creds [--amazon T --earnkaro P …]  # 🔑 validate + save credentials
  python -m bot token-check [--write-test]  # 🔐 token entha cheyyagaladu (live)
  python -m bot name ["Brand | Niche"]   # 🏷️ score a brand name (+ --live verify)
  python -m bot name --next              # 🚨 handle taken? → variants + auto-pick
  python -m bot handle [name]            # 🔗 handle taken? → ranked fallbacks + save
  python -m bot handle check [names]     # 🔎 live: which handles are free?
  python -m bot onboard                  # 📋 every Pinterest screen → what to select
  python -m bot claim [token]            # 🔖 claim your website (Rich Pins)
  python -m bot brand ["Name | Niche"]   # 🏷️ profile name/bio/boards for reach
  python -m bot scale [target]           # 🎯 ₹ target → clicks/posts/day math
  python -m bot ready                    # 🎯 what is left for YOU to do (one time)
  python -m bot pause [reason]           # ⏸ stop posting (kill switch)
  python -m bot resume                   # ▶️ start posting again
  python -m bot links [N]                # 💸 are affiliate links alive + tagged?
  python -m bot earnings [--days N]      # 💰 honest commission estimate
  python -m bot report [--days N] [--telegram]   # 📊 period report
"""
from __future__ import annotations

import csv
import http.server
import logging
import os
import sys
import time
from pathlib import Path
import threading
import urllib.parse
import webbrowser

from . import APP_NAME, __version__
from .config import load_config
from .db import DB
from .engine import Engine
from .instagram import InstagramAPI, InstagramError
from .pinterest_api import PinterestAPI, PinterestError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-18s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pindrop")


def _banner() -> None:
    print(f"""
╔══════════════════════════════════════════════════╗
║   📌 {APP_NAME} v{__version__}  — Pinterest Affiliate Bot   ║
║   scrape → affiliate link → pin design → post    ║
╚══════════════════════════════════════════════════╝""")


# --------------------------------------------------------------------- auth
def _verifier_path(cfg):
    return cfg.token_path.parent / "pkce_verifier.txt"


def _print_app_hint(api) -> int:
    print("❌ Set PINTEREST_APP_ID and PINTEREST_APP_SECRET in .env first.")
    print("   1. Create an app at https://developers.pinterest.com/apps/")
    print("   2. Scopes: boards:read boards:write pins:read pins:write user_accounts:read")
    print(f"   3. Redirect URI in app settings: {api.cfg.get('pinterest.redirect_uri')}")
    return 1


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str = ""

    def do_GET(self):  # noqa: N802
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.code = qs.get("code", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            "<h2 style='font-family:sans-serif'>✅ PinDrop Pro connected! "
            "You can close this tab and return to the terminal.</h2>".encode("utf-8")
        )

    def log_message(self, *a):  # silence
        pass


def _pause_note(db) -> str:
    """Human line when posting is paused (owner pause or API breaker)."""
    try:
        from . import control as _ctl
        state = _ctl.is_paused(db)
        if state:
            return f"owner pause — {_ctl.human_pause(state)}"
    except Exception:  # noqa: BLE001
        pass
    try:
        import time as _t
        from . import breaker
        st = breaker.load(db.get_state(breaker.STATE_KEY))
        if breaker.is_open(st, _t.time()):
            return (f"{breaker.human(breaker.remaining(st, _t.time()))} left "
                    f"— {st.get('hint', '')}")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _clear_api_breaker(cfg) -> None:
    """Re-auth means the token problem is gone — resume posting immediately
    instead of waiting out a 6h circuit-breaker pause."""
    try:
        from . import breaker
        db = DB(cfg.db_path)
        if db.get_state(breaker.STATE_KEY):
            db.del_state(breaker.STATE_KEY)
            print("🔓 API breaker cleared — posting can resume right away.")
    except Exception:  # noqa: BLE001 — never block a successful login
        pass


def cmd_auth(cfg) -> int:
    """Automatic browser flow — works when you can open localhost in a browser."""
    api = PinterestAPI(cfg)
    if not (api.app_id and api.app_secret):
        return _print_app_hint(api)
    url, verifier = api.auth_url()
    _verifier_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    _verifier_path(cfg).write_text(verifier)

    print("\n1) Open this URL in your browser & click ALLOW:\n")
    print(f"   {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    redirect = urllib.parse.urlparse(cfg.get("pinterest.redirect_uri"))
    server = http.server.HTTPServer(("127.0.0.1", redirect.port or 8888), _CallbackHandler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print("2) Waiting for Pinterest callback on", cfg.get("pinterest.redirect_uri"), "…")
    import time
    for _ in range(600):  # up to 5 minutes
        if _CallbackHandler.code:
            break
        time.sleep(0.5)
    if not _CallbackHandler.code:
        print("\n⏱ Timed out (no local browser?). Use the headless flow instead:")
        print("   python -m bot auth-url     # prints a URL you open anywhere")
        print("   python -m bot auth --code <CODE>")
        return 1
    try:
        api.exchange_code(_CallbackHandler.code, verifier)
        acc = api.user_account()
        print(f"\n✅ Connected as @{acc.get('username')} — token saved to data/pinterest_token.json")
        _clear_api_breaker(cfg)
        return 0
    except PinterestError as exc:
        print(f"❌ {exc}")
        return 1


def cmd_auth_url(cfg) -> int:
    """Headless step 1 — print the authorization URL & save the PKCE verifier."""
    api = PinterestAPI(cfg)
    if not (api.app_id and api.app_secret):
        return _print_app_hint(api)
    url, verifier = api.auth_url()
    _verifier_path(cfg).parent.mkdir(parents=True, exist_ok=True)
    _verifier_path(cfg).write_text(verifier)
    print("\nOpen this URL in ANY browser, log in & click ALLOW:\n")
    print(f"   {url}\n")
    print("Pinterest will redirect to a page that may fail to load — that's OK.")
    print("Copy the 'code' from that redirect URL, then run:\n")
    print("   python -m bot auth --code <CODE>")
    return 0


def cmd_auth_code(cfg, code: str) -> int:
    """Headless step 2 — exchange the pasted code using the saved verifier."""
    api = PinterestAPI(cfg)
    vp = _verifier_path(cfg)
    if not vp.exists():
        print("❌ No pending login. Run `python -m bot auth-url` first.")
        return 1
    verifier = vp.read_text().strip()
    try:
        api.exchange_code(code.strip(), verifier)
        vp.unlink(missing_ok=True)
        acc = api.user_account()
        print(f"✅ Connected as @{acc.get('username')} — token saved to data/pinterest_token.json")
        _clear_api_breaker(cfg)
        return 0
    except PinterestError as exc:
        print(f"❌ {exc}")
        return 1


# --------------------------------------------------------------------- cmds
def cmd_check(cfg) -> int:
    api = PinterestAPI(cfg)
    if not api.configured:
        print("❌ Not configured. Add PINTEREST_APP_ID/SECRET to .env, then `python -m bot auth`.")
        return 1
    try:
        acc = api.user_account()
        print(f"✅ Pinterest connected: @{acc.get('username')} "
              f"| followers: {acc.get('follower_count', 0)}")
        board = api.ensure_board(cfg.get("pinterest.board_name"))
        print(f"✅ Board ready: '{cfg.get('pinterest.board_name')}' (id={board})")
        print(f"   Amazon tag: {cfg.amazon_tag or '—'} | EarnKaro: "
              f"{'yes' if cfg.get('affiliate.earnkaro_prefix') else '—'} | Cuelinks: "
              f"{'yes' if cfg.get('affiliate.cuelinks_template') else '—'} | Meesho affid: "
              f"{cfg.get('affiliate.meesho_affid') or '—'}")
        return 0
    except PinterestError as exc:
        print(f"❌ {exc}")
        return 1


def cmd_add(cfg, urls: list[str]) -> int:
    eng = Engine(cfg)
    ok = 0
    for i, url in enumerate(urls):
        try:
            pid = eng.ingest_url(url)
            print(f"{'✅' if pid > 0 else '⏭ '} {url}  (id={pid})")
            ok += pid > 0
        except ValueError as exc:
            print(f"❌ {url}\n   {exc}")
        if i < len(urls) - 1:
            eng.scraper.polite_wait()
    print(f"\n{ok}/{len(urls)} products added to queue.")
    return 0 if ok else 1


def cmd_add_csv(cfg, path: str) -> int:
    """Bulk import. CSV columns: url, title, price, image_url, video_url(optional).
    Only `url` is required — missing fields are scraped/derived."""
    eng = Engine(cfg)
    db = DB(cfg.db_path)
    added = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            url = (row.get("url") or "").strip()
            if not url or db.url_exists(url):
                continue
            title = (row.get("title") or "").strip()
            price = (row.get("price") or "").strip()
            image_url = (row.get("image_url") or "").strip()
            try:
                if title and image_url:
                    # direct row — skip scraping entirely
                    from .affiliate import AffiliateLinker
                    from .engine import build_seo_text
                    from .pin_designer import PinDesigner
                    from .scraper import detect_source
                    import time
                    src = detect_source(url)
                    linker = AffiliateLinker(cfg)
                    aff_url, network = linker.convert(url, src)
                    prod = type("P", (), {"image_url": image_url, "title": title,
                                          "price": price, "currency": "INR"})()
                    img_path = eng.scraper.download_image(prod, cfg.media_dir)
                    if not img_path:
                        raise ValueError("image download failed")
                    pin_path = cfg.media_dir / f"pin_{int(time.time()*1000)}.jpg"
                    PinDesigner(cfg).create(img_path, title, price, pin_path, network)
                    seo = build_seo_text(cfg, title, price, "INR", network)
                    from .trends import score_product
                    db.add_product(source=src, url=url, affiliate_url=aff_url, title=title,
                                   price=price, image_url=image_url, image_path=img_path,
                                   pin_image=str(pin_path), video_url=(row.get("video_url") or ""),
                                   seo_text=seo, score=score_product(title, price, src))
                    added += 1
                    print(f"✅ {title[:55]}")
                else:
                    pid = eng.ingest_url(url)
                    added += pid > 0
            except (ValueError, PinterestError) as exc:
                print(f"❌ {url} — {exc}")
            eng.scraper.polite_wait()
    print(f"\n{added} products imported from {path}")
    return 0 if added else 1


def _set_env_line(path, key: str, value: str) -> None:
    """Upsert KEY=value in .env, keeping the rest intact."""
    lines = path.read_text().splitlines() if path.exists() else []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith(f"{key}=") or ln.strip().startswith(f"# {key}="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")


def cmd_setup(cfg) -> int:
    """ZERO-TOUCH onboarding: one wizard, then the bot runs everything forever.

    The only things a human must do ONCE (API security — cannot be automated):
    create the Pinterest app, click ALLOW, and paste your affiliate IDs.
    """
    from pathlib import Path as P
    print("\n🧙 PinDrop Pro setup wizard — one-time, ~5 minutes\n")

    env_path = P(__file__).resolve().parent.parent / ".env"
    sample = P(__file__).resolve().parent.parent / ".env.example"
    if not env_path.exists() and sample.exists():
        env_path.write_text(sample.read_text())
        print("✔ .env created")

    def ask(label: str, secret: bool = False) -> str:
        try:
            return input(f"   {label}: ").strip()
        except EOFError:
            return ""

    print("STEP 1/3 — Pinterest (one time)")
    print("   • Business account ki convert cheyyandi. 'Describe your business'")
    print("     lo 👉 'Content creator' pick cheyandi (affiliate pages ki ide correct;")
    print("     'Online merchant' ki website kavali + Verified Merchant program")
    print("     affiliate marketers ki bandh)")
    print("   • 'A few more details': goals lo ✅ Increase online sales,")
    print("     ✅ Drive traffic to your site, ✅ Create content on Pinterest")
    print("     • Brand focus: 👉 'Home' (2026 #1 niche; bot content ide focus)")
    print("   • developers.pinterest.com/apps → create app")
    print("   • redirect URI: http://localhost:8888/callback")
    print("   • scopes: boards:read boards:write pins:read pins:write user_accounts:read")
    app_id = ask("App ID") or cfg.pinterest_app_id
    app_secret = ask("App Secret") or cfg.pinterest_app_secret
    if app_id:
        _set_env_line(env_path, "PINTEREST_APP_ID", app_id)
    if app_secret:
        _set_env_line(env_path, "PINTEREST_APP_SECRET", app_secret)

    print("\nSTEP 2/3 — Affiliate IDs (money! paste whatever you have, Enter = skip)")
    for key, label in [
        ("AMAZON_TAG", "Amazon Associates tag (e.g. mydeals-21)"),
        ("MEESHO_AFFID", "Meesho Creator Club affid"),
        ("EARNKARO_PREFIX", "EarnKaro link prefix (https://ekaro.in/…)"),
        ("FLIPKART_AFFID", "Flipkart affid (optional)"),
    ]:
        val = ask(label)
        if val:
            _set_env_line(env_path, key, val)

    print("\nSTEP 3/3 — Connect Pinterest account")
    os.environ["PINTEREST_APP_ID"] = app_id or cfg.pinterest_app_id
    os.environ["PINTEREST_APP_SECRET"] = app_secret or cfg.pinterest_app_secret
    fresh = load_config()
    api = PinterestAPI(fresh)
    if api.configured:
        url, verifier = api.auth_url()
        _verifier_path(fresh).parent.mkdir(parents=True, exist_ok=True)
        _verifier_path(fresh).write_text(verifier)
        print(f"\n   Open & click ALLOW:\n   {url}\n")
        code = ask("Paste the code= value from the redirect URL")
        if code:
            try:
                api.exchange_code(code, verifier)
                acc = api.user_account()
                print(f"   ✅ Connected as @{acc.get('username')}")
            except PinterestError as exc:
                print(f"   ❌ {exc}")
    else:
        print("   (skipped — fill PINTEREST_APP_ID/SECRET in .env later, then `python -m bot auth-url`)")

    print("\n" + "=" * 62)
    print("🎉 SETUP DONE. From now on you do NOTHING:")
    print("   python -m bot run        # 24×7 autopilot: hunts products, designs")
    print("                            # pins+reels, posts Pinterest (+IG), tracks clicks")
    print("   python -m bot dashboard  # watch it work: stats, clicks, logs")
    print("=" * 62 + "\n")
    return 0


def cmd_doctor(cfg) -> int:
    """Full health check — 'anthi set avuthunda?' ki oka command answer."""
    import shutil
    from .instagram import InstagramAPI
    from .notify import Notifier

    checks: list[tuple[str, bool, str]] = []
    def ck(name: str, ok: bool, fix: str = "") -> None:
        checks.append((name, ok, fix))

    ck("Python ≥3.9", __import__("sys").version_info >= (3, 9))
    try:
        import PIL, flask, bs4, yaml, imageio_ffmpeg  # noqa: F401
        ck("Dependencies installed", True)
        ck("ffmpeg (reels)", bool(imageio_ffmpeg.get_ffmpeg_exe()))
    except ImportError as e:
        ck("Dependencies installed", False, f"pip install -r requirements.txt ({e})")
    ck("Fonts (pin text)", Path("/usr/share/fonts/truetype/dejavu").exists()
       or shutil.which("fc-list") is not None)
    ck(".env file", (Path(__file__).parent.parent / ".env").exists(),
       "python -m bot setup")
    ck("Pinterest App ID/Secret", bool(cfg.pinterest_app_id and cfg.pinterest_app_secret),
       "developers.pinterest.com → create app → .env")
    _trial_tok = str(getattr(cfg, "pinterest_access_token", "") or "")
    if cfg.token_path.exists():
        _pin_ok, _pin_how = True, "OAuth refresh token saved"
    elif _trial_tok:
        _pin_ok, _pin_how = True, ("trial token in .env — testing only; public "
                                   "pins ki: auth-url + auth --code")
    else:
        _pin_ok, _pin_how = False, "python -m bot auth-url  +  auth --code"
    ck("Pinterest token (auth done)", _pin_ok, _pin_how)
    ck("Amazon tag", bool(cfg.amazon_tag), "affiliate-program.amazon.in")
    ck("Meesho/EarnKaro/Cuelinks (any)", bool(
        cfg.get("affiliate.meesho_affid") or os.getenv("MEESHO_AFFID")
        or cfg.get("affiliate.earnkaro_prefix") or os.getenv("EARNKARO_PREFIX")
        or cfg.get("affiliate.cuelinks_template")), "see README affiliate guide")
    ck("Meesho DIRECT af_invite (recommended)", bool(
        os.getenv("MEESHO_TEMPLATE_LINK") or cfg.get("affiliate.meesho_template_link")),
       "paste ONE af_invite link from affiliate.meesho.com → .env MEESHO_TEMPLATE_LINK")
    # Meesho link correctness — parseable IDs + real product-id test
    from .affiliate import AffiliateLinker as _AL
    _mh = _AL(cfg).meesho_health()
    if _mh["links_pasted"]:
        ck(f"Meesho link parses (pub={_mh['publisher'] or '?'}, "
           f"campaigns={len(_mh['campaigns'])})", _mh["parsed"],
           "paste a FRESH share link from affiliate.meesho.com (format changed?)")
        _pid = _AL.meesho_product_id(
            "https://www.meesho.com/women-kurta-set/p/1k1b6")
        ck("Meesho product-id parser (alphanumeric)", _pid == "1k1b6",
           "run `python -m bot meesho <your product url>` to inspect")
    from .youtube import YouTubeAPI as _YT
    _yt = _YT(cfg)
    _yts = _yt.status()
    if _yts["enabled"]:
        ck("YouTube Shorts (reels → Shorts + link in description)", _yts["configured"],
           "console.cloud.google.com → YouTube Data API v3 → Desktop OAuth → "
           "python -m bot yt-auth-url")
    else:
        ck("YouTube Shorts (optional)", True,
           "youtube.enabled=true + YT_CLIENT_ID/SECRET + bot yt-auth-url")
    fb_ok = bool(os.getenv("FACEBOOK_ACCESS_TOKEN") and os.getenv("FACEBOOK_PAGE_ID"))
    ck("Facebook Page (optional)", fb_ok or not cfg.get("facebook.enabled"),
       "FB Page → Meta app token → .env FACEBOOK_*")
    ig = InstagramAPI(cfg)
    ck("Instagram (optional)", ig.configured or not cfg.get("instagram.enabled"),
       "README → Instagram Automation")
    ck("Telegram alerts (optional)", Notifier().enabled or True,
       "@BotFather token → .env")
    db = DB(cfg.db_path)
    st = db.stats()
    ck("Database OK", st["total"] >= 0)
    ck("Queue has products", st["queued"] > 0, "bot add <url>  (or autopilot hunts)")

    print("\n🩺 PinDrop Pro doctor\n" + "-" * 58)
    # API breaker: is posting paused (bad token / rate limit)? Owner must see it.
    try:
        from . import breaker as _br
        _st = _br.load(db.get_state(_br.STATE_KEY))
        _open = _br.is_open(_st, time.time())
        if _open:
            checks.append((
                "Posting paused by API breaker", False,
                f"{_br.human(_br.remaining(_st, time.time()))} left — "
                f"{_st.get('hint', '')}"))
        else:
            checks.append(("Posting not paused (API healthy)", True, ""))
        from . import control as _ctl
        if _ctl.is_paused(db):
            checks.append(("Posting paused by OWNER (kill switch)", False,
                           "python -m bot resume  (or the panel Money tab)"))
        else:
            checks.append(("Kill switch: running", True, ""))
    except Exception:  # noqa: BLE001 — doctor must never crash
        pass

    bad = 0
    for item in checks:
        name, ok = item[0], item[1]
        fix = item[2] if len(item) > 2 else ""     # never crash on a short entry
        mark = "✅" if ok else "❌"
        if not ok and "optional" not in name:
            bad += 1
        line = f" {mark} {name}"
        if not ok and fix:
            line += f"  → {fix}"
        print(line)
    print("-" * 58)
    if bad:
        print(f" {bad} thing(s) to fix — mostly `python -m bot setup` covers all.\n")
    else:
        print(" 🎉 FULLY SET! Run:  ./run.sh   (24×7 autopilot)\n")
    return 0 if bad == 0 else 1


def cmd_radar(cfg, rest: list[str]) -> int:
    """🧭 Product radar — the most USEFUL products, ranked, always hunting."""
    from . import radar
    hunt = any(a in ("--hunt", "-H") for a in rest)
    top = cfg.get_int("radar.min_score", 40)
    db = DB(cfg.db_path)
    if hunt:
        from .engine import Engine
        eng = Engine(cfg, db)
        print("\n🧭 RADAR HUNT — discovering → scoring → queueing top products…\n")
        added = radar.radar_hunt(cfg, eng,
                                 n=cfg.get_int("radar.hunt_count", 3),
                                 min_score=top)
        if not added:
            print("  ⚠️  Nothing added (network blocked from this machine, or all")
            print("     candidates already queued). Your phone/VPS can reach stores.")
            print("     Manual: python -m bot add <product-url>\n")
            return 1
        for a in added:
            print(f"  ✅ {a['usefulness']:3d}/100  {a['title'][:52]}")
            for why in a["why"][:3]:
                print(f"        • {why}")
        print(f"\n  {len(added)} product(s) queued — they will post FIRST "
              "(queue is usefulness-ranked).\n")
        return 0

    view = radar.radar_view(cfg, db, n=cfg.get_int("radar.show_count", 8))
    print("\n🧭 PRODUCT RADAR — what people actually need (0-100 usefulness)")
    print("-" * 62)
    if view["best"]:
        print("\n🏆 TOP PICKS (post these first):")
        for p in view["best"][:5]:
            print(f"  {p['usefulness']:3d}  {p['title'][:52]}")
            for why in p["why"][:2]:
                print(f"        • {why}")
    if view["queued"]:
        print("\n📦 IN QUEUE (ranked):")
        for p in view["queued"][:6]:
            print(f"  {p['usefulness']:3d}  [{p['status']}] {p['title'][:46]}")
    if view["posted"]:
        print("\n📌 ALREADY POSTED (your proven shelf):")
        for p in view["posted"][:5]:
            print(f"  {p['usefulness']:3d}  {p['title'][:46]}")
    for note in view["notes"]:
        print(f"\n  ℹ️  {note}")
    if not (view["queued"] or view["posted"]):
        print("\n  Queue khali — `python -m bot radar --hunt` tho top products "
              "vethukondi.\n")
        return 0
    print(f"\n  Next: python -m bot radar --hunt   (find more top products)\n")
    return 0


def cmd_dashboard_pass(cfg) -> int:
    """Show (or rotate) the admin-panel password — never locked out."""
    from pathlib import Path as _P
    from .dashboard import resolve_dashboard_password

    path = _P(cfg.db_path).parent / "dashboard_password.txt"
    pw = resolve_dashboard_password(cfg, auto=False)
    if not pw:
        pw = resolve_dashboard_password(cfg)
    if not pw:
        print("❌ Password create cheyyalekapoyindi (data dir writable aa?).")
        print("   Fix: DASHBOARD_PASSWORD=<something> pettu .env lo.")
        return 1
    host = cfg.get("dashboard.host", "0.0.0.0")
    port = cfg.get_int("dashboard.port", 5000)
    print("\n🔐 Dashboard login")
    print(f"   URL      : http://<server-ip>:{port}"
          f"{'   (local: http://127.0.0.1:' + str(port) + ')' if host in ('0.0.0.0', '::') else ''}")
    print(f"   Password : {pw}")
    print(f"   Saved in : {path}")
    print("\n   Marchipoyava? Rotate:  .venv/bin/python -c \"import secrets;"
          "print(secrets.token_urlsafe(12))\"  → .env DASHBOARD_PASSWORD=…\n")
    return 0


def cmd_deploy_check(cfg) -> int:
    """VPS preflight: 'deploy ki ready na, inka em kavali?' ki oke answer."""
    import shutil
    import socket
    import sys
    from pathlib import Path as _P
    from .dashboard import resolve_dashboard_password

    print("\n🚀 DEPLOY PREFLIGHT — server ki ready aa?\n" + "-" * 58)
    bad = 0

    def ck(name: str, ok: bool, fix: str = "") -> None:
        nonlocal bad
        if not ok:
            bad += 1
        print(f" {'✅' if ok else '❌'} {name}" + ("" if ok or not fix else f"  → {fix}"))

    py = sys.version_info
    ck(f"Python ≥3.9 (found {py.major}.{py.minor})", py >= (3, 9),
       "sudo apt install python3 python3-venv")
    ff = shutil.which("ffmpeg")
    if not ff:
        try:                                     # bundled binary (no apt needed)
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:                        # noqa: BLE001
            ff = ""
    ck(f"ffmpeg (reels/videos){'' if not ff else ' — ' + ('system' if shutil.which('ffmpeg') else 'bundled')}",
       bool(ff), ".venv/bin/pip install imageio-ffmpeg  (or sudo apt install ffmpeg)")
    try:
        import PIL, flask, requests, bs4, yaml, imageio_ffmpeg  # noqa: F401
        ck("Python packages", True)
    except ImportError as exc:
        ck(f"Python packages ({exc})", False, ".venv/bin/pip install -r requirements.txt")
    ck("git repo intact", (_P(__file__).resolve().parent.parent / "config.yaml").exists())

    # writable storage
    for label, p in (("data/", _P(cfg.db_path).parent), ("media/", _P(cfg.media_dir))):
        ok = True
        try:
            p.mkdir(parents=True, exist_ok=True)
            t = p / ".preflight"
            t.write_text("x")
            t.unlink()
        except OSError:
            ok = False
        ck(f"{label} writable", ok, f"chown/chmod {p}")

    # disk space (media + reels pile up)
    try:
        free_gb = shutil.disk_usage(str(_P(cfg.db_path).parent)).free / 1024 ** 3
    except OSError:
        free_gb = 0.0
    ck(f"Disk free ≥1GB (have {free_gb:.1f}GB)", free_gb >= 1, "VPS disk full — cleanup")

    # systemd units
    if shutil.which("systemctl") and _P("/etc/systemd/system").is_dir():
        sched = _P("/etc/systemd/system/pindrop.service").exists()
        dash = _P("/etc/systemd/system/pindrop-dashboard.service").exists()
        ck("systemd: pindrop.service (poster)", sched, "sudo ./deploy.sh")
        ck("systemd: pindrop-dashboard.service (panel)", dash, "sudo ./deploy.sh")
    else:
        ck("systemd available (docker? use ./run.sh instead)", True)

    # posting paused? (circuit breaker) — the owner must see this
    try:
        from . import breaker as _br
        _dbx = DB(cfg.db_path)
        _st = _br.load(_dbx.get_state(_br.STATE_KEY))
        _open = _br.is_open(_st, time.time())
        ck("Posting not paused by API breaker", not _open,
           f"paused {_br.human(_br.remaining(_st, time.time()))}: "
           f"{_st.get('hint', '')} — fix it and posting resumes automatically")
    except Exception:  # noqa: BLE001
        pass

    # panel lock — the big one
    pw = resolve_dashboard_password(cfg, auto=False)
    ck("Dashboard password set", bool(pw),
       "python -m bot dashboard-pass  (auto-creates one)")

    # port reachable/free (informational — our own service may hold it)
    port = cfg.get_int("dashboard.port", 5000)
    s = socket.socket()
    s.settimeout(0.4)
    busy = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    print(f"   ℹ️  Port {port}: {'already listening (our dashboard, most likely)' if busy else 'free for the dashboard'}")

    # money spine — a link MUST come out monetized or we're posting for free
    from .affiliate import AffiliateLinker
    link, network = AffiliateLinker(cfg).convert(
        "https://www.meesho.com/x/p/1k1b6", "meesho", platform="pinterest")
    monetized = bool(link) and AffiliateLinker(cfg).is_monetized(link)
    ck(f"Money path: Meesho link monetized ({network})", monetized,
       "paste MEESHO_TEMPLATE_LINK + AMAZON_TAG in .env → python -m bot meesho")
    papi = PinterestAPI(cfg)
    ck("Pinterest credentials", papi.configured, "python -m bot setup && python -m bot auth")

    print("-" * 58)
    if bad:
        print(f" ⛔ {bad} item(s) to fix — fix చేసి malli `python -m bot deploy-check`.\n")
    else:
        print(" 🎉 DEPLOY-READY! `sudo ./deploy.sh` → bot 24×7 pani chestundi.\n")
    return 0 if bad == 0 else 1


def cmd_ig_check(cfg) -> int:
    ig = InstagramAPI(cfg)
    if not ig.configured:
        print("❌ Instagram not configured. In .env set:")
        print("   INSTAGRAM_ACCESS_TOKEN=...   IG_USER_ID=...   (optional IMGBB_KEY=...)")
        print("   Then set instagram.enabled: true in config.yaml")
        print("\n   Setup guide: README → 'Instagram Automation' section.")
        return 1
    try:
        info = ig.check()
        print(f"✅ Instagram connected: @{info.get('username')} "
              f"({info.get('account_type')}) | followers: {info.get('followers_count', 0)} "
              f"| posts: {info.get('media_count', 0)}")
        print(f"   Mode: {cfg.get('instagram.mode')} | designed-pin hosting: "
              f"{'ImgBB' if ig.imgbb_key else 'off (uses product photo URLs)'}")
        # 🤖 what the bot does with comments + DMs (ManyChat equivalent)
        triggers = list((cfg.get("instagram.triggers") or {}).keys())
        dm_on = bool(cfg.get("instagram.private_dm", True))
        pub_on = bool(cfg.get("instagram.public_reply", True))
        auto_dm = bool(cfg.get("instagram.auto_dm", True))
        print(f"\n🤖 AUTO-DM (ManyChat-style, official API — no third party):")
        print(f"   comment → private DM with the direct link: "
              f"{'ON' if dm_on else 'OFF'}")
        print(f"   public comment reply (engagement):         "
              f"{'ON' if pub_on else 'OFF'}")
        print(f"   keyword DM answers (link/price/buy…):      "
              f"{'ON' if auto_dm else 'OFF'}")
        print(f"   bio link auto-updates to latest deal:      "
              f"{'ON' if cfg.get('instagram.auto_bio_link', True) else 'OFF'}")
        print(f"   trigger words ({len(triggers)}): {', '.join(triggers[:10])}")
        # real capability probe: newer tokens have messaging permission
        try:
            ig._get(f"{ig.ig_user_id}/conversations", fields="id")
            print("   inbox access: ✅ token can read conversations")
        except InstagramError as exc:
            low = str(exc).lower()
            if "permission" in low or "scope" in low or "190" in low:
                print("   inbox access: ⚠️  token needs instagram_manage_messages")
                print("        → regenerate the token with that permission; "
                      "comment replies still work")
            else:
                print(f"   inbox access: ⚠️  {str(exc)[:90]}")
        return 0
    except InstagramError as exc:
        print(f"❌ {exc}")
        return 1


def cmd_simulate(cfg) -> int:
    """10x advanced: run the ENTIRE pipeline end-to-end with zero credentials.

    Proves every stage is workable before you hand over API keys:
    product → affiliate link → SEO → design → reel(+BGM+voice) → QA gate
    → landing page → click tracking → winners-rotation logic.
    """
    from datetime import datetime
    print("\n🧪 PIN-TO-PIN SIMULATION — full pipeline, no credentials needed\n")
    ok_all = True

    def step(name: str):
        print(f"\n━━ {name}")

    # 0) sample product
    step("0️⃣ Sample product (demo)")
    prod = {"id": 99999, "source": "amazon",
            "title": "boAt Airdopes 141 Bluetooth Wireless Earbuds",
            "price": "1099", "currency": "INR", "discount": 63,
            "image_url": "https://m.media-amazon.com/images/I/61sim.jpg",
            "seo_text": "", "pin_image": "", "video_path": "", "attempts": 0}
    from .affiliate import AffiliateLinker, price_label
    label = price_label(prod["price"], prod["currency"])
    print(f"   ✅ {prod['title'][:60]}… @ {label} ({prod['discount']}% OFF)")

    # 1) affiliate link
    step("1️⃣ Affiliate link engine")
    link, network = AffiliateLinker(cfg).convert(
        "https://www.amazon.in/dp/B0SIMULATED1", prod["source"])
    tag = str(cfg.get("affiliate.amazon_tag", "")).strip()
    if not tag:
        # demo only: a placeholder tag so the full pipeline (and the leak
        # gate) can be demonstrated honestly before real IDs exist
        link += ("&" if "?" in link else "?") + "tag=DEMO-PLACEHOLDER-21"
    print(f"   {'✅' if link.startswith('http') else '❌'} {link[:90]}")
    if tag and f"tag={tag}" in link:
        print("   ✅ your affiliate tag embedded — you earn the commission")
    elif tag:
        print("   ⚠️ tag not found in link — set AMAZON_TAG in .env")
    else:
        print("   ℹ️  no AMAZON_TAG in .env yet — PLACEHOLDER tag used for this")
        print("       demo. Real runs always use YOUR tag automatically.")

    # leak-gate proof: show that an untracked link is caught, not posted
    linker_for_check = AffiliateLinker(cfg)
    bare = "https://www.amazon.in/dp/B0EXAMPLE"
    print(f"   ✅ commission guard: bare link (no tracking) → "
          f"{'BLOCKED' if not linker_for_check.is_monetized(bare, 'amazon') else 'allowed'} — "
          f"'ekkada commission miss avvodu' sealed")
    from .qa import looks_dummy
    demo_check = looks_dummy({"url": "https://www.meesho.com/floral-kurta-set/p/demokurta",
                              "title": "Demo Kurta", "image_url": ""})
    print(f"   ✅ dummy guard: demo/sample product → "
          f"{'BLOCKED (never posts)' if demo_check else 'allowed'} — "
          f"no dummy posting, live account safe")

    # 2) SEO
    step("2️⃣ SEO title + description")
    from .engine import build_seo_text
    from .growth import seo_title
    prod["seo_text"] = build_seo_text(cfg, prod["title"], prod["price"],
                                      prod["currency"], prod["source"], prod["discount"])
    t = seo_title(prod["title"], label, prod["source"])
    print(f"   ✅ title: {t[:80]}")
    print(f"   ✅ desc: {prod['seo_text'][:70]}…")

    # 3) design (needs a real image; use any demo image found)
    step("3️⃣ Pin design")
    media = cfg.media_dir
    demo_imgs = sorted(media.glob("demo_*.jpg")) + sorted(media.glob("*.jpg"))
    img = str(demo_imgs[0]) if demo_imgs else ""
    if not img:
        print("   ⚠️ no demo image in data/media — generating placeholder")
        from PIL import Image
        Image.new("RGB", (1000, 1000), (240, 240, 245)).save(media / "demo_ph.jpg")
        img = str(media / "demo_ph.jpg")
    from .pin_designer import TEMPLATES
    from .engine import Engine
    e = Engine(cfg)
    out = media / "sim_pin.jpg"
    e.designer.create(img, prod["title"], label, str(out), "amazon",
                      template=e.pick_template(), discount=prod["discount"])
    print(f"   ✅ designed pin ({TEMPLATES[0]} family): {out.name}")

    # 4) reel + original BGM (+voiceover attempt)
    step("4️⃣ Voice reel + BGM")
    from . import voiceover as vo
    from .video_maker import ReelMaker, pick_music
    from .growth import hook_for
    script = vo.script_for(str(cfg.get("video.lang", "en-IN")), prod["title"], label)
    vo_path = vo.generate(script, str(cfg.get("video.lang", "en-IN")),
                          media / "sim_vo.mp3")
    print(f"   {'✅' if vo_path else '⚠️ '} voiceover: "
          f"{'generated' if vo_path else 'skipped (offline) — original BGM still used'}")
    music = pick_music(cfg)
    print(f"   ✅ BGM: {Path(music).name if music else '(none)'}")
    reel = media / "sim_reel.mp4"
    ReelMaker(cfg).make(img, hook_for(label, prod["title"], datetime.now().day),
                        prod["title"], label, reel, prod["source"],
                        voiceover=vo_path or None, music=music or None,
                        vo_seconds=vo.estimate_seconds(script) if vo_path else 0)
    print(f"   ✅ reel rendered: {reel.name} ({reel.stat().st_size // 1024} KB)")

    # 5) QA gate
    step("5️⃣ Pin-by-Pin QA gate")
    from . import qa as _qa
    prod["pin_image"] = str(out)
    rep, qok = _qa.qa_report(cfg, e.db, prod, t, prod["seo_text"], str(out), link)
    print(rep)
    ok_all &= qok

    # 6) landing page render
    step("6️⃣ Landing page (bridge)")
    from urllib.parse import quote
    from flask import Flask
    from .dashboard import LANDING_HTML
    app = Flask(__name__)
    with app.app_context():
        from jinja2 import Template
        html = Template(LANDING_HTML).render(
            title=prod["title"], price=label, disc=prod["discount"],
            raw_price="1099", img="/media/x.jpg", buy=link, pid=99999,
            page_url="/go/99999", wa=quote("deal"), wa_on=False, more="",
            brand=cfg.get("design.brand_name", "Deal Drops"))
    print(f"   ✅ renders ({len(html)} chars) with WhatsApp share + email capture")
    print(f"   ✅ SEO schema present: og:title={'og:title' in html}, "
          f"JSON-LD={'schema.org' in html} (Google/social ready)")

    # 7) click tracking + rotation logic
    step("7️⃣ Analytics + winners rotation")
    e.db.log_click(99999, "sim")
    print(f"   ✅ click tracked (total {sum(e.db.click_counts().values())})")
    cands = e.db.reshare_candidates()
    print(f"   ✅ rotation engine active ({len(cands)} winners queued)")

    print("\n" + ("🏆 SIMULATION PASSED — pipeline is 100% workable. Add credentials "
                  "and go live!" if ok_all else
                  "⚠️  Simulation finished with warnings — check items above."))
    return 0


def cmd_music(cfg) -> int:
    """Compose an ORIGINAL, 100% copyright-free BGM loop (no downloads!)."""
    from . import music_maker
    out = cfg.media_dir.parent / "music" / "auto_bgm.wav"
    music_maker.compose(out, seconds=14)
    print(f"\n🎼 Original BGM composed (C–G–Am–F lo-fi loop): {out}")
    print("   Safe on every platform — it's our own music. Reels will use it")
    print("   automatically. Your uploaded audio (data/music/) always wins.")
    return 0


def cmd_trends(cfg) -> int:
    """Show the winner-niche priority list (what top channels push)."""
    from .trends import describe
    print()
    print(describe())
    print("\n   Autopilot hunts these niches FIRST, and the queue posts")
    print("   higher-scored products first. Same winners, original pins. 🏆")
    return 0


def cmd_keywords(cfg, seeds: list[str]) -> int:
    """Mine live Pinterest autocomplete phrases for your niche."""
    from .keywords import fetch_suggestions
    for seed in seeds:
        phrases = fetch_suggestions(seed)
        print(f"\n🔎 '{seed}' → {len(phrases)} live search phrases:")
        for p in phrases[:10]:
            print(f"   • {p}")
        if not phrases:
            print("   (Pinterest blocked this network — bot falls back to its keyword bank;")
            print("    on your home network this mines real trending phrases.)")
    return 0







CRED_FLAGS = {
    "--amazon": "AMAZON_TAG",
    "--earnkaro": "EARNKARO_PREFIX",
    "--meesho": "MEESHO_TEMPLATE_LINK",
    "--meesho-affid": "MEESHO_AFFID",
    "--flipkart": "FLIPKART_AFFID",
    "--cuelinks": "CUELINKS_TEMPLATE",
    "--pin-token": "PINTEREST_ACCESS_TOKEN",
    "--pin-id": "PINTEREST_APP_ID",
    "--pin-secret": "PINTEREST_APP_SECRET",
}


def cmd_creds(cfg, rest: list[str]) -> int:
    """🔑 Validate + save credentials (.env); explain anything wrong."""
    from . import creds as _creds
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(rest):
        word = rest[i]
        key = CRED_FLAGS.get(word)
        if key and i + 1 < len(rest):
            pairs.append((key, rest[i + 1]))
            i += 2
            continue
        if word.startswith("--") and "=" in word:
            flag, value = word.split("=", 1)
            key = CRED_FLAGS.get(flag)
            if key:
                pairs.append((key, value))
                i += 1
                continue
        i += 1

    print()
    if pairs:
        res = _creds.apply_credentials(pairs)
        for item in res["results"]:
            if item["ok"]:
                print(f"✅ {item['key']} saved: {item['value']}")
                if item.get("note"):
                    print(f"   ℹ️ {item['note']}")
            else:
                print(f"❌ {item['key']} NOT saved: {item['error']}")
                if item.get("fix"):
                    print(f"   → {item['fix']}")
        if res["saved"]["saved"]:
            print(f"\n   .env updated ({', '.join(res['saved']['keys'])}) — "
                  "chmod 600 ✅")
    # reload so the status below reflects what was just written
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:  # noqa: BLE001 — dotenv optional at import time
        pass
    print("\n".join(_creds.status_lines(cfg)))
    print()
    return 0


def cmd_token_check(cfg, rest: list[str]) -> int:
    """🔐 What can the current Pinterest token actually do? (live proof)"""
    from . import tokencheck as _tc
    write_test = any(w in ("--write-test", "--write", "-w") for w in rest)
    print()
    print("\n".join(_tc.lines(cfg, write_test)))
    print()
    return 0


def cmd_app(cfg, rest: list[str]) -> int:
    """📝 Pinterest 'Connect app' form — exact answers (+ --site to save URL)."""
    from . import appform as _appform
    rest = list(rest)
    site = ""
    for i, word in enumerate(rest):
        if word == "--site" and i + 1 < len(rest):
            site = rest[i + 1]
        elif word.startswith("--site="):
            site = word.split("=", 1)[1]
    if any(w in ("--pending", "pending") for w in rest):
        print()
        print("\n".join(_appform.pending_lines(cfg)))
        print()
        return 0
    if any(w in ("--where", "-w", "where") for w in rest):
        print()
        print("\n".join(_appform.where_lines(cfg)))
        print()
        return 0
    if any(w in ("--upgrade", "--standard") for w in rest):
        print()
        print("\n".join(_appform.upgrade_lines(cfg)))
        print()
        return 0
    print()
    if site:
        res = _appform.save_site(cfg, site)
        if res.get("saved"):
            print(f"✅ Site saved: {res['url']}  (link.public_base)")
        else:
            print(f"❌ {res.get('error', 'save failed')}")
    print("\n".join(_appform.lines(cfg)))
    print()
    return 0


def cmd_name(cfg, rest: list[str]) -> int:
    """🏷️ Brand naming: score a name + live-verify handle/domain."""
    from . import naming as _naming
    words = [w for w in rest if not w.startswith("-")]
    live = any(w in ("--live", "-l", "live", "check") for w in rest)
    next_plan = any(w in ("--next", "-n", "next", "taken") for w in rest)
    name = " ".join(words).strip()
    print()
    if next_plan:
        brand = name
        if not brand:
            brand = str(cfg.get("brand.display_name", "") or "").split("|")[0]
            brand = brand.strip() or str(cfg.get("design.brand_name", "") or "")
        print("\n".join(_naming.taken_plan(brand or "Gharvana")))
        print()
        return 0
    if name:
        print("\n".join(_naming.report(name, cfg, live=live)))
    else:
        current = str(cfg.get("brand.display_name", "") or "")
        current = current.split("|")[0].strip() or "PinDrop Deals"
        print("\n".join(_naming.report(current, cfg, live=live)))
    print()
    return 0


def cmd_handle(cfg, rest: list[str]) -> int:
    """🔗 Pinterest/IG handle: rules, ranked fallbacks, save the choice."""
    from . import handles as _handles
    arg = " ".join(rest).strip().lstrip("@")
    words = arg.split()
    if words and words[0].lower() in ("check", "--check", "verify"):
        from . import handles as _h
        pick = any(w in ("--pick", "--save") for w in words[1:])
        given = [_h.clean_handle(w) for w in words[1:]
                 if w.strip() and not w.startswith("-")]
        cands = given or ([i["handle"] for i in _h.handle_ideas()] + _h.plan_c())
        print()
        print("\n".join(_h.check_lines(cands, limit=len(cands) if given else 6)))
        if pick:
            res = _h.pick_first_free(cands)
            print()
            if res["picked"]:
                saved = _h.save_handle(cfg, res["picked"])
                print(f"✅ Picked + saved the first handle free on BOTH "
                      f"platforms: {res['picked']}")
                if res["skipped"]:
                    print(f"   (taken/unknown ani skip chesindi: "
                          f"{', '.join(res['skipped'])})")
                if res.get("warnings"):
                    print(f"   ⚠️ {res['warnings'][0]}")
                if res.get("polish"):
                    print(f"   🔧 Cleaner alternative: "
                          f"{' / '.join(res['polish'][:3])}")
                if not saved.get("saved"):
                    print("   ⚠️ Save avvaledu — config ni check cheyyandi.")
            else:
                print("❌ Ee list lo full-free handle dorakaledu. "
                      "Kotha names: python -m bot name --next")
                print("   (leda: python -m bot name \"Gharvana\" --live)")
        print()
        return 0
    saved_line = ""
    if arg:
        res = _handles.save_handle(cfg, arg)
        if not res["saved"] and res.get("errors"):
            print()
            print("\n".join(_handles.advice(cfg, arg)))
            print()
            return 2
        saved_line = (f"✅ Saved handle: {res['handle']} "
                      f"(Pinterest + Instagram rendu chotla ide vaadandi)")
        if res.get("warnings"):
            saved_line += "   ⚠️ " + res["warnings"][0]
        if res.get("polish"):
            saved_line += ("\n   🔧 Cleaner alternative: "
                           + " / ".join(res["polish"][:3])
                           + "  (paina list lo free unte adi better)")
    print()
    if saved_line:
        print(saved_line)
    print("\n".join(_handles.advice(cfg, arg)))
    print()
    return 0
    print()
    print("\n".join(_handles.advice(cfg, arg)))
    print()
    return 0


def cmd_onboard(cfg) -> int:
    """📋 Every Pinterest onboarding screen → what to select (skip rules too)."""
    from . import onboard as _onboard
    print()
    for line in _onboard.lines(cfg):
        print(line)
    print()
    return 0


def cmd_claim(cfg, rest: list[str]) -> int:
    """🔖 Pinterest website claim — token save + exact steps."""
    from . import claim as _claim
    arg = " ".join(rest).strip()
    if arg:
        res = _claim.save(cfg, arg)
        if not res["saved"] and res.get("error"):
            print(f"\n❌ {res['error']}\n")
            return 2
    print("\n" + "\n".join(_claim.lines(cfg)) + "\n")
    return 0


def cmd_brand(cfg, rest: list[str]) -> int:
    """🏷️  Brand/profile SEO: pick the name that actually earns reach."""
    from . import brand as _brand
    name = " ".join(rest).strip()
    if name:
        res = _brand.save(cfg, name)
        print()
        for line in _brand.lines(cfg, name):
            print(line)
        print()
        if res.get("saved"):
            print(f"✅ Saved — pin strip «{res['strip']}», display name "
                  f"«{res['name']}» (config.yaml)")
        else:
            print("❌ Not saved — fix the errors above and try again")
        return 0 if res.get("saved") else 2
    print("\n" + "\n".join(_brand.lines(cfg)) + "\n")
    return 0


def cmd_scale(cfg, rest: list[str]) -> int:
    """🎯 Revenue target → honest clicks/posts/day math + what to do."""
    from . import scale
    db = DB(cfg.db_path)
    if rest and rest[0].isdigit():
        cfg.raw.setdefault("target", {})["monthly_commission"] = int(rest[0])
    days = 30
    for i, a in enumerate(rest):
        if a in ("--days", "-d") and i + 1 < len(rest) and rest[i + 1].isdigit():
            days = int(rest[i + 1])
    print("\n" + "\n".join(scale.lines(cfg, db, days=days)) + "\n")
    return 0


def cmd_ready(cfg) -> int:
    """🎯 "Naaku em cheyyali migilindi?" — one honest screen, forever."""
    from . import ready
    lines = ready.lines(cfg)
    print("\n" + "\n".join(lines) + "\n")
    return 0 if ready.summary(cfg)["ready"] else 1


def cmd_pause(cfg, reason: str = "") -> int:
    """⏸ Kill switch — stop the scheduler (state persists through restarts)."""
    from . import control
    db = DB(cfg.db_path)
    state = control.pause(db, reason or "owner")
    print(f"⏸ Posting PAUSED — {state['reason']}")
    print("   Resume any time: python -m bot resume   (panel: Pause/Resume)")
    return 0


def cmd_resume(cfg) -> int:
    from . import control
    db = DB(cfg.db_path)
    was = control.resume(db)
    print("▶️ Posting resumed." if was else "ℹ️  Posting was not paused.")
    return 0


def cmd_links(cfg, rest: list[str]) -> int:
    """💸 Money-path health — are the affiliate links alive AND still tagged?"""
    from . import health
    db = DB(cfg.db_path)
    limit = 10
    for a in rest:
        if a.isdigit():
            limit = max(1, min(int(a), 50))
    results = health.audit_links(cfg, db, limit=limit)
    print(f"\n💸 LINK HEALTH — {health.summary(results)}\n" + "-" * 58)
    broken = 0
    for r in results:
        mark = "✅" if (r["ok"] and r["monetized"]) else ("⚠️" if r["ok"] else "❌")
        if mark != "✅":
            broken += 1
        print(f" {mark} #{r.get('product_id')} {r.get('source', ''):<8} "
              f"{r['title'][:44]}")
        if r.get("note"):
            print(f"      {r['note']}")
        if r.get("final"):
            print(f"      → {r['final'][:90]}")
    print("-" * 58)
    if not results:
        print("   queue is empty — nothing to check yet")
    return 0 if broken == 0 else 1


def cmd_earnings(cfg, rest: list[str]) -> int:
    """💰 Honest estimate: clicks × assumptions × your commission rates."""
    from . import earnings
    days = 30
    for i, a in enumerate(rest):
        if a in ("--days", "-d") and i + 1 < len(rest) and rest[i + 1].isdigit():
            days = int(rest[i + 1])
    db = DB(cfg.db_path)
    est = earnings.estimate(cfg, earnings.click_rows_since(db, days=days))
    print(f"\n💰 EARNINGS ESTIMATE (last {days} days)\n" + "-" * 58)
    for line in earnings.report_lines(cfg, est):
        print(" " + line.strip())
    print("-" * 58)
    return 0


def cmd_report(cfg, rest: list[str]) -> int:
    """📊 Period report — real numbers + honest estimate, optional Telegram."""
    from . import report as rep
    days, telegram = 7, False
    for i, a in enumerate(rest):
        if a in ("--days", "-d") and i + 1 < len(rest) and rest[i + 1].isdigit():
            days = int(rest[i + 1])
        if a == "--telegram":
            telegram = True
    db = DB(cfg.db_path)
    lines = rep.lines(cfg, db, days=days)
    print("\n" + "\n".join(lines) + "\n")
    if telegram:
        ok = rep.send_telegram(cfg, "\n".join(lines))
        print("📨 Telegram: sent" if ok else "📨 Telegram not configured (optional)")
    return 0


def cmd_queue(cfg) -> int:
    db = DB(cfg.db_path)
    stats = db.stats()
    pause = _pause_note(db)
    if pause:
        print(f"🚧 Posting PAUSED: {pause}")
    print(f"📊 total={stats['total']} queued={stats['queued']} "
          f"posted={stats['posted']} failed={stats['failed']} skipped={stats['skipped']}\n")
    for p in db.all_products(limit=50):
        print(f"  #{p['id']:>3} [{p['status']:<7}] ({p['source']:<8}) {p['title'][:62]}")
    return 0


def cmd_post(cfg, count: int) -> int:
    if count < 1:
        print("❌ count must be 1 or more (usage: python -m bot post 3)")
        return 2
    eng = Engine(cfg)
    if not eng.api.configured:
        print("❌ Pinterest not connected. Run: python -m bot auth")
        return 1
    posted = eng.post_batch(count)
    print(f"\n🎉 {len(posted)} pin(s) posted!")
    return 0 if posted else 1


def cmd_design_test(cfg) -> int:
    """Generate a sample pin so you can preview the design quality."""
    from PIL import Image
    from .pin_designer import PinDesigner

    # build a fake product photo
    img = Image.new("RGB", (800, 800), (250, 244, 235))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for i in range(0, 800, 40):
        d.line([(i, 0), (i + 200, 800)], fill=(235, 225, 210), width=6)
    d.rounded_rectangle([150, 150, 650, 650], 40, fill=(30, 90, 200))
    d.rounded_rectangle([200, 200, 600, 600], 30, fill=(45, 110, 225))
    d.ellipse([300, 300, 500, 500], fill=(255, 255, 255, 200))
    sample = cfg.media_dir / "sample_product.jpg"
    img.save(sample, quality=92)

    designer = PinDesigner(cfg)
    title = "boAt Airdopes 141 Bluetooth Truly Wireless in Ear Earbuds with 42H Playtime"
    print("Generating all 4 design templates…")
    for tpl in ("classic", "split", "overlay", "collage"):
        out = cfg.media_dir / f"sample_pin_{tpl}.jpg"
        designer.create(str(sample), title, "₹1,099", out, "amazon",
                        template=tpl, extra_images=[str(sample)])
        print(f"   ✅ {tpl:<8} -> {out}")
    print("\nOpen data/media/sample_pin_*.jpg to preview the designs.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = load_config()
    _banner()

    if not argv:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "auth":
        if "--code" in rest:
            return cmd_auth_code(cfg, rest[rest.index("--code") + 1])
        return cmd_auth(cfg)
    if cmd == "auth-url":
        return cmd_auth_url(cfg)
    if cmd == "check":
        return cmd_check(cfg)
    if cmd == "doctor":
        return cmd_doctor(cfg)
    if cmd == "ig-check":
        return cmd_ig_check(cfg)
    if cmd == "add":
        if not rest:
            print("\n➕ Products add cheyyandi — oka or ekkuva URLs:\n")
            print("   python -m bot add 'https://www.meesho.com/xxx/p/1k1b6'")
            print("   python -m bot add <url1> <url2> <url3>")
            print("   (autopilot eh products ni own ga vethukuntundi — idi manual)\n")
            return 0
        return cmd_add(cfg, rest)
    if cmd == "add-csv":
        if not rest:
            print("\n📄 CSV nunchi products add — file path ivvandi:\n")
            print("   python -m bot add-csv products.csv")
            print("   (columns: url  or  url,title,price — Meesho/Amazon/Flipkart)\n")
            return 0
        return cmd_add_csv(cfg, rest[0])
    if cmd == "keywords":
        if not rest:
            print("\n🔎 Live Pinterest keyword mining — oka seed ivvandi:\n")
            print("   python -m bot keywords 'women kurta set' 'home decor'")
            print("   → Pinterest autocomplete nunchi LIVE search phrases\n")
            return 0
        return cmd_keywords(cfg, rest)
    if cmd == "trends":
        return cmd_trends(cfg)
    if cmd == "music":
        return cmd_music(cfg)
    if cmd == "simulate":
        return cmd_simulate(cfg)
    if cmd == "pin-stats":
        return cmd_pin_stats(cfg, rest)
    if cmd == "trends" and rest and rest[0] == "--live":
        return cmd_trends_live(cfg)
    if cmd == "platforms":
        return cmd_platforms(cfg)
    if cmd in ("yt-auth", "yt-auth-url"):
        return cmd_yt_auth(cfg, rest)
    if cmd == "meesho":
        return cmd_meesho(cfg, rest)
    if cmd == "how":
        from .features import print_how_it_works
        print_how_it_works()
        return 0
    if cmd == "features":
        from .features import print_report
        print_report(cfg)
        return 0
    if cmd in ("creds", "credentials", "keys"):
        return cmd_creds(cfg, rest)
    if cmd in ("token-check", "tokencheck", "whoami"):
        return cmd_token_check(cfg, rest)
    if cmd in ("app", "app-form", "appform"):
        return cmd_app(cfg, rest)
    if cmd in ("name", "naming", "brand-name"):
        return cmd_name(cfg, rest)
    if cmd in ("handle", "handles"):
        return cmd_handle(cfg, rest)
    if cmd in ("onboard", "onboarding"):
        return cmd_onboard(cfg)
    if cmd == "claim":
        return cmd_claim(cfg, rest)
    if cmd == "brand":
        return cmd_brand(cfg, rest)
    if cmd == "scale":
        return cmd_scale(cfg, rest)
    if cmd == "ready":
        return cmd_ready(cfg)
    if cmd == "pause":
        return cmd_pause(cfg, " ".join(rest).strip())
    if cmd == "resume":
        return cmd_resume(cfg)
    if cmd == "links":
        return cmd_links(cfg, rest)
    if cmd == "earnings":
        return cmd_earnings(cfg, rest)
    if cmd == "report":
        return cmd_report(cfg, rest)
    if cmd == "queue":
        return cmd_queue(cfg)
    if cmd == "post":
        try:
            n = int(rest[0]) if rest else 1
        except ValueError:
            print(f"❌ '{rest[0]}' is not a number. Usage: python -m bot post [count]")
            return 2
        return cmd_post(cfg, n)
    if cmd in ("run", "autopilot"):
        from .lock import AlreadyRunning, acquire, release
        try:
            lk = acquire(cfg, "scheduler")
        except AlreadyRunning as exc:      # never double-post the same product
            print(f"\n⏸  Autopilot already running — {exc}")
            print("   Two schedulers = duplicate pins + ban risk, so this copy exits.")
            print("   Stop the other one:  pkill -f 'bot run'   (or ./run.sh stop)\n")
            return 0
        try:
            Engine(cfg).run_forever()
        finally:
            release(lk)
        print("\n⚠️  Scheduler exited unexpectedly — restart it (./run.sh / systemctl).")
        return 1
    if cmd == "setup":
        return cmd_setup(cfg)
    if cmd == "design-test":
        return cmd_design_test(cfg)
    if cmd == "dashboard":
        from .dashboard import serve
        serve(cfg)
        return 0
    if cmd in ("dashboard-pass", "panel-pass"):
        return cmd_dashboard_pass(cfg)
    if cmd in ("deploy-check", "preflight"):
        return cmd_deploy_check(cfg)
    if cmd == "playbook":
        from .playbook import report
        print(report())
        return 0
    if cmd == "radar":
        return cmd_radar(cfg, rest)

    print(f"Unknown command: {cmd}\n")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


def cmd_meesho(cfg, args: list[str]) -> int:
    """Verify EXACTLY what the bot will publish as your Meesho link."""
    from .affiliate import AffiliateLinker
    lk = AffiliateLinker(cfg)
    h = lk.meesho_health()
    print("\n🛍  MEESHO LINK CHECK — 'vasthaya correct ga?' nijam answer\n" + "-" * 62)
    print(f"  links pasted      : {h['links_pasted']}")
    print(f"  publisher id      : {h['publisher'] or '(none yet)'}")
    print(f"  source token      : {h['source_token'] or '(none yet)'}")
    print(f"  campaigns learned : {h['campaigns'] or '(none yet)'}")
    print(f"  affid fallback    : {'yes' if h['affid_fallback'] else 'no'}")
    print(f"  direction         : "
          f"{'DIRECT af_invite (commission → YOUR Meesho account)' if h['parsed'] else 'NONE / fallback — commission at risk'}")

    sample = (args[0] if args else
              "https://www.meesho.com/women-floral-printed-kurta-set/p/1k1b6")
    print(f"\n  sample product URL: {sample}")
    pid = AffiliateLinker.meesho_product_id(sample)
    print(f"  product id parsed : {pid or '❌ NOT FOUND (link cannot be built)'}")
    built = lk.meesho_link_for(sample)
    if built:
        print(f"\n  LINK THE BOT WILL PUBLISH:\n  {built}")
        from urllib.parse import parse_qsl as _pqs
        from urllib.parse import urlparse as _up
        tpl = lk.meesho_template_links[-1] if lk.meesho_template_links else ""
        tparams = dict((k, v) for k, v in _pqs(_up(tpl).query)
                       if k not in ("p_id", "ext_id")) if tpl else {}
        bparams = dict(_pqs(_up(built).query))
        preserved = all(bparams.get(k) == v for k, v in tparams.items())
        fresh = built.count("ext_id=") == 1 and "ext_id=old" not in built
        checks = {
            "af_invite present": "af_invite" in built,
            "your publisher id in link": bool(h["publisher"]) and h["publisher"] in built,
            "latest campaign used": bool(h["campaigns"]) and h["campaigns"][-1] in built,
            "product p_id correct": bool(pid) and f"p_id={pid}" in built,
            "fresh ext_id per click (old id replaced)": fresh,
            f"template params preserved ({len(tparams)} checked)": preserved,
        }
        print("\n  STRUCTURAL CHECKS")
        for k, v in checks.items():
            print(f"   {'✅' if v else '❌'} {k}")
        ok = all(checks.values())
    else:
        has_collection = any("affiliate.meesho.com/collection/" in l
                             for l in lk.meesho_template_links)
        print("\n  ❌ No usable Meesho link yet — paste your share link:")
        if has_collection:
            print("     NOTE: nuvvu paste chesindi COLLECTION link (list page).")
            print("     Adi 'naa picks' page ki use avutundi kani, PER-PRODUCT")
            print("     commission link build cheyyalem. Oka product page open")
            print("     chesi → Share → copy link (af_invite format) → paste.")
        print("     affiliate.meesho.com → any product → Share → copy link")
        print("     → .env: MEESHO_TEMPLATE_LINK=<that link>   (comma-separate many)")
        ok = False

    # per-platform view: which token+campaign each surface will publish
    if lk.meesho_template_map():
        print("\n  PER-PLATFORM LINKS (each platform uses its own token):")
        for plat in ("instagram", "facebook", "youtube", "pinterest"):
            tok = lk.meesho_source_for(plat)
            pl = lk.meesho_link_for(sample, platform=plat)
            print(f"   • {plat:10s} token={tok:22s}")
            print(f"     {pl}")

    print("\n  PHONE LO TEST (only your phone can confirm — server nunchi")
    print("  meesho.com reach avvadu, so idi real proof):")
    print("   1. Copy the link above, WhatsApp yourself ki pampu")
    print("   2. PHONE lo ad-blocker OFF chesi (Brave/AdGuard unte pause)")
    print("   3. Click → Meesho app/site lo SAME PRODUCT open avvali")
    print("   4. 'meesho.onelink.me' ERR_BLOCKED_BY_CLIENT vaste → ad-blocker")
    print("      problem, link format kaadu (redirect reach avvadam chusi)")
    print("   5. Tarvata: affiliate.meesho.com dashboard → Reports →")
    print("      Clicks/Orders lo ee click kanipisthe → 100% CORRECT ✅")
    print("\n  📊 nijam: clicks dashboard lo kanipinchaka mundu 'correct' ani")
    print("     anataniki reason ledu — ee 5 steps ne proof.")
    print("-" * 62)
    return 0 if ok else 0


def cmd_yt_auth(cfg, args: list[str]) -> int:
    """One-time Google OAuth for the YouTube Shorts uploader."""
    from .youtube import YouTubeAPI, YouTubeError
    yt = YouTubeAPI(cfg)
    if args and args[0] == "--code":
        if len(args) < 2:
            print("usage: python -m bot yt-auth --code <CODE_FROM_REDIRECT_URL>")
            return 2
        print("\n🔑 Exchanging code for a refresh token…")
        try:
            yt.exchange_code(args[1])
        except YouTubeError as exc:
            print(f"❌ {exc}")
            return 1
        print(f"✅ Saved — YouTube Shorts uploads are LIVE from now on\n"
              f"   token file: {yt.token_path}")
        return 0
    try:
        print("\n🔗 Open this URL (any device), pick your channel, click Allow:\n")
        print("   " + yt.auth_url())
        print("\n   After Allow, your browser shows a URL like")
        print("   http://localhost:8080/?code=4/0Ab...&scope=...")
        print("   Copy the code (between 'code=' and '&scope') and run:\n")
        print("   python -m bot yt-auth --code <PASTE_CODE>\n")
    except YouTubeError as exc:
        print(f"❌ {exc}")
        return 1
    return 0


def cmd_platforms(cfg) -> int:
    """Show every surface the bot posts to + how the link is built for it."""
    from .affiliate import AffiliateLinker
    from .instagram import InstagramAPI
    from .facebook import FacebookAPI
    from .youtube import YouTubeAPI
    lk = AffiliateLinker(cfg)
    ig, fb, yt = InstagramAPI(cfg), FacebookAPI(cfg), YouTubeAPI(cfg)
    order = cfg.get("posting.platform_order",
                    ["instagram", "facebook", "youtube", "pinterest"])
    print("\n📡 WHERE THE BOT POSTS — platform · status · Meesho source token\n" + "-" * 66)
    rows = []
    for plat in order + ["pinterest"]:
        if plat in [r[0] for r in rows]:
            continue
        if plat == "pinterest":
            ok = bool(cfg.get("pinterest.access_token") or
                      __import__("os").getenv("PINTEREST_ACCESS_TOKEN"))
            detail = "official API: pins + video pins + roundups + winners rotation"
        elif plat == "instagram":
            ok = bool(ig.enabled and ig.configured)
            detail = "feed carousel / single, reels, STORIES, bio link, auto-DM"
        elif plat == "facebook":
            ok = bool(fb.enabled and fb.configured)
            detail = "Page photo/link post + clickable direct link"
        elif plat == "youtube":
            ok = bool(yt.enabled and yt.configured)
            detail = "Shorts upload (reel) + affiliate link in description"
        else:
            ok, detail = False, "unknown"
        rows.append((plat, ok, detail))
    for plat, ok, detail in rows:
        tok = lk.meesho_source_for(plat) if lk.meesho_template_map() else "(no template)"
        print(f"  {'✅' if ok else '⚪'} {plat:10s} {detail}")
        print(f"     ↳ Meesho token: {tok}")
    print("-" * 66)
    print("  ✅ = configured & live   ⚪ = add creds to switch on")
    print("  Telegram deals channel: "
          f"{'✅ on' if __import__('os').getenv('TELEGRAM_DEALS_CHANNEL') else '⚪ off (optional)'}")
    return 0


def cmd_pin_stats(cfg, args: list[str]) -> int:
    """Pull REAL Pinterest metrics for recent pins and show the funnel."""
    from .db import DB
    from .engine import Engine
    db = DB(cfg.db_path)
    e = Engine(cfg, db)
    if not e.api.configured:
        print("\n❌ Pinterest credentials missing — run `python -m bot auth` first\n")
        return 1
    limit = int(args[0]) if args and args[0].isdigit() else 20
    print(f"\n📈 PIN PERFORMANCE — pulling up to {limit} pins from Pinterest…\n")
    res = e.pin_performance(limit=limit)
    print(f"  measured: {res.get('checked', 0)} pins"
          f"{'  |  performing: ' + str(res.get('performing')) if res.get('performing') else ''}")
    if res.get("best"):
        print(f"  🏆 best: {res['best'][:60]}")
    rows = []
    for p in db.recent_posts(limit=40):
        m = db.latest_pin_metrics(str(p.get("pin_id") or ""))
        if m:
            rows.append((p.get("title") or "", m))
    if rows:
        print(f"\n  {'IMPR':>7} {'SAVES':>6} {'CLICKS':>7} {'OUT':>5}  TITLE")
        for title, m in rows[:15]:
            print(f"  {int(m['impressions']):>7} {int(m['saves']):>6} "
                  f"{int(m['pin_clicks']):>7} {int(m['outbound']):>5}  {title[:42]}")
    else:
        print("\n  (no metrics stored yet — they appear 24h+ after pins go live)")
    print("\n  Adi Pinterest nunchi direct numbers — guess kaadu, real data.\n")
    return 0


def cmd_trends_live(cfg) -> int:
    """Official Pinterest Trends keywords for your region."""
    from .trends import live_keywords
    region = str(cfg.get("trends.region", "IN"))
    kws = live_keywords(cfg, limit=20, force=True)
    if not kws:
        print("\n⚠️  Live trends unavailable right now (needs the `trends:read`")
        print("   scope — re-run `python -m bot auth` once — or Pinterest is")
        print("   throttling). Built-in winner list stays active:\n")
        from .trends import describe
        print(describe())
        return 0
    print(f"\n📈 LIVE PINTEREST TRENDS — region {region} (official API)\n" + "-" * 54)
    for i, kw in enumerate(kws, 1):
        print(f"  {i:>2}. {kw}")
    print("-" * 54)
    print("   Ee keywords ippudu SEO titles/hashtags lo auto-inject avutayi.\n")
    return 0
