# 📌 PinDrop Pro — Pinterest Affiliate Auto-Poster Bot

**Fully-advanced Pinterest affiliate automation.**

```
product URL ─▶ scrape (title/price/image) ─▶ YOUR affiliate link
           ─▶ 1000×1500 pin graphic design ─▶ SEO title/description/hashtags
           ─▶ post / schedule to Pinterest (image or video pin)
```

Amazon Associates + Meesho + Flipkart (EarnKaro / Cuelinks) — **anni support**.

**Surfaces:** Pinterest (main) · Instagram (feed + reels + **Stories** + bio + auto-DM) · Facebook Page · **YouTube Shorts** (optional uploader) · **Telegram deals channel** (optional broadcast).
Bot scrape chestundi, mee affiliate link petti, manchi pin design chesi,
daily automatic ga Pinterest lo post chestundi → **meeru commission earn chestaru**.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🕷 **Smart Scraper** | Amazon.in / Meesho / Flipkart / any shop — JSON-LD → OpenGraph → CSS fallback; grabs the **full photo gallery + product video** |
| 💰 **Affiliate Engine** | Amazon `?tag=`, Meesho `affid`, Flipkart `affid`, EarnKaro & Cuelinks deep-link wrapping |
| 🎨 **4 Pin Design Templates** | classic / split / overlay / collage — rotated randomly so no two pins look alike |
| 🖼 **Multi-variation pins** | Each product posts as N pins (different photo + template) → more reach, no duplicates |
| 🎬 **Real media upload** | Photos & videos are **downloaded and uploaded** to Pinterest (base64 image pins + 2-step video upload) — not just linked |
| 📝 **SEO Writer** | Keyword hashtags + deal-style descriptions for every pin |
| 📌 **Official Pinterest API v5** | OAuth, boards auto-create, image pins, video pins, scheduling up to 14 days |
| ⏰ **Human-like Scheduler** | N pins/day inside IST posting window, randomized gaps (safe for your account) |
| 📸 **Instagram Auto-Post** | Same products cross-posted to your IG page (single / carousel / reels) via Meta Graph API |
| 🖥 **Web Dashboard** | Add products, manual add, one-click posting, queue, stats, logs — live preview |
| 🧾 **CSV Bulk Import** | Add 100s of products in one command |
|  **Safe by default** | Rate limits, retries, dedupe, error logging, graceful fallbacks |

---

## 🛸 ZERO-TOUCH MODE (nenu em cheyakunda)

```bash
./run.sh &            # one command. Forever. (or: python -m bot setup first)
```

That's it. Autopilot then does EVERYTHING by itself, 24×7:
- 🛰 **hunts trending products** on Amazon/Meesho/Flipkart when the queue runs low
- 🎨 designs fresh pins + auto-reels, ✍️ writes SEO titles from LIVE Pinterest keywords
- 📌 posts in peak windows with human gaps, retries failures, skips 3-strike products
- 📸 cross-posts to Instagram, 🔗 tracks every click, 🧾 logs everything

The ONLY one-time human steps (API security — nobody can automate account logins):
`python -m bot setup` → paste Pinterest App ID/Secret + click ALLOW + paste your
affiliate IDs (Amazon tag / Meesho affid / EarnKaro). ~5 minutes, once in a lifetime.

Guardian: `run.sh` auto-installs deps and restarts the bot if it ever crashes.

---

## 🚀 Setup (first time, 10 minutes)

### 1. Install
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Linux/Mac
# Windows:  .venv\Scripts\pip install -r requirements.txt
```

### 2. Pinterest app (5 min)
1. Go to **https://developers.pinterest.com/apps/** → *Create app*.
2. You need a **Pinterest Business account** (free to convert personal → business in Settings).
3. In the app: add the redirect URI exactly as: `http://localhost:8888/callback`
4. Enable scopes: `boards:read, boards:write, pins:read, pins:write, user_accounts:read`
5. Copy **App ID** and **App Secret**.

### 3. Secrets — copy `.env.example` → `.env` and fill in
```bash
cp .env.example .env
# edit .env:
PINTEREST_APP_ID=...
PINTEREST_APP_SECRET=...
AMAZON_TAG=yourtag-21        # from affiliate-program.amazon.in
```

### 4. Connect Pinterest account
```bash
.venv/bin/python -m bot auth          # opens browser, click ALLOW → done
```
Headless server? Two-step:
```bash
.venv/bin/python -m bot auth-url      # prints URL — open it anywhere, click ALLOW
.venv/bin/python -m bot auth --code <CODE_FROM_REDIRECT_URL>
```
Verify: `.venv/bin/python -m bot check`

