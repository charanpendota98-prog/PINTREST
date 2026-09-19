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


def _fit_text(draw, text: str, max_w: int, max_lines: int,
              start: int = 64, floor: int = 26):
    """Shrink the font until EVERY word fits — a cut-off hook kills the reel.

    Returns (lines, size). Never returns a truncated string: if even the
    floor size cannot hold it, the caller still gets all words wrapped.
    """
    words = " ".join(str(text or "").split())
    size = int(start)
    while size >= floor:
        font = _font(True, size)
        lines = _wrap(draw, words, font, max_w, max_lines)
        if " ".join(lines) == words:
            return lines, size
        size -= 6
    return _wrap(draw, words, _font(True, floor), max_w, max_lines + 2), floor


# --------------------------------------------------- "model shot" picking
def _person_score(img: Image.Image) -> int:
    """Rough "is somebody WEARING it in this photo?" score (0-100).

    Honest heuristic, no ML: product galleries front-load the model shot and
    model shots are portrait crops full of skin tones. It never claims more
    than it is — ties keep the gallery's own order.
    """
    small = img.copy()
    small.thumbnail((160, 160))
    w, h = small.size
    px = small.load()
    skin = total = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y][:3]
            total += 1
            if (r > 95 and g > 40 and b > 20 and r > g > b and (r - b) > 15
                    and abs(r - g) > 15 and max(r, g, b) - min(r, g, b) > 15):
                skin += 1
    return int(100 * skin / total) if total else 0


def pick_hero(paths: list) -> list:
    """Order gallery photos: likely model-wearing shot first, rest as given."""
    scored = []
    for i, p in enumerate(paths or []):
        try:
            img = Image.open(p)
            w, h = img.size
            portrait = 12 if h >= w * 1.1 else 0
            big = 6 if max(w, h) >= 900 else 0
            person = min(20, _person_score(img) // 3)
            scored.append((-(portrait + big + person), i, p))
        except Exception:  # noqa: BLE001 — unreadable file sorts last
            scored.append((0, i, p))
    scored.sort()
    return [p for _, _, p in scored]


def _proof_label(rating: float, reviews: int) -> str:
    """'4.0★ · 1.36L ratings' — real numbers only; '' when the page had none."""
    try:
        r, n = float(rating or 0), int(reviews or 0)
    except (TypeError, ValueError):
        return ""
    if r <= 0 or n <= 0:
        return ""
    if n >= 100_000:
        cnt = f"{n / 100000:.2f}".rstrip("0").rstrip(".") + "L"
    elif n >= 1000:
        cnt = f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    else:
        cnt = str(n)
    return f"{r:.1f}★ · {cnt} ratings"


def _sticker(canvas: Image.Image, text: str, cx: int, cy: int, *,
             fill=(255, 214, 0), text_fill=(24, 20, 16), angle: float = -9,
             size: int = 52) -> Image.Image:
    """Slanted price sticker — "JUST ₹299" popping on the photo."""
    font = _font(True, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    tw = int(probe.textlength(text, font=font))
    w, h = tw + int(size * 1.3), int(size * 1.9)
    tag = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(tag)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 3, fill=fill,
                        outline=(255, 255, 255, 240), width=4)
    d.text((w / 2, h / 2), text, font=font, fill=text_fill, anchor="mm")
    tag = tag.rotate(angle, expand=True, resample=Image.BICUBIC)
    canvas = canvas.convert("RGBA")
    canvas.alpha_composite(tag, (int(cx - tag.width / 2), int(cy - tag.height / 2)))
    return canvas.convert("RGB")


def pick_video(cfg) -> str:
    """Pick a video the USER uploaded (data/videos/).

    You have your own product videos? Drop them in — they're used INSTEAD
    of auto-generated reels (your footage = your brand, better trust).
    Rotates across products automatically.
    """
    import random as _r
    from pathlib import Path as _P
    vdir = _P(__file__).resolve().parent.parent / "data" / "videos"
    if vdir.exists():
        cands = [str(p) for p in vdir.iterdir()
                 if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv")]
        if cands:
            return _r.choice(cands)
    return ""


_MUSIC_CACHE: dict[tuple, bool] = {}


def music_usable(path: str | None) -> bool:
    """True only if ffmpeg can actually DECODE this audio file.

    Guards the 'reel went silent' failure mode: a corrupt/partial upload
    (or a text file renamed .wav) used to fail the mix silently.
    Results are cached per (path, mtime, size) so per-reel probes stay fast.
    """
    if not path:
        return False
    from pathlib import Path as _P
    p = _P(path)
    try:
        st = p.stat()
    except OSError:
        return False
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _MUSIC_CACHE:
        return _MUSIC_CACHE[key]
    if not p.is_file() or st.st_size < 1024:
        _MUSIC_CACHE[key] = False
        return False
    try:
        import subprocess
        import imageio_ffmpeg
        r = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(path),
             "-f", "null", "-"], capture_output=True, timeout=60)
        _MUSIC_CACHE[key] = r.returncode == 0
        return _MUSIC_CACHE[key]
    except Exception:  # noqa: BLE001 — never break a render over a probe
        return True  # can't probe → let the mix try (it has its own fallback)


