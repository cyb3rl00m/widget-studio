#!/usr/bin/env python3
"""Draws docs/banner.png (README header) and docs/social-preview.png (GitHub's link
preview). Needs Pillow:  pip install pillow   then:  python3 packaging/make-artwork.py"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

BG = (6, 20, 13)
GRID = (14, 38, 25)
CARD = (11, 33, 22)
CARD_EDGE = (46, 107, 58)
ACCENT = (129, 199, 132)
BRIGHT = (230, 255, 233)
TEXT = (140, 190, 145)
DIM = (85, 127, 95)

# 5x7 dot-matrix glyphs
GLYPHS = {
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    " ": ["00000"] * 7,
}


def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
              "/usr/share/fonts/TTF"):
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def mono(size):
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"):
        p = os.path.join(d, "DejaVuSansMono.ttf")
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def mono_bold(size):
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"):
        p = os.path.join(d, "DejaVuSansMono-Bold.ttf")
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return mono(size)


def dot_text(draw, x, y, text, pitch, color, off=None):
    """Draw text as dots. pitch = distance between dot centers. Unlit dots in 'off'."""
    r = pitch * 0.36
    for ch in text:
        rows = GLYPHS[ch]
        for j, row in enumerate(rows):
            for i, bit in enumerate(row):
                cx, cy = x + i * pitch, y + j * pitch
                if bit == "1":
                    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
                elif off:
                    rr = r * 0.55
                    draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=off)
        x += 6 * pitch
    return x


def dot_width(text, pitch):
    return len(text) * 6 * pitch - pitch


def background(w, h):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    for y in range(10, h, 20):
        for x in range(10, w, 20):
            d.ellipse((x - 1.2, y - 1.2, x + 1.2, y + 1.2), fill=GRID)
    return img, d


def widget_card(d, x, y, w):
    """An illustration of a widget made with Widget Studio."""
    h = 452
    d.rounded_rectangle((x, y, x + w, y + h), radius=22, fill=CARD, outline=CARD_EDGE, width=2)
    pitch = 9
    clock = "21:47"
    cx = x + (w - dot_width(clock, pitch)) // 2
    dot_text(d, cx, y + 34, clock, pitch, ACCENT, off=(20, 52, 34))
    d.text((x + w // 2, y + 116), "FRI 23 OCT 2026", font=mono(19), fill=TEXT, anchor="mm")
    d.line((x + 24, y + 142, x + w - 24, y + 142), fill=CARD_EDGE, width=2)
    d.text((x + 24, y + 156), "WEATHER", font=mono(13), fill=DIM)
    d.text((x + 24, y + 174), "18°", font=font(40, True), fill=BRIGHT)
    d.text((x + 112, y + 190), "CLEAR", font=mono(20), fill=TEXT)
    d.text((x + 24, y + 228), "FEELS 17°  HUM 52%  WIND 9 KM/H", font=mono(13), fill=TEXT)
    d.line((x + 24, y + 256, x + w - 24, y + 256), fill=CARD_EDGE, width=2)
    d.text((x + 24, y + 270), "OCTOBER 2026", font=mono(13), fill=DIM)
    days = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    f = mono(16)
    colw = (w - 48) / 7
    for i, name in enumerate(days):
        d.text((x + 24 + colw * i + colw / 2, y + 300), name, font=f, fill=DIM, anchor="mm")
    day = 1
    for row in range(5):
        for col in range(7):
            if row == 0 and col < 3:
                continue
            if day > 31:
                break
            cx, cy = x + 24 + colw * col + colw / 2, y + 326 + row * 22
            if day == 23:   # today: brightest color, bold (like the real widget's highlight)
                d.text((cx, cy), str(day), font=mono_bold(17), fill=BRIGHT, anchor="mm")
            else:
                d.text((cx, cy), str(day), font=f, fill=DIM if day < 23 else TEXT, anchor="mm")
            day += 1
    return h


def compose(w, h, card_scale=1.0):
    img, d = background(w, h)
    pitch = 13 if h >= 600 else 11
    left = 80
    top = (h - (18 * pitch + 150)) // 2   # title (2 dot rows) + text block, centered
    dot_text(d, left, top, "WIDGET", pitch, ACCENT, off=(16, 44, 29))
    dot_text(d, left, top + 9 * pitch, "STUDIO", pitch, BRIGHT, off=(16, 44, 29))
    ty = top + 18 * pitch
    d.text((left, ty), "Design your own desktop widgets for Linux.", font=font(30, True), fill=BRIGHT)
    d.text((left, ty + 44), "Clock, weather, calendar and system stats.",
           font=font(24), fill=TEXT)
    d.text((left, ty + 76), "Your colors, your fonts, live on your desktop.", font=font(24), fill=TEXT)
    d.text((left, ty + 124), "COSMIC  ·  KDE Plasma  ·  Cinnamon  ·  XFCE   —   free and open source",
           font=font(18), fill=DIM)

    card_w = 340
    card_x = w - card_w - 80
    card_y = (h - 452) // 2
    widget_card(d, card_x, card_y, card_w)
    return img


def main():
    os.makedirs(DOCS, exist_ok=True)
    compose(1280, 640).save(os.path.join(DOCS, "social-preview.png"), optimize=True)
    compose(1280, 560).save(os.path.join(DOCS, "banner.png"), optimize=True)
    print("wrote docs/social-preview.png and docs/banner.png")


if __name__ == "__main__":
    main()
