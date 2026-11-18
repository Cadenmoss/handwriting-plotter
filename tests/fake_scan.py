"""Fill the template with a handwriting-style system font to test scan_to_glyphs.py."""
import json, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, ".")
from hwlib import BASELINE_FROM_TOP, CELL_UNITS

FONT = sys.argv[1]
meta = json.load(open("template/meta.json"))
cell = meta["cell_px"]; unit = cell / CELL_UNITS
gx, gy = meta["grid_origin_px"]
probe = ImageFont.truetype(FONT, 200)
b = probe.getbbox("x", anchor="ls"); size = int(200 * unit / (b[3] - b[1]))
font = ImageFont.truetype(FONT, size)
for pi, pm in enumerate(meta["pages"], 1):
    im = Image.open(f"template/page{pi}.png").convert("RGB"); d = ImageDraw.Draw(im)
    for k, c in enumerate(pm["cells"]):
        r, col = divmod(k, meta["cols"])
        x0, y0 = gx + col * cell, gy + r * cell
        d.text((x0 + 0.8 * unit + (k % 3) * 8, y0 + BASELINE_FROM_TOP * unit + (k % 5) * 3 - 6), c["char"], font=font, fill=(20, 20, 30), anchor="ls")
    im.save(f"tests/fake_scan{pi}.png")
print("ok", size)
