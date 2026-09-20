"""R61: the exact answers for Pinterest's "Connect app" form.

The form asks for a company website and a privacy policy URL, and the bot
already serves both (`/about`, `/privacy`, `/terms`). This module turns that into
one printable answer sheet — plus `--site <url>` to save the public base URL so
the sheet stops showing placeholders.
"""
from __future__ import annotations

import re
from pathlib import Path

APP_NAME = "Gharvanaa Deals Publisher"
COMPANY = "Gharvanaa"
ICON = "brand/app_icon_1024.png"

PURPOSE_TEXT = (
    "Internal publishing tool for our own Pinterest business account. It uses "
    "the Pinterest API only on that single account to: create boards, publish "
    "our own curated product pins on a schedule, and read our own pins and "
    "boards to avoid duplicates and report performance. It does not access "
    "other users' data, does not run ads, and is not offered to third parties."
)

USE_CASES = (
    "Pin creation & scheduling  (posting our own pins, scheduled daily)",
    "Reporting  (reading our own pins/boards to avoid duplicates + stats)",
)

REDIRECT_URI = "http://localhost:8888/callback"
SCOPES = "pins:read, pins:write, boards:read, boards:write, user_accounts:read"


def site_of(cfg) -> str:
    """Configured public site, without a trailing slash."""
    try:
        return str(cfg.get("link.public_base", "") or "").strip().rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def urls(cfg) -> tuple[str, str]:
    """(company website URL, privacy policy URL)."""
    base = site_of(cfg)
    if base:
        return f"{base}/about", f"{base}/privacy"
    return ("http://<VPS-IP>:5000/about", "http://<VPS-IP>:5000/privacy")


