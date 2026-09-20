"""Oracle Cloud "Always Free" idle-reclaim guard.

THE REAL RISK (verified on Oracle's own policy): OCI may RECLAIM an Always
Free instance when, over a 7-day window, it looks idle —

  * CPU utilization (95th percentile) < 10%
  * Network utilization < 10%
  * Memory utilization < 10%   (A1/Ampere shapes)

A telegram-polling affiliate bot is mostly idle between posts, so a free VM
can be stopped/reclaimed — and then the shape may be unavailable to recreate.

Two honest fixes, in order of preference:

  1. Upgrade the account to Pay-As-You-Go. Always-Free resources stay free
     (set a $1 billing alert); idle reclaim does NOT apply to PAYG accounts.
     This is Oracle's own recommended path.
  2. This module: `python -m bot keepalive` keeps the instance measurably
     busy — a small, bounded CPU duty cycle plus an optional resident memory
     block — so it never looks idle. It does REAL work per cycle (timing it),
     nothing destructive, and you can stop it any time with Ctrl+C.
"""
from __future__ import annotations

import logging
import math
import os
import time

log = logging.getLogger("pindrop.keepalive")

# Oracle judges the 95th percentile; sitting a bit ABOVE 10% keeps margin.
DEFAULT_TARGET_PCT = 13.0
DEFAULT_CYCLE = 60.0          # seconds per cycle
DEFAULT_MEM_MB = 1024         # ~1 GB on a 12 GB A1 = well over the 10% line


def keepalive_plan(ncpu: int, target_pct: float = DEFAULT_TARGET_PCT,
                   cycle: float = DEFAULT_CYCLE) -> tuple[float, float]:
    """(busy_seconds, sleep_seconds) of ONE core per cycle.

    Utilization of the whole machine = busy / (cycle * ncpu), so hitting
    `target_pct` of total capacity means busy = target% × cycle × ncpu.
    """
    ncpu = max(1, int(ncpu or 1))
    target_pct = max(1.0, min(90.0, float(target_pct)))
    cycle = max(10.0, float(cycle))
    busy = min(cycle * 0.5, (target_pct / 100.0) * cycle * ncpu)
    return round(busy, 2), round(cycle - busy, 2)


def cpu_burn(seconds: float) -> float:
    """Burn ~`seconds` of CPU on one core. Returns a checksum (so the work is
    real and cannot be optimised away)."""
    end = time.monotonic() + max(0.0, float(seconds))
    total = 0.0
    while time.monotonic() < end:
        for i in range(1, 20001):
            total += math.sqrt(i) * (i % 7 + 1)
    return total


def hold_memory(mb: int) -> bytearray:
    """Reserve resident memory (pages touched) — for the A1 memory rule."""
    mb = max(0, int(mb))
    if not mb:
        return bytearray()
    buf = bytearray(mb * 1024 * 1024)
    step = 4096                                    # touch every page
    for i in range(0, len(buf), step):
        buf[i] = 1
    return buf


def cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))          # container-aware
    except AttributeError:
        return os.cpu_count() or 1


def run_forever(target_pct: float = DEFAULT_TARGET_PCT,
                mem_mb: int = DEFAULT_MEM_MB,
                cycle: float = DEFAULT_CYCLE,
                once: bool = False) -> None:
    """Keep the instance above Oracle's idle thresholds."""
    n = cpu_count()
    busy, rest = keepalive_plan(n, target_pct, cycle)
    buf = hold_memory(mem_mb)
    print(f"🛡 Oracle idle-guard: {n} CPU, {target_pct:g}% duty target → "
          f"{busy:g}s busy / {rest:g}s idle per {cycle:g}s cycle, "
          f"memory held: {mem_mb} MB")
    print("   (PAYG account aithe idi avasaram ledu — reclaim rule padadu)")
    while True:
        try:
            t0 = time.monotonic()
            cpu_burn(busy)
            if buf:                                # re-touch pages occasionally
                for i in range(0, len(buf), 65536):
                    buf[i] = (buf[i] + 1) % 2
            spent = time.monotonic() - t0
            if once:
                log.info("keepalive: one cycle done (%.1fs busy)", spent)
                print(f"✅ one cycle done — {spent:.1f}s CPU burned, "
                      f"press Ctrl+C not needed (--once)")
                return
            time.sleep(max(0.5, cycle - spent))
        except KeyboardInterrupt:
            print("\n→ keepalive stopped")
            return
        except Exception as exc:                   # noqa: BLE001 — never die
            log.warning("keepalive cycle failed: %s", exc)
            time.sleep(30)
