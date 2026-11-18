#!/usr/bin/env python3
"""Make a printable handwriting template (for the 'scan my writing' route).

  .venv/bin/python make_template.py            -> template/page1.png ... template.pdf, template/meta.json

Print template.pdf at 100% scale (US Letter), write one glyph in every square
with a dark pen, then scan each page flat (300 dpi is plenty) and run
scan_to_glyphs.py. The light-blue guides drop out when the scan is thresholded.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

from hwlib import BASELINE_FROM_TOP, CELL_UNITS

CHARS = [*"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,!?'\"-:;()"]
VARIANTS = 2
W, H = 2550, 3300            # US Letter at 300 dpi
COLS, CELL = 6, 375
ROWS = 7
GRID_X0 = (W - COLS * CELL) // 2
GRID_Y0 = 330
PAD, FRAME_W = 18, 8         # frame sits PAD px outside the grid


def main():
    os.makedirs("template", exist_ok=True)
    items = [(c, v) for v in range(VARIANTS) for c in CHARS]     # all glyphs once, then again
    per_page = COLS * ROWS
    pages, meta_pages = [], []
    font = ImageFont.load_default(size=40)
    small = ImageFont.load_default(size=30)
    for pi in range(0, len(items), per_page):
        chunk = items[pi:pi + per_page]
        im = Image.new("RGB", (W, H), "white")
        d = ImageDraw.Draw(im)
        d.text((GRID_X0, 120), f"Handwriting template - page {len(pages) + 1}", fill=(40, 40, 40), font=font)
        d.text((GRID_X0, 185), "Write the shown character in each square, sitting on the solid line. "
               "Dashed line = height of a lowercase 'x'. Use a dark pen; stay inside the squares.",
               fill=(90, 90, 90), font=small)
        d.text((GRID_X0, 235), "Scan flat, all four frame edges visible, nothing outside the black frame.",
               fill=(90, 90, 90), font=small)
        for k, (ch, var) in enumerate(chunk):
            r, c = divmod(k, COLS)
            x0, y0 = GRID_X0 + c * CELL, GRID_Y0 + r * CELL
            d.rectangle([x0, y0, x0 + CELL, y0 + CELL], outline=(190, 215, 255), width=3)
            by = y0 + CELL * BASELINE_FROM_TOP / CELL_UNITS
            xh = CELL / CELL_UNITS
            d.line([x0, by, x0 + CELL, by], fill=(150, 185, 245), width=3)
            for xx in range(x0, x0 + CELL, 24):
                d.line([xx, by - xh, xx + 12, by - xh], fill=(190, 215, 255), width=3)
            d.text((x0 + 8, y0 + 4), f"{ch}", fill=(150, 185, 245), font=small)
        o = (GRID_X0 - PAD, GRID_Y0 - PAD, GRID_X0 + COLS * CELL + PAD, GRID_Y0 + ROWS * CELL + PAD)
        d.rectangle(o, outline="black", width=FRAME_W)
        pages.append(im)
        meta_pages.append({"cells": [{"char": ch, "variant": v} for ch, v in chunk]})
        im.save(f"template/page{len(pages)}.png", dpi=(300, 300))
    pages[0].save("template.pdf", save_all=True, append_images=pages[1:], resolution=300)
    meta = {"page_px": [W, H], "cols": COLS, "rows": ROWS, "cell_px": CELL,
            "grid_origin_px": [GRID_X0, GRID_Y0], "frame_outer_px": list(o),
            "pages": meta_pages}
    with open("template/meta.json", "w") as f:
        json.dump(meta, f)
    print(f"wrote template.pdf ({len(pages)} pages, {len(items)} squares) and template/meta.json")


if __name__ == "__main__":
    main()
