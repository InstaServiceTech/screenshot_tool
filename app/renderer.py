"""
renderer.py — draws the "Service Information" screen as a PNG using Pillow.

All geometry, colours and type sizes in this file were measured pixel-by-pixel
from a real device screenshot (1080 x 2400, Android, density 2.625), so the
design space below IS that screenshot: 1 unit == 1 pixel of the real screen.

Icons are hand-drawn vector approximations of the app's own glyphs:
  - map pin (solid teardrop with knockout)
  - hourglass with flowing sand (filled top bulb, outlined lower bulb, mound)
  - ZIP envelope (solid envelope + "ZIP" tag)
  - calendar with clock (steel-blue line icon, binding rings, dot grid)
  - green check badge (tapered heavy check)

Public API (unchanged):
    render_service_screen(data: ServiceRecord, out_path: str) -> str
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

# ── Fonts ────────────────────────────────────────────────────────────────────
# The app uses Roboto. Real Roboto is bundled in app/fonts/ and is required for
# an exact match — DejaVu is only an emergency fallback and will NOT match.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BUNDLED = os.path.join(_HERE, "fonts")

_REG_CANDIDATES = [
    os.path.join(_BUNDLED, "Roboto-Regular.ttf"),
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    os.path.join(_BUNDLED, "DejaVuSans.ttf"),
]
_BOLD_CANDIDATES = [
    os.path.join(_BUNDLED, "Roboto-Bold.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    os.path.join(_BUNDLED, "DejaVuSans-Bold.ttf"),
]


def _first_existing(cands):
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


_REG = _first_existing(_REG_CANDIDATES)
_BOLD = _first_existing(_BOLD_CANDIDATES) or _REG

# ── Canvas ───────────────────────────────────────────────────────────────────
REF_W = 1080                   # design space width == real screenshot width
REF_H = 2400                   # real screenshot height (used when not fitting)
OUT_W = 1080                   # output width; set 386 for a small PNG
FIT_TO_CONTENT = False         # False: fixed 1080x2400 phone frame (matches a real
#                                screenshot). True: grow to fit, nothing cropped.
SS = 2                         # supersample factor (downscaled at the end)
BOTTOM_MARGIN = 34

_SCRATCH_H = 6000


def _f(bold: bool, size: int):
    """Font at design-space `size`, scaled up for supersampling."""
    path = _BOLD if bold else _REG
    if path:
        try:
            return ImageFont.truetype(path, int(round(size * SS)))
        except OSError:
            pass
    return ImageFont.load_default(size=int(round(size * SS)))


def P(v: float) -> float:
    """Design-space unit -> supersampled canvas unit."""
    return v * SS


# ── Palette (sampled from the reference screenshot) ──────────────────────────
C_BG = (255, 255, 255)
C_STATUS_BG = (250, 250, 250)
C_NAVY = (29, 53, 87)             # #1D3557 — all body/heading text
C_RED = (228, 37, 53)             # #E42535 — back arrow + Reject
C_CARD_BG = (255, 250, 229)       # #FFFAE5
C_CARD_BORDER = (242, 175, 87)    # #F2AF57
C_CARD_DIVIDER = (237, 242, 244)  # #EDF2F4
C_ACCEPT_L = (228, 39, 53)        # #E42735
C_ACCEPT_R = (230, 85, 57)        # #E65539
C_LINE = (237, 242, 244)          # #EDF2F4 — Details divider
C_BOX_BORDER = (235, 235, 235)    # #EBEBEB — service box outline
C_INCLUDE_BG = (248, 249, 250)    # #F8F9FA
C_INCLUDE_TXT = (100, 116, 139)   # #64748B
C_CHECK_BG = (224, 242, 233)      # #E0F2E9
C_CHECK = (17, 17, 17)
C_CAL_ICON = (141, 153, 174)      # #8D99AE
C_CHIP_ICON = (0, 0, 0)

# ── Type scale (design-space px; divide by 2.625 for sp) ─────────────────────
T_STATUS = 34
T_HEADER = 51
T_AMOUNT = 37
T_TITLE = 49
T_DATE = 32
T_CHIP = 32
T_BUTTON = 41
T_DETAILS = 44
T_LABEL = 39
T_VALUE = 42
T_INSTR = 38
T_SERVICE = 58
T_INCL_HEAD = 52
T_INCL_ITEM = 43

# Gap between the three chips (pin/city, hourglass/time, ZIP/zipcode).
# 30 is the exact device measurement; a little more air reads better.
CHIP_GAP = 42 * SS


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


# ── Text helpers ─────────────────────────────────────────────────────────────
def _txt(d, x, y, s, font, fill):
    """Draw so the ink's top-left lands exactly on (x, y) — matches measurements."""
    s = "" if s is None else str(s)
    if not s:
        return
    bb = font.getbbox(s)
    d.text((x - bb[0], y - bb[1]), s, font=font, fill=fill)


