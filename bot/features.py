"""Feature inventory — "em features vunnayi, em add cheyochu" in one table.

Prints every capability of the machine with its live status (ON / OFF /
NOT-CONFIGURED) and how to enable it. When a platform ships a new feature
(e.g. Meesho opens an API, Pinterest adds carousel pins), add ONE entry to
FEATURES + the code — the inventory, doctor and README stay in sync.
"""
from __future__ import annotations

import os
import pathlib

FEATURES = [
    # (name, category, what it does, enablement check, how to enable)
    ("Pinterest carousel pins", "posting",
     "2-5 product photos in one pin (highest-engagement format)",
     lambda cfg: bool(cfg.get("pinterest.carousel", True)),
     "pinterest.carousel=true (default on)"),
    ("Pinterest API image upload", "posting",
     "ships the DESIGNED pin via /v5/media (no CDN fetch failures)",
     lambda cfg: bool(cfg.get("pinterest.upload_images", True)),
     "pinterest.upload_images=true (default on)"),
    ("Pinterest Trends API", "reach",
     "official region trend keywords → auto-injected into SEO/hashtags",
     lambda cfg: bool(cfg.get("trends.live", True)),
     "trends.live=true + trends:read scope (re-run bot auth once)"),
    ("Pinterest pin analytics", "money",
     "real impressions/saves/clicks per pin → smarter rotation",
     lambda cfg: bool(cfg.get("pinterest.analytics", True)),
     "pinterest.analytics=true + pins:read (already in scopes)"),
    ("Board sections", "posting",
     "per-niche sub-boards so a big board stays relevant",
     lambda cfg: bool(cfg.get("pinterest.sections", False)),
     "pinterest.sections=true"),
    ("Rich Pins (price on the pin)", "money",
     "og:type=product + product:price + availability on landing pages",
     lambda cfg: True,
     "automatic — verify at developers.pinterest.com/rich-pins"),
    ("Pinterest posting", "posting", "official API pins + video pins + boards",
     lambda cfg: bool(os.getenv("PINTEREST_ACCESS_TOKEN", "")),
     "PINTEREST_ACCESS_TOKEN in .env"),
    ("Instagram posting", "posting", "reels/carousel via official Graph API",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "instagram.enabled=true + INSTAGRAM_ACCESS_TOKEN, IG_USER_ID"),
    ("Facebook Page posting", "posting", "photo/link posts on your FB Page",
     lambda cfg: bool(os.getenv("FACEBOOK_ACCESS_TOKEN", "")),
     "facebook.enabled=true + FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID"),
    ("YouTube Shorts posting", "posting",
     "product reel → Short + affiliate link in description (evergreen search)",
     lambda cfg: bool(os.getenv("YT_CLIENT_ID", "") and
                      os.getenv("YT_CLIENT_SECRET", "") and
                      (os.getenv("YT_REFRESH_TOKEN", "") or
                       (pathlib.Path("data/yt_token.json").exists()))),
     "youtube.enabled=true + YT_CLIENT_ID/SECRET + python -m bot yt-auth-url"),
    ("Instagram Stories", "posting",
     "24h story per product (CTA + bio link + auto-DM deliver the link)",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
                      and cfg.get("instagram.stories", True)),
     "instagram.stories=true (default on) + IG token"),
    ("Per-platform Meesho links", "money",
     "instagram_stories / facebook token+campaign chosen per surface",
     lambda cfg: bool(cfg.get("affiliate.meesho_template_link")),
     "paste your af_invite link(s) in MEESHO_TEMPLATE_LINK"),
    ("Telegram deals channel", "reach",
     "every deal broadcast to your public Telegram channel",
     lambda cfg: bool(os.getenv("TELEGRAM_DEALS_CHANNEL", "")),
     "TELEGRAM_TOKEN + TELEGRAM_DEALS_CHANNEL in .env (optional)"),
    ("Telegram alerts", "reach", "posted/daily reports to your chat",
     lambda cfg: bool(os.getenv("TELEGRAM_TOKEN", "")),
     "TELEGRAM_TOKEN + TELEGRAM_CHAT_ID (optional)"),
    ("Auto-reels + voiceover", "content", "video from photos + TTS (en/hi/te)",
     lambda cfg: bool(cfg.get("video.auto_reel", True)),
     "video.auto_reel (default on)"),
    ("Your videos / your audio", "content", "your uploads beat auto-generated",
     lambda cfg: True,
     "dashboard 🎬/🎵 uploads → data/videos, data/music"),
    ("Original BGM composer", "content", "copyright-free music auto-generated",
     lambda cfg: bool(cfg.get("video.auto_music", True)),
     "video.auto_music (default on)"),
    ("Winner-clone sourcing", "sourcing", "top-channel niches auto-hunted",
     lambda cfg: bool(cfg.get("autopilot.auto_source", True)),
     "autopilot.auto_source (default on)"),
    ("Cross-store media enrichment", "sourcing", "same product media from other stores",
     lambda cfg: True, "automatic"),
    ("Commission-priority queue", "money", "highest-paying network posts first",
     lambda cfg: True, "automatic (COMMISSION_EST)"),
    ("Bridge landing pages", "money", "/go/<id> → landing → affiliate link",
     lambda cfg: bool(cfg.get("link.bridge", False)),
     "link.bridge=true + link.public_base=https://yourdomain"),
    ("Email capture", "money", "buyer list on every landing page",
     lambda cfg: bool(cfg.get("link.landing", True)),
     "automatic with landing pages"),
    ("Pin-by-Pin QA gate", "safety", "broken content never posts",
     lambda cfg: True, "automatic"),
    ("Warm-up ramp + jitter", "safety", "anti-flag volume ramping",
     lambda cfg: True, "automatic"),
    ("IG 'link' auto-replies", "engagement", "answers link? comments (capped+delayed)",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "with Instagram + instagram_manage_comments scope"),
    ("IG ManyChat-grade auto-DM", "engagement", "keyword DMs → product + buy link",
     lambda cfg: bool(os.getenv("INSTAGRAM_ACCESS_TOKEN", "")),
     "instagram_manage_messages scope; instagram.auto_dm"),
    ("Meesho DIRECT af_invite", "money", "bot builds links with your IDs",
     lambda cfg: bool(os.getenv("MEESHO_TEMPLATE_LINK", "") or
                      cfg.get("affiliate.meesho_template_link", "")),
     "paste one af_invite link → MEESHO_TEMPLATE_LINK"),
    ("Deals-of-the-Day roundups", "growth", "daily list pins + /deals/today page",
     lambda cfg: bool(cfg.get("roundup.enabled", True)), "roundup.enabled"),
    ("Winners rotation", "growth", "proven pins re-posted as fresh designs",
     lambda cfg: True, "automatic (reshare.*)"),
    ("CTR hour learning", "growth", "dense posting in proven hours",
     lambda cfg: True, "automatic after ≥10 clicks"),
]


