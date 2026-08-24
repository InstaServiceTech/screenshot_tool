"""
renderer.py — draws the "Service Information" screen as a PNG using Pillow.

Fixed to the reference dimensions (386 x 858), rendered at 2x then downscaled
for crisp text. No browser / emulator / Appium.

Public API:
    render_service_screen(data: ServiceRecord, out_path: str) -> str
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

# ── Fonts (cross-platform) ───────────────────────────────────────────────────
# To match your app's Roboto exactly, drop Roboto-Regular.ttf / Roboto-Bold.ttf
# into app/fonts/ — they are preferred automatically. Otherwise the bundled
# DejaVu Sans is used, then common system fonts, then Pillow's built-in font.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BUNDLED = os.path.join(_HERE, "fonts")

_REG_CANDIDATES = [
    os.path.join(_BUNDLED, "Roboto-Regular.ttf"),
    os.path.join(_BUNDLED, "DejaVuSans.ttf"),
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_BOLD_CANDIDATES = [
    os.path.join(_BUNDLED, "Roboto-Bold.ttf"),
    os.path.join(_BUNDLED, "DejaVuSans-Bold.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _first_existing(cands):
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


_REG = _first_existing(_REG_CANDIDATES)
_BOLD = _first_existing(_BOLD_CANDIDATES) or _REG


def _font(bold: bool, size: int):
    path = _BOLD if bold else _REG
    if path:
        try:
            return ImageFont.truetype(path, int(size * SCALE))
        except OSError:
            pass
    return ImageFont.load_default(size=int(size * SCALE))


# ── Canvas ───────────────────────────────────────────────────────────────────
OUT_W, OUT_H = 386, 858        # width is fixed; OUT_H used only in fixed mode
SCALE = 2                      # supersample for crisp text, then downscale
FIT_TO_CONTENT = False         # image-1 mode: fixed OUT_H frame (858).
#                                set False to force a fixed OUT_H (386x858) frame
W = OUT_W * SCALE
H = 1600 * SCALE               # generous scratch height; cropped/clipped at the end
BOTTOM_MARGIN = 16             # px of breathing room below the last element
PAD = 16 * SCALE

# ── Palette (sampled from the reference) ─────────────────────────────────────
C_BG = (255, 255, 255)
C_STATUS = (249, 249, 249)
C_TEXT = (26, 33, 48)
C_MUTED = (120, 126, 136)
C_RED = (216, 51, 54)          # #d83336
C_CARD_BG = (253, 250, 225)    # #fdfae1
C_CARD_BORDER = (230, 198, 166)  # #e6c6a6 (sampled from reference)
C_ACCENT_L = (214, 0, 52)      # Accept gradient left  (#d60034)
C_ACCENT_R = (217, 64, 55)     # Accept gradient right (#d94037)
C_DIVIDER = (238, 231, 200)    # faint gold divider inside card
C_LINE = (233, 235, 238)
C_INCLUDE_BOX = (245, 246, 247)  # #f5f6f7
C_CHECK_BG = (232, 244, 238)     # #e8f4ee
C_CHECK = (32, 46, 40)
C_INCLUDE_TXT = (74, 100, 132)
C_SERVICE_BORDER = (233, 235, 238)


@dataclass
class ServiceRecord:
    amount: str = ""
    service_name: str = ""
    estimated_time: str = ""
    city: str = ""
    zipcode: str = ""
    customer_name: str = ""
    customer_instructions: str = ""
    booking_datetime: str = "Mon, Aug 24, 2026, 10:30 AM"
    status_time: str = "11:30"
    includes: List[str] = field(default_factory=list)
    addons: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def clean_service_name(self) -> str:
        return self.service_name.split("*")[0].strip()


def _tw(d, s, f):
    return int(d.textlength(s, font=f))


def _wrap(d, s, f, max_w):
    if s is None or str(s) == "":
        return []
    lines, line = [], ""
    for word in str(s).split():
        trial = (line + " " + word).strip()
        if _tw(d, trial, f) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _rr(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _pin(d, x, y, s, color, hole):
    r = s / 2
    d.ellipse([x, y, x + s, y + s], fill=color)
    d.polygon([(x + r, y + s + r * 0.85), (x + s * 0.22, y + s * 0.72),
               (x + s * 0.78, y + s * 0.72)], fill=color)
    d.ellipse([x + r - s * 0.15, y + r - s * 0.15, x + r + s * 0.15, y + r + s * 0.15], fill=hole)


def _hourglass(d, x, y, s, color):
    lw = max(1, int(SCALE))
    # top & bottom caps
    d.line([x, y, x + s, y], fill=color, width=lw + 1)
    d.line([x, y + s, x + s, y + s], fill=color, width=lw + 1)
    # solid sand triangles meeting in the middle (filled, matches reference)
    d.polygon([(x, y), (x + s, y), (x + s / 2, y + s / 2)], fill=color)
    d.polygon([(x, y + s), (x + s, y + s), (x + s / 2, y + s / 2)], fill=color)


def _mailbox(d, x, y, s, color, bg):
    """Mailbox glyph for the ZIP code (arched-top box + flag + slot)."""
    lw = max(1, int(SCALE))
    # body with rounded/arched top
    d.rounded_rectangle([x, y + s * 0.34, x + s * 0.82, y + s], radius=int(s * 0.14), fill=color)
    d.pieslice([x, y + s * 0.10, x + s * 0.82, y + s * 0.62], 180, 360, fill=color)
    # mail slot (light)
    d.line([x + s * 0.16, y + s * 0.58, x + s * 0.5, y + s * 0.58], fill=bg, width=lw)
    # flag on the right, raised
    d.rectangle([x + s * 0.82, y + s * 0.20, x + s * 0.9, y + s * 0.5], fill=color)
    d.rectangle([x + s * 0.9, y + s * 0.20, x + s, y + s * 0.34], fill=color)


def _calendar(d, x, y, s, color):
    lw = max(1, int(SCALE))
    _rr(d, [x, y + s * 0.14, x + s, y + s], r=int(s * 0.14), outline=color, width=lw)
    d.line([x, y + s * 0.4, x + s, y + s * 0.4], fill=color, width=lw)
    d.line([x + s * 0.28, y, x + s * 0.28, y + s * 0.26], fill=color, width=lw)
    d.line([x + s * 0.72, y, x + s * 0.72, y + s * 0.26], fill=color, width=lw)


def _check_badge(d, x, y, s):
    d.ellipse([x, y, x + s, y + s], fill=C_CHECK_BG)
    p = s * 0.26
    lw = max(2, int(SCALE) + 1)
    d.line([(x + p, y + s * 0.52), (x + s * 0.44, y + s - p)], fill=C_CHECK, width=lw)
    d.line([(x + s * 0.44, y + s - p), (x + s - p, y + p)], fill=C_CHECK, width=lw)


def _hgrad_rounded(img, box, r, c_left, c_right):
    """Fill a rounded rectangle with a left-to-right horizontal gradient."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for i in range(w):
        t = i / max(1, w - 1)
        col = tuple(int(c_left[k] + (c_right[k] - c_left[k]) * t) for k in range(3))
        gd.line([(i, 0), (i, h)], fill=col)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    img.paste(grad, (x0, y0), mask)