def _txt_right(d, right, y, s, font, fill):
    """Right-align so the ink's right edge lands on `right` (stays inside the box)."""
    s = "" if s is None else str(s)
    if not s:
        return
    bb = font.getbbox(s)
    _txt(d, right - (bb[2] - bb[0]), y, s, font, fill)


def _tw(d, s, f) -> float:
    return d.textlength("" if s is None else str(s), font=f)


def _wrap(d, s, f, max_w) -> List[str]:
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
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=int(width))


def _hgrad_rounded(img, box, r, c_left, c_right):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    for i in range(w):
        t = i / max(1, w - 1)
        gd.line([(i, 0), (i, h)],
                fill=tuple(int(c_left[k] + (c_right[k] - c_left[k]) * t) for k in range(3)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(r), fill=255)
    img.paste(grad, (x0, y0), mask)


# ── Icons ────────────────────────────────────────────────────────────────────
def _pin(d, x, y, w, h, color, hole):
    """Solid teardrop map pin with a knocked-out circle (matches the app glyph)."""
    r = w / 2.0
    cx, cy = x + r, y + r
    d.ellipse([x, y, x + w, y + w], fill=color)
    tip_y = y + h
    d.polygon([
        (cx - r * 0.99, cy + r * 0.10),
        (cx - r * 0.86, cy + r * 0.55),
        (cx - r * 0.50, cy + (tip_y - cy) * 0.62),
        (cx, tip_y),
        (cx + r * 0.50, cy + (tip_y - cy) * 0.62),
        (cx + r * 0.86, cy + r * 0.55),
        (cx + r * 0.99, cy + r * 0.10),
    ], fill=color)
    hr = w * 0.155
    d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=hole)


def _bulb_side(x_out, x_in, y_out, y_in, curve=1.15, steps=20):
    """Flank of an hourglass bulb: stays wide near the cap, pinches at the neck."""
    return [(x_out + (x_in - x_out) * ((i / steps) ** curve),
             y_out + (y_in - y_out) * (i / steps)) for i in range(steps + 1)]


def _hourglass(d, x, y, w, h, color, bg):
    """Hourglass with flowing sand: thick caps, filled top bulb, sand mound below."""
    bar = h * 0.085
    lw = max(1, int(round(w * 0.10)))
    nx, ny = x + w / 2.0, y + h / 2.0
    y_top, y_bot = y + bar, y + h - bar

    # upper bulb — solid sand, with a thin air gap under the cap
    left = _bulb_side(x + w * 0.03, nx - w * 0.045, y_top, ny)
    right = _bulb_side(x + w * 0.97, nx + w * 0.045, y_top, ny)
    d.polygon(left + right[::-1], fill=color)
    d.rectangle([x + w * 0.10, y_top, x + w * 0.90, y_top + h * 0.075], fill=bg)

    # lower bulb — outline only, plus the sand mound it is falling into
    l2 = _bulb_side(x + w * 0.03, nx - w * 0.045, y_bot, ny)
    r2 = _bulb_side(x + w * 0.97, nx + w * 0.045, y_bot, ny)
    d.line(l2, fill=color, width=lw, joint="curve")
    d.line(r2, fill=color, width=lw, joint="curve")

    mound_top = y_bot - h * 0.185
    d.polygon([(x + w * 0.05, y_bot), (x + w * 0.95, y_bot),
               (nx + w * 0.30, mound_top), (nx - w * 0.30, mound_top)], fill=color)
    d.line([(nx, ny), (nx, mound_top)], fill=color, width=max(1, int(lw * 0.7)))

    # caps
    d.rectangle([x, y, x + w, y + bar], fill=color)
    d.rectangle([x, y + h - bar, x + w, y + h], fill=color)


