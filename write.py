#!/usr/bin/env python3
"""Turn text into pen strokes in your handwriting.

  .venv/bin/python write.py -g glyphs.json -t "Hello there" -o out/hello
  .venv/bin/python write.py -g glyphs.json -f letter.txt -o out/letter --paper a5

Always writes <out>.svg (preview, paper-sized in mm). Writes <out>.gcode only when
plotter.json is fully calibrated (see README), so a half-configured run cannot
send the pen somewhere unexpected.
"""
import argparse
import json
import math
import os
import random
import sys

from hwlib import config_problems, load_config, strokes_to_gcode, strokes_to_svg

PAPERS = {"a5": (148, 210), "a4": (210, 297), "letter": (215.9, 279.4),
          "halfletter": (139.7, 215.9), "4x6": (101.6, 152.4), "index": (76.2, 127)}


def parse_paper(s):
    if s.lower() in PAPERS:
        return PAPERS[s.lower()]
    w, h = s.lower().split("x")
    return float(w), float(h)


# Simple straight-stroke stand-ins for characters the template does not have.
# Units are x-heights, origin at the left ink edge on the baseline (y up).
FALLBACK = {
    "=": [[[0, 0.35], [0.9, 0.35]], [[0, 0.8], [0.9, 0.8]]],
    "+": [[[0, 0.58], [0.9, 0.58]], [[0.45, 0.1], [0.45, 1.05]]],
    "/": [[[0.7, 1.5], [0, -0.2]]],
    "*": [[[0.1, 0.5], [0.7, 1.3]], [[0.7, 0.5], [0.1, 1.3]]],
}


def glyph_width(strokes):
    return max((p[0] for s in strokes for p in s), default=0.0)


def layout(text, glyphs, paper_w, paper_h, margin, xh, pitch, jitter, rng):
    spacing, space = 0.28, 0.95          # in x-height units
    avail = paper_w - 2 * margin
    last_variant = {}
    missing = set()

    def pick(ch):
        vs = [v for v in glyphs.get(ch, []) if v]
        if not vs:
            missing.add(ch)
            return None
        choices = [i for i in range(len(vs)) if i != last_variant.get(ch)] or list(range(len(vs)))
        i = rng.choice(choices)
        last_variant[ch] = i
        return vs[i]

    def word_items(word):
        items = []
        for ch in word:
            g = pick(ch)
            if g is not None:
                items.append((ch, g, glyph_width(g)))
        return items

    def word_w(items):
        return sum((w + spacing) * xh for _, _, w in items)

    # wrap into lines of words
    lines = []
    for para in text.split("\n"):
        cur, cur_w = [], 0.0
        for word in para.split():
            items = word_items(word)
            ww = word_w(items)
            sp = space * xh if cur else 0.0
            if cur and cur_w + sp + ww > avail:
                lines.append(cur)
                cur, cur_w, sp = [], 0.0, 0.0
            cur.append(items)
            cur_w += sp + ww
        lines.append(cur)

    strokes = []
    y = margin + 2.1 * xh
    for words in lines:
        if y + 0.6 * xh > paper_h - margin:
            print(f"warning: text does not fit on the page; stopped before line {lines.index(words) + 1}",
                  file=sys.stderr)
            break
        slope = rng.uniform(-0.004, 0.004) * jitter
        cx = margin
        for wi, items in enumerate(words):
            if wi:
                cx += space * xh * (1 + rng.uniform(-0.15, 0.15) * jitter)
            for ch, g, w in items:
                s = xh * (1 + rng.uniform(-0.04, 0.04) * jitter)
                th = math.radians(rng.uniform(-2.0, 2.0) * jitter)
                dy = rng.uniform(-0.03, 0.03) * xh * jitter
                c, sn = math.cos(th), math.sin(th)
                for st in g:
                    out = []
                    for u, v in st:
                        uu, vv = u * c - v * sn, u * sn + v * c
                        X = cx + s * uu
                        out.append((X, y - s * vv + dy + slope * (X - margin)))
                    strokes.append(out)
                cx += (w + spacing) * s * (1 + rng.uniform(-0.08, 0.08) * jitter)
        y += pitch
    if missing:
        print("warning: no captured glyph for: " + " ".join(sorted(missing)), file=sys.stderr)
    return strokes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-g", "--glyphs", default="glyphs.json")
    ap.add_argument("-t", "--text")
    ap.add_argument("-f", "--file")
    ap.add_argument("-o", "--out", default="out/page")
    ap.add_argument("--paper", default="a5", help="a5, a4, letter, halfletter, 4x6, index or WxH in mm")
    ap.add_argument("--margin", type=float, default=12.0, help="mm")
    ap.add_argument("--xheight", type=float, default=2.6, help="lowercase letter height, mm")
    ap.add_argument("--pitch", type=float, default=8.0, help="line spacing, mm (ruled paper is ~7-9)")
    ap.add_argument("--jitter", type=float, default=1.0, help="0 = perfectly regular, 1 = natural")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--config", default="plotter.json")
    a = ap.parse_args()

    if bool(a.text) == bool(a.file):
        ap.error("give exactly one of --text or --file")
    text = a.text if a.text else open(a.file).read()
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                                         "–": "-", "—": "-", "…": "..."}))
    with open(a.glyphs) as f:
        glyphs = json.load(f)["glyphs"]
    for ch, strokes in FALLBACK.items():
        glyphs.setdefault(ch, [strokes])
    pw, ph = parse_paper(a.paper)
    rng = random.Random(a.seed)
    strokes = layout(text, glyphs, pw, ph, a.margin, a.xheight, a.pitch, a.jitter, rng)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    strokes_to_svg(strokes, pw, ph, a.out + ".svg")
    print(f"wrote {a.out}.svg  ({len(strokes)} strokes, paper {pw}x{ph} mm)")

    cfg = load_config(a.config)
    bad = config_problems(cfg)
    if bad:
        print("G-code NOT written. Still to do:")
        for b in bad:
            print("  - " + b)
        return
    try:
        g = strokes_to_gcode(strokes, cfg, ph, base_dir=os.path.dirname(os.path.abspath(a.config)))
    except ValueError as e:
        sys.exit(f"G-code NOT written: {e}")
    with open(a.out + ".gcode", "w") as f:
        f.write(g)
    print(f"wrote {a.out}.gcode")


if __name__ == "__main__":
    main()
