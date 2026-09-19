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

### 2. Pinterest account + app (5 min)

**2a. Business account — "Describe your business" screen lo emi pick cheyali?**

> 🔎 Full screen-by-screen sheet (ee doc chadavalasina avasaram ledu):
> `python -m bot onboard` — every Pinterest onboarding screen + what to select,
> including which cards are **skippable** (most of them are).

👉 **`Content creator`** pick cheyandi. (Ide correct answer — affiliate pages ki.)

Enduku:
- Affiliate account = nuvvu **content create** chestunnav (pins/reels), own
  store catalog ammudu ledu → "Content creator" (bloggers/influencers) exact fit.
- `Online merchant or marketplace` **website required** (adi lekapote proceed kadu)
  and adi actual shops ki; Pinterest **Verified Merchant Program** affiliate
  marketers ki **bandh** (official merchant guidelines) — ee route teesukunte
  later problems.
- `Service provider` / `Agency` / `Publisher` — mana model ki kaadu.
- `Other` — safe fallback, kani Content creator best (analytics + creator tools).

Tarvata (optional kani recommended, deploy ayyaka): business **website** =
mana landing page URL (`link.public_base`, e.g. `https://yourdomain.com`) →
Pinterest lo **Claim** cheyandi (Settings → Claimed accounts). Claim cheste
**Rich Pins** + pins ki mana site attribution vasthundi (extra reach).

**2a-2. "A few more details" screen — emi pick cheyali?**

**Business goals** (multi-select — ee moodu pick cheyandi):
- ✅ `Increase online sales` — ide mana core (commission)
- ✅ `Drive traffic to your site` — **chala important**: Pinterest analytics lo
  *outbound clicks* (mana money metric) ee goal tho highlight avutundi, and
  Pinterest ranking ki outbound clicks positive signal
- ✅ `Create content on Pinterest to grow an audience` — reach/creator tools
- ⬜ `Grow brand awareness` — optional (harm ledu)
- ⬜ `Generate more leads` — mana daggara email capture undi, kani primary kaadu
- ⬜ `Not sure yet` — vaddu

**Brand focus** (single select — okate pick cheyali):
👉 **`Home`** — enduku:
- 2026 lo Pinterest lo **#1 niche** = home decor & organization (billions of pins)
- Mana radar kuda **problem-solver home/kitchen** products ki highest score
  isthundi (organizers, storage, kitchen gadgets) — bot content ee focus lo untundi