def _zip_envelope(d, x, y, w, h, color, bg):
    """Solid envelope with a folded flap and a 'ZIP' tag over the bottom-right."""
    ex0, ey0 = x, y
    ex1, ey1 = x + w * 0.93, y + h
    d.rectangle([ex0, ey0, ex1, ey1], fill=color)

    flw = max(1, int(round(h * 0.085)))
    apex = ((ex0 + ex1) / 2.0, ey0 + h * 0.52)
    d.line([(ex0 + flw * 0.45, ey0 + flw * 0.45), apex], fill=bg, width=flw, joint="curve")
    d.line([(ex1 - flw * 0.45, ey0 + flw * 0.45), apex], fill=bg, width=flw, joint="curve")

    tx0, ty0, tx1, ty1 = x + w * 0.34, y + h * 0.52, x + w, y + h
    g = max(1, int(round(h * 0.075)))
    d.rectangle([tx0 - g, ty0 - g, tx1, ty1], fill=bg)
    d.rectangle([tx0, ty0, tx1, ty1], fill=color)

    zf = _f(True, max(6, int(round((ty1 - ty0) * 0.66 / SS))))
    bb = d.textbbox((0, 0), "ZIP", font=zf)
    d.text(((tx0 + tx1) / 2 - (bb[2] - bb[0]) / 2 - bb[0],
            (ty0 + ty1) / 2 - (bb[3] - bb[1]) / 2 - bb[1]), "ZIP", font=zf, fill=bg)


def _calendar_clock(d, x, y, w, h, color, bg):
    """Line-art calendar with binding rings, a dot grid and an overlapping clock."""
    lw = max(1, int(round(w * 0.062)))
    bw = w * 0.80
    bx0, by0, bx1, by1 = x, y + h * 0.135, x + bw, y + h * 0.90
    _rr(d, [bx0, by0, bx1, by1], r=int(w * 0.10), outline=color, width=lw)
    d.line([(bx0, by0 + h * 0.185), (bx1, by0 + h * 0.185)], fill=color, width=lw)

    for fx in (0.18, 0.38, 0.58, 0.78):
        rx = bx0 + bw * fx
        d.line([(rx, y + h * 0.03), (rx, y + h * 0.235)], fill=color, width=lw)

    dw, dh = bw * 0.145, h * 0.052
    cols = [0.12, 0.32, 0.52, 0.72]
    for ry, active in ((0.42, (1, 2, 3)), (0.585, (0, 1, 2, 3)), (0.735, (0, 1))):
        for ci in active:
            dx0 = bx0 + bw * cols[ci]
            dy0 = y + h * ry
            _rr(d, [dx0, dy0, dx0 + dw, dy0 + dh], r=int(dh / 2), fill=color)

    ccx, ccy, cr = x + w * 0.775, y + h * 0.735, w * 0.245
    d.ellipse([ccx - cr - lw * 1.7, ccy - cr - lw * 1.7,
               ccx + cr + lw * 1.7, ccy + cr + lw * 1.7], fill=bg)
    d.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr], outline=color, width=lw)
    d.line([(ccx, ccy), (ccx, ccy - cr * 0.55)], fill=color, width=lw)
    d.line([(ccx, ccy), (ccx + cr * 0.55, ccy)], fill=color, width=lw)


def _check_badge(d, x, y, s, bg=C_CHECK_BG, color=C_CHECK):
    """Pale circle + heavy tapered check mark."""
    d.ellipse([x, y, x + s, y + s], fill=bg)
    sx, sy = x + s * 0.235, y + s * 0.505
    ex, ey = x + s * 0.435, y + s * 0.715
    tx, ty = x + s * 0.790, y + s * 0.290
    t1, t2 = s * 0.105, s * 0.075
    d.polygon([
        (sx, sy - t1 * 0.55),
        (ex, ey - t1 * 1.15),
        (tx, ty - t2),
        (tx + t2 * 0.45, ty + t2 * 0.35),
        (ex + t1 * 0.10, ey + t1 * 0.55),
        (sx - t1 * 0.35, sy + t1 * 0.95),
    ], fill=color)


