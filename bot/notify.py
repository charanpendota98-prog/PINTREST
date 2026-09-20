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

    def send_to(self, chat_id: str, text: str) -> bool:
        """Send to a specific chat (the control bot's replies)."""
        if not (self.token and chat_id):
            return False
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={"chat_id": chat_id, "text": str(text)[:4000],
                      "disable_web_page_preview": "true"}, timeout=15)
            return resp.status_code == 200
        except requests.RequestException as exc:
            log.warning("Telegram send_to failed: %s", exc)
            return False

    def deal(self, title: str, price: str, url: str, image: str = "",
             discount: int = 0, rating: float = 0.0, reviews: int = 0,
             source: str = "") -> bool:
        """Broadcast a deal card to your public deals channel (optional).

        Telegram renders emoji fine, so the card carries the triggers readers
        actually scan: discount, REAL rating/rating count, price, store.
        Returns True only when Telegram accepted it (caller records it).
        """
        if not (self.token and self.deals_channel):
            return False
        bits = [f"🔥 {title}"]
        if discount >= 10:
            bits.append(f"🏷 {discount}% OFF")
        bits.append(f"💰 {price}")
        try:
            r, n = float(rating or 0), int(reviews or 0)
        except (TypeError, ValueError):
            r, n = 0.0, 0
        if r >= 4.0 and n > 0:
            cnt = (f"{n/100000:.2f}L" if n >= 100000
                   else f"{n/1000:.1f}k" if n >= 1000 else str(n))
            bits.append(f"⭐ {r:.1f}★ · {cnt} ratings")
        if source:
            bits.append(f"🛍 {source.title()}")
        bits.append(f"👉 {url}")
        bits.append("#Deals #Offer #India")
        caption = "\n".join(bits)[:1000]
        try:
            if image:
                requests.post(f"https://api.telegram.org/bot{self.token}/sendPhoto",
                              data={"chat_id": self.deals_channel, "photo": image,
                                    "caption": caption}, timeout=20)
            else:
                requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                              data={"chat_id": self.deals_channel, "text": caption,
                                    "disable_web_page_preview": "false"}, timeout=20)
            return True
        except requests.RequestException as exc:
            log.warning("Telegram deals broadcast failed: %s", exc)
        return False

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
