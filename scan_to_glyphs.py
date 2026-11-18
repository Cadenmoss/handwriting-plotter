#!/usr/bin/env python3
"""Turn scans of the filled-in template into glyphs.json (single-line strokes).

  .venv/bin/python scan_to_glyphs.py template/meta.json scan1.png scan2.png ... -o glyphs.json

Scans must be in page order, flat and unrotated, with the black frame fully
visible and nothing dark outside it.
"""
import argparse
import json
import warnings

warnings.filterwarnings("ignore")   # scikit-image deprecation chatter

import numpy as np
from PIL import Image
from skimage.measure import label, regionprops
from skimage.morphology import closing, disk, remove_small_objects

from hwlib import BASELINE_FROM_TOP, CELL_UNITS, normalize_glyphs, trace_mask


def load_min_channel(path):
    im = np.asarray(Image.open(path).convert("RGB"))
    return im.min(axis=2)                      # min channel: blue guides stay "paper"


def find_frame_corners(mask):
    """Corners (tl, tr, br, bl) of the biggest connected dark blob = the black frame."""
    lab = label(mask, connectivity=2)
    props = regionprops(lab)
    if not props:
        raise SystemExit("no dark frame found in scan")
    big = max(props, key=lambda r: r.area_bbox)
    ys, xs = big.coords[:, 0], big.coords[:, 1]
    pick = lambda score: (float(xs[np.argmax(score)]), float(ys[np.argmax(score)]))
    return pick(-(xs + ys)), pick(xs - ys), pick(xs + ys), pick(ys - xs)


def deskew(gray, meta, threshold):
    """Warp the scan so the frame lands exactly where it is on the template
    (fixes rotation, scale and mild perspective), then threshold to ink."""
    tl, tr, br, bl = find_frame_corners(gray < threshold)
    ox0, oy0, ox1, oy1 = meta["frame_outer_px"]
    w, h = ox1 - ox0, oy1 - oy0
    quad = (*tl, *bl, *br, *tr)                # PIL QUAD order: NW, SW, SE, NE of the source
    warped = Image.fromarray(gray).transform((w, h), Image.QUAD, quad, Image.BILINEAR, fillcolor=255)
    return np.asarray(warped) < threshold


def extract_page(path, meta, page_meta, threshold, glyphs):
    mask = deskew(load_min_channel(path), meta, threshold)
    ox0, oy0, _, _ = meta["frame_outer_px"]
    gx, gy = meta["grid_origin_px"]
    cell = meta["cell_px"]
    unit = cell / CELL_UNITS
    gx0, gy0 = gx - ox0, gy - oy0
    got = 0
    for k, c in enumerate(page_meta["cells"]):
        r, col = divmod(k, meta["cols"])
        x0, y0 = int(round(gx0 + col * cell)), int(round(gy0 + r * cell))
        inset = int(0.03 * cell)
        sub = mask[y0 + inset:y0 + cell - inset, x0 + inset:x0 + cell - inset]
        sub = remove_small_objects(sub, max_size=20)
        if sub.sum() < 30:
            continue
        sub = closing(sub, disk(max(1, int(unit * 0.02))))
        paths = trace_mask(sub, min_spur=0.12 * unit, eps=0.012 * unit)
        if not paths:
            continue
        base_px = BASELINE_FROM_TOP * unit - inset        # baseline row inside the cropped cell
        glyph = [[((x + inset) / unit, (base_px + inset - y) / unit) for x, y in p] for p in paths]
        minx = min(p[0] for s in glyph for p in s)
        glyph = [[[round(x - minx, 3), round(y, 3)] for x, y in s] for s in glyph]
        glyphs.setdefault(c["char"], []).append(glyph)
        got += 1
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meta")
    ap.add_argument("scans", nargs="+")
    ap.add_argument("-o", "--out", default="glyphs.json")
    ap.add_argument("--threshold", type=int, default=120, help="0-255; ink is darker than this (default 120)")
    a = ap.parse_args()
    meta = json.load(open(a.meta))
    glyphs = {}
    for path, pm in zip(a.scans, meta["pages"]):
        n = extract_page(path, meta, pm, a.threshold, glyphs)
        print(f"{path}: {n}/{len(pm['cells'])} squares had ink")
    glyphs, info = normalize_glyphs(glyphs)
    print("normalised baselines/size:", info)
    json.dump({"version": 1, "unit": "x-height", "glyphs": glyphs}, open(a.out, "w"))
    print(f"wrote {a.out}: {len(glyphs)} characters, {sum(map(len, glyphs.values()))} samples")


if __name__ == "__main__":
    main()
