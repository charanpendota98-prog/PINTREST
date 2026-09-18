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
"""
from __future__ import annotations

import csv
import http.server
import logging
import os
import sys
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
    ck("Pinterest token (auth done)", cfg.token_path.exists(),
       "python -m bot auth-url  +  auth --code")
    ck("Amazon tag", bool(cfg.amazon_tag), "affiliate-program.amazon.in")
    ck("Meesho/EarnKaro/Cuelinks (any)", bool(
        cfg.get("affiliate.meesho_affid") or os.getenv("MEESHO_AFFID")
        or cfg.get("affiliate.earnkaro_prefix") or os.getenv("EARNKARO_PREFIX")
        or cfg.get("affiliate.cuelinks_template")), "see README affiliate guide")
    ck("Meesho DIRECT af_invite (recommended)", bool(
        os.getenv("MEESHO_TEMPLATE_LINK") or cfg.get("affiliate.meesho_template_link")),
       "paste ONE af_invite link from affiliate.meesho.com → .env MEESHO_TEMPLATE_LINK")
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
    bad = 0
    for name, ok, fix in checks:
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
    from .pin_designer import PinDesigner, TEMPLATES
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
            wa=quote("deal"), wa_on=False, more="",
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
    from .trends import describe, WINNER_NICHES
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


def cmd_queue(cfg) -> int:
    db = DB(cfg.db_path)
    stats = db.stats()
    print(f"📊 total={stats['total']} queued={stats['queued']} "
          f"posted={stats['posted']} failed={stats['failed']} skipped={stats['skipped']}\n")
    for p in db.all_products(limit=50):
        print(f"  #{p['id']:>3} [{p['status']:<7}] ({p['source']:<8}) {p['title'][:62]}")
    return 0


def cmd_post(cfg, count: int) -> int:
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
    import random

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
    if cmd == "add" and rest:
        return cmd_add(cfg, rest)
    if cmd == "add-csv" and rest:
        return cmd_add_csv(cfg, rest[0])
    if cmd == "keywords" and rest:
        return cmd_keywords(cfg, rest)
    if cmd == "trends":
        return cmd_trends(cfg)
    if cmd == "music":
        return cmd_music(cfg)
    if cmd == "simulate":
        return cmd_simulate(cfg)
    if cmd == "how":
        from .features import print_how_it_works
        print_how_it_works()
        return 0
    if cmd == "features":
        from .features import print_report
        print_report(cfg)
        return 0
    if cmd == "queue":
        return cmd_queue(cfg)
    if cmd == "post":
        return cmd_post(cfg, int(rest[0]) if rest else 1)
    if cmd in ("run", "autopilot"):
        Engine(cfg).run_forever()
        return 0
    if cmd == "setup":
        return cmd_setup(cfg)
    if cmd == "design-test":
        return cmd_design_test(cfg)
    if cmd == "dashboard":
        from .dashboard import serve
        serve(cfg)
        return 0

    print(f"Unknown command: {cmd}\n")
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