def _dollar_badge(d, x, y, s, circle=C_NAVY, glyph=(255, 255, 255)):
    d.ellipse([x, y, x + s, y + s], fill=circle)
    f = _f(True, max(6, int(round(s * 0.60 / SS))))
    bb = d.textbbox((0, 0), "$", font=f)
    d.text((x + s / 2 - (bb[2] - bb[0]) / 2 - bb[0],
            y + s / 2 - (bb[3] - bb[1]) / 2 - bb[1]), "$", font=f, fill=glyph)


def _back_arrow(d, x, y, w, h, color):
    lw = max(2, int(round(h * 0.19)))
    mid = y + h / 2.0
    d.line([(x + lw * 0.4, mid), (x + w, mid)], fill=color, width=lw)
    d.line([(x + lw * 0.5, mid), (x + w * 0.46, y + lw * 0.5)],
           fill=color, width=lw, joint="curve")
    d.line([(x + lw * 0.5, mid), (x + w * 0.46, y + h - lw * 0.5)],
           fill=color, width=lw, joint="curve")


def _wifi(d, x, y, w, h, color):
    """Android wifi glyph: a filled fan — apex at the bottom, arc across the top."""
    cx, cy = x + w / 2.0, y + h
    r = h
    half = math.degrees(math.asin(min(1.0, (w / 2.0) / r)))
    d.pieslice([cx - r, cy - r, cx + r, cy + r], 270 - half, 270 + half, fill=color)


def _signal(d, x, y, w, h, color):
    """Signal strength: filled right triangle, vertical edge on the right."""
    d.polygon([(x, y + h), (x + w, y + h), (x + w, y)], fill=color)


def _battery(d, x, y, w, h, color):
    """Upright battery: rounded body with a small nub on top."""
    nub_h = h * 0.09
    d.rounded_rectangle([x, y + nub_h, x + w, y + h], radius=max(1, w * 0.16), fill=color)
    d.rounded_rectangle([x + w * 0.30, y, x + w * 0.70, y + nub_h * 2],
                        radius=max(1, w * 0.10), fill=color)


def _status_bar(d, w, data):
    """Status bar measured from the device: #FAFAFA strip, #646464 glyphs."""
    ink = (100, 100, 100)
    d.rectangle([0, 0, w, P(62)], fill=C_STATUS_BG)
    _txt(d, P(46), P(12), data.status_time, _f(False, T_STATUS), ink)

    right = w - P(75)                       # battery's right edge
    _battery(d, right - P(20), P(14), P(20), P(34), ink)
    _signal(d, right - P(20) - P(19) - P(33), P(14), P(33), P(33), ink)
    _wifi(d, right - P(20) - P(19) - P(33) - P(4) - P(39), P(14), P(39), P(33), ink)


def _home_indicator(d, w, h):
    """The gesture pill at the bottom of the phone frame."""
    bw = P(284)
    d.rounded_rectangle([w / 2 - bw / 2, h - P(36), w / 2 + bw / 2, h - P(27)],
                        radius=P(5), fill=(29, 33, 41))


