#!/usr/bin/env python3
"""Write a pen-height calibration G-code: a row of short lines, each drawn a bit lower.

  .venv/bin/python calibrate.py --z-start 6 --step 0.2 --count 20

--z-start must be a Z value where the pen is CLEARLY ABOVE the paper (measure it,
don't guess: Z numbers depend on how your header zeroes Z). The first line that
shows on the paper tells you z_down; set z_down a little lower (spring travel
forgives ~0.5 mm), and z_up about 2-3 mm above z_down, in plotter.json.
Requires header_verified, pen_offset_mm and paper_origin_mm to be set.
"""
import argparse
import os

from hwlib import load_config, read_block


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--z-start", type=float, required=True)
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--out", default="out/calibrate.gcode")
    ap.add_argument("--config", default="plotter.json")
    a = ap.parse_args()
    cfg = load_config(a.config)
    base = os.path.dirname(os.path.abspath(a.config))
    miss = [k for k in ("paper_origin_mm", "pen_offset_mm") if cfg.get(k) is None]
    if miss or not cfg.get("header_verified"):
        raise SystemExit(f"set {', '.join(miss) or 'header_verified'} in plotter.json first")
    ox, oy = cfg["paper_origin_mm"]
    dx, dy = cfg["pen_offset_mm"]
    xmin, ymin, xmax, ymax = cfg["bounds_mm"]
    lines = [read_block(os.path.join(base, cfg["header_file"])), "G90",
             f"G1 Z{a.z_start + 3:.2f} F{cfg['feed_z']}"]
    for i in range(a.count):
        z = a.z_start - i * a.step
        x0, y0 = ox + 15 - dx, oy + 15 + i * 4 - dy
        if not (xmin <= x0 and x0 + 20 <= xmax and ymin <= y0 <= ymax):
            raise SystemExit("calibration lines leave the bounds; adjust paper_origin_mm/bounds_mm")
        lines += [f"; line {i + 1}: Z={z:.2f}", f"G1 X{x0:.2f} Y{y0:.2f} F{cfg['feed_travel']}",
                  f"G1 Z{z:.2f} F{cfg['feed_z']}", f"G1 X{x0 + 20:.2f} Y{y0:.2f} F{cfg['feed_draw']}",
                  f"G1 Z{a.z_start + 3:.2f} F{cfg['feed_z']}"]
    lines.append(read_block(os.path.join(base, cfg["footer_file"])))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w").write("\n".join(lines))
    print(f"wrote {a.out}: lines go from Z={a.z_start} down to Z={a.z_start - (a.count - 1) * a.step:.2f}; "
          "note which numbered line is the first to mark the paper")


if __name__ == "__main__":
    main()
