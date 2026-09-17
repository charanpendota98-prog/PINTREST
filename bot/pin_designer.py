"""Pin graphic designer.

Generates Pinterest-optimized 1000x1500 vertical images:
blurred product backdrop, crisp product photo on top, price badge,
title card and a CTA strip. Pure Pillow — no external services.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

log = logging.getLogger("pindrop.designer")

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


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               max_width: int, max_lines: int) -> list[str]:
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
    for i, ln in enumerate(lines):
        if draw.textlength(ln, font=font) > max_width:
            # hard-break very long words (URLs, model numbers)
            while draw.textlength(ln, font=font) > max_width and len(ln) > 3:
                ln = ln[:-1]
            lines[i] = ln + "…"
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(3, len(lines[-1]) - 1)] + "…"
    return lines


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img2 = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)),
                      Image.LANCZOS)
    img2 = ImageOps.fit(img2, (w, h), Image.LANCZOS)
    return img2


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=0):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    except AttributeError:  # very old Pillow
        draw.rectangle(box, fill=fill, outline=outline, width=width)


class PinDesigner:
    def __init__(self, cfg):
        self.cfg = cfg
        self.W = int(cfg.get("design.width", 1000))
        self.H = int(cfg.get("design.height", 1500))
        self.accent = _hex(cfg.get("design.accent_color", "#E60023"))
        self.brand = str(cfg.get("design.brand_name", "")).strip()
        self.cta = str(cfg.get("design.cta_text", "Shop Now ➜"))

    # ------------------------------------------------------------------
    def create(self, product_image_path: str, title: str, price_label: str,
               out_path: str | Path, source_name: str = "") -> str:
        """Build the final pin graphic; returns saved path."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        W, H = self.W, self.H

        try:
            product = Image.open(product_image_path).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            log.error("Cannot open product image %s: %s", product_image_path, exc)
            product = Image.new("RGB", (W, H), (245, 245, 245))

        # -- backdrop: blurred, darkened cover of the product photo
        backdrop = _cover(product.copy(), W, H).filter(ImageFilter.GaussianBlur(18))
        overlay = Image.new("RGBA", (W, H), (20, 20, 25, 150))
        backdrop = Image.alpha_composite(backdrop.convert("RGBA"), overlay).convert("RGB")
        canvas = backdrop

        draw = ImageDraw.Draw(canvas)

        # -- product photo card (centered, white rounded card behind)
        card_w = int(W * 0.86)
        card_h = int(H * 0.52)
        card_top = int(H * 0.10)
        card_box = ((W - card_w) // 2, card_top, (W + card_w) // 2, card_top + card_h)
        _rounded_rect(draw, card_box, 42, fill=(255, 255, 255, 255))

        # fit product image inside card with padding
        pad = 36
        target_w, target_h = card_w - 2 * pad, card_h - 2 * pad
        pw = product.copy()
        ratio = min(target_w / pw.width, target_h / pw.height)
        pw = pw.resize((max(1, int(pw.width * ratio)), max(1, int(pw.height * ratio))),
                       Image.LANCZOS)
        canvas.paste(pw, (card_box[0] + (card_w - pw.width) // 2,
                          card_box[1] + (card_h - pw.height) // 2))

        # -- brand strip (top)
        if self.brand:
            font_brand = _font(True, 34)
            tw = draw.textlength(self.brand.upper(), font=font_brand)
            chip_w = int(tw + 60)
            chip_box = ((W - chip_w) // 2, 44, (W + chip_w) // 2, 44 + 64)
            _rounded_rect(draw, chip_box, 32, fill=(0, 0, 0, 160))
            draw.text((W / 2, 44 + 32), self.brand.upper(), font=font_brand,
                      fill=(255, 255, 255), anchor="mm")

        # -- price badge (overlapping card bottom-right)
        if price_label:
            font_price = _font(True, 64)
            plabel = f"  {price_label}  "
            ptw = draw.textlength(plabel, font=font_price)
            pb_w, pb_h = int(ptw + 40), 104
            pb_x = card_box[2] - pb_w + 20
            pb_y = card_box[3] - pb_h // 2
            _rounded_rect(draw, (pb_x, pb_y, pb_x + pb_w, pb_y + pb_h), 52,
                          fill=self.accent + (255,))
            draw.text((pb_x + pb_w / 2, pb_y + pb_h / 2 - 4), plabel, font=font_price,
                      fill=(255, 255, 255), anchor="mm")

        # -- title card (bottom area)
        title_top = card_box[3] + 90
        font_title = _font(True, 58)
        lines = _wrap_text(draw, title, font_title, int(W * 0.84), 3)
        line_h = 74
        block_h = line_h * len(lines)
        # title text block
        y = title_top
        for ln in lines:
            # soft shadow
            draw.text((W / 2 + 3, y + 3), ln, font=font_title, fill=(0, 0, 0, 200),
                      anchor="ma")
            draw.text((W / 2, y), ln, font=font_title, fill=(255, 255, 255), anchor="ma")
            y += line_h

        # -- CTA button
        font_cta = _font(True, 46)
        cta_text = self.cta
        if source_name:
            cta_text = f"{self.cta}  •  {source_name.title()}"
        ct_w = int(draw.textlength(cta_text, font=font_cta) + 110)
        ct_h = 96
        ct_y = max(y + 46, H - ct_h - 64)
        ct_box = ((W - ct_w) // 2, ct_y, (W + ct_w) // 2, ct_y + ct_h)
        _rounded_rect(draw, ct_box, ct_h // 2, fill=self.accent + (255,))
        draw.text((W / 2, ct_y + ct_h / 2 - 2), cta_text, font=font_cta,
                  fill=(255, 255, 255), anchor="mm")

        canvas.save(out_path, "JPEG", quality=92, optimize=True)
        return str(out_path)
