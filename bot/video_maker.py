"""Auto reel maker — turns product PHOTOS into a viral-style MP4 video.

This is the trick top affiliates use: they never wait for brand videos,
they build 6-second reels from photos:

  [0.0–1.2s]  HOOK frame   — dark screen, curiosity headline pops in
  [1.2–4.4s]  PRODUCT      — Ken Burns zoom on the photo + price badge
  [4.4–6.0s]  CTA frame    — accent screen, brand + "shop now / link in bio"

720×1280 (9:16) H.264 mp4 → perfect for Pinterest video pins & IG reels.
Uses the bundled ffmpeg binary from imageio-ffmpeg (no system install).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

log = logging.getLogger("pindrop.video")

W, H, FPS = 720, 1280, 24
T_HOOK, T_PROD, T_CTA = 1.2, 3.2, 1.6

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    for p in ([FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
              if FONT_DIR.exists() else []):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = f"{line} {w}".strip()
        if draw.textlength(t, font=font) <= max_w:
            line = t
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines[:max_lines]


def _accent() -> tuple[int, int, int]:
    return (230, 0, 35)


def pick_music(cfg) -> str:
    """Pick a BGM track the USER added manually.

    Drop mp3/m4a/wav files into data/music/ (or upload via dashboard) —
    the bot rotates them automatically into every new reel. Your trending
    audio + our automation = best of both.
    """
    import random as _r
    from pathlib import Path as _P
    cands: list[str] = []
    mdir = _P(__file__).resolve().parent.parent / str(
        cfg.get("video.music_dir", "data/music"))
    if mdir.exists():
        cands += [str(p) for p in mdir.iterdir()
                  if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac")]
    single = str(cfg.get("video.music", "") or "")
    if single and _P(single).exists():
        cands.append(single)
    return _r.choice(cands) if cands else ""


class ReelMaker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.brand = str(cfg.get("design.brand_name", "")).strip()

    # ------------------------------------------------------------------
    def make(self, image_path: str, hook: str, title: str, price_label: str,
             out_path: str | Path, source: str = "",
             voiceover: str | None = None, music: str | None = None,
             vo_seconds: float = 0.0) -> str:
        """Render the reel; returns the mp4 path.

        voiceover: path to a TTS mp3 (voiceover.py) — mixed in with ffmpeg.
        music:     optional BGM mp3 the user drops in (ducked under voice).
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            photo = Image.open(image_path).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"reel: bad image {image_path}: {exc}") from exc

        # stretch product scene to fit the voiceover length
        global T_PROD
        T_PROD = max(3.2, vo_seconds - T_HOOK - T_CTA + 1.0) if vo_seconds else 3.2

        import imageio_ffmpeg
        silent = out_path.with_suffix(".silent.mp4")
        writer = imageio_ffmpeg.write_frames(
            str(silent), (W, H), fps=FPS, codec="libx264",
            pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
            output_params=["-crf", "27", "-preset", "veryfast"],
        )
        writer.send(None)  # init

        n_hook = int(T_HOOK * FPS)
        n_prod = int(T_PROD * FPS)
        n_cta = int(T_CTA * FPS)
        for i in range(n_hook):
            writer.send(self._frame_hook(hook, i / n_hook).tobytes())
        for i in range(n_prod):
            t = i / n_prod
            writer.send(self._frame_product(photo, title, price_label, t,
                                            caption=hook).tobytes())
        for i in range(n_cta):
            writer.send(self._frame_cta(source, i / n_cta).tobytes())
        writer.close()

        final = self._mix_audio(silent, out_path, voiceover, music)
        try:
            silent.unlink(missing_ok=True)
        except OSError:
            pass
        log.info("Reel rendered: %s (%d frames, voice=%s)",
                 out_path.name, n_hook + n_prod + n_cta, bool(voiceover))
        return str(final)

    # ------------------------------------------------------------ audio
    @staticmethod
    def _mix_audio(silent: Path, out: Path, voiceover: str | None,
                   music: str | None) -> Path:
        import subprocess
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if not (voiceover or music):
            silent.rename(out)
            return out
        cmd = [exe, "-y", "-i", str(silent)]
        if voiceover:
            cmd += ["-i", voiceover]
        if music:
            cmd += ["-stream_loop", "-1", "-i", music]
        if voiceover and music:
            cmd += ["-filter_complex",
                    "[1:a]volume=1.0[v];[2:a]volume=0.25[m];"
                    "[v][m]amix=inputs=2:duration=first[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-shortest", str(out)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            return out
        except (subprocess.CalledProcessError, OSError) as exc:
            log.warning("Audio mix failed (%s) — keeping silent reel", exc)
            silent.rename(out)
            return out

    # ------------------------------------------------------------ frames
    def _frame_hook(self, hook: str, t: float) -> Image.Image:
        img = Image.new("RGB", (W, H), (16, 16, 20))
        d = ImageDraw.Draw(img)
        # subtle vignette bars
        d.rectangle((0, 0, W, 90), fill=(230, 0, 35))
        d.rectangle((0, H - 90, W, H), fill=(230, 0, 35))
        if self.brand:
            d.text((W / 2, 45), self.brand.upper(), font=_font(True, 40),
                   fill=(255, 255, 255), anchor="mm")
        f = _font(True, 64)
        lines = _wrap(d, hook, f, int(W * 0.84), 3)
        scale = min(1.0, t * 3 + 0.4)          # pop-in
        fh = _font(True, max(20, int(64 * scale)))
        lines = _wrap(d, hook, fh, int(W * 0.84), 3)
        y = H / 2 - len(lines) * 45
        for ln in lines:
            d.text((W / 2, y), ln, font=fh, fill=(255, 255, 255), anchor="ma")
            y += 90 * scale
        d.text((W / 2, H - 45), "wait for it…", font=_font(True, 30),
               fill=(255, 220, 220), anchor="mm")
        return img

    def _frame_product(self, photo: Image.Image, title: str, price: str,
                       t: float, caption: str = "") -> Image.Image:
        # Ken Burns: zoom 1.05 → 1.22
        zoom = 1.05 + 0.17 * t
        base = ImageOps.fit(photo, (W, H), Image.LANCZOS)
        zw, zh = int(W * zoom), int(H * zoom)
        base = base.resize((zw, zh), Image.LANCZOS)
        x = (zw - W) // 2
        y = (zh - H) // 2
        img = base.crop((x, y, x + W, y + H))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(260):
            od.line([(0, i), (W, i)], fill=(8, 8, 10, int(190 * (1 - i / 260))))
            od.line([(0, H - 1 - i), (W, H - 1 - i)],
                    fill=(8, 8, 10, int(210 * (1 - i / 260))))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        d = ImageDraw.Draw(img)
        # hook line at top
        d.text((W / 2, 70), title[:42] + ("…" if len(title) > 42 else ""),
               font=_font(True, 40), fill=(255, 255, 255), anchor="ma")
        # price badge bottom (pop at t>0.15)
        if price and t > 0.12:
            f = _font(True, 72)
            label = f"  {price}  "
            tw = d.textlength(label, font=f)
            bw, bh = int(tw + 50), 120
            bx = (W - bw) // 2
            by = H - 300
            try:
                d.rounded_rectangle((bx, by, bx + bw, by + bh), bh // 2, fill=_accent())
            except AttributeError:
                d.rectangle((bx, by, bx + bw, by + bh), fill=_accent())
            d.text((W / 2, by + bh / 2), label, font=f, fill=(255, 255, 255), anchor="mm")
            d.text((W / 2, H - 140), "🛒 link in bio / tap to shop",
                   font=_font(True, 34), fill=(255, 235, 235), anchor="ma")
        # burned-in subtitle (what the voice is saying right now)
        if caption:
            line = caption if t < 0.45 else (f"Only {price}!" if price else caption)
            cf = _font(True, 40)
            d.text((W / 2 + 2, H - 62 + 2), line, font=cf, fill=(0, 0, 0), anchor="ma")
            d.text((W / 2, H - 62), line, font=cf, fill=(255, 255, 80), anchor="ma")
        return img

    def _frame_cta(self, source: str, t: float) -> Image.Image:
        img = Image.new("RGB", (W, H), _accent())
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, W, H), outline=(255, 255, 255), width=0)
        f1 = _font(True, 76)
        d.text((W / 2, H / 2 - 140), "GRAB THE DEAL", font=f1, fill=(255, 255, 255), anchor="ma")
        f2 = _font(True, 44)
        src = source.title() if source else "Online"
        d.text((W / 2, H / 2 - 20), f"on {src}  •  link in bio", font=f2,
               fill=(255, 230, 230), anchor="ma")
        if self.brand:
            d.text((W / 2, H / 2 + 90), f"@ {self.brand}", font=_font(True, 40),
                   fill=(255, 255, 255), anchor="ma")
        # pulsing arrow
        dy = int(12 * math.sin(t * math.pi * 4))
        d.text((W / 2, H / 2 + 220 + dy), "▼", font=_font(True, 60),
               fill=(255, 255, 255), anchor="ma")
        return img
