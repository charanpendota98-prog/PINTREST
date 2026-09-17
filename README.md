# 📌 PinDrop Pro — Pinterest Affiliate Auto-Poster Bot

**Fully-advanced Pinterest affiliate automation.**

```
product URL ─▶ scrape (title/price/image) ─▶ YOUR affiliate link
           ─▶ 1000×1500 pin graphic design ─▶ SEO title/description/hashtags
           ─▶ post / schedule to Pinterest (image or video pin)
```

Amazon Associates + Meesho + Flipkart (EarnKaro / Cuelinks) — **anni support**.
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