def _back_arrow(d, x, y, s, color):
    lw = max(2, int(SCALE) + 1)
    mid = y + s / 2
    d.line([(x, mid), (x + s, mid)], fill=color, width=lw)
    d.line([(x, mid), (x + s * 0.42, mid - s * 0.36)], fill=color, width=lw)
    d.line([(x, mid), (x + s * 0.42, mid + s * 0.36)], fill=color, width=lw)


def render_service_screen(data: ServiceRecord, out_path: str) -> str:
    img = Image.new("RGB", (W, H), C_BG)
    d = ImageDraw.Draw(img)

    f_status = _font(True, 12)
    f_h = _font(True, 16)
    f_amt = _font(True, 15)
    f_title = _font(True, 18)
    f_body = _font(False, 11)
    f_chip = _font(False, 11)
    f_details = _font(True, 15)
    f_service = _font(True, 18)
    f_incl_h = _font(True, 13)
    f_label = _font(False, 11)
    f_value = _font(True, 12)
    f_btn = _font(True, 13)

    # ── Status bar (22px) ────────────────────────────────────────
    sb_h = 22 * SCALE
    d.rectangle([0, 0, W, sb_h], fill=C_STATUS)
    d.text((PAD, sb_h / 2), data.status_time, font=f_status, fill=C_TEXT, anchor="lm")
    bx = W - PAD - 18 * SCALE
    d.rectangle([bx, sb_h / 2 - 4 * SCALE, bx + 15 * SCALE, sb_h / 2 + 4 * SCALE], outline=C_TEXT, width=max(1, int(SCALE)))
    d.rectangle([bx + 15 * SCALE, sb_h / 2 - 2 * SCALE, bx + 17 * SCALE, sb_h / 2 + 2 * SCALE], fill=C_TEXT)
    d.rectangle([bx + 1 * SCALE, sb_h / 2 - 3 * SCALE, bx + 11 * SCALE, sb_h / 2 + 3 * SCALE], fill=C_TEXT)
    for i in range(4):
        hh = (i + 1) * 1.8 * SCALE
        sx = bx - 26 * SCALE + i * 4 * SCALE
        d.rectangle([sx, sb_h / 2 + 3 * SCALE - hh, sx + 2 * SCALE, sb_h / 2 + 3 * SCALE], fill=C_TEXT)

    # ── Header (text row ~y55 in the reference) ──────────────────
    hy = 47 * SCALE
    _back_arrow(d, PAD, hy, 14 * SCALE, C_RED)
    d.text((PAD + 26 * SCALE, hy + 7 * SCALE), "Service Information", font=f_h, fill=C_TEXT, anchor="lm")

    # ── Offer card (measured: top y=100, height ~269) ────────────
    card_x0, card_x1 = PAD, W - PAD
    ipad = 19 * SCALE
    inner = card_x0 + ipad
    inner_w = card_x1 - card_x0 - 2 * ipad
    title_lines = _wrap(d, data.service_name, f_title, inner_w)

    card_y0 = 100 * SCALE
    ch = 28 * SCALE                             # top pad -> amount
    ch += 15 * SCALE + 17 * SCALE               # amount row + gap
    ch += len(title_lines) * 23 * SCALE         # title (line height 23)
    ch += 8 * SCALE + 12 * SCALE                # divider block
    ch += 20 * SCALE                            # date
    ch += 8 * SCALE + 12 * SCALE                # divider block
    ch += 18 * SCALE                            # chips
    ch += 9 * SCALE + 12 * SCALE                # divider block
    ch += 36 * SCALE                            # buttons
    ch += 19 * SCALE                            # bottom pad
    card_y1 = card_y0 + ch
    _rr(d, [card_x0, card_y0, card_x1, card_y1], r=int(12 * SCALE),
        fill=C_CARD_BG, outline=C_CARD_BORDER, width=max(1, int(SCALE)))

    cy = card_y0 + 28 * SCALE
    badge = 15 * SCALE
    d.ellipse([inner, cy, inner + badge, cy + badge], fill=C_TEXT)
    d.text((inner + badge / 2, cy + badge / 2), "$", font=_font(True, 9), fill=(255, 255, 255), anchor="mm")
    d.text((inner + badge + 7 * SCALE, cy + badge / 2), f"${data.amount}", font=f_amt, fill=C_TEXT, anchor="lm")
    cy += 15 * SCALE + 17 * SCALE
    for ln in title_lines:
        d.text((inner, cy), ln, font=f_title, fill=C_TEXT)
        cy += 23 * SCALE
    cy += 8 * SCALE
    d.line([(inner, cy), (inner + inner_w, cy)], fill=C_DIVIDER, width=max(1, int(SCALE)))
    cy += 12 * SCALE
    _calendar(d, inner, cy - 1 * SCALE, 12 * SCALE, C_MUTED)
    d.text((inner + 18 * SCALE, cy + 1 * SCALE), data.booking_datetime, font=f_body, fill=C_MUTED)
    cy += 20 * SCALE + 8 * SCALE
    d.line([(inner, cy), (inner + inner_w, cy)], fill=C_DIVIDER, width=max(1, int(SCALE)))
    cy += 12 * SCALE
    cx = inner
    _pin(d, cx, cy - 1 * SCALE, 10 * SCALE, C_TEXT, C_CARD_BG); cx += 15 * SCALE
    d.text((cx, cy + 1 * SCALE), str(data.city), font=f_chip, fill=C_TEXT)
    cx += _tw(d, str(data.city), f_chip) + 15 * SCALE
    _hourglass(d, cx, cy, 10 * SCALE, C_TEXT); cx += 15 * SCALE
    d.text((cx, cy + 1 * SCALE), str(data.estimated_time), font=f_chip, fill=C_TEXT)
    cx += _tw(d, str(data.estimated_time), f_chip) + 15 * SCALE
    _mailbox(d, cx, cy, 12 * SCALE, C_TEXT, C_CARD_BG); cx += 16 * SCALE
    d.text((cx, cy + 1 * SCALE), str(data.zipcode), font=f_chip, fill=C_TEXT)
    cy += 18 * SCALE + 9 * SCALE
    d.line([(inner, cy), (inner + inner_w, cy)], fill=C_DIVIDER, width=max(1, int(SCALE)))
    cy += 12 * SCALE
    btn_h = 36 * SCALE
    d.text((inner + 20 * SCALE, cy + btn_h / 2), "Reject", font=f_btn, fill=C_RED, anchor="lm")
    acc_w = 128 * SCALE
    acc_x0 = inner + inner_w - acc_w
    _hgrad_rounded(img, [acc_x0, cy, inner + inner_w, cy + btn_h], int(6 * SCALE), C_ACCENT_L, C_ACCENT_R)
    d.text((acc_x0 + acc_w / 2, cy + btn_h / 2), "Accept", font=f_btn, fill=(255, 255, 255), anchor="mm")

    # ── Details (measured y~411) ─────────────────────────────────
    y = card_y1 + 40 * SCALE
    d.text((PAD, y), "Details", font=f_details, fill=C_TEXT)
    y += 35 * SCALE
    d.text((PAD, y), "Customer", font=f_label, fill=C_MUTED)
    y += 28 * SCALE
    d.text((PAD, y), str(data.customer_name), font=f_value, fill=C_TEXT)
    y += 26 * SCALE
    d.line([(PAD, y), (W - PAD, y)], fill=C_LINE, width=max(1, int(SCALE)))
    y += 18 * SCALE
    d.text((PAD, y), "Customer Instructions", font=f_label, fill=C_MUTED)
    y += 21 * SCALE
    for ln in _wrap(d, data.customer_instructions, f_value, W - 2 * PAD):
        d.text((PAD, y), ln, font=f_value, fill=C_TEXT)
        y += 21 * SCALE
    y += 18 * SCALE

    # ── Service box (bordered) ───────────────────────────────────
    box_top = y
    bx0, bx1 = PAD, W - PAD
    bpad = 18 * SCALE
    yy = box_top + 24 * SCALE
    for ln in _wrap(d, data.clean_service_name, f_service, bx1 - bx0 - 2 * bpad):
        d.text((bx0 + bpad, yy), ln, font=f_service, fill=C_TEXT)
        yy += 26 * SCALE
    yy += 10 * SCALE
    d.line([(bx0 + bpad, yy), (bx1 - bpad, yy)], fill=C_LINE, width=max(1, int(SCALE)))
    yy += 24 * SCALE
    if data.includes:
        d.text((bx0 + bpad, yy), "Service Includes", font=f_incl_h, fill=C_TEXT)
        yy += 28 * SCALE
        inc_top = yy - 8 * SCALE
        row_items = []
        rows_h = 0
        for item in data.includes:
            lines = _wrap(d, item, f_body, bx1 - bx0 - 2 * bpad - 26 * SCALE - 12 * SCALE)
            rh = max(1, len(lines)) * 17 * SCALE + 15 * SCALE
            row_items.append((lines, rh)); rows_h += rh
        _rr(d, [bx0 + bpad - 8 * SCALE, inc_top, bx1 - bpad + 8 * SCALE, inc_top + rows_h + 8 * SCALE],
            r=int(8 * SCALE), fill=C_INCLUDE_BOX)
        yy = inc_top + 8 * SCALE
        for lines, rh in row_items:
            _check_badge(d, bx0 + bpad, yy, 17 * SCALE)
            ty = yy + 1 * SCALE
            for ln in lines:
                d.text((bx0 + bpad + 27 * SCALE, ty), ln, font=f_body, fill=C_INCLUDE_TXT)
                ty += 17 * SCALE
            yy += rh
        yy += 8 * SCALE
    if data.addons:
        yy += 2 * SCALE
        d.text((bx0 + bpad, yy), "Service Details", font=f_incl_h, fill=C_TEXT)
        yy += 26 * SCALE
        for q, a in data.addons:
            d.text((bx0 + bpad, yy), str(q), font=f_label, fill=C_MUTED)
            d.text((bx1 - bpad, yy), str(a), font=f_value, fill=C_TEXT, anchor="ra")
            yy += 24 * SCALE
    yy += bpad
    _rr(d, [bx0, box_top, bx1, yy], r=int(10 * SCALE), outline=C_SERVICE_BORDER, width=max(1, int(SCALE)))

    # ── Frame to fixed OUT_H (image-1) or fit-to-content ─────────
    content_bottom = int(min(yy + BOTTOM_MARGIN * SCALE, H))
    if FIT_TO_CONTENT:
        cropped = img.crop((0, 0, W, content_bottom))
        final = cropped.resize((OUT_W, max(1, round(content_bottom / SCALE))), Image.LANCZOS)
    else:
        frame = Image.new("RGB", (W, OUT_H * SCALE), C_BG)
        frame.paste(img.crop((0, 0, W, min(content_bottom, OUT_H * SCALE))), (0, 0))
        final = frame.resize((OUT_W, OUT_H), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    final.save(out_path)
    return out_path
