"""Pin graphic designer — 4 pro templates.

Every pin is Pinterest-optimized 1000x1500 vertical. A random template is
picked per pin (or forced) so your feed never shows duplicate-looking pins:

  classic  – blurred backdrop + white product card + price badge + CTA pill
  split    – full-bleed photo on top, clean white info panel below
  overlay  – full-bleed photo + dark gradient + text over image
  collage  – main photo + 2 gallery thumbs + info strip

Pure Pillow — no external services.
"""
from __future__ import annotations

import logging
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

log = logging.getLogger("pindrop.designer")

TEMPLATES = ("classic", "split", "overlay", "collage")
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    candidates = []
    if FONT_DIR.exists():
        candidates.append(FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"))
    candidates += [
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def _wrap_text(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    for i, ln in enumerate(lines):
        if draw.textlength(ln, font=font) > max_width:
            while draw.textlength(ln, font=font) > max_width and len(ln) > 3:
                ln = ln[:-1]
            lines[i] = ln + "…"
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(3, len(lines[-1]) - 1)] + "…"
    return lines


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    return ImageOps.fit(img, (w, h), Image.LANCZOS)


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = min(w / img.width, h / img.height)
    return img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
                      Image.LANCZOS)


def _rounded(draw, box, radius, fill, outline=None, width=0):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    except AttributeError:
        draw.rectangle(box, fill=fill, outline=outline, width=width)


class PinDesigner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W = cfg.get_int("design.width", 1000)
        self.H = cfg.get_int("design.height", 1500)
        self.accent = _hex(cfg.get("design.accent_color", "#E60023"))
        self.brand = str(cfg.get("design.brand_name", "")).strip()
        self.cta = str(cfg.get("design.cta_text", "Shop Now ➜") or "Shop Now ➜")
        # "JUST ₹299" wording — the impulse trigger the owner asked for
        self.price_prefix = str(cfg.get("design.price_prefix", "JUST")).strip()

    # ==================================================================
    def create(self, product_image_path: str, title: str, price_label: str,
               out_path: str | Path, source_name: str = "",
               template: str | None = None, extra_images: list | None = None,
               discount: int = 0) -> str:
        """Build a pin graphic with a random (or given) template; returns path.

        `discount` (0-99) draws a "% OFF" burst — the single strongest
        click/conversion trigger in Indian e-commerce pins.
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            product = Image.open(product_image_path).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            log.error("Cannot open product image %s: %s", product_image_path, exc)
            product = Image.new("RGB", (self.W, self.H), (240, 240, 240))

        extras: list[Image.Image] = []
        for p in (extra_images or []):
            try:
                extras.append(Image.open(p).convert("RGB"))
            except Exception:  # noqa: BLE001
                continue

        tpl = template if template in TEMPLATES else random.choice(TEMPLATES)
        canvas = {
            "classic": self._t_classic,
            "split": self._t_split,
            "overlay": self._t_overlay,
            "collage": self._t_collage,
        }[tpl](product, extras, title, price_label, source_name)

        if discount >= 15:
            canvas = self._burst(canvas, discount)

        canvas.convert("RGB").save(out_path, "JPEG", quality=92, optimize=True)
        log.info("Pin designed with template '%s' -> %s", tpl, out_path.name)
        return str(out_path)

    # ------------------------------------------------------ shared pieces
    def _brand_chip(self, draw, y: int = 40, on_dark: bool = True):
        if not self.brand:
            return
        f = _font(True, 34)
        tw = draw.textlength(self.brand.upper(), font=f)
        w = int(tw + 60)
        box = ((self.W - w) // 2, y, (self.W + w) // 2, y + 64)
        fill = (0, 0, 0, 170) if on_dark else self.accent + (255,)
        _rounded(draw, box, 32, fill=fill)
        draw.text((self.W / 2, y + 32), self.brand.upper(), font=f,
                  fill=(255, 255, 255), anchor="mm")

    def _price_badge(self, draw, price_label: str, x2: int, y_center: int):
        if not price_label:
            return
        f = _font(True, 62)
        text = f"{self.price_prefix} {price_label}".strip()
        label = f"  {text}  "
        w = int(draw.textlength(label, font=f) + 36)
        h = 102
        box = (x2 - w, y_center - h // 2, x2, y_center + h // 2)
        _rounded(draw, box, h // 2, fill=self.accent + (255,))
        draw.text(((box[0] + box[2]) / 2, y_center - 3), label, font=f,
                  fill=(255, 255, 255), anchor="mm")

    def _cta_button(self, draw, y: int, source_name: str, on_dark: bool = True):
        f = _font(True, 46)
        text = f"{self.cta}  •  {source_name.title()}" if source_name else self.cta
        w = int(draw.textlength(text, font=f) + 110)
        h = 96
        box = ((self.W - w) // 2, y, (self.W + w) // 2, y + h)
        _rounded(draw, box, h // 2, fill=self.accent + (255,))
        draw.text((self.W / 2, y + h / 2 - 2), text, font=f,
                  fill=(255, 255, 255), anchor="mm")

    def _burst(self, canvas: Image.Image, discount: int) -> Image.Image:
        """Yellow starburst '% OFF' badge, top-right — proven CTR magnet."""
        canvas = canvas.convert("RGBA")
        size = 260
        burst = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bd = ImageDraw.Draw(burst)
        cx = size // 2
        import math as _m
        points = []
        spikes = 12
        for i in range(spikes * 2):
            r = cx if i % 2 == 0 else int(cx * 0.82)
            a = _m.pi * i / spikes
            points.append((cx + r * _m.sin(a), cx + r * _m.cos(a)))
        bd.polygon(points, fill=(255, 196, 0, 255))
        f1 = _font(True, 74)
        f2 = _font(True, 40)
        bd.text((cx, cx - 18), f"{discount}%", font=f1, fill=(20, 20, 20), anchor="mm")
        bd.text((cx, cx + 44), "OFF", font=f2, fill=(20, 20, 20), anchor="mm")
        burst = burst.rotate(-12, expand=True, resample=Image.BICUBIC)
        canvas.alpha_composite(burst, (self.W - size - 30, 110))
        return canvas

    # ============================================================ TEMPLATES
    def _t_classic(self, product, extras, title, price_label, source_name):
        W, H = self.W, self.H
        backdrop = _cover(product.copy(), W, H).filter(ImageFilter.GaussianBlur(18))
        canvas = Image.alpha_composite(
            backdrop.convert("RGBA"), Image.new("RGBA", (W, H), (20, 20, 25, 150))
        ).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        self._brand_chip(draw)

        cw, ch = int(W * 0.86), int(H * 0.52)
        top = int(H * 0.10)
        card = ((W - cw) // 2, top, (W + cw) // 2, top + ch)
        _rounded(draw, card, 42, fill=(255, 255, 255, 255))
        pad = 36
        pw = _fit(product, cw - 2 * pad, ch - 2 * pad)
        canvas.paste(pw, (card[0] + (cw - pw.width) // 2, card[1] + (ch - pw.height) // 2))
        self._price_badge(draw, price_label, card[2] + 20, card[3])

        f = _font(True, 58)
        y = card[3] + 96
        for ln in _wrap_text(draw, title, f, int(W * 0.84), 3):
            draw.text((W / 2 + 3, y + 3), ln, font=f, fill=(0, 0, 0, 200), anchor="ma")
            draw.text((W / 2, y), ln, font=f, fill=(255, 255, 255), anchor="ma")
            y += 74
        self._cta_button(draw, max(y + 42, H - 160), source_name)
        return canvas

    def _t_split(self, product, extras, title, price_label, source_name):
        W, H = self.W, self.H
        photo_h = int(H * 0.62)
        canvas = Image.new("RGB", (W, H), (255, 255, 255))
        canvas.paste(_cover(product.copy(), W, photo_h), (0, 0))
        draw = ImageDraw.Draw(canvas)
        # accent divider
        draw.rectangle((0, photo_h, W, photo_h + 10), fill=self.accent)
        self._brand_chip(draw)

        y = photo_h + 70
        f = _font(True, 62)
        for ln in _wrap_text(draw, title, f, int(W * 0.86), 2):
            draw.text((W * 0.07, y), ln, font=f, fill=(25, 25, 30), anchor="la")
            y += 80

        # price chip on its own row (left)
        if price_label:
            y = max(y + 20, H - 300)
            pf = _font(True, 56)
            label = f" {price_label} "
            pw = int(draw.textlength(label, font=pf) + 60)
            _rounded(draw, (W * 0.07, y, W * 0.07 + pw, y + 96), 48,
                     fill=(252, 240, 238, 255), outline=self.accent + (255,), width=4)
            draw.text((W * 0.07 + pw / 2, y + 48), label, font=pf,
                      fill=self.accent, anchor="mm")
        # CTA centered at the very bottom
        cf = _font(True, 44)
        ctext = f"{self.cta}  •  {source_name.title()}" if source_name else self.cta
        cw = int(draw.textlength(ctext, font=cf) + 90)
        cx = (W - cw) // 2
        cy = H - 165
        _rounded(draw, (cx, cy, cx + cw, cy + 96), 48, fill=self.accent + (255,))
        draw.text((W / 2, cy + 48), ctext, font=cf, fill=(255, 255, 255), anchor="mm")
        return canvas

    def _t_overlay(self, product, extras, title, price_label, source_name):
        W, H = self.W, self.H
        canvas = _cover(product.copy(), W, H).convert("RGBA")
        grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for i in range(int(H * 0.55), H):
            alpha = int(235 * (i - H * 0.55) / (H * 0.45))
            gd.line([(0, i), (W, i)], fill=(10, 10, 14, alpha))
        canvas = Image.alpha_composite(canvas, grad).convert("RGB")
        draw = ImageDraw.Draw(canvas)
        self._brand_chip(draw)

        f = _font(True, 64)
        lines = _wrap_text(draw, title, f, int(W * 0.86), 3)
        y = H - 330
        for ln in lines:
            draw.text((W / 2 + 3, y + 3), ln, font=f, fill=(0, 0, 0, 220), anchor="ma")
            draw.text((W / 2, y), ln, font=f, fill=(255, 255, 255), anchor="ma")
            y += 82
        self._price_badge(draw, price_label, W - 60, y + 20)
        self._cta_button(draw, H - 170, source_name)
        return canvas

    def _t_collage(self, product, extras, title, price_label, source_name):
        W, H = self.W, self.H
        canvas = Image.new("RGB", (W, H), (24, 24, 30))
        draw = ImageDraw.Draw(canvas)
        self._brand_chip(draw)

        mw, mh = int(W * 0.88), int(H * 0.46)
        mtop = int(H * 0.09)
        mbox = ((W - mw) // 2, mtop, (W + mw) // 2, mtop + mh)
        _rounded(draw, mbox, 36, fill=(255, 255, 255, 255))
        main = _fit(product, mw - 60, mh - 60)
        canvas.paste(main, (mbox[0] + (mw - main.width) // 2,
                            mbox[1] + (mh - main.height) // 2))

        # thumbnail row (gallery images)
        ty = mtop + mh + 34
        th = int(H * 0.14)
        thumbs = extras[:2] if extras else [product, product]
        tw = int(W * 0.42)
        xs = [int(W * 0.06), int(W * 0.52)]
        for img, x in zip(thumbs, xs):
            tbox = (x, ty, x + tw, ty + th)
            _rounded(draw, tbox, 28, fill=(255, 255, 255, 255))
            t = _cover(img.copy(), tw - 24, th - 24)
            canvas.paste(t, (x + 12, ty + 12))
        self._price_badge(draw, price_label, W - 50, ty - 4)

        f = _font(True, 56)
        y = ty + th + 70
        for ln in _wrap_text(draw, title, f, int(W * 0.86), 2):
            draw.text((W / 2, y), ln, font=f, fill=(255, 255, 255), anchor="ma")
            y += 72
        self._cta_button(draw, max(y + 34, H - 150), source_name)
        return canvas

    # ================================================== list-pin (roundup)
    def design_roundup(self, items: list[dict], title: str, out_path) -> str:
        """'Deals of the Day' list pin: header + N numbered product rows.

        items: dicts with title, price (label), pin_image/image_path.
        These list pins are what top channels ride to viral saves.
        """
        from .affiliate import price_label as _pl  # local import avoids cycle

        def clean(t: str) -> str:
            # DejaVu fonts have no emoji glyphs → strip pictographs & VS16
            return re.sub(r"[\u2600-\u27BF\U0001F000-\U0001FAFF️‍]", "", t).strip()

        W, H = self.W, self.H
        canvas = Image.new("RGB", (W, H), (250, 246, 240))
        draw = ImageDraw.Draw(canvas)

        # header band
        title = clean(title)
        draw.rectangle((0, 0, W, 320), fill=self.accent)
        hf = _font(True, 64)
        y = 70
        for ln in _wrap_text(draw, title, hf, W - 120, 2):
            draw.text((W / 2, y), ln, font=hf, fill=(255, 255, 255), anchor="ma")
            y += 84
        sf = _font(False, 30)
        draw.text((W / 2, 262), "today's best — hand-picked & price-checked",
                  font=sf, fill=(255, 235, 235), anchor="ma")

        # product rows (spread evenly across the body)
        rows = items[:5]
        top, bottom = 370, H - 170
        rh = max(150, (bottom - top) // max(1, len(rows)))
        tf = _font(True, 38)
        pf = _font(True, 34)
        nf = _font(True, 44)
        for i, p in enumerate(rows):
            ry = top + i * rh
            _rounded(draw, (50, ry + 8, W - 50, ry + rh - 8), 26,
                     fill=(255, 255, 255))
            # number badge
            draw.ellipse((74, ry + rh // 2 - 30, 134, ry + rh // 2 + 30),
                         fill=self.accent)
            draw.text((104, ry + rh // 2), str(i + 1), font=nf,
                      fill=(255, 255, 255), anchor="mm")
            # thumbnail
            img_path = p.get("pin_image") or p.get("image_path") or ""
            tx1, tx2 = W - 210, W - 70
            try:
                if img_path and Path(img_path).exists():
                    with Image.open(img_path) as im:
                        th = _cover(im.convert("RGB"), tx2 - tx1, rh - 40)
                    canvas.paste(th, (tx1, ry + 20))
                else:
                    _rounded(draw, (tx1, ry + 20, tx2, ry + rh - 20), 16,
                             fill=(235, 230, 224))
            except Exception:  # noqa: BLE001 — cosmetic only
                _rounded(draw, (tx1, ry + 20, tx2, ry + rh - 20), 16,
                         fill=(235, 230, 224))
            # title + price
            ttl = clean(str(p.get("title", ""))[:46])
            for j, ln in enumerate(_wrap_text(draw, ttl, tf, tx1 - 160, 2)):
                draw.text((156, ry + 34 + j * 46), ln, font=tf, fill=(35, 30, 28))
            price = (p.get("price_label")
                     or _pl(str(p.get("price", "")), str(p.get("currency", "INR")))
                     or str(p.get("price", "")))
            if price:
                draw.text((156, ry + rh - 62), clean(price), font=pf,
                          fill=self.accent)

        # footer CTA
        fy = H - 120
        _rounded(draw, (90, fy, W - 90, fy + 90), 30, fill=self.accent)
        draw.text((W / 2, fy + 45), "SHOP THE FULL LIST — LINK IN PIN",
                  font=_font(True, 40), fill=(255, 255, 255), anchor="mm")
        if self.brand:
            draw.text((W / 2, H - 18), self.brand, font=_font(False, 24),
                      fill=(150, 145, 140), anchor="ma")
        canvas.save(str(out_path), quality=92)
        log.info("Roundup pin designed (%d items): %s", len(rows), out_path)
        return str(out_path)
