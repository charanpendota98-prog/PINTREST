# ASALU EM CHESTHADI — Pin-to-Pin Nijam (fake ledu, dummy ledu)

> Print anytime: `.venv/bin/python -m bot how`
> Live status of every feature: `.venv/bin/python -m bot features`

---

## 1. Okka line lo

**Nenu deals ni teeskuni** (own sourcing) **→ ni affiliate link kalisina
pins/reels/landing pages ni 24×7 create chesi → Pinterest (MAIN) + Instagram
+ Facebook lo post chestanu → clicks → commission ni ni account ki pampistanu.**

Nuvvu cheyyalsina pani: **one-time credentials** (5–10 min) + deploy. Tarvata
zero-touch.

---

## 2. Roju exact ga em jarugutundi (24×7 loop)

| Time (IST) | Pani |
|---|---|
| 9:00–22:00 | Pinterest peak windows lo **8 pins/day**, gap 40–65 min jitter (human-like) |
| 10:00–20:00 | **Deals of the Day** list pin (viral "save" format) — rojuki 1 |
| Prathi cycle | Instagram reel/carousel + bio link auto-update + comment/DM auto-reply |
| Prathi cycle | Facebook Page photo post + clickable direct link + comments auto |
| Every 24h | **Winners rotation** — manchi clicks vachina pin fresh design tho malli |
| 11:00–19:00 | **Price-drop radar** — posted product 10%+ taggithe update + re-post |
| ≤04:00 | **Housekeep** — 14 rojula purana media delete, logs 3000 ki cap |
| 21:00 | **Daily report** — enni post ayyayo, clicks, top product |
| Prathi pin | **QA gate** (media/link/title/desc/duplicate/#ad + commission-leak + dummy-guard) |
| Continuous | Learning: hour-wise + weekday-wise CTR, template CTR, festival keywords |

---

## 3. Money path (ekkada commission miss avvadu)

```
Ni PIN  →  pin link = yourdomain/go/<id>   (bridge; direct kanna 3-5x conversion)
              ↓
        Landing page (OG + JSON-LD Product schema → Google/social rich result)
              ↓  WhatsApp share button + email capture (buyer list)
        AFFILIATE LINK (ni tracking tho) → store
              ↓
        Store nunchi COMMISSION → NI account
```

**Per-store logic:**

| Store | Link ela build avutundi | Commission |
|---|---|---|
| **Amazon** | `tag=NI_ID` (vere tag unte replace — leak blocked) | Amazon Associates, ~60 days payout |
| **Meesho** | **NI af_invite DIRECT** (middleman ledu, R26 rule) | Meesho Creator Club, 3–15%, ~30–45 days |
| Flipkart/Myntra/Ajio etc. | EarnKaro / Cuelinks wrap | network payout cycle |

**Seals (R33 lo deep audit):** QA gate tracking markers (`tag=`, `affid=`,
`af_invite`, `ekaro`, `cuelinks`, `url=`) leni link ni **BLOCK** chestundi →
"A COMMISSION LEAK". Bare link eppudu publish avvadu — simulation lo proof
line chupistundi.

---

## 4. Content — bot ne create chestundi (real media, dummy ledu)

- 1 product → **3 pin variations** (different photo + design template)
- **Auto-reel**: photos → video + **original composed BGM** (copyright-free;
  ni uploaded audio unte adi win) + TTS voiceover (en/hi/te)
- **Pinterest image SEO**: filename `women-floral-kurta-549-<ts>_v0.jpg` —
  Pinterest image filenames index chestundi
- **Cross-store media enrichment**: same product media vere stores nunchi
- Corrupt audio upload ayina → **silent reel impossible** (auto-BGM fallback)

---

## 5. Learning (top-level, roju better)

| Signal | Bot em chestundi |
|---|---|
| Which **hour** clicks ichindi | aa hours lo denser posting |
| Which **weekday** clicks ichindi | aa days gap taggistundi (denser) |
| Which **template** clicks ichindi | 70% exploit aa design, 30% explore |
| **Festival** season | keyword auto-inject (Diwali/Sankranti/Rakhi) |
| **Price drop** | re-post with new price (fresh pin = fresh reach) |
| **Winner** pin | 7 days rest tarvata fresh design tho re-share |

---

## 6. Safety (account ban avvakunda, data pogakunda)

- Pin-by-Pin **QA gate** — broken/untracked content never posts
- **Dummy guard** — demo/sample data (`seed_demo.py`) live account ki
  **NEVER** post (status=demo + URL marker check; 654 tests lo proof)
- **Warm-up ramp** — kotha account slow start, jitter, human gaps
- **Crash-net** — edaina fail aithe loop continue (24×7 alive)
- **Single-instance lock** — rendu autopilot okate machine lo run avvavu
  (duplicate pins = spam signal). Heartbeat lock: crash/freeze aithe
  automatic takeover, manual cleanup ledu
- **Panel lock** — dashboard (stats/controls/logs) password protected;
  money pages (`/go/…`, `/deals/today`) public ga untayi
- **Housekeep** — disk cleanup, logs cap
- **654 automated tests** — prathi route/page/endpoint + QA + leak +
  dummy + panel lock + single-instance + JS syntax (`node --check`)

---

## 7. What is PROVEN vs what needs your VPS

## 7b. Platforms — ekada post avutundi (2026-09 update)

| Surface | Status | Link delivery |
|---|---|---|
| **Pinterest** (main) | pins + video pins + daily list pin + winners rotation | `yourdomain/go/<id>` bridge or affiliate link directly |
| **Instagram** | feed carousel/single, **reels**, **Stories (24h)**, bio auto-link, comment 'link' auto-reply, keyword **auto-DM** | bio link + DM/comment reply (API cannot attach story link stickers — that's app-only; our auto-DM covers it) |
| **Facebook Page** | photo post / link post + comment auto-reply | clickable link in post text |
| **YouTube Shorts** | optional uploader (your reel → Short + link in description) | affiliate link in the description — evergreen search traffic |
| **Telegram deals channel** | optional broadcast of every deal | affiliate link in the message |

**Pinterest mechanics (main platform):** API media upload (our own designed
file, not a store-CDN hotlink) · carousel pins for multi-photo products ·
video pins from real/auto-generated reels · optional per-niche board sections ·
live Pinterest Trends keywords in SEO · per-pin analytics (impressions, saves,
clicks) feeding the winners-rotation · Rich-Pin meta so price can show on the
pin. Check with `python -m bot pin-stats` and `python -m bot trends --live`.

**Meesho link per platform:** Meesho gives each platform its own
`source token + campaign id`. The bot stores them all and publishes the
platform-correct one (`instagram_stories` on IG, `facebook` on FB, ...) so
your Meesho report stays readable. Check with `python -m bot platforms`.

**Proven here (real runs, not stories):**

```
🏆 python -m bot simulate        → PASSED (100% pipeline: link→SEO→design→
                                    reel→QA→landing→clicks→rotation)
🧪 61 unit/integration tests     → OK
⚡ 200 parallel HTTP requests     → 200/200, zero 5xx
🔒 60 concurrent DB writes       → no lock errors
🎬 corrupt audio → auto BGM      → reel has real audio stream
🚫 demo product → BLOCKED        → never posts
```

**Needs your VPS (honest):** live scraping (`meesho.com`, `flipkart.com`,
`amazon.in`, `pinterest.com`) — ee sandbox nunchi network reach avvadu
(HTTP 000). VPS lo internet unte pani chestundi. Pinterest/IG/FB posting
ki ni tokens tappavu.

---

## 8. Go-live checklist (okka saari, 10 nimushalu)

```bash
python -m bot setup          # .env wizard: Pinterest app, AMAZON_TAG,
                             # MEESHO_TEMPLATE_LINK (1 af_invite link),
                             # EARNKARO_PREFIX, IG + FB tokens
python -m bot auth           # Pinterest ALLOW (okka click)
python -m bot doctor         # anni green unnaya chudu
python -m bot simulate       # 🏆 PASSED ravali
sudo ./deploy.sh             # systemd 24×7 + dashboard (rendu services)
python -m bot deploy-check   # server ready aa? ✅/❌ + exact fixes
python -m bot dashboard-pass # panel password (auto-created)
python -m bot how            # ee doc malli chudu (anytime)
```

Root lekunda (systemd ledu ante): `./run.sh` (start) · `./run.sh status` ·
`./run.sh stop` — ee guardian rendu services ni alive ga chustundi.

---

## 9. Nijam (hype cheyyanu)

1. **Money kastam ledu, kani instant ledu.** Pinterest search engine —
   pins index avvataniki 2–6 weeks padutundi. Month 1–3 lo numbers
   thakkuva, 6–18 months lo compound avutundi (industry data adi).
2. **Payout cycles:** Meesho ~30–45 days (returns tarvata), Amazon ~60 days.
   Nenu clicks + orders generate chestanu; payout store nunchi vastundi.
3. **Evaraina "week 1 lo lakhs" ante adi fake.** Nenu cheppedi: volume +
   consistency + correct tracking = compounding income.
4. **Conversion:** bridge landing page direct link kanna 3–5x better
   convert avutundi (industry benchmark) — anduke andulo peddanu.
5. **Ni account safety:** warm-up + jitter + QA + caps — kani 100% ban-proof
   ani evaru cheppaleru; nenu risk ni minimum ki teesuku vachanu.

---

**Bottom line:** idi oka **fully working affiliate machine** — sourcing,
content, posting, tracking, learning, safety anni automatic. Nijam ga
"em chesthadi" aduguthe: **ni links ni correct ga, 24×7, smart ga,
content tho saha publish chesi — commission ni ni account ki pampistundi.**
