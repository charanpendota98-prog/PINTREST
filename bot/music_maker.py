"""Original BGM composer — 100% copyright-free, zero downloads.

Downloading trending songs = copyright strikes + muted reels + bans
(platforms fingerprint audio). Instead, this module COMPOSES a pleasant
lo-fi loop (C–G–Am–F arpeggios with soft envelopes) using pure Python —
it's OUR original music, so it's safe on every platform, forever,
fully automatic. No network, no license, no risk.

If you still want a specific trending sound, upload it manually
(dashboard 🎵) — user-provided audio always wins over auto BGM.
"""
from __future__ import annotations

import math
import random
import wave
from pathlib import Path

SR = 22050  # sample rate

# C major – G – A minor – F (the most pleasant loop in pop music)
CHORDS = [
    (261.63, 329.63, 392.00),   # C
    (196.00, 246.94, 293.66),   # G
    (220.00, 261.63, 329.63),   # Am
    (174.61, 220.00, 261.63),   # F
]


def _env(i: int, n: int) -> float:
    """Soft attack, exponential decay, no clicks."""
    a = min(1.0, i / (SR * 0.01))                 # 10ms attack
    d = math.exp(-3.0 * i / n)                    # decay
    w = 0.5 - 0.5 * math.cos(2 * math.pi * (n - i) / (SR * 0.05)) if n - i < SR * 0.05 else 1.0
    return a * d * w


def compose(path: str | Path, seconds: float = 12.0, bpm: int = 92) -> str:
    """Render an original lo-fi BGM loop to a WAV file; returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    total = int(seconds * SR)
    buf = [0.0] * total

    beat = 60.0 / bpm
    note_len = beat / 2          # 8th notes
    step = int(note_len * SR)

    rnd = random.Random(42)      # deterministic, always pleasant
    t = 0
    ci = 0
    while t < total:
        root, third, fifth = CHORDS[ci % len(CHORDS)]
        chord_samples = int(beat * 4 * SR)   # one bar
        # bass (root, one octave down, gentle)
        for i in range(min(chord_samples, total - t)):
            buf[t + i] += 0.16 * math.sin(2 * math.pi * (root / 2) * i / SR) * _env(i, chord_samples)
        # arpeggio: root-third-fifth-third pattern, octaves sparkle
        seq = [root, third, fifth, third, root * 2, fifth, third, fifth]
        for k, f in enumerate(seq):
            start = t + k * step
            if start >= total:
                break
            n = min(step * 2, total - start)   # let notes ring over
            for i in range(n):
                vib = 1.0 + 0.002 * math.sin(2 * math.pi * 5 * i / SR)
                buf[start + i] += (0.22 * math.sin(2 * math.pi * f * vib * i / SR)
                                   * _env(i, n))
        # airy sparkle (random pentatonic ping per bar)
        ping_f = random.choice([root * 4, fifth * 4, third * 4]) if rnd.random() < 0.7 else None
        if ping_f:
            ps = t + int(rnd.random() * chord_samples * 0.7)
            n = min(int(0.6 * SR), total - ps)
            for i in range(n):
                buf[ps + i] += 0.07 * math.sin(2 * math.pi * ping_f * i / SR) * _env(i, n)
        t += chord_samples
        ci += 1

    # normalize + gentle fade in/out
    peak = max(1e-6, max(abs(x) for x in buf))
    fade = int(0.8 * SR)
    frames = bytearray()
    for i, x in enumerate(buf):
        g = 0.85 / peak
        if i < fade:
            g *= i / fade
        if i > total - fade:
            g *= (total - i) / fade
        frames += struct_pack(int(max(-1, min(1, x * g)) * 32767))

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return str(path)


def struct_pack(v: int) -> bytes:
    return v.to_bytes(2, "little", signed=True)
