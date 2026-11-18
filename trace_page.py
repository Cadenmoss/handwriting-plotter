#!/usr/bin/env python3
"""Trace a scan/photo of ANY handwritten page into pen strokes, as-is.

  .venv/bin/python trace_page.py page.jpg --width-mm 140 -o out/traced

This copies your real page stroke for stroke (it cannot type new text; use
glyphs.json + write.py for that). Output rules are the same as write.py: an SVG
preview always, G-code only once plotter.json is calibrated.
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")   # scikit-image deprecation chatter

import numpy as np
from PIL import Image
from skimage.filters import threshold_local
from skimage.morphology import binary_closing, disk, remove_small_objects

from hwlib import config_problems, load_config, strokes_to_gcode, strokes_to_svg, trace_mask


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--width-mm", type=float, required=True, help="width the image should have on paper")
    ap.add_argument("-o", "--out", default="out/traced")
    ap.add_argument("--offset", type=float, default=12.0,
                    help="how much darker than local paper (0-255) a pixel must be to count as ink")
    ap.add_argument("--crop", help="left,top,right,bottom as fractions 0-1, e.g. 0.05,0,1,1 to cut off a table edge")
    ap.add_argument("--config", default="plotter.json")
    a = ap.parse_args()

    im = Image.open(a.image).convert("L")
    if a.crop:
        l, t, r, b = (float(v) for v in a.crop.split(","))
        im = im.crop((int(l * im.width), int(t * im.height), int(r * im.width), int(b * im.height)))
    if max(im.size) > 3000:
        im.thumbnail((3000, 3000))
    g = np.asarray(im).astype(float)
    mask = g < threshold_local(g, 51, offset=a.offset)     # copes with shadows on phone photos
    mask = remove_small_objects(mask, 20)
    mask = binary_closing(mask, disk(1))
    h, w = mask.shape
    s = a.width_mm / w
    strokes = [[(x * s, y * s) for x, y in p] for p in trace_mask(mask, min_spur=8, eps=0.8)]
    ph = h * s
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    strokes_to_svg(strokes, round(a.width_mm, 2), round(ph, 2), a.out + ".svg")
    print(f"wrote {a.out}.svg  ({len(strokes)} strokes, {a.width_mm:.0f} x {ph:.0f} mm)")

    cfg = load_config(a.config)
    bad = config_problems(cfg)
    if bad:
        print("G-code NOT written. Still to do:")
        for b in bad:
            print("  - " + b)
        return
    try:
        code = strokes_to_gcode(strokes, cfg, ph, base_dir=os.path.dirname(os.path.abspath(a.config)))
    except ValueError as e:
        sys.exit(f"G-code NOT written: {e}")
    open(a.out + ".gcode", "w").write(code)
    print(f"wrote {a.out}.gcode")


if __name__ == "__main__":
    main()
