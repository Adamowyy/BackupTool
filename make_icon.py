#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generuje icon.ico / icon.png dla BackupTool (bez zewnętrznych plików)."""

import os

from PIL import Image, ImageDraw

ACCENT_TOP = (59, 130, 246)
ACCENT_BOTTOM = (29, 78, 216)
BASE = 512


def rounded_gradient(size: int, radius: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size))
    pixels = gradient.load()
    for y in range(size):
        ratio = y / (size - 1)
        color = tuple(int(ACCENT_TOP[i] + (ACCENT_BOTTOM[i] - ACCENT_TOP[i]) * ratio)
                      for i in range(3))
        for x in range(size):
            pixels[x, y] = color + (255,)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    image.paste(gradient, (0, 0), mask)
    return image


def draw_icon(size: int) -> Image.Image:
    image = rounded_gradient(size, radius=int(size * 0.22))
    draw = ImageDraw.Draw(image)
    unit = size / 100.0

    # strzałka w dół (kopia zapasowa)
    shaft_w = 13 * unit
    top = 24 * unit
    bottom = 55 * unit
    cx = size / 2
    draw.rounded_rectangle([cx - shaft_w / 2, top, cx + shaft_w / 2, bottom - 6 * unit],
                           radius=int(4 * unit), fill=(255, 255, 255, 255))
    arrow = [(cx - 19 * unit, bottom - 12 * unit), (cx + 19 * unit, bottom - 12 * unit),
             (cx, bottom + 8 * unit)]
    draw.polygon(arrow, fill=(255, 255, 255, 255))

    # taca pod spodem
    draw.rounded_rectangle([20 * unit, 68 * unit, 80 * unit, 82 * unit],
                           radius=int(6 * unit), fill=(255, 255, 255, 235))
    return image


def main() -> None:
    base = draw_icon(BASE)
    here = os.path.dirname(os.path.abspath(__file__))
    base.resize((256, 256), Image.LANCZOS).save(os.path.join(here, "icon.png"))
    base.save(os.path.join(here, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("zapisano icon.ico i icon.png")


if __name__ == "__main__":
    main()
