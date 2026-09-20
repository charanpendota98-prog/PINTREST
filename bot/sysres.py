"""System-resource awareness — the small-VM safety net.

Oracle's free AMD micro (VM.Standard.E2.1.Micro) has **1 GB RAM**. Rendering
a 720×1280 reel opens PIL images plus an ffmpeg encoder; together they can
push a 1 GB box into the OOM killer, which would kill the scheduler
MID-POST (worst possible moment). Everything here answers one question
honestly: "does this machine have room to render a video right now?"

Numbers are read from /proc/meminfo on Linux and degrade to "unknown"
(never a crash) everywhere else.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("pindrop.sysres")

# A 720×1280 render needs roughly this much headroom (frames + encoder).
REEL_NEED_MB = 350
LOW_MEM_MB = 1500          # below this we treat the box as "small"


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            num = rest.strip().split()[0] if rest.strip() else "0"
            try:
                out[key.strip()] = int(num) // 1024        # kB → MB
            except ValueError:
                continue
    except OSError:
        pass
    return out


def mem_total_mb() -> int:
    info = _meminfo()
    if info.get("MemTotal"):
        return info["MemTotal"]
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * size / (1024 * 1024))
    except (ValueError, OSError, AttributeError):
        return 0                                   # unknown


def mem_available_mb() -> int:
    info = _meminfo()
    if info.get("MemAvailable"):
        return info["MemAvailable"]
    if info.get("MemFree"):
        return info["MemFree"]
    return 0                                       # unknown


def swap_total_mb() -> int:
    return _meminfo().get("SwapTotal", 0)


def is_low_memory(threshold_mb: int = LOW_MEM_MB) -> bool:
    total = mem_total_mb()
    return bool(total and total < threshold_mb)


def can_render_video(need_mb: int = REEL_NEED_MB) -> tuple[bool, str]:
    """(ok, human reason). Unknown values never block — fail-open by design."""
    total = mem_total_mb()
    avail = mem_available_mb()
    if not total:
        return True, "memory info ledu (fail-open)"
    if avail >= need_mb:
        return True, f"{avail} MB available (need {need_mb} MB)"
    swap = swap_total_mb()
    if swap >= 1024:
        return True, (f"RAM thin ({avail} MB) kani {swap} MB swap undi — "
                      f"slow ga render avutundi")
    return False, (f"RAM thin: {avail} MB available, swap {swap} MB — "
                   f"reel skip (image pin post avutundi; swap add cheyyali: "
                   f"'sudo fallocate -l 2G /swapfile && sudo mkswap /swapfile "
                   f"&& sudo swapon /swapfile')")


def disk_free_mb(path) -> int:
    try:
        return int(shutil.disk_usage(str(path)).free / (1024 * 1024))
    except OSError:
        return 0


def describe() -> str:
    """One-line summary for `bot doctor` / `bot deploy-check`."""
    total, avail, swap = mem_total_mb(), mem_available_mb(), swap_total_mb()
    if not total:
        return "memory: unknown"
    tag = " (⚠️  small VM — swap + reel guard active)" if is_low_memory() else ""
    return (f"memory: {total} MB total, {avail} MB free, swap {swap} MB{tag}")