- Fashion (#2), Beauty (#3) taruvata vastayi — kani focus okate undali,
  Pinterest single-focus accounts ni better ga rank chestundi
- Later change cheyyali anipisthe: Settings → Business → edit (lock kaadu)

**2a-3. "Claim your website" (after deploy — Rich Pins + attribution)**

Aa onboarding card lo **`Claim your website`** = Pinterest analytics +
**attribution for your content** + **Rich Pins** ki dooram. Bot idi one-command
ga chestundi:

```bash
python -m bot claim                 # steps + current state
python -m bot claim <TOKEN>         # meta tag inject + file route ON
```
- Bot mana pages lo `<meta name="p:domain_verify" content="...">` ni inject
  chestundi (landing, deals, login) — **DNS access avasaram ledu**.
- File method kuda ready: `https://yourdomain.com/pinterest-<token>.html`
  (public, no login — Pinterest fetch cheyyagaladu).
- Pinterest lo: Settings → Claimed accounts → Claim website → 'Add HTML tag'
  leda 'Upload HTML file' → Verify.

> Note: ee card mandatory kaadu ("Share ideas"/"Showcase your brand" la) —
> **Next** click chesi skip cheyyochu, tarvata eppudaina cheyyochu.
> Kani deploy tarvata idi cheyyadam = free extra reach (Rich Pins).

**2a-4. Pinterest "Connect app" form — field by field (EE ANSWERS PEDU)**

App review forms ki **company website + privacy policy link** kavali. Bot eh
aa pages ni serve chestundi (third-party site avasaram ledu):

| Page | URL (nee domain tho) | Em untundi |
|---|---|---|
| About | `https://yourdomain.com/about` | Company page — brand, what we do, how we earn, contact |
| Privacy | `https://yourdomain.com/privacy` | Data: email only if subscribe, anonymous click counts, no selling |
| Terms | `https://yourdomain.com/terms` | Prices/stock retailer-side, affiliate disclosure, liability |

Ee moodu **public** (login ledu) and domain-verify meta tag kuda veetilo
padutundi (`python -m bot claim <token>` tarvata).

```bash
python -m bot app                      # form ki exact answers (copy-paste)
python -m bot app --site https://yourdomain.com   # URLs ni real ga set cheyyi
```
`--site` ee URL ni `link.public_base` lo save chestundi (comments safe) — app
form lo `/about` + `/privacy` links automatic ga correct ga vasthayi. Ippudu set
cheyyakapote sheet lo `http://<VPS-IP>:5000/about` la placeholders chupistundi
(and "submit cheyyaku mundu set cheyyi" ani warn chestundi).

Form answers (personal-use app ki — idi correct, honest route):

| Field | Answer |
|---|---|
| App name | `Gharvanaa Deals Publisher` (company name undi, "Pinterest" ledu) |
| Company name | `Gharvanaa` |
| Company website | `https://yourdomain.com/about` |
| Privacy policy | `https://yourdomain.com/privacy` |
| App purpose | **Personal API access (single, personal use)** |
| Who are you sharing access with? | **Only me / Myself** |
| Use cases | Pin creation & scheduling ✅ · Publishing content on Pinterest ✅ · Getting data about your account ✅ · Reporting ✅ (migilinavi vaddu) |
| Audience | **Businesses** (nee business ee app vaadutundi) |
| Reads Pins/Boards data | **Yes, mine** (own pins/boards matrame) |

> 🔒 **Takuva scopes = easy review + safe account.** Ad campaign / Pinner App /
> Ecommerce / Recommendations vaddu — avi nee use case kaadu — review slow avutundi, extra questions vasthayi.
> 🖼️ App icon: `brand/app_icon_1024.png` (house+heart+bag, Pinterest logo ledu).

**2a-5. App create ayyaka — Trial → Standard (public pins) path**

App page malli open cheyyali ante (console tab close aithe):
`python -m bot app --where` → click-path + nee app ID tho direct URL.

App approve ayyaka ee 4 steps (order lo):

| # | Step | Command / place |
|---|---|---|
| 1 | **Redirect URI** add | app page → Redirect URLs → `http://localhost:8888/callback` (http+localhost allowed) |
| 2 | **Trial token** (immediate testing) | app page → "Generate access tokens" (Trial) → copy → `.env`: `PINTEREST_ACCESS_TOKEN='...'` |
| 2b | **Proof** kavali ante | `python -m bot token-check` (read live) · `python -m bot token-check --write-test` (private board create+delete) |
| 3 | **OAuth** (permanent) | app secret unlock ayyaka: `python -m bot auth-url` → code → `python -m bot auth --code <CODE>` |
| 4 | **Standard access request** | app page → **Upgrade** → `python -m bot app --upgrade` answers copy-paste |

> 🔒 **'Trial access pending' lo Redirect URLs field grey/disabled ga untundi**
> (App secret kuda lock). Adi Pinterest lock — tappu kaadu. Ippudu cheyyalsinadi:
> `Generate Access Tokens` → `.env` → `python -m bot token-check`. Full detail:
> `python -m bot app --pending`.
>
> ⚠️ **Trial = public pins kaadu.** Pinterest access table lo unde: Trial mode lo
> "Writing standard Pins → **visible only to the user who creates them**"
> (1000 req/day). Ante pins create avutayi kani **evariki kanipistavi kaavu** →
> reach/clicks/commission ledu. So **Standard access** eh real go-live gate;
> trial ni pipeline test ki vaadandi.
>
> `python -m bot doctor` → "Pinterest token (auth done)" line lo ee mode live
> ga undo chupistundi (OAuth / trial token).

**2b. Developer app (API access):**
1. Go to **https://developers.pinterest.com/apps/** → *Create app*.
2. In the app: add the redirect URI exactly as: `http://localhost:8888/callback`
3. Enable scopes: `boards:read, boards:write, pins:read, pins:write, user_accounts:read`
4. Copy **App ID** and **App Secret**.

### 2c. Brand name + profile SEO (one command)

Pinterest is a search engine, so the **display name is a ranked field**. The
2026 format that works: `Brand | Primary Niche Keyword`, ideally ≤30 chars so it
never truncates on mobile. The **pin strip** is different — it is printed on
every pin artwork and must stay SHORT (2-4 words).

```bash
python -m bot brand                              # rules + name ideas + bio + boards
python -m bot brand "PinDrop Deals | Home & Kitchen"   # save your choice
```
Saving writes both roles into `config.yaml` (`design.brand_name` = short strip,
`brand.display_name` + `brand.bio` = profile copy) and leaves every other line,
including comments, untouched.

Also pick the **username/handle** as the plain brand (e.g. `pindropdeals`) and
use the same handle on Instagram so the two accounts reinforce each other.

> 📝 `python -m bot brand` ippudu Pinterest **"Edit profile" form ni
> field-by-field** print chestundi — Name (keyword field), Username (@handle),
> About (bio), Pronouns (blank), Website (**warning tho**).
>
> ⚠️ **Common trap:** `pindropdeals` ni **Name** field lo pettakandi (appudu
> keyword poyindi) — adi **Username** field lo pettali.
**Handle (username) rules + "already taken" ladder**

Pinterest username: **3-30 chars**, letters + numbers + underscore matrame
(hyphen ❌ dot ❌ space ❌, anni numbers ❌). Instagram kuda ide set allow
chestundi → **oke handle rendu chotla** vaadandi (brand consistency).

```bash
python -m bot handle                 # rules + ranked fallbacks + save hint
python -m bot handle pindrop_deals   # save the one you picked
```

`pindropdeals` taken aithe ee order lo try cheyyandi (top = best):

| # | Handle | Enduku |
|---|---|---|
| 1 | `pindrop_deals` | Brand ki closest (space → underscore), cleanest |
| 2 | `pindropdealshome` | Niche keyword (Home) — search/suggest lo brand+niche |
| 3 | `pindropdealsindia` | Market keyword — India account la kanipistundi |
| 4 | `thepindropdeals` | Prefix — real brand la, fan account la kaadu |
| 5 | `getpindropdeals` | Prefix — action word, voice search ki best |
| 6-9 | `...hq` · `...co` · `...daily` · `...shop` | Chinnadi + brand-ish |
| 10 | `pindropdeals01` | ⚠️ **Last option** — numbers = duplicate/fan la kanipistundi |

Antha `pindrop*` taken aa? Fresh family: `dealdropsindia`, `homedealsdrop`,
`smartfindsindia`, `gharfinds`, `dealfindsindia`.

> 🔧 **Trailing/leading underscore avoid cheyyandi** (`pindrop_deals_` la):
> Pinterest allow chestundi, kani generated/bot account la kanipistundi.
> Intentionally separate cheddam anukunte `pindropdeals_home` (brand + niche)
> leda `pindrop_deals` vaadandi. `python -m bot handle <name>` cleaner variants
> ni cheptundi.

### 🏆 FINAL BRAND (R59): **Gharvanaa** — `@gharvanaa`

| Field | Value |
|---|---|
| **Name** (ranked keyword field) | `Gharvanaa | Home Deals & Finds` (30 chars ✨) |
| **Username / handle** | `gharvanaa` (same on Pinterest + Instagram) |
| **Pin strip** (artwork) | `Gharvanaa` |
| **About** | `Gharvana shares hand-picked deals — home, kitchen, fashion & beauty finds under ₹999. Organizers, gadgets & kurtas. New drops daily. Tap the pin to shop.` (153) |

**Enduku "deals" vadilesamu** (research tho, opinion kaadu):
- `NestKart` → nestkart.in live store, same categories
- `NestBazaar` → `pinterest.com/nestbazaar1` — **active home & kitchen
  affiliate account, exact same model**
- `Aangan` → aanganofindia.com · `Nestora` → nestorahome.us / nestora.pk ·
  `Grihika` → girikaflair.com
- Descriptive names anni crowded → **coined name = ownable**, and keywords
  belong in the NAME field (adi ranked), not in the handle (URL matrame).

**Gharvanaa = Ghar + Nirvana** ("home bliss") — 9 letters, spam-coding ledu
(loot/free/cheap ledu), numbers ledu.

> ✍️ **Enduku double 'a'?** `gharvana` handle already taken. Spelling variant
> theesukunnam → **brand word kuda ippudu fully ownable**: ee spelling tho
> inkevaru ledu, so Pinterest search lo "gharvanaa" = 100% nee account.
> Rendu fields oke spelling lo undali (strip + NAME) — `bot ready` adi
> automatic ga check chestundi.

#### "Deals" ni brand name lo pettala? (R57 — research tho answer)

**Ledu** — "SuperDeals" laanti peru = **promo phrase, brand kaadu**:

| Check | SuperDeals |
|---|---|
| Already in use | Super Deals India (FB), Superdeals.in (FB), Online SUPER DEALS (Chandigarh) — plus every deals page ever |
| Recall | Generic — evaru gurthu pettukoru (brand identity ledu) |
| Pinterest | `super/hot/daily` promo words spam signal → distribution thakkuva |
| Ownership | Trademark/claim cheyyalem — evadaina vaadagaladu |

**Correct formula:** owned brand word + `Deals` keyword **NAME field** lo —

| Slot | Value | Enduku ikkada |
|---|---|---|
| Brand word (pin strip) | `Gharvana` | Short, ownable, gurthu pettukuntaru |
| NAME field | `Gharvana | Home Deals & Finds` | **Ranked + visible** — keywords ikkada pani chestayi |
| Bio / boards | "hand-picked deals" + categories | Keyword + trust |

```bash
python -m bot name "Gharvana"          # score + deals formula + collisions
python -m bot name "SuperDeals"        # ⛔ "already in use — vaddu" ani cheptundi
```

> 📦 **"Anni products pedudtham"** — correct, kani oka **anchor niche** undali
> (home & kitchen). Pinterest topical authority istundi (focus unna account ki
> ekkuva distribution); "everything store" accounts tagguthayi. Boards lo
> Fashion/Beauty/Kids unnayi — so ani categories vestham, anchor okate.

```bash
python -m bot name "Gharvana" --live   # score + live handle/domain check
python -m bot name --next              # 🚨 handle taken? → full plan
python -m bot handle check --pick gharvanahome gharvanadeals thegharvana
                                       # rendu chotla free unna modati handle auto-save
```

#### Handle already taken aa? (ee case lo)

**Brand name marchalsina avasaram ledu.** Pinterest lo NAME unique kaadu —
handle matrame unique. Order lo try cheyyandi:

| # | Handle | Enduku |
|---|---|---|
| 0 | `gharvanaa` | ✅ **TEESUKUNNADI** — spelling variant, brand word fully ownable |
| 1 | `gharvanahome` | Brand + niche (Home) — SEO-friendly (ee line nunchi fallback) |
| 2 | `gharvanadeals` | Brand + "deals" — positioning ki match |
| 3 | `gharvanafinds` | Brand + "finds" — NAME field wording ki match |
| 4 | `thegharvana` | Official account la kanipistundi |
| 5 | `gharvanaindia` | India market signal |
| 6 | `gharvanahq` | Short, brand-studio feel |
| 7 | `gharvana_home` | Intentional separator (trailing underscore **vaddu**) |

**Fully ownable brand kavali ante** (name + handle rendu nee vi): spelling
variant teesukondi — `Gharvanaa`, `Gharvanah`, `Gharvaniya`, `Gharvanika`.
Appudu NAME field kuda maarchali (`Gharvaniya | Home Deals & Finds`).

> ⚙️ **One command (VPS lo):**
> `python -m bot handle check --pick gharvanahome gharvanadeals gharvanafinds`
> → Pinterest + Instagram rendu chotla free unna **modati** handle ni
> automatic ga save chestundi (blocked/unknown ni skip chestundi, guess cheyyadu).

Brand marchali ante (rendu commands, config comments safe):
`python -m bot brand "Brand | Home & Kitchen"` + `python -m bot handle <name>`

### Handle wiring

Saved handle (`brand.handle`) 4 chotla pani chestundi:
1. landing page JSON-LD lo `sameAs` (Pinterest + Instagram profile URLs) —
   Google/social entity linking;
2. landing page lo "📌 Follow @gharvana" link — visitors ni followers ga
   marchutundi (free reach);
3. `bot onboard` / `bot brand` lo ide handle kanipistundi (paste cheyyadaniki);
4. `bot ready` profile item auto-detect (handle+name+bio+strip unte done).

> 💡 **Name field unique kaadu** — `PinDrop Deals | Home & Kitchen` pettachu
> (adi keyword/ranking field). Handle lo keywords stuff cheyyakandi (adi URL
> matrame, ranking ki peddaga use ledu).

> ⚠️ **Website field lo `t.me` / `wa.me` / shortener links pettakandi** —
> Pinterest vaatini claim cheyyanivvadu (Rich Pins + attribution pothayi) and
> loot-deal links ni spam pattern ga chustundi. Deploy ayyaka mana landing
> domain petti, appudu claim cheyyandi (`python -m bot claim`).

### 3. Secrets — copy `.env.example` → `.env` and fill in

> 🔑 **Easier: `python -m bot creds --amazon <tag> --earnkaro <ekaro.in/enkr…>`**
> — validate chesi .env lo save chestundi (comments safe, `chmod 600`), tarvata
> status chupistundi. Thappu format isthe save cheyyadu, enduku + fix cheptundi.

> ⚠️ **EarnKaro referral link (`earnkaro.com?r=…`) pani cheyyadu** — adi vere
> vaallu EarnKaro join ayye link, product clicks ki commission raadu.
>
> 🏷 **Best: EarnKaro API token** — `python -m bot earnkaro capture` (browser
> login → token auto-save), leda `python -m bot creds --earnkaro-token '<jwt>'`.
> Appudu bot prati product URL ni **nee own profit link** ki convert chestundi —
> `webapi.earnkaro.com/api/affiliate/link-converter` (EarnKaro site/app vaade API),
> commission nee EarnKaro account ki **direct** (reseller / middleman ledu).
> Live proof: `python -m bot earnkaro probe` · cache: `data/earnkaro_links.json`
> (product okkasari convert aithe malli call ledu — API down aina post avutundi).
>
> ℹ️ Deeplink **prefix** (`ekaro.in/enkr…` + `?url=<product>`) legacy fallback —
> API token unte daanavasaram ledu. Tracking ledu ante aa store pins QA gate
> **quarantine** chestundi (leak avvadu, kani post avvavu).
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
  earnkaro_api_token: "eyJhbGciOi…"  # ⭐ `python -m bot earnkaro capture`
  earnkaro_prefix: ""               # legacy fallback only (no API token)
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

# 🖥 web control panel  (owner-locked — password printed at startup)
.venv/bin/python -m bot dashboard    # http://localhost:5000

# 🔐 forgot the panel password?
.venv/bin/python -m bot dashboard-pass

# 🚀 "deploy ki ready aa? inka em kavali?" → one command, full checklist
.venv/bin/python -m bot deploy-check
```

Keep `run` alive 24×7 on any cheap VPS/PC, or with `nohup`:
```bash
nohup .venv/bin/python -m bot run > pindrop.log 2>&1 &
```

### 🔐 The panel is LOCKED, the money pages are OPEN
The dashboard is an **admin area** (post now, delete products, read logs), so it
is password-protected the moment you deploy:

| Route | Access |
|-------|--------|
| `/`, `/api/*` (panel + controls) | 🔒 password (auto-created on first run) |
| `/go/<id>`, `/deals/today`, `/subscribe/<id>`, `/media/*` | 🌍 public — this is the money path (pin → landing → affiliate link) |
| `/healthz` | 🌍 public uptime probe |

- Password: `DASHBOARD_PASSWORD` in `.env`, else auto-generated once and saved
  in `data/dashboard_password.txt` (see it: `python -m bot dashboard-pass`).
- Log in on your phone once — the session lasts 30 days.
- Scripts/curl: `curl -H "X-Dashboard-Token: <password>" http://ip:5000/api/status`
- 5 wrong passwords from one IP = 429 block for 5 minutes.
- Locked API calls return `401 {"ok":false,"login":"/login"}` — never a 500.

**Firewall note (VPS):** the panel listens on `dashboard.host:port`
(default `0.0.0.0:5000`). If you only need it from your own network, either set
`DASHBOARD_PASSWORD` (recommended) or restrict the port
(`sudo ufw allow 5000/tcp` / SSH tunnel `ssh -L 5000:127.0.0.1:5000 user@vps`).

### 🛡 One bot, never two (single-instance lock)
`python -m bot run` and `python -m bot dashboard` take a **heartbeat lock**
(`data/locks/*.lock`). A second copy refuses to start and tells you who holds
it, so the same product can never be posted twice (duplicate pins are spam
signals — exactly how accounts get limited) and two panels can't fight over
port 5000:

```bash
$ python -m bot run
⏸  Autopilot already running — another instance is already running: pid 3147
   Two schedulers = duplicate pins + ban risk, so this copy exits.
```
A crashed or frozen instance (no heartbeat for 120s) is taken over
automatically — you never have to delete lock files by hand.

```bash
./run.sh            # start both guardians (refuses to double-start)
./run.sh status      # guardian? poster? panel? — one line each
./run.sh stop        # stop guardians + children
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
(real keywords), `python -m bot features` (what's switched on),
`python -m bot radar` (most useful products, scored 0-100), `python -m bot playbook`
(the 2026 hook/carousel/timing playbook the bot follows automatically),
`python -m bot links` (are the affiliate links alive and still tagged?),
`python -m bot earnings` (honest commission estimate from real clicks) and
`python -m bot report --days 7 [--telegram]` (period report) and
`python -m bot ready` (exactly what is left for YOU to do — nothing else) and
`python -m bot scale` (your ₹ target converted into honest clicks/posts-per-day
math, with the measured gap and an ETA once there is real data). Owner control:
`python -m bot pause "reason"` / `python -m bot resume` — also on the panel's
💰 Money tab together with Pause/Resume, earnings and link-health buttons.

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
| Instagram (feed / product tag) | `instagram_product_tag` (yours) | the feed link surface Meesho made for product tagging |
| Instagram Story | `instagram_stories` (yours) | story link sticker surface |
| Facebook | `facebook` (yours) | clean Meesho report |
| YouTube Shorts/videos | `youtube_long_form` (yours) | Meesho's YouTube surface |
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
- **🚀 `sudo ./deploy.sh`** — VPS pe one command: venv + deps + **two** systemd
  services (poster + panel, auto-start on boot, auto-restart on crash).
  Non-root? `./run.sh` starts the same pair as guardians. True 24×7 set.
- **🚦 `python -m bot deploy-check`** — VPS preflight: python/ffmpeg/disk/
  systemd/port/panel-lock/money-link/Pinterest-creds, each with the exact fix
  command. Exit 0 = ready to deploy.
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

## 🤖 Auto-DM / Auto-Reply (free ManyChat equivalent — official API)

**Endi jarugutundi (exact flow), roju automatic:**

1. Nuvvu post chesina reel/carousel ki evaraina comment chestharu: `link`,
   `price`, `buy`, `rate`, `order`, `chahiye`, `kitna`… (13 trigger words).
2. Bot aa comment ni chusi **aa commenter ki PRIVATE DM** pampistundi —
   andulo **aa product peru + price + NE DIRECT affiliate link** untundi
   (Instagram official *private reply* API; comment chesina 7 rojulu varaku
   allowed).
3. Same comment ki **public reply** kuda pedtundi ("link in bio!") — reach
   peragadaniki (comments lo clickable link undadu, anduke bio/DM route).
4. Oke comment ki **rendu saarlu DM povadu** — DB ledger lo comment id store
   avutundi (restart chesina gurtu untundi).
5. DM lo kuda evaraina `link`/`price` type chesthe → bot product match chesi
   link tho answer istundi (`instagram.auto_dm`).
6. Prathi post tarvata **bio website auto-update** avutundi aa deal ki —
   "link in bio" nijamga pani chestundi (`instagram.auto_bio_link`).

**Edi kaadu (honesty):** evaru interact cheyyani follower ki DM pampinchalemu —
adi Instagram policy (spam control), ManyChat ki kuda ade limit. Comment ki
private reply = 7 rojulu; conversation continue = 24 hours. Ee bot third-party
service vaadadu, password share cheyyadu — direct official API.

**Scopes (token lo undali):** `instagram_basic`, `instagram_content_publish`,
`instagram_manage_comments` (public replies), **`instagram_manage_messages`**
(private DM + inbox). Token lo messages permission lekapote bot public reply
ki fallback avutundi (pani agadu) — `python -m bot ig-check` lo exact ga
cheptundi enti missing o.

**Controls:** `instagram.private_dm` (DM on/off), `instagram.public_reply`,
`instagram.auto_dm`, `instagram.auto_bio_link`, `instagram.triggers` (keywords +
templates), `instagram.reply_delay_seconds` (human-ish pause).

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
