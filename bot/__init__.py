"""PinDrop Pro — Fully Advanced Pinterest Affiliate Auto-Poster Bot.

Modules
-------
config          – loads config.yaml + .env secrets
db              – SQLite storage (products, posts, logs)
scraper         – pulls product info from Amazon / Meesho / Flipkart / any page
affiliate       – converts plain links into your affiliate links
pin_designer    – generates beautiful 1000x1500 pin graphics
pinterest_api   – official Pinterest v5 API (OAuth, boards, pins, videos)
scheduler       – human-like daily posting queue
dashboard       – Flask web control panel
main            – CLI entry point
"""

__version__ = "1.0.0"
APP_NAME = "PinDrop Pro"