# ── Main ─────────────────────────────────────────────────────────────────────
def render_service_screen(data: ServiceRecord, out_path: str) -> str:
    W = int(P(REF_W))
    img = Image.new("RGB", (W, int(P(_SCRATCH_H))), C_BG)
    d = ImageDraw.Draw(img)

    f_header = _f(True, T_HEADER)
    f_amount = _f(True, T_AMOUNT)
    f_title = _f(True, T_TITLE)
    f_date = _f(False, T_DATE)
    f_chip = _f(True, T_CHIP)
    f_btn = _f(True, T_BUTTON)
    f_details = _f(True, T_DETAILS)
    f_label = _f(False, T_LABEL)
    f_value = _f(True, T_VALUE)
    f_instr = _f(True, T_INSTR)
    f_service = _f(True, T_SERVICE)
    f_incl_h = _f(True, T_INCL_HEAD)
    f_incl = _f(False, T_INCL_ITEM)

    _status_bar(d, W, data)
    _back_arrow(d, P(65), P(139), P(42), P(32), C_RED)
    _txt(d, P(159), P(136), "Service Information", f_header, C_NAVY)

    # ── Offer card ───────────────────────────────────────────────
    CX0, CX1 = P(44), P(1035)
    IN_L, IN_R = P(98), P(980)
    card_y0 = P(273)

    title_lines = _wrap(d, data.service_name, f_title, IN_R - IN_L)
    instr_lines = _wrap(d, data.customer_instructions, f_instr, P(1036) - P(44))

    card_y1 = card_y0 + P(168) + len(title_lines) * P(55) + P(477)

    _rr(d, [CX0, card_y0, CX1, card_y1], r=P(32),
        fill=C_CARD_BG, outline=C_CARD_BORDER, width=max(1, int(P(1.5))))

    _dollar_badge(d, IN_L, card_y0 + P(88), P(36))
    _txt(d, P(162), card_y0 + P(88), f"${data.amount}", f_amount, C_NAVY)

    ty = card_y0 + P(168)
    for ln in title_lines:
        _txt(d, IN_L, ty, ln, f_title, C_NAVY)
        ty += P(55)

    y = ty + P(22)
    d.rectangle([IN_L, y, IN_R, y + P(2)], fill=C_CARD_DIVIDER)

    y += P(49)
    _calendar_clock(d, IN_L, y, P(39), P(40), C_CAL_ICON, C_CARD_BG)
    _txt(d, P(151), y + P(8), data.booking_datetime, f_date, C_NAVY)

    y += P(85)
    d.rectangle([IN_L, y, IN_R, y + P(2)], fill=C_CARD_DIVIDER)

    y += P(50)
    _pin(d, IN_L, y + P(1), P(27), P(33), C_CHIP_ICON, C_CARD_BG)
    cx = IN_L + P(40)
    _txt(d, cx, y + P(1), data.city, f_chip, C_NAVY)
    cx += _tw(d, data.city, f_chip) + CHIP_GAP
    _hourglass(d, cx, y, P(26), P(34), C_CHIP_ICON, C_CARD_BG)
    cx += P(26) + P(13)
    _txt(d, cx, y + P(1), data.estimated_time, f_chip, C_NAVY)
    cx += _tw(d, data.estimated_time, f_chip) + CHIP_GAP - P(4)
    _zip_envelope(d, cx, y + P(2), P(40), P(32), C_CHIP_ICON, C_CARD_BG)
    cx += P(40) + P(26)
    _txt(d, cx, y + P(1), data.zipcode, f_chip, C_NAVY)

    y += P(83)
    d.rectangle([IN_L, y, IN_R, y + P(3)], fill=C_CARD_DIVIDER)

    y += P(29)
    btn_h = P(105)
    _txt(d, P(254), y + P(33), "Reject", f_btn, C_RED)
    ax0, ax1 = P(581), P(953)
    _hgrad_rounded(img, [ax0, y, ax1, y + btn_h], P(16), C_ACCEPT_L, C_ACCEPT_R)
    bb = d.textbbox((0, 0), "Accept", font=f_btn)
    d.text(((ax0 + ax1) / 2 - (bb[2] - bb[0]) / 2 - bb[0],
            y + btn_h / 2 - (bb[3] - bb[1]) / 2 - bb[1]),
           "Accept", font=f_btn, fill=(255, 255, 255))

    # ── Details ──────────────────────────────────────────────────
    PX0, PX1 = P(44), P(1036)
    y = card_y1 + P(107)
    _txt(d, PX0, y, "Details", f_details, C_NAVY)
    y += P(98)
    _txt(d, P(45), y, "Customer", f_label, C_NAVY)
    y += P(80)
    _txt(d, PX0, y, data.customer_name, f_value, C_NAVY)
    y += P(84)
    d.rectangle([PX0, y, PX1, y + P(3)], fill=C_LINE)
    y += P(39)
    _txt(d, P(45), y, "Customer Instructions", f_label, C_NAVY)
    y += P(63)
    for ln in instr_lines:
        _txt(d, PX0, y, ln, f_instr, C_NAVY)
        y += P(59)

    # ── Service box ──────────────────────────────────────────────
    box_y0 = y + P(49)
    BX0, BX1 = P(43), P(1036)
    BIN_L, BIN_R = P(98), P(982)

    yy = box_y0 + P(83)
    for ln in _wrap(d, data.clean_service_name, f_service, BIN_R - BIN_L):
        _txt(d, BIN_L, yy, ln, f_service, C_NAVY)
        yy += P(66)
    yy += P(48)
    d.rectangle([BIN_L, yy, BIN_R, yy + P(3)], fill=C_CARD_DIVIDER)
    yy += P(60)

    if data.includes:
        _txt(d, P(99), yy, "Service Includes", f_incl_h, C_NAVY)
        yy += P(85)
        rows = []
        text_w = BIN_R - P(252) - P(20)
        for item in data.includes:
            lines = _wrap(d, item, f_incl, text_w)
            rows.append((lines, len(lines) * P(55) + P(24)))
        box_h = P(78) + sum(h for _, h in rows) + P(27) * (len(rows) - 1)
        _rr(d, [P(97), yy, P(982), yy + box_h], r=P(20), fill=C_INCLUDE_BG)

        ry = yy + P(39)
        for lines, rh in rows:
            centre = ry + rh / 2
            _check_badge(d, P(129), centre - P(39), P(78))
            ty2 = centre - (len(lines) * P(55)) / 2 + P(12)
            for ln in lines:
                _txt(d, P(252), ty2, ln, f_incl, C_INCLUDE_TXT)
                ty2 += P(55)
            ry += rh + P(27)
        yy += box_h + P(20)

    if data.addons:
        _txt(d, P(99), yy, "Service Details", f_incl_h, C_NAVY)
        yy += P(85)
        gap = P(28)
        for q, a in data.addons:
            q = "" if q is None else str(q)
            a = "" if a is None else str(a)
            q_w = _tw(d, q, f_label)
            a_max = BIN_R - BIN_L - q_w - gap
            if a_max < P(160):
                _txt(d, BIN_L, yy, q, f_label, C_INCLUDE_TXT)
                yy += P(50)
                a_lines = _wrap(d, a, f_value, BIN_R - BIN_L) or [a]
            else:
                _txt(d, BIN_L, yy, q, f_label, C_INCLUDE_TXT)
                a_lines = _wrap(d, a, f_value, a_max) or [a]
            ty = yy
            for ln in a_lines:
                _txt_right(d, BIN_R, ty, ln, f_value, C_NAVY)
                ty += P(50)
            yy = max(yy + P(66), ty + P(16))
        yy += P(10)

    yy += P(60)
    _rr(d, [BX0, box_y0, BX1, yy], r=P(26), outline=C_BOX_BORDER, width=max(1, int(P(1.5))))

    # ── Output ───────────────────────────────────────────────────
    bottom = int(min(yy + P(BOTTOM_MARGIN), P(_SCRATCH_H)))
    if FIT_TO_CONTENT:
        final_h = max(1, int(round(bottom / SS)))
        canvas = img.crop((0, 0, W, bottom))
    else:
        # 1080x2400 phone frame. Grow only when cleaning Service Details
        # (Deep Cleaning, etc.) would otherwise be clipped off the bottom.
        min_h = int(P(REF_H))
        if data.addons and bottom > min_h:
            frame_h = bottom
            final_h = int(round(frame_h / SS))
        else:
            frame_h = min_h
            final_h = REF_H
        canvas = Image.new("RGB", (W, frame_h), C_BG)
        canvas.paste(img.crop((0, 0, W, min(bottom, frame_h))), (0, 0))
        _home_indicator(ImageDraw.Draw(canvas), W, frame_h)

    out_h = max(1, int(round(final_h * OUT_W / REF_W)))
    final = canvas.resize((OUT_W, out_h), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    final.save(out_path)
    return out_path