def save_site(cfg, url: str, path: str | Path | None = None) -> dict:
    """Persist `link.public_base` (comment-preserving), validating the shape."""
    url = str(url or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+$", url):
        return {"saved": False,
                "error": "URL 'https://yourdomain.com' la undali (http/https)."}
    from . import claim as _claim
    cfg.raw.setdefault("link", {})["public_base"] = url
    source = getattr(cfg, "source_path", None)
    target = (Path(path) if path
              else Path(source) if source
              else Path(__file__).resolve().parent.parent / "config.yaml")
    try:
        target.write_text(_claim._patch_scalar(
            target.read_text(), "link", "public_base", url))
        import yaml
        yaml.safe_load(target.read_text())
        wrote = True
    except Exception:  # noqa: BLE001 — saving must never crash the CLI
        wrote = False
    return {"saved": wrote, "url": url}


def lines(cfg=None) -> list[str]:
    """The whole form, field by field, in the order the page shows it."""
    try:
        site_url, privacy_url = urls(cfg)
    except Exception:  # noqa: BLE001
        site_url, privacy_url = ("http://<VPS-IP>:5000/about",
                                 "http://<VPS-IP>:5000/privacy")
    brand = COMPANY
    try:
        brand = str(cfg.get("design.brand_name", "") or "") or COMPANY
    except Exception:  # noqa: BLE001
        pass
    live = bool(site_of(cfg)) if cfg is not None else False

    out = [
        "═" * 70,
        "📝 PINTEREST 'CONNECT APP' FORM — exact answers (copy-paste)",
        "═" * 70,
        f"   App icon (upload)          : {ICON}  (1024x1024, no Pinterest logo)",
        f"   App name                   : {brand} Deals Publisher",
        f"   Company name               : {brand}",
        f"   Company website or App link: {site_url}",
        f"   Link to Privacy policy     : {privacy_url}",
        "",
        "   App purpose (free text — paste as-is):",
    ]
    for line in _wrap(PURPOSE_TEXT, 64):
        out.append(f"      {line}")
    out += [
        "",
        "   Developer purpose          : ● Personal API access (single, personal use)",
        "   Who are you sharing with?  : Only me / Myself",
        "",
        "   Use cases (select these only):",
    ]
    for case in USE_CASES:
        out.append(f"      ☑ {case}")
    out += [
        "   Audience                   : ☑ Businesses   (migilinavi vaddu)",
        "   Reads Pins and/or Boards   : ● Yes, mine     (ippudu 'No' unte maarchu!)",
        "   reCAPTCHA                  : ☑ I'm not a robot",
        "",
        "   ❌ Kandi select cheyyakandi: Ad campaign management · Pinner App ·",
        "      Ecommerce · Recommendations & experimentation · MCP/AI connector",
        "",
        "─" * 70,
        "🧭 App page malli open cheyyadam: python -m bot app --where",
        "⏳ 'Trial access pending' lo Redirect URLs + App secret LOCK lo untayi",
        "   (grey field — tappu kaadu). Emi cheyyocho: python -m bot app --pending",
        "",
        "SUBMIT TARVATA: redirect URI + scopes → app secret unlock → OAuth.",
        "⏭️  TARVATA KAAVALSINADI: public pins ki **Standard access request** —",
        "    python -m bot app --upgrade   (answers ready, scope justification tho)",
        "",
        "SUBMIT TARVATA (redirect URI + scopes screen):",
        f"   Redirect URI: {REDIRECT_URI}",
        f"   Scopes      : {SCOPES}",
        "   → App ID + App Secret copy → .env  (python -m bot setup adi adigutundi)",
        "",
    ]
    if not live:
        out += [
            "⚠️  Paiki URLs lo <VPS-IP> placeholders unnayi — form submit cheyyaku",
            "    mundu nee real URL pettu:",
            "      python -m bot app --site https://yourdomain.com",
            "      (leda VPS IP tho: python -m bot app --site http://1.2.3.4:5000)",
            "    VPS IP teliyali ante (VPS lo):  curl -s ifconfig.me",
        ]
    else:
        out += [
            f"✅ Site set: {site_of(cfg)}",
            f"   Check: curl -s -o /dev/null -w '%{{http_code}}\\n' {site_url}",
        ]
    return out


def where_lines(cfg=None) -> list[str]:
    """Exact click-path back to the app page (people lose the console tab)."""
    app_id = ""
    try:
        import os
        app_id = str(os.getenv("PINTEREST_APP_ID", "") or "")
    except Exception:  # noqa: BLE001
        app_id = ""
    direct = (f"https://developers.pinterest.com/apps/{app_id}/" if app_id
              else "https://developers.pinterest.com/apps/")
    shown_id = app_id or "1613412"
    return [
        "═" * 70,
        "🧭 APP PAGE EKKADA? (ee 30 seconds lo open cheyyi)",
        "═" * 70,
        "1. Browser lo:  https://developers.pinterest.com",
        "   → login cheyyi **gharvanaa** account tho (app ee account kinda undi).",
        "",
        "2. Top-right lo nee profile icon click → **My apps**",
        "   leda direct ga:  https://developers.pinterest.com/apps/",
        "",
        f"3. App card 'Gharvanaa Deals Publisher' (App ID {shown_id}) "
        "kanipistundi",
        "   → aa card meeda **Manage** button click cheyyi",
        f"   leda direct:  {direct}",
        "",
        "4. App page lo TABS:  Configure | Collaborators | Details",
        "   → **Configure** tab (default eh untundi) → kindaki scroll:",
        "",
        "   ▸ **Redirect URLs**  →  input box lo pedu:",
        "        http://localhost:8888/callback",
        "     → **Enter** kottu (leda 'Add' click) → URL chip ga kanipinchali ✅",
        "     ⚠️ 'Trial access pending' lo ee field GREY/disabled ga untundi —",
        "        adi Pinterest lock, tappu kaadu. Approval tarvata add cheyyi",
        "        (OAuth ki appudu eh kavali). Details: python -m bot app --pending",
        "",
        "   ▸ **Generate Access Tokens** (same tab, kindaki) →",
        "        Environment: Production Limited → **Generate token**",
        "     → token copy (ventane, browser nunchi vellaka mundu)",
        "     → .env lo:  PINTEREST_ACCESS_TOKEN='<token>'",
        "",
        "   ▸ **API scopes** (same tab, chivari section) → ee 5 read/write",
        "     scopes nee app ki kaavali:",
        "        boards:read · boards:write · pins:read · pins:write ·",
        "        user_accounts:read",
        "     (dashboard trial token ee write scopes ivvadu — adi OAuth tarvata)",
        "",
        "5. Verify (VPS lo):  python -m bot token-check",
        '   → "READ works ✅" vasthe token correct;  --write-test tho write kuda',
        "",
        "💡 Tab close aithe parvaledu — paiki unna URL bookmark chesuko:",
        f"   {direct}",
    ]


def pending_lines(cfg=None) -> list[str]:
    """What the app page allows while 'Trial access pending' (and why)."""
    return [
        "═" * 70,
        "⏳ 'TRIAL ACCESS PENDING' — emi lock lo untundi, emi ippude cheyyochu",
        "═" * 70,
        "   Pinterest ee state lo app CONFIG ni lock chestundi (nuvvu tappu",
        "   cheyyaledu):",
        "     🔒 App secret key      → 'Unavailable while trial access pending'",
        "     🔒 Redirect URLs field → grey/disabled, Add button kuda disable",
        "",
        "   ✅ Ippude cheyyagaligedi (lock ledu):",
        "     • **Generate Access Tokens** → 'Production Limited' → Generate token",
        "       (read-only token: pins:read, boards:read, user_accounts:read)",
        "     • Aa token ni .env lo:  PINTEREST_ACCESS_TOKEN='...'",
        "     • Proof:  python -m bot token-check",
        "     • .env lo migilinavi: Amazon tag, Meesho af_invite, IG/FB tokens",
        "     • VPS deploy + domain + /about /privacy pages",
        "",
        "   ⏭️ Approval email vachaka (eppudu):",
        "     • App secret unlock → Redirect URL kuda add cheyyochu:",
        "         http://localhost:8888/callback",
        "     • Appudu: python -m bot auth-url  →  python -m bot auth --code <CODE>",
        "     • Tarvata: python -m bot app --upgrade  (public pins ki standard)",
        "",
        "   💡 Order mukhyam kaadu: OAuth ki redirect URI appudu kavali — ippudu",
        "      add avvakapoyina workflow aagadu. Trial token tho ippude test cheyyi.",
    ]


def timeline_lines(cfg=None) -> list[str]:
    """Honest answer to "approve eppudu avuddi?" — researched, not guessed.

    Sources: Pinterest's own developer-community replies (staff say there is no
    published turnaround time and that 2026 approvals are delayed), the Blotato
    2026 API guide (trial reviewed each business day; standard review "inside a
    week when the application is clean and inside three to four weeks when
    reviewers want changes"), plus community threads (11 days trial pending,
    26 days standard pending).
    """
    site_url, privacy_url = urls(cfg) if cfg is not None else (
        "https://yourdomain.com/about", "https://yourdomain.com/privacy")
    return [
        "═" * 70,
        "⏳ 'APPROVE EPPUDU AVUDDI?' — nijamaina timeline (2026-09)",
        "═" * 70,
        "   Rendu separate approvals unnayi — total wait ee rendu kalipi:",
        "",
        "   1) TRIAL ACCESS  (nuvvu ippudu unnadi: 'Trial access pending')",
        "      • Rule: trial applications 'reviewed each business day'",
        "      • Reality 2026: Pinterest staff post chesaru (May-Aug 2026)",
        "        'we are aware of current delays in the app approval process'",
        "      • Community: mostly 1-3 days, kani 11+ days pending cases kuda",
        "      • Expected: 2 dinam - 3 weeks",
        "",
        "   2) STANDARD ACCESS  (trial approve ayyaka request cheyyali)",
        "      • Manual review + VIDEO DEMO kavali (OAuth + real pin create)",
        "      • Pinterest public timeline ivvaledu ('no published turnaround')",
        "      • Clean application: ~1 week · changes adigithe: 3-4 weeks",
        "      • Recent community report: 26 days pending, no reply",
        "",
        "   ⚠️ MUKHYAM: approval ki EMAIL RADU. Nuvve app page ni prati 2-3",
        "      rojulu okasari open chesi chudali.",
        "",
        "   📈 ESCALATION (2-3 weeks datithe):",
        "      • Status adagandi: https://help.pinterest.com/en/contact",
        "        (Developer/API access category) — app id 1613412 pettu",
        "      • App profile complete ga undali: name, description, logo,",
        "        website, privacy policy URL — half-filled apps ki reply late",
        f"      • Nee URLs: {site_url}  |  {privacy_url}",
        "      • 3 weeks datithe inka detail tho re-apply",
        "",
        "   ✅ ILOPU AAGAKU — Pinterest wait lo migilinavi ippude live avutayi:",
        "      • Telegram deals channel (bot admin ✅) → nijam ga pani chestundi",
        "      • Instagram + Facebook + YouTube tokens iste aa posting automatic",
        "      • Bot Pinterest ni 'pending' ga mark chesi, token vachina ventane",
        "        pins start chestundi — nuvvu em cheyyalsina avasaram ledu",
        "",
        "   👉 Next: python -m bot app --pending  (emi lock, emi cheyyochu)",
        "             python -m bot app --demo     (standard access video script)",
    ]


def demo_lines(cfg=None) -> list[str]:
    """The exact recording Pinterest asks for at the Standard-access upgrade.

    Pinterest's own requirement: 'Prepare a video recording of your app
    completing an action using the Pinterest API.' Reviewers reject on missing
    screens, so this is the shot list — record once, ~3 minutes.
    """
    site_url, privacy_url = urls(cfg) if cfg is not None else (
        "https://yourdomain.com/about", "https://yourdomain.com/privacy")
    return [
        "═" * 70,
        "🎬 STANDARD ACCESS VIDEO DEMO — exact shot list (~3 nimushalu)",
        "═" * 70,
        "   Pinterest adigedi: 'video recording of your app completing an",
        "   action using the Pinterest API'. Ee order lo record cheyyi:",
        "",
        "   SHOT 1 (0:00-0:20) — App profile",
        "     • developers.pinterest.com → My apps → app page",
        "     • Kanipinchali: app name, logo, description, website,",
        f"       privacy policy ({privacy_url})",
        "",
        "   SHOT 2 (0:20-1:10) — OAuth flow (FULL, cuts levu)",
        "     • Terminal:  python -m bot auth-url",
        "     • URL ni browser lo open → Pinterest login → 'Give access'",
        "     • Redirect avvadam (localhost:8888/callback) chupinchali",
        "     • Tarvata:  python -m bot auth --code <CODE>",
        "     • Terminal lo 'token saved' line kanipinchali",
        "",
        "   SHOT 3 (1:10-2:30) — REAL pin create (ide main proof)",
        "     • Terminal:  python -m bot run   (leda  python -m bot post 1)",
        "     • Logs: scrape → link build → pin design → upload",
        "     • Pinterest profile lo aa pin LIVE ga undadam chupinchali",
        "",
        "   SHOT 4 (2:30-3:00) — Boards + own pins read",
        "     • Terminal:  python -m bot pin-stats",
        "     • Boards list + created pins kanipinchali",
        "",
        "   NAAPU TIPS (reviewers ivanni chustaru):",
        "     • Oka take lo cheyyi — cuts unte reject avvochu",
        "     • Narration English lo: 'this is our own account, our own",
        "       products, single user, no third parties'",
        "     • Recording: OBS / Windows Game Bar (Win+G) / QuickTime",
        f"     • Naatu lo site open pettu: {site_url}",
        "     • Demo mundu 'python -m bot doctor' → anni green ga undali",
        "",
        "   📤 SUBMIT: app page → 'Upgrade to Standard access' → video link",
        "      (YouTube unlisted best) + `bot app --upgrade` answers",
    ]


def upgrade_lines(cfg=None) -> list[str]:
    """Standard access request — the step that makes pins PUBLIC.

    Pinterest's own access-tier table says it plainly: on Trial, writing standard
    Pins is "visible only to the user who creates them". An affiliate page earns
    nothing from pins only the owner can see, so this request is the real go-live
    gate — not a formality.
    """
    site_url, privacy_url = urls(cfg) if cfg is not None else (
        "https://yourdomain.com/about", "https://yourdomain.com/privacy")
    return [
        "═" * 70,
        "🚀 STANDARD ACCESS REQUEST — public pins ki ide gate",
        "═" * 70,
        "   Pinterest access tiers (their own table):",
        "     Trial    : writing standard Pins → 'visible only to the user who",
        "                creates them' (1000 req/day)",
        "     Standard : pins are PUBLIC + variable rate limits",
        "   So trial = pipeline test matrame. Money ki Standard access kavali.",
        "",
        "WHERE: developers.pinterest.com → My apps → your app → 'Upgrade' /",
        "       'Request standard access' (top-right of the app page).",
        "",
        "HOW TO ANSWER (copy-paste):",
        "",
        "   What will your app do?",
        "   → Internal publishing tool for our own Pinterest business account:",
        "     it creates our boards, publishes our own product pins on a daily",
        "     schedule, and reads our own pins/boards to avoid duplicates and",
        "     report performance. Single account, single owner, no third-party",
        "     users.",
        "",
        "   Scope justification:",
        "   • boards:read    → find our own board ids by name before posting",
        "   • boards:write   → create our niche boards once (Home & Kitchen,",
        "                      Fashion, Beauty, Deals…)",
        "   • pins:read      → check the last N pins to skip duplicates",
        "   • pins:write     → publish our own curated pins (5-15/day)",
        "   • user_accounts:read → confirm which account is connected",
        "",
        "   Expected volume: ~15-40 API calls/day (a few pins + duplicate checks).",
        "   Data use: only our own account data; nothing is shared or resold.",
        f"   Company website : {site_url}",
        f"   Privacy policy  : {privacy_url}",
        "",
        "BEFORE YOU SUBMIT (ee rendu ready ga undali):",
        "   1) Public pages live:  curl -s -o /dev/null -w '%{http_code}\\n' "
        f"{site_url}",
        "      (200 ravali — leda: sudo ./deploy.sh  +  python -m bot app "
        "--site <url>)",
        "   2) Trial lo pipeline run ayyi undali (pins create avvadam proof):",
        "      python -m bot doctor  →  python -m bot run   (oka pin test)",
        "",
        "⏳ Review tharvata: OAuth (`python -m bot auth-url` + `auth --code`) "
        "okasari",
        "   chesi, .env lo trial token ni theeseyyandi — appudu permanent refresh",
        "   token tho 24x7 autopilot.",
    ]


def _wrap(text: str, width: int) -> list[str]:
    words, cur, lines = text.split(), "", []
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