def usable_or_auto_bgm(cfg, music: str | None) -> str:
    """Return `music` if it decodes; else fall back to original composed BGM.

    This keeps every reel sounding premium even when the owner's uploaded
    audio is corrupt — no silent reels, ever.
    """
    if music_usable(music):
        return music or ""
    if music:
        log.warning("BGM unusable (corrupt/partial file): %s — "
                    "falling back to original composed BGM", music)
    try:
        from pathlib import Path as _P
        from . import music_maker
        mdir = _P(__file__).resolve().parent.parent / str(
            cfg.get("video.music_dir", "data/music"))
        mdir.mkdir(parents=True, exist_ok=True)
        auto = mdir / "auto_bgm.wav"
        if not auto.exists() or auto.stat().st_size < 1024:
            music_maker.compose(auto, seconds=14)
        return str(auto) if auto.exists() else ""
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-BGM fallback failed: %s", exc)
        return music or ""


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
    if cands:
        good = [c for c in cands if music_usable(c)]
        if good:
            return _r.choice(good)
        log.warning("All uploaded audio is corrupt/partial — composing "
                    "original BGM instead (reels never go silent)")
    # nothing usable? compose ORIGINAL royalty-free BGM on the fly
    if cfg.get("video.auto_music", True):
        try:
            from . import music_maker
            auto = mdir / "auto_bgm.wav"
            if not auto.exists():
                music_maker.compose(auto, seconds=14)
            return str(auto)
        except Exception as exc:  # noqa: BLE001
            log.warning("Auto-BGM compose failed: %s", exc)
    return ""


