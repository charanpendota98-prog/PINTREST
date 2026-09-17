"""Telegram alerts — your phone rings when the machine makes moves.

Optional (TELEGRAM_TOKEN + TELEGRAM_CHAT_ID in .env). Best-effort: a failed
notification never blocks posting.

Get a token: talk to @BotFather → create bot → token.
Get chat id: message your bot once, then open
https://api.telegram.org/bot<TOKEN>/getUpdates
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("pindrop.notify")


class Notifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        # top Indian affiliates run Telegram DEALS channels — broadcast mode:
        self.deals_channel = os.getenv("TELEGRAM_DEALS_CHANNEL", "").strip()

    def deal(self, title: str, price: str, url: str, image: str = "") -> None:
        """Broadcast a deal card to your public deals channel (optional)."""
        if not (self.token and self.deals_channel):
            return
        caption = (f"🔥 {title}\n💰 {price}\n👉 {url}\n\n#Deals #Offer #India")[:1000]
        try:
            if image:
                requests.post(f"https://api.telegram.org/bot{self.token}/sendPhoto",
                              data={"chat_id": self.deals_channel, "photo": image,
                                    "caption": caption}, timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                              data={"chat_id": self.deals_channel, "text": caption,
                                    "disable_web_page_preview": "false"}, timeout=20)
        except requests.RequestException as exc:
            log.warning("Telegram deals broadcast failed: %s", exc)

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={"chat_id": self.chat_id, "text": text[:4000]},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException as exc:
            log.warning("Telegram notify failed: %s", exc)
            return False

    def posted(self, title: str, pin_id: str, network: str) -> None:
        self.send(f"📌 Pin LIVE on Pinterest!\n{title[:80]}\n[{network}] pin {pin_id}")

    def daily_summary(self, stats: dict, clicks: int) -> None:
        self.send(
            f"🤖 PinDrop daily report\n"
            f"📥 queue {stats.get('queued', 0)} | ✅ posted {stats.get('posted', 0)} | "
            f"❌ failed {stats.get('failed', 0)}\n👆 total clicks: {clicks}"
        )
