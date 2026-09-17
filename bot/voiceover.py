"""Voiceover engine — the #1 trick of faceless affiliate channels.

Top "Amazon finds" reels are NOT silent: they have a punchy Indian voiceover
("Wait for the price… only 1099 rupees! Link in bio!"). This module generates
that voiceover for FREE with Microsoft edge-tts (no API key), in English,
Hindi or Telugu — then the reel maker mixes it (plus your optional BGM) into
the video.

Voices (free, neural, natural):
  en-IN  → en-IN-NeerjaNeural      (Indian English, female)
  hi-IN  → hi-IN-SwaraNeural       (Hindi, female)
  te-IN  → te-IN-ShrutiNeural      (Telugu, female)  🇮🇳
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("pindrop.voice")

VOICES = {
    "en-IN": "en-IN-NeerjaNeural",
    "hi-IN": "hi-IN-SwaraNeural",
    "te-IN": "te-IN-ShrutiNeural",
}

SCRIPT = {
    "en-IN": "Wait for the price! {title}. Only {price}! Link in bio — grab it now!",
    "hi-IN": "Price sun kar hairan ho jaoge! {title}. Sirf {price}! Link bio mein hai!",
    "te-IN": "Price chuste shock avtaru! {title}. Kevalam {price}! Link bio lo undi!",
}


def script_for(lang: str, title: str, price: str) -> str:
    tpl = SCRIPT.get(lang, SCRIPT["en-IN"])
    short = " ".join(title.split()[:8])
    return tpl.format(title=short, price=price or "super price")


def generate(text: str, lang: str, out_path: str | Path) -> str:
    """Render TTS voiceover mp3; returns path ('' on failure)."""
    try:
        import edge_tts
    except ImportError:
        log.warning("edge-tts not installed — silent reels")
        return ""
    voice = VOICES.get(lang, VOICES["en-IN"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        comm = edge_tts.Communicate(text, voice)
        await comm.save(str(out_path))

    try:
        asyncio.run(_run())
        log.info("Voiceover (%s): %s", voice, out_path.name)
        return str(out_path)
    except Exception as exc:  # noqa: BLE001 — voiceover is a bonus, never fatal
        log.warning("Voiceover failed: %s", exc)
        return ""


def estimate_seconds(text: str) -> float:
    """Rough TTS duration (words / ~2.6 wps)."""
    return max(3.0, len(text.split()) / 2.6)