### 5. Your affiliate IDs (commission settings)
In `config.yaml` (or `.env`):
```yaml
affiliate:
  amazon_tag: "yourtag-21"
  meesho_affid: "MEESH123"          # Meesho affiliate program id
  flipkart_affid: ""                # or let it wrap via EarnKaro/Cuelinks
  earnkaro_prefix: "https://ekaro.in/enkr2024xxxxx"   # EarnKaro personal link
  cuelinks_template: "https://...cuelinks...?url={url}"
```
Priority: Amazon tag → Meesho affid → Flipkart affid → EarnKaro → Cuelinks → generic.

---

## 🎮 Daily usage

```bash
# add products (scrapes + converts link + designs pin + queues it)
.venv/bin/python -m bot add https://www.amazon.in/dp/B0XXXXXX https://www.meesho.com/x/p/abc

# bulk import (columns: url,title,price,image_url,video_url — only url is required)
.venv/bin/python -m bot add-csv products.csv        # see products_sample.csv

# see what's queued
.venv/bin/python -m bot queue

# post right now
.venv/bin/python -m bot post 3

# 🤖 run the 24×7 automatic scheduler (8 pins/day, 9am–10pm IST, human gaps)
.venv/bin/python -m bot run

# 🎨 preview all 4 pin design templates
.venv/bin/python -m bot design-test

# 🖥 web control panel
.venv/bin/python -m bot dashboard    # http://localhost:5000
```

Keep `run` alive 24×7 on any cheap VPS/PC, or with `nohup`:
```bash
nohup .venv/bin/python -m bot run > pindrop.log 2>&1 &
```

### 🔥 Fully-advanced mode (photos + videos, maximum reach)
In `config.yaml`:
```yaml
posting:
  pins_per_product: 3   # 1 product → 3 different pins (different photo + template)
scraping:
  max_images: 3         # gallery photos downloaded per product
```
- Product **photos are downloaded** and designed into pins (uploaded to Pinterest as
  base64 media — never hot-linked).
- When a product page exposes a **video**, the bot downloads it and publishes a real
  **video pin** via Pinterest's 2-step video upload.
- Every pin carries your **affiliate link** (Amazon tag / Meesho affid / wrappers).

---

## 🧪 Tests
```bash
.venv/bin/python -m unittest tests.test_core -v
.venv/bin/python -m bot design-test     # makes a sample pin so you can preview the design
```

---

## 📁 Project layout
```
bot/
  config.py          behavior config loader (config.yaml + .env)
  scraper.py         Amazon/Meesho/Flipkart/generic product scraper
  affiliate.py       affiliate link engine (tag/affid/wrappers)
  pin_designer.py    1000×1500 pin graphic generator (Pillow)
  pinterest_api.py   Pinterest v5 API client (OAuth, pins, videos, schedule)
  engine.py          pipeline + human-like scheduler
  dashboard.py       Flask web control panel
  main.py            CLI
templates/           dashboard UI
tests/               unit tests
data/                sqlite db + generated pins (git-ignored)
```

---

## 🧠 Viral Tricks Playbook — top creators em chestunnaro, bot lo anni unnai

Deep analysis of how 6-figure affiliate creators post on Pinterest + Instagram
in 2026, and where each trick lives in this bot:

