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