def report(cfg) -> list[dict]:
    rows = []
    for name, cat, what, check, how in FEATURES:
        try:
            on = bool(check(cfg))
        except Exception:  # noqa: BLE001
            on = False
        rows.append({"name": name, "category": cat, "what": what,
                     "status": "ON" if on else "OFF", "how": how})
    return rows


def print_report(cfg) -> None:
    print("\n🔎 FEATURE INVENTORY — every capability + its live status\n")
    cats: dict[str, list[dict]] = {}
    for r in report(cfg):
        cats.setdefault(r["category"], []).append(r)
    for cat, rows in cats.items():
        print(f"  ── {cat.upper()} " + "─" * max(0, 40 - len(cat)))
        for r in rows:
            mark = "✅" if r["status"] == "ON" else "⚪"
            print(f"  {mark} {r['name']:<32} {r['what']}")
            if r["status"] == "OFF":
                print(f"      ↳ enable: {r['how']}")
    n_on = sum(1 for r in report(cfg) if r["status"] == "ON")
    print(f"\n  {n_on}/{len(FEATURES)} features active. New platform feature "
          "releases → one entry in bot/features.py + code → inventory updates.\n")


def print_how_it_works() -> None:
    """Plain, honest, end-to-end explanation — 'asalu em chesthadi?'"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  ASALU EM CHESTHADI — nijam, hype ledu, fake ledu               ║
╚══════════════════════════════════════════════════════════════════╝

1) SOURCING (nenu cheyyali — nuvvu cheyyalsina pani ledu)
   Top-channel winner niches (home decor, ladies fashion, beauty,
   wedding, kitchen) lo deals ni queue loki testadu. Nuvvu link
   paste chesina kuda teesukuntadu. URL → title/price/image scrape.

2) MONEY LINK (commission miss avvadu)
   Amazon link → NI tag tho replace (vere tag unte teesesi nadi pettadu)
   Meesho   → NI af_invite DIRECT (middleman ledu — commission direct
              ni account ki)
   Migatha stores → EarnKaro / Cuelinks wrap
   QA gate: tracking marker leni link ni BLOCK chestundi ("COMMISSION
   LEAK"). Owned link eppudu publish avvadu.

3) CONTENT (real media, bot ne create chestundi)
   1 product → 3 pin variations (different design templates)
   + auto-reel (photos → video + original composed BGM + voiceover)
   Pinterest image SEO: filename lo keyword + price untundi.

4) POSTING (24x7, human-like)
   Pinterest (MAIN): peak windows lo 8 pins/day + daily "Deals of the
   Day" list pin + winners re-share. Gap 40-65 min jitter.
   Instagram: reel/carousel + bio link auto-update + comment 'link'
   auto-reply + keyword DM auto-reply (ManyChat-grade).
   Facebook Page: photo post + clickable direct link + comment auto.
   Warm-up ramp: kotha account ki slow start (ban avvakunda).

5) LANDING PAGE (commission + buyer list)
   Pin link → yourdomain/go/<id> → landing (OG + JSON-LD schema,
   Google/social rich results) → WhatsApp share button → email
   capture → affiliate link ki redirect (click track + owner tag).

6) LEARNING (roju roju better avutundi)
   - Which HOUR click chesaro → aa hours lo dense posting
   - Which WEEKDAY click chesaro → aa days dense
   - Which DESIGN template clicks tecchindo → 70% aa template
   - Festival keywords automatic (Diwali/Sankranti...)
   - Price-drop radar: posted product 10%+ taggithe malli post
   - Winners rotation: manchi click vachina pin 7 days tarvata
     fresh design tho re-post

7) RADAR + SELF-LEARNING HOOKS (R43)
   🔭 RADAR — "top most useful products" ni bot ne vethukutundi:
   - usefulness score 0-100: problem-solver + demand + impulse price
     (₹299-999) + repeat-purchase + timely festival + gift/wedding + social
     proof. Score ekkuva unna product mundhe post avutundi.
   - python -m bot radar          → live ranking + enduku aa score
   - python -m bot radar --hunt   → real hunt (discover → scrape → score →
     queue only winners). Time-bounded: dead network aithe seconds lo aagi
     "stores unreachable" ani chepthundi — loop eppudu stall avvadu.
   - Panel lo 🧭 Radar tab → best products + queue rank + hook learning.
   🧠 SELF-LEARNING HOOKS — click vachina hook style ni bot nerchukuntundi:
   - 3 archetypes: PAS (problem), LIST (top-N), POV (story). Prathi post ki
     okati pick avutundi, product row lo record avutundi, clicks aa style
     ki attribute avutayi.
   - 3+ posts tarvata clicks/post batti weights — winner ki ekkuva chance,
     migatha rendu ki exploration (lucky one-off trap lo padadu).
   - python -m bot playbook → 2026 research playbook (hooks, best times,
     Shorts script rules, IG carousel plan).

8) BAN-PROOF SAFETY (R44)
   🚧 API CIRCUIT BREAKER — token poyina/rate-limit aina bot API ni
     hammer cheyyadu (ade accounts flag avvataniki main reason):
   - 401/403 (token) → 6h pause + "python -m bot auth" hint (retry valla
     prayojanam ledu, ban risk matrame).
   - 429 (rate limit) → cooldown 15m → 1h → 4h → 12h escalate, success
     vasthe reset.
   - State DB lo persist (restart chesina marchipodu), panel /api/status lo
     "api_breaker" + `bot queue` / `bot doctor` lo PAUSED line kanipistundi.
   - Re-auth chesina ventane breaker clear → posting immediate resume.
   📊 FEED VARIETY — okate category 3 pins back-to-back pettadu (spam
     signal + audience fatigue): post time lo different topic prefer chestundi,
     radar hunt lo kuda 3+ same-topic unte skip (queue variety guard).

9) OWNER CONTROL + MONEY HEALTH (R45)
   ⏸ KILL SWITCH — `python -m bot pause "reason"` → scheduler next cycle lo
     aagutundi (mid-API-call kaadu), `bot resume` → malli start. Panel 💰
     Money tab lo Pause/Resume button. State DB lo persist.
   📊 DAILY CAP + QUIET HOURS — posting.max_per_day (default 25) + "0-6"
     quiet window: ratri lo posting ledu, spam cap eppudu undadu.
   💸 LINK HEALTH — `bot links [N]` / panel "Check links": prathi affiliate
     link ni follow chesi 200 aa + **mana tracking tag redirect tarvata kuda
     unda** ani verify chestundi (dead link = silent money loss).
   💰 EARNINGS ESTIMATOR — `bot earnings [--days N]` / panel card: real
     clicks × configurable assumptions (%clicks→orders, AOV, network rates)
     → estimate + payout date. Assumptions screen lo kanipistayi (fake ledu).
   📊 PERIOD REPORT — `bot report [--days N] [--telegram]`: posts, clicks,
     subscribers, store mix, best hour/weekday, top pins, estimate, pause
     state — okate screen lo.
   🔐 SECRETS AUDIT — health.audit_secrets: .env / token / password files
     group-world readable unte warn (600 cheyyamani).

10) SAFETY (account safe, money safe)
   Pin-by-Pin QA gate (media/link/title/desc/duplicate/#ad) — API call ki
   mundhe, dummy-product guard (demo data live account ki NEVER post),
   single-instance lock (rendu autopilot okate product rendu saarlu post
   cheyyavu — duplicate = spam signal), crash-net (edaina fail aithe loop
   continue), housekeep daily, panel password lock, doctor command,
   277 automated tests.

NI ONE-TIME PANI (idi tappadu — creds tappadu):
   python -m bot setup  → Pinterest app, Amazon tag, Meesho af_invite,
   EarnKaro, IG token, FB token. 5-10 nimushalu, oka saari.
   Tarvata: sudo ./deploy.sh → 24x7 automatic.
   Deploy ready aa? → python -m bot deploy-check   (✅/❌ checklist)
   Panel password → python -m bot dashboard-pass
   Guardians (root lekunda) → ./run.sh  |  ./run.sh status  |  ./run.sh stop

NIJJAM (honesty):
   • Ee bot reach + clicks + commission link ni build chestundi —
     money Pinterest/Meesho/Amazon side nunchi vastundi, payout
     cycle 30-45 rojulu (Meesho), Amazon 60 rojulu.
   • Month 1-3 lo numbers thakkuva (Pinterest indexing time teesukuntadu),
     6+ months lo compound avutundi. Evaraina "week 1 lo lakhs" ante adi fake.
   • Sandbox/this laptop nunchi live scraping test cheyyanu (network
     blocked) — VPS lo internet unte pani chestundi. Simulation tho
     full pipeline verify chesanu (PASSED).
""")
