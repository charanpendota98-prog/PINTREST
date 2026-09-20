"""Seed the queue with 3 demo products (fresh DB) so you can preview the
full pipeline output without any credentials. Run: .venv/bin/python scripts/seed_demo.py"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.affiliate import AffiliateLinker
from bot.config import load_config
from bot.db import DB
from bot.engine import build_seo_text
from bot.pin_designer import PinDesigner
from bot.scraper import Product as PM
from bot.trends import score_product

cfg = load_config()
db = DB(cfg.db_path)
linker = AffiliateLinker(cfg)
designer = PinDesigner(cfg)

DEMO = [
    ("https://www.meesho.com/floral-kurta-set/p/demokurta", "meesho",
     "Women Yellow Floral Printed Cotton Kurta Set", "549", "1299",
     "data/media/demo_kurta.jpg"),
    ("https://www.amazon.in/dp/B0CDEAR01", "amazon",
     "boAt Airdopes 141 Bluetooth Truly Wireless Earbuds with 42H Playtime",
     "1099", "2999", "data/media/demo_earbuds.jpg"),
    ("https://www.flipkart.com/smartwatch/p/itmdemo123", "flipkart",
     "Noise ColorFit Pro 5 Smart Watch with AMOLED Display", "2499", "4999",
     "data/media/demo_watch.jpg"),
]

for url, src, title, price, mrp, img in DEMO:
    aff_url, network = linker.convert(url, src)
    disc = PM(url=url, price=price, mrp=mrp).discount_pct
    seo = build_seo_text(cfg, title, price, "INR", network, discount=disc)
    for v, tpl in enumerate(["split", "collage"]):
        pin = cfg.media_dir / f"pin_demo_{int(time.time() * 1000)}_{network}_v{v}.jpg"
        designer.create(img, title, f"₹{price}", pin, network, template=tpl,
                        extra_images=[img], discount=disc)
        db.add_product(source=src, url=url, affiliate_url=aff_url, title=title,
                       price=price, image_url=img, image_path=img,
                       pin_image=str(pin), variant=v, seo_text=seo,
                       score=score_product(title, price, src), discount=disc,
                       template=tpl, status="demo")  # PREVIEW ONLY — never posts
print("✅ demo queue seeded (PREVIEW ONLY — status=demo, autopilot "
      "can never post these):", db.stats())