class ReelMaker:
    def __init__(self, cfg):
        self.cfg = cfg
        self.brand = str(cfg.get("design.brand_name", "")).strip()

    # ------------------------------------------------------------------
    def make(self, image_path: str, hook: str, title: str, price_label: str,
             out_path: str | Path, source: str = "",
             voiceover: str | None = None, music: str | None = None,
             vo_seconds: float = 0.0, *, discount: int = 0,
             rating: float = 0.0, reviews: int = 0) -> str:
        """Single-photo reel — kept for compatibility; see `make_multi`."""
        return self.make_multi([image_path], hook, title, price_label, out_path,
                               source, voiceover=voiceover, music=music,
                               vo_seconds=vo_seconds, discount=discount,
                               rating=rating, reviews=reviews)

    # ------------------------------------------------------------------
    def make_multi(self, images: list, hook: str, title: str, price_label: str,
                   out_path: str | Path, source: str = "",
                   voiceover: str | None = None, music: str | None = None,
                   vo_seconds: float = 0.0, *, discount: int = 0,
                   rating: float = 0.0, reviews: int = 0,
                   scene_seconds: float | None = None) -> str:
        """PHOTOS → ONE reel: model shot first, every photo its own camera move.

        A still frame gets scrolled past; 3 photos with movement keep people
        watching. `pick_hero()` puts the worn shot ("ela untundi" frame) first,
        the price rides a slanted JUST ₹ sticker, and the social-proof chip
        only appears when the page really showed ★ + count.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        photos = []
        for p in pick_hero([p for p in (images or []) if p]):
            try:
                photos.append(Image.open(p).convert("RGB"))
            except Exception as exc:  # noqa: BLE001
                log.warning("reel: skipping unreadable photo %s (%s)", p, exc)
        if not photos:
            raise ValueError(f"reel: no usable photo in {images!r}")

        if scene_seconds is None:
            stretch = (max(3.2, vo_seconds - T_HOOK - T_CTA + 1.0)
                       if vo_seconds else T_PROD)
            scene_seconds = max(1.4, min(3.4, stretch))
        n_hook = max(6, int(T_HOOK * FPS))
        n_scene = max(8, int(scene_seconds * FPS))
        n_cta = max(6, int(T_CTA * FPS))

        import imageio_ffmpeg
        silent = out_path.with_suffix(".silent.mp4")
        writer = imageio_ffmpeg.write_frames(
            str(silent), (W, H), fps=FPS, codec="libx264",
            pix_fmt_in="rgb24", pix_fmt_out="yuv420p",
            output_params=["-crf", "27", "-preset", "veryfast"],
        )
        writer.send(None)  # init
        frames = 0
        for i in range(n_hook):
            writer.send(self._frame_hook(hook, i / n_hook,
                                         bg=photos[0]).tobytes())
            frames += 1
        proof = _proof_label(rating, reviews)
        for idx, photo in enumerate(photos):
            motion = idx % 3                      # push-in → pan → pull-out
            for i in range(n_scene):
                frame = self._frame_scene(
                    photo, title, price_label, i / max(1, n_scene - 1),
                    caption=hook, motion=motion,
                    discount=discount if idx == 0 else 0, proof=proof,
                    scene_no=idx + 1, scenes=len(photos))
                writer.send(frame.tobytes())
                frames += 1
        for i in range(n_cta):
            writer.send(self._frame_cta(source, i / n_cta).tobytes())
            frames += 1
        writer.close()

        final = self._mix_audio(silent, out_path, voiceover, music)
        try:
            silent.unlink(missing_ok=True)
        except OSError:
            pass
        log.info("Reel rendered: %s (%d frames, %d photo(s), voice=%s)",
                 out_path.name, frames, len(photos), bool(voiceover))
        return str(final)

    # ------------------------------------------------------- scene frame
    def _frame_scene(self, photo: Image.Image, title: str, price: str, t: float,
                     caption: str = "", motion: int = 0, discount: int = 0,
                     proof: str = "", scene_no: int = 1,
                     scenes: int = 1) -> Image.Image:
        """One photo with a camera move + title band + JUST ₹ sticker."""
        z = (1.18 - 0.13 * t) if motion == 2 else (1.05 + 0.13 * t)
        zw, zh = max(W + 2, int(W * z)), max(H + 2, int(H * z))
        base = ImageOps.fit(photo, (zw, zh), method=Image.LANCZOS,
                            centering=(0.5, 0.35))
        if motion == 1:                            # pan left → right
            left = int((zw - W) * t)
            box = (left, (zh - H) // 2, left + W, (zh - H) // 2 + H)
        else:                                      # centered push / pull
            top = int((zh - H) * (0.35 if motion == 0 else 0.35 + 0.2 * t))
            box = ((zw - W) // 2, top, (zw - W) // 2 + W, top + H)
        img = base.crop(box)

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle((0, 0, W, 230), fill=(0, 0, 0, 135))
        od.rectangle((0, H - 240, W, H), fill=(0, 0, 0, 155))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        d = ImageDraw.Draw(img)

        f_title = _font(True, 46)
        for i, ln in enumerate(_wrap(d, title[:60], f_title, W - 120, 2)):
            d.text((W / 2, 34 + i * 56), ln, font=f_title, fill=(255, 255, 255),
                   anchor="ma")
        if scenes > 1:
            d.text((W / 2, 176), f"{scene_no}/{scenes}", font=_font(True, 30),
                   fill=(235, 235, 235), anchor="ma")

        if price and t > 0.12:                     # sticker pops in
            label = f"JUST {price}"
            if discount >= 15:
                label += f"  •  {discount}% OFF"
            img = _sticker(img, label, W // 2, int(H * 0.56))

        if proof:
            d2 = ImageDraw.Draw(img)
            f = _font(True, 34)
            tw = int(d2.textlength(proof, font=f))
            y0 = int(H * 0.56) + 86
            box = ((W - tw) // 2 - 30, y0, (W + tw) // 2 + 30, y0 + 62)
            d2.rounded_rectangle(box, radius=31, fill=(0, 0, 0, 170))
            d2.text((W / 2, y0 + 31), proof, font=f, fill=(255, 236, 130),
                    anchor="mm")

        if caption and t < 0.5:
            d.text((W / 2, H - 150), caption[:44], font=_font(True, 40),
                   fill=(255, 255, 255), anchor="ma")
        d.text((W / 2, H - 74), "link in bio / tap to shop",
               font=_font(True, 30), fill=(255, 230, 120), anchor="ma")
        return img

    # ------------------------------------------------------------ audio
    def _mix_audio(self, silent: Path, out: Path, voiceover: str | None,
                   music: str | None) -> Path:
        import subprocess
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        # never let a corrupt upload kill the soundtrack: swap in original BGM
        if music:
            music = usable_or_auto_bgm(self.cfg, music) or None
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
            # second chance: keep the VOICEOVER if music was the problem
            if voiceover and music:
                log.warning("Audio mix failed with BGM — retrying voice-only")
                retry = [exe, "-y", "-i", str(silent), "-i", voiceover,
                         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                         "-c:a", "aac", "-shortest", str(out)]
                try:
                    subprocess.run(retry, check=True, capture_output=True,
                                   timeout=300)
                    return out
                except (subprocess.CalledProcessError, OSError) as exc2:
                    exc = exc2
            log.warning("Audio mix failed (%s) — keeping silent reel", exc)
            if out.exists():
                out.unlink(missing_ok=True)
            silent.rename(out)
            return out

    # ------------------------------------------------------------ frames
    def _frame_hook(self, hook: str, t: float,
                    bg: Image.Image | None = None) -> Image.Image:
        """Opening frame. With `bg` the product itself sits behind the
        headline (blurred + darkened) — the viewer sees WHAT it is in second
        one, which is exactly how the top reels open."""
        if bg is not None:
            base = ImageOps.fit(bg, (W, H), method=Image.LANCZOS,
                                centering=(0.5, 0.35))
            img = Image.blend(base.filter(ImageFilter.GaussianBlur(9)),
                              Image.new("RGB", (W, H), (12, 12, 16)), 0.58)
        else:
            img = Image.new("RGB", (W, H), (16, 16, 20))
        d = ImageDraw.Draw(img)
        # subtle vignette bars
        d.rectangle((0, 0, W, 90), fill=(230, 0, 35))
        d.rectangle((0, H - 90, W, H), fill=(230, 0, 35))
        if self.brand:
            d.text((W / 2, 45), self.brand.upper(), font=_font(True, 40),
                   fill=(255, 255, 255), anchor="mm")
        scale = min(1.0, t * 3 + 0.45)          # pop-in
        lines, size = _fit_text(d, hook, int(W * 0.88), 5,
                                start=max(26, int(64 * scale)), floor=26)
        fh = _font(True, size)
        y = H / 2 - len(lines) * (size * 0.75)
        for ln in lines:
            d.text((W / 2, y), ln, font=fh, fill=(255, 255, 255), anchor="ma")
            y += size * 1.5
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
