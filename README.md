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
| 🕷 **Smart Scraper** | Amazon.in / Meesho / Flipkart / any shop — JSON-LD → OpenGraph → CSS fallback |
| 💰 **Affiliate Engine** | Amazon `?tag=`, Meesho `affid`, Flipkart `affid`, EarnKaro & Cuelinks deep-link wrapping |
| 🎨 **Auto Pin Designer** | Pinterest-perfect 1000×1500 graphics: product card, price badge, brand strip, CTA |
| 📝 **SEO Writer** | Keyword hashtags + deal-style descriptions for every pin |
| 📌 **Official Pinterest API v5** | OAuth, boards auto-create, image pins, video pins, scheduling up to 14 days |
| ⏰ **Human-like Scheduler** | N pins/day inside IST posting window, randomized gaps (safe for your account) |
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

# 🖥 web control panel
.venv/bin/python -m bot dashboard    # http://localhost:5000
```

Keep `run` alive 24×7 on any cheap VPS/PC, or with `nohup`:
```bash
nohup .venv/bin/python -m bot run > pindrop.log 2>&1 &
```

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

## ⚠️ Important notes

- **Amazon sometimes blocks scraping** from servers/VPNs. On your home Wi-Fi it usually
  works. If a URL fails, use **manual add** in the dashboard or CSV import — same
  pipeline afterwards.
- Don't spam: Pinterest rewards consistent, spaced posting. Default is 8 pins/day with
  random 40–65 min gaps — safe. Raise `pins_per_day` slowly once the account is warm.
- Affiliate disclosure: Pinterest ToS & FTC guidelines — your profile/descriptions should
  mention affiliate links ("I may earn a commission").
- Secrets live only in `.env` — never commit it (it's git-ignored).