| # | The trick they use | Why it works | In this bot |
|---|---|---|---|
| 1 | **Fresh pins only** — 5–15 NEW pins/day, never repost the same image | Pinterest's 2026 algorithm prioritizes fresh content over repins [1](https://improvado.io/blog/pinterest-marketing-tactics)[2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/) | `pins_per_product: 3` variations, random template each time |
| 2 | **3–5 designs per product** testing headlines/visuals | More surfaces = more chances to hit a segment [2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/) | 4 templates (`classic/split/overlay/collage`) rotated |
| 3 | **Video / Idea pins** — up to 9× the reach of static pins | Video stops the scroll [2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/) | `video.auto_reel` — builds a 6s reel (hook → Ken Burns zoom → CTA) from photos when the page has no video; real product videos downloaded when they exist |
| 4 | **Hook in first 1–3 seconds** ("Wait for the price 👀") | Curiosity = watch time = distribution | `bot/growth.py` HOOKS in reel intro + captions |
| 5 | **Keyword-stuffed titles & descriptions** (Pinterest = search engine) | Pins rank in search for months/years [1](https://improvado.io/blog/pinterest-marketing-tactics)[5](https://www.shopify.com/pk/blog/pinterest-affiliate-marketing) | `seo_title()` ≤100 chars + tiered hashtag mix + alt text |
| 6 | **Text overlay on the image** (price, bold headline) | Pinterest visual search reads text; overlay = CTR | Designer always burns price badge + title + CTA into the pin |
| 7 | **Post in peak windows**, spread out, human gaps | Consistency + timing beats bursts [1](https://improvado.io/blog/pinterest-marketing-tactics)[4](https://www.clickbank.com/blog/pinterest-affiliate-marketing/) | `peak_mode` scheduler (IST windows) + 40–65 min random gaps |
| 8 | **Roundups / "3 finds under ₹X"** value content | Converts better than raw product pins [3](https://www.outfy.com/blog/pinterest-affiliate-marketing/)[5](https://www.shopify.com/pk/blog/pinterest-affiliate-marketing) | collage template + `roundup_title()` |
| 9 | **Niche boards with keyword names** | Boards rank too [2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/) | board auto-create; name it per niche in `config.yaml` |
| 10 | **Disclose #ad / #affiliate** | Pinterest ToS + FTC; builds trust [2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/)[5](https://www.shopify.com/pk/blog/pinterest-affiliate-marketing) | auto-appended to every description |
| 11 | **Track everything (UTM)** | Know which pin/platform makes money [2](https://affiliatemarketingforsuccess.com/affiliate-marketing/affiliate-marketing-on-pinterest/) | `utm_source=pinterest` auto-added to links |
| 12 | **IG: reel + "comment LINK" + link in bio** | IG captions have no clickable links; comment-bait = engagement = reach | Instagram module captions + reel mode |

**How those viral videos are built (analysis):** almost none are "real" shoots —
they're 5–8s edits: hook text → zooming product photo → price pop → CTA screen.
That's exactly what `bot/video_maker.py` renders automatically from photos,
24×7, for every product.

## 💬 ManyChat? — not needed, we ship it free

ManyChat is a paid SaaS for IG comment/DM automation. We cover the same
ground with official API + zero monthly cost:

| ManyChat feature | PinDrop Pro built-in |
|---|---|
| Keyword triggers ("link", "price", "buy"…) | ✅ `instagram.triggers` — configurable templates |
| Per-product replies | ✅ media→product mapping, {title}/{price} auto-fill |
| Rate safety | ✅ caps + human delays + duplicate skip |
| Visual flow builder | ⚪ not needed — templates are config, not drag-drop |
| Auto-DM (keyword → product + link) | ✅ `auto_dm` — official Instagram Messaging API, polls conversations, answers with matched product & buy link (needs instagram_manage_messages scope) |

If you STILL want ManyChat someday: connect it to the same IG account —
it complements us (you'd just be paying for a drag-drop UI).

## 📋 Deals-of-the-Day Roundups — the list-post weapon

Top channels ride LIST pins (viral saves); we generate them daily,
automatically:

- **Segments** (audience-aware, women-first like Pinterest itself):
  Ladies Special ✨ · Home & Kitchen 🏠 · Kids Corner 🧸 · Gadget Deals 📱
- **Smart picks**: segment match + winner score + commission priority
- **Trend-aware titles**: seasonal tag (festive/gifting/summer/monsoon) +
  festival calendar + your own CTR learning
- **List pin design**: numbered rows, thumbs, ₹ prices, % OFF, CTA footer
- **Deals page** `/deals/today`: the pin links to a page where EVERY item
  carries its own tracked affiliate link
- Posted once daily (10 AM–8 PM) to a "Deals of the Day" SEO board; also
  available on demand via `engine.post_roundup()`.

Autopilot needs NO manual links from you: it hunts Meesho/Amazon/Flipkart
winner-niche products itself, monetizes them (affid or your generated links
pass through untouched) and posts. Manual links = optional boost.

## 🌐 Where we post — and platform truth

| Platform | How | Status |
|---|---|---|
| Pinterest | Official Pins API (pins, video pins, boards) | ✅ primary |
| Instagram | Official Graph API (reels, carousels, comment replies) | ✅ optional creds |
| **Facebook Page** | Official Graph API (photo/link posts) | ✅ optional creds |
| Telegram | Broadcast channel + private reports | ⚪ optional, off by default |
| WhatsApp | Share button on landing | ⛔ owner said NO → disabled by default |

`python -m bot features` prints the live inventory of ALL capabilities.

**Meesho deep-analysis (honest):** Meesho ships nice in-app features
(auto-comments, reseller tools) but exposes **no public API** — automating
their app would mean app-internal hacks = account ban. The money move stays:
we promote Meesho PRODUCTS (highest commission!) through Pinterest/IG/FB,
where we ARE allowed to automate. If Meesho ever opens an API, adding it =
one file + one FEATURES entry — the architecture is plug-ready.

## 🛡️ Safety Layer — "ekkada dorakakudadu" (never get caught)

Deep self-audit of every ban/flag risk, and the fix shipped for each:

| Risk | How we stay safe |
|---|---|
| New account blasting pins = flagged | **Warm-up ramp**: ~30% volume on day 1, +10%/day, full by week 1 |
| Robotic identical daily volume | **±15% daily jitter** + human-like 40–65 min gaps with random jitter |
| IG comment-reply spam = throttled | **Capped 5 replies/cycle**, 3–8s human delays, duplicate-reply skip |
| Spammy identical pins | Fresh design per post + winners re-pinned only after rest window |
| Affiliate policy violations | `#ad #affiliate` disclosure baked into every description |
| Scraping bans | Rotating real UAs, retries, polite delays; graceful manual-add fallback |
| Leaked credentials | `.env` + `data/` git-ignored — tokens NEVER in the repo |
| Broken content going live | Pin-by-Pin QA gate quarantines anything wrong |

Everything above is automatic — you don't configure any of it.

## 💸 Commission-Leak Audit — "ekkada commission miss avvaddu"

Every known leak path, audited & sealed:

| Leak path | Seal |
|---|---|
| Pin with untracked link (clicks pay nobody) | ✅ QA gate quarantines — "COMMISSION LEAK" |
| Amazon pin carrying someone else's tag | ✅ amazonize replaces with YOURS |
| Meesho plain links | ✅ direct af_invite (your IDs) → affid → aggregator |
| Meesho ALPHANUMERIC product ids (`/p/1k1b6`, `-p/489088490`, `-p-1k1b6`) | ✅ all 3 shapes parsed — digits-only parsing used to silently fall back (fixed R35) |
| Meesho template params (utm/extra) dropped when rebuilding | ✅ your latest share link's params are copied VERBATIM; only `p_id` + `ext_id` change |
| Meesho template unparseable (format changed) | ✅ loud warning + `bot doctor` + `bot meesho` structural report |
| Flipkart / other stores | ✅ affid → EarnKaro/Cuelinks wrap |
| Link rewritten & broken | ✅ monetized links pass through UNTOUCHED |
| Bio/DM/comment links | ✅ bridge/affiliate link per product |
| Winners going stale | ✅ price-watch re-announces 📉 drops + rotation |

## 📌 Pinterest power layer — top-0.1% mechanics (photos + videos)

Pinterest is the main money surface, so every pin goes out with the best
available mechanics — all via the official v5 API, verified by tests:

| Mechanic | What we do | Why it wins |
|---|---|---|
| **API media upload** | `POST /v5/media` (register → S3 upload → poll `succeeded`) for images AND videos | `image_url` makes Pinterest fetch a store CDN that can block/404 — uploading our own designed file means the pin we designed is the pin that ships. Falls back to inline base64, then URL |
| **Carousel pins** | 2–5 product photos, each item with its own link (`multiple_image_urls`) | Pinterest's highest-engagement pin format; buyer taps the exact variant they want; auto-falls back to a single pin if the product has one photo or the API refuses |
| **Video pins** | real product video, else our auto-generated reel (`video_id` after upload), with `alt_text` | video pins get extra distribution; still the same affiliate link |
| **Board sections** | optional per-niche sub-boards (`pinterest.sections`) | keeps a big board tidy and signals relevance to Pinterest |
| **Live Trends API** | `GET /v5/trends/keywords/IN/top/growing|monthly` → cached 24h → injected into titles/hashtags | real regional demand instead of guesswork; `bot trends --live` |
| **Pin analytics** | `GET /v5/pins/{id}/analytics` → impressions, saves, pin clicks, outbound clicks, stored per pin | honest funnel data; drives the winners-rotation (Pinterest-verified winners get reshared first) |
| **Rich Pins** | landing pages ship `og:type=product` + `product:price:amount` + `product:price:currency` + `og:availability` + absolute `og:image`/`og:url` | price + availability can appear on the pin itself; better click-through |
| **Scheduling** | `created_time` (±14-day window) or the local human-like scheduler | organic-looking cadence, no API abuse |

Verify any time: `python -m bot pin-stats` (real numbers), `python -m bot trends --live`
(real keywords), `python -m bot features` (what's switched on).

## 🛍 Meesho affiliate — exactly how it works (no API needed)

Meesho has **no public affiliate API**, and it doesn't need one: Meesho's own
"Get commission link" screen produces an `af_invite` URL that *is* the
affiliate mechanism. Your publisher id + source token + campaign id live in
that URL; the product is selected by `p_id`.

```
your share link (from affiliate.meesho.com)
  /af_invite/24197020:instagram_stories:11075346?p_id=5121&ext_id=3y9
             ▲ publisher      ▲ source token  ▲ campaign   ▲ product
                                                          (Meesho fills
                                                           product when you
                                                           share from a page)

bot builds, for ANY scraped product:
  /af_invite/24197020:instagram_stories:11075346?p_id=<REAL PRODUCT>&ext_id=<fresh 6-char>&utm_source=instagram_stories
              ▲ same publisher/campaign/params — only product + click id change
```

**Per platform** (Meesho gives each surface its own token + campaign):

| Surface | Token used | Why |
|---|---|---|
| Instagram | `instagram_stories` (yours) | matches where the click came from |
| Facebook | `facebook` (yours) | clean Meesho report |
| YouTube | `youtube` if you created one, else newest | Meesho offers "YouTube Shorts/videos" |
| Pinterest | override in `affiliate.meesho_platform_tokens` | Meesho has no Pinterest option — map it to any token (commission is unaffected; publisher id decides the money) |

Verify in one command: `python -m bot meesho "https://www.meesho.com/<product>"` →
prints the exact link per platform + structural checks. `python -m bot platforms`
shows every surface + its token. Honest limit: only your phone + the Meesho
dashboard can confirm a click end-to-end (see `bot meesho` output).

## 💰 Money Layer — deep-level revenue thinking

1. **Commission-priority posting** (`COMMISSION_EST` in trends.py): products
   are scored by expected commission — Meesho (3–15%) jumps the queue, so the
   highest-paying clicks happen FIRST. Money-per-post goes up automatically.
2. **Your own videos** — dashboard 🎬 upload → `data/videos/`. Your footage
   beats auto-reels (your brand, more trust) and posts as Pinterest video
   pins + IG reels, with your trending audio mixed in.
3. **Multi-network affiliate engine** — Amazon, Meesho, Flipkart, EarnKaro,
   Cuelinks + custom. New program arrives → add creds in `.env` → done.
4. Every pin's money path: pin → YOUR bridge link (tracked) → landing →
   affiliate URL. Clicks are attributed per pin per hour → the machine
   learns what earns and does more of it.

## 📸 How REAL photos/videos are captured (no dummies, no AI fakes)

The bot posts ONLY the store's own product media — exactly what top
affiliates do (Amazon Associates allows using product images/videos for
promotion):

1. **You paste a product link** (dashboard) or autopilot hunts winner niches.
2. Scraper downloads the page with **rotating real browser UAs**, retries,
   polite delays.
3. Gallery extraction, pro-grade:
   - **Amazon `colorImages` JS blob** → full **hiRes gallery** forced to
     1500px (`_SL1500_`) + **brand product videos** (same payload Amazon's
     own viewer uses — survives lazy-loading)
   - Meesho product JSON → image list + `videoUrl` reel
   - JSON-LD / OpenGraph / Flipkart selectors as fallbacks
4. Real images → designer overlays (price, % OFF burst, CTA) → real video →
   Pinterest video pin / IG reel (hosted automatically).
5. **Pin-by-Pin QA gate** blocks anything broken before posting.

### 🔍 Cross-store enrichment — "you never make media"

Thin gallery or no video? The bot searches the **same product on the other
stores** (Amazon ⇄ Flipkart ⇄ Meesho) and merges that listing's official
gallery + brand video. Official store images are watermark-free by store
policy. One polite enrichment pass per product; and if still nothing →
auto-generated voice reel from the photos you DO have. Every path ends in
real media. Zero manual media work for you.

> Demo queue in this preview uses AI placeholder images ONLY because the
> preview sandbox's datacenter IP is blocked by Amazon/Flipkart/Meesho
> (TLS drop — verified). On **your home network** (via `deploy.sh`) real
> scraping works. If any store ever blocks, paste the link in dashboard
> "Manual add" with the image URL — never a dead end.

## 🧪 10x Layer — Pin-by-Pin QA, Simulation, Analytics

Nothing posts blind anymore:

1. **Pin-by-Pin QA gate** (`bot/qa.py`) — EVERY pin passes a checklist right
   before the API call: media ≥600px & readable & <32MB · link valid with YOUR
   affiliate tag · title 5–100 chars · description keyword-rich with `#ad`
   disclosure · not a duplicate inside the rest window. Fail → quarantined
   with the exact reasons (never silent junk).
2. **Full-pipeline simulation** — `python -m bot simulate` runs the entire
   machine end-to-end (link → SEO → design → reel+BGM+voice → QA → landing →
   click tracking → rotation) **with zero credentials** and prints the report.
3. **Analytics tab** — dashboard 📊: clicks-by-hour chart (feeds the posting
   brain), top pins (winners auto-rotate), template CTR, subscribers.

## 🔬 Top-0.1% Micro Layer — the small moves that compound

| Micro trick | What it does |
|---|---|
| 🔁 **Winners rotation** (`reshare_winners`) | products that earned clicks get re-posted as FRESH pins daily (new design + keywords) — Pinterest boosts freshness, winners earn each round |
| 💬 **WhatsApp share button** on every landing page | India's #1 viral loop — family/WhatsApp-group sharing = free distribution |
| 📢 **Telegram deals channel** (`TELEGRAM_DEALS_CHANNEL`) | broadcast every deal to a public channel — how India's top affiliates scale |
| 📋 **SEO board descriptions** | boards created with keyword-rich descriptions (Pinterest indexes them) |
| 🎣 **Hook bank** (incl. Hinglish) | 15+ rotating curiosity hooks, tested phrasing, A/B by template CTR |
| ⏰ **Hour-wise CTR learning** | denser posting in YOUR proven click hours (≥10 clicks learned) |

## 🎬 "Amazon photos/videos tho top vallu em chestunnaru?" — Gap Analysis

How the big faceless channels actually operate, and our coverage:

| They do… | Why | We have it? |
|---|---|---|
| Download Amazon gallery photos & brand videos | raw material | ✅ scraper (gallery + video + MRP) |
| Edit 5-8s reels: hook → zoom → price → CTA | watch-time | ✅ video_maker |
| **Add voiceover** ("only ₹1099! link in bio!") | voice = trust + retention | ✅ **voiceover.py** (free neural TTS: English/Hindi/**Telugu**) mixed into reel + burned subtitles |
| Add trending/BGM audio | retention | ✅ **Bot composes its OWN original BGM** (`music_maker.py` — lo-fi C–G–Am–F loop, 100% copyright-free, zero downloads) and mixes it automatically. You can ALSO upload any trending/royalty-free sound via dashboard 🎵 — user audio always wins. ⚠️ Licensed songs can never be downloaded & reused (copyright strikes); even top creators only add those in-app |
| Post pin via Pinterest scheduler/API | consistency | ✅ official API + scheduler |
| Post IG reel + "comment LINK" bait | reach | ✅ IG module + **auto-reply to "link" comments** |
| Use affiliate tag/links everywhere | money | ✅ 6-network affiliate engine |
| As Amazon Associates, product images are OK to use for promotion | policy | ✅ that's exactly what the program allows (never claim ownership, add #ad) |
| Reply to every comment fast | engagement signal | ✅ IG auto-reply loop |

**Nothing big is missing anymore.** The only manual options left are intentional
(human-only by platform design): clicking ALLOW once, adding licensed trending
audio in-app if you want it, and replying to DMs.

## 📡 Ultimate Layer — alerts, buyer list, self-learning, one-command deploy

- **🔔 Telegram alerts** — phone lo notification when pins go live + daily
  report (`.env`: TELEGRAM_TOKEN/CHAT_ID; optional).
- **📧 Email capture** — landing pages collect buyer emails into YOUR list
  (dashboard shows count). Email lists convert 8-15% — your own asset, not
  rented traffic.
- **🕐 Hour-wise CTR learning** — scheduler posts denser in the hours YOUR
  clicks actually happen (learns from `/go/` click timestamps).
- **🩺 `python -m bot doctor`** — one command answers "anthi set avuthunda?":
  full ✅/❌ checklist with exact fixes.
- **🚀 `sudo ./deploy.sh`** — VPS pe one command: venv + deps + systemd
  service (auto-start on boot, auto-restart on crash). True 24×7 set.
- **`scripts/seed_demo.py`** — preview the pipeline with demo data, no creds.

## 💰 Conversion Engine — products EKUVA KONIPINCHADAM (sales focus)

Views alone ≠ money. These systems turn views into PURCHASES:

1. **% OFF starburst badges** — MRP is scraped; when discount ≥15% a yellow
   "63% OFF" burst is burned onto the pin. India's #1 click trigger.
2. **Urgency copy** — "⏳ Limited stock", "⚡ FLAT X% OFF today" auto-added to
   every description/caption.
3. **Mini landing pages** (`/go/<id>`) — warm-up page with hero photo, price +
   % OFF, trust bullets and a giant BUY button. Landing pages convert **3-8×**
   raw affiliate links (direct 1-2% vs landing 3-8%+).
4. **Festival & payday boosts** — Diwali/Rakhi/Holi/etc. calendar: 1.5× pins in
   the 7 days before each festival + festival keywords; 1.25× on salary days.
5. **CTR learning loop** — clicks counted per template; best-converting design
   used 70% of the time (exploit) + 30% testing (explore).
6. **Winner scoring** — proven-earner products post first (see below).

## 🏆 Winner Cloning — top channels em peduthunnavo, FIRST priority

Data-driven analysis of the highest-view affiliate channels (Pinterest + IG,
2026) shows the same winning niches again and again [2](https://sociavault.com/blog/pinterest-affiliate-marketing-data-driven)[4](https://pingroupie.com/blog/pinterest-trending-niches-2026):

1. **Women's Fashion** (kurtas/sarees — Meesho's kingdom; 13B+ pins category) [4](https://pingroupie.com/blog/pinterest-trending-niches-2026)
2. **Home Decor & Organization** (top performer, huge saves) [4](https://pingroupie.com/blog/pinterest-trending-niches-2026)
3. **Beauty & Skincare** (6B+ pins) [4](https://pingroupie.com/blog/pinterest-trending-niches-2026)
4. **Tech gadgets under ₹1,500** (India impulse zone; Flipkart/Amazon) [5](https://www.investkraft.com/blog/top-affiliate-marketing-websites-india-2026)
5. Kitchen tools → Jewellery → Kids → Fitness

`bot/trends.py` encodes this as a **priority engine**:
- **Autopilot hunts these niches first** (store search queries per niche)
- every product gets a **winner score** (niche priority + sweet-price ₹199–₹999
  + hooky words) — the queue posts **highest score first** 🏆
- dashboard shows the 🏆 score per product
- `python -m bot trends` prints the current winner list

⚠️ We clone the winning *categories* (that's data) — never someone's images or
videos. Original pins for the same winning niches = safe + effective.

---

## 🚀 Top-Views Advanced Systems (rank #1 tricks)

1. **Live Pinterest keyword mining** (`bot/keywords.py`) — pulls the exact phrases
   people type (Pinterest autocomplete/typeahead) and stuffs them into pin titles.
   Pins rank for what users SEARCH. 6h cache + offline fallback bank.
   Try it: `python -m bot keywords "earbuds under"`
2. **Niche keyword boards** (`board_strategy: niche`) — products auto-sort into
   "Fashion Finds" / "Tech Deals" / "Home & Kitchen Ideas" / "Beauty Picks"…
   Boards themselves rank in Pinterest search → many more surfaces.
3. **Own-domain link bridge** (`link.bridge: true` + `public_base`) — pins link to
   `https://YOURDOMAIN/go/<id>` which 302-redirects to your affiliate URL.
   Why top earners do this: Pinterest never sees a flagged affiliate short-domain,
   your domain builds trust, and **every click is counted** in the dashboard
   ("👆 Clicks" column) so you know exactly which pin/template earns.
   Host the dashboard on any cheap VPS/domain (or Cloudflare Tunnel) to use it.
4. **CTR feedback data** — clicks per product/template in SQLite → double down on
   winning designs, skip losers.

## ❓ "Idi ACTUAL ga work avuthunda?" — the honest truth

**YES — every piece is real, tested code** (17 unit tests, live dashboard, real
generated pins/reels in this repo). But be clear-eyed about what needs YOU:

| Part | Works without you? | Needs from you |
|---|---|---|
| Scrape, design pins, make reels, queue, scheduler, dashboard | ✅ proven here | nothing |
| Posting to Pinterest | ❌ (API security) | Business account + app credentials + one-time `bot auth` (5 min) |
| Affiliate links earning | ❌ | YOUR Amazon tag / Meesho affid / EarnKaro prefix (2 min each) |
| Instagram cross-post | ❌ | IG Professional + Meta token (10 min) |
| Live keyword mining / scraping | ⚠️ blocked on datacenter IPs | run on home Wi‑Fi / VPS — works there |

**Realistic expectations (from industry data):**
- Months 1–3: Pinterest evaluates your account — views grow slowly; focus on
  consistency + keywords, not money [5](https://www.shopify.com/pk/blog/pinterest-affiliate-marketing).
- Months 4–8: old pins compound → first regular commissions.
- Commissions confirm AFTER return windows (Meesho ~45 days) [4](https://earnkaro.com/blog/meesho-affiliate-program/).
- This is a **systems game**: 5–15 fresh pins/day, months of consistency = the
  "trick". Anyone promising overnight lakhs is selling a dream.

The bot gives you the exact machine top creators run; the fuel is your consistency. 💪

---

## 💸 Affiliate Programs Guide — anni ivvi join avvandi (2026)

Meeru promote cheyagలిగే programs — commission + join link:

| Program | Commission | Ela join avvali | Best for |
|---|---|---|---|
| **Amazon Associates** | 1–10% category-wise | [affiliate-program.amazon.in](https://affiliate-program.amazon.in) → signup → get `tag` | Electronics, gadgets |
| **Meesho Creator Club** (official) | 3–15% | Meesho app/website → Affiliate/Creator Club registration → links from Creator Dashboard [3](https://earnyatra.com/meesho-affiliate-program/) | Fashion, home, beauty — **trending!** |
| **EarnKaro** | up to 15% Meesho; Flipkart/Myntra/AJIO/Nykaa anni | [earnkaro.com](https://earnkaro.com/blog/meesho-affiliate-program/) app → free signup, **no documents** [4](https://earnkaro.com/blog/meesho-affiliate-program/) | Easiest starter — one app, many stores |
| **Cuelinks** | store-wise | [cuelinks.com](https://www.cuelinks.com) → any-link converter | Blogs + many Indian stores |
| **Myntra** | 4–10% | via Admitad / EarnKaro [3](https://earnyatra.com/meesho-affiliate-program/) | Fashion |
| **Flipkart** | category-wise | via EarnKaro / Cuelinks / Admitad | Mobiles, appliances |

**Pro tip:** EarnKaro lo Meesho new-user orders ki **12%**, old users ki 4% untundi; Meesho Creator Club lo top performers ki **15%** varaku [3](https://earnyatra.com/meesho-affiliate-program/)[4](https://earnkaro.com/blog/meesho-affiliate-program/). Rendu lo join avvandi — same product ki hang link use cheyandi.

Bot config lo pettaledhi:
```yaml
affiliate:
  amazon_tag: "yourtag-21"          # Amazon
  meesho_affid: "YOURMEESHID"       # Meesho Creator Club id
  earnkaro_prefix: "https://ekaro.in/enkrXXXX"  # EarnKaro profit links
```

### 🛍 Meesho strategy (best results kosam)
- **Categories:** fashion (kurtas, sarees), home & kitchen, beauty, jewellery — ₹199–₹699 range convert avతాయి best.
- Meesho = mass market, low price → impulse buys ekkuva. Return rate chudandi: fashion 299 @ 12% commission > gadget 1499 @ 4% with 20% returns [3](https://earnyatra.com/meesho-affiliate-program/).
- Bot lo Meesho links vesthe automatic ga `affid` + `utm_source=affiliate` attach avతundi; Creator Club dashboard lo clicks/commisions track cheskondi.
- Links **Creator Dashboard nunchi generate** cheyandi (copied app links track avvu) — aa links ni CSV/manual add lo vadandi.

---

## 📸 Instagram Automation (fully automatic cross-posting)

Every product Pinterest lo post avvగానే, same product mee **Instagram page** lo kuda
post avతుంది — single post / carousel / reel mode.

### One-time setup (~10 min)
1. Instagram account → **Switch to Professional account** (Settings → Account type).
2. Instagram ni oka **Facebook Page** ki connect cheyandi.
3. [developers.facebook.com](https://developers.facebook.com) → create app → add
   **Instagram API** product; permissions:
   `instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement`.
4. Long-lived token generate cheసి `.env` lo pettandi:
   ```
   INSTAGRAM_ACCESS_TOKEN=EAAB...
   IG_USER_ID=178414XXXXXXXXX
   IMGBB_KEY=...            # optional — designed pins host cheyadaniki (free, api.imgbb.com)
   ```
5. `config.yaml`:
   ```yaml
   instagram:
     enabled: true
     mode: carousel     # single | carousel | reel
     host_designed_pins: true   # your designed pin graphics IG lo (needs IMGBB_KEY)
   ```
6. Test: `python -m bot ig-check`

### How it posts
- **Carousel/single**: designed pin (ImgBB hosted) + product photo — caption tho
  hashtags + "Comment 'LINK' — link in bio!" (IG lo links clickable kaavu — bio lo
  Linktree/affiliate links pettandi).
- **Reel**: product page lo video unte aa video URL tho reel.
- Fail ayina Pinterest post affect avదు — IG best-effort only, logs lo untundi.

---

## ⚠️ Important notes

- **Amazon sometimes blocks scraping** from servers/VPNs. On your home Wi-Fi it usually
  works. If a URL fails, use **manual add** in the dashboard or CSV import — same
  pipeline afterwards.
- Don't spam: Pinterest rewards consistent, spaced posting. Default is 8 pins/day with
  random 40–65 min gaps — safe. Raise `pins_per_day` slowly once the account is warm.
- Affiliate disclosure: Pinterest ToS & FTC guidelines — your profile/descriptions should
  mention affiliate links ("I may earn a commission").
- Secrets live only in `.env` — never commit it (it's git-ignored).
