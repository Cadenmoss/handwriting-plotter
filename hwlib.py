"""Shared helpers for the handwriting plotter.

Glyph coordinate convention (used by capture.html, make_template.py,
scan_to_glyphs.py and write.py):
  * units are "x-heights" (1 unit = height of a lowercase letter like 'x')
  * origin is the left ink edge of the glyph, on the baseline
  * +y is UP
  * a capture/template cell is 4 x 4 units, baseline 2.6 units below the top
"""
import json
import math
from collections import Counter, defaultdict

import numpy as np

CELL_UNITS = 4.0
BASELINE_FROM_TOP = 2.6

# --------------------------------------------------------------------------
# Small geometry helpers
# --------------------------------------------------------------------------


def path_len(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def rdp(pts, eps):
    """Ramer-Douglas-Peucker simplification."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        ax, ay = pts[s]
        bx, by = pts[e]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        best, bi = -1.0, None
        for i in range(s + 1, e):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / n if n else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if bi is not None and best > eps:
            keep[bi] = True
            stack += [(s, bi), (bi, e)]
    return [p for p, k in zip(pts, keep) if k]


def smooth(pts, w=2):
    """Moving average that keeps both end points fixed."""
    if len(pts) < 2 * w + 1:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        k = min(w, i, len(pts) - 1 - i)
        seg = pts[i - k:i + k + 1]
        out.append((sum(p[0] for p in seg) / len(seg), sum(p[1] for p in seg) / len(seg)))
    out.append(pts[-1])
    return out


# --------------------------------------------------------------------------
# Skeleton tracing: binary ink mask -> list of centre-line polylines
# --------------------------------------------------------------------------
_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def trace_mask(mask, min_spur=6.0, smooth_w=2, eps=0.7):
    """Skeletonise `mask` (bool array, True = ink) and return polylines of
    (x, y) pixel coordinates (y down), ordered so that the pen can follow
    them with as few lifts as possible."""
    from skimage.morphology import skeletonize

    skel = skeletonize(mask)
    ys, xs = np.nonzero(skel)
    pix = set(zip(ys.tolist(), xs.tolist()))
    if not pix:
        return []
    nbrs = {p: [(p[0] + dy, p[1] + dx) for dy, dx in _NB if (p[0] + dy, p[1] + dx) in pix] for p in pix}
    deg = {p: len(n) for p, n in nbrs.items()}
    is_node = {p for p, d in deg.items() if d != 2}

    # cluster adjacent node pixels into one node
    cid, nodes = {}, []
    for p in is_node:
        if p in cid:
            continue
        k = len(nodes)
        cid[p] = k
        stack, members = [p], []
        while stack:
            q = stack.pop()
            members.append(q)
            for r in nbrs[q]:
                if r in is_node and r not in cid:
                    cid[r] = k
                    stack.append(r)
        nodes.append(members)

    # walk chains of degree-2 pixels between nodes
    edges, visited = [], set()
    for p in is_node:
        for q in nbrs[p]:
            if q in is_node or q in visited:
                continue
            path, prev, cur = [p, q], p, q
            visited.add(q)
            while True:
                nxt = [r for r in nbrs[cur] if r != prev]
                if not nxt:
                    break
                r = nxt[0]
                path.append(r)
                if r in is_node or r in visited:
                    break
                visited.add(r)
                prev, cur = cur, r
            if path[-1] in is_node:
                a, b = cid[p], cid[path[-1]]
                if a == b and path_len(path) < 10:
                    continue
                edges.append((a, b, path))

    # pure loops with no nodes at all (e.g. a perfect 'o')
    closed = []
    for p in pix:
        if p in visited or p in is_node:
            continue
        loop, cur = [p], p
        visited.add(p)
        while True:
            cand = [r for r in nbrs[cur] if r not in visited]
            if not cand:
                break
            cur = cand[0]
            visited.add(cur)
            loop.append(cur)
        loop.append(loop[0])
        closed.append(loop)

    # prune short spurs hanging off junctions
    alive = [True] * len(edges)
    dm = Counter()
    for a, b, _ in edges:
        dm[a] += 1
        dm[b] += 1
    lens = [path_len(e[2]) for e in edges]
    changed = True
    while changed:
        changed = False
        for i, (a, b, _) in enumerate(edges):
            if not alive[i] or a == b or lens[i] >= min_spur:
                continue
            if (dm[a] == 1 and dm[b] >= 3) or (dm[b] == 1 and dm[a] >= 3):
                alive[i] = False
                dm[a] -= 1
                dm[b] -= 1
                changed = True

    def npos(k):
        m = nodes[k]
        return (sum(p[1] for p in m) / len(m), sum(p[0] for p in m) / len(m))

    inc = defaultdict(list)  # node -> [(edge, end)]
    for i, (a, b, _) in enumerate(edges):
        if alive[i]:
            inc[a].append((i, 0))
            inc[b].append((i, 1))

    def pts_from(i, end):
        p = [(c[1], c[0]) for c in edges[i][2]]
        return p if end == 0 else p[::-1]

    def out_dir(i, end):
        p = pts_from(i, end)
        q = p[min(5, len(p) - 1)]
        return (q[0] - p[0][0], q[1] - p[0][1])

    used, paths, pos = set(), [], None
    alive_idx = [i for i in range(len(edges)) if alive[i]]
    while True:
        rem = [i for i in alive_idx if i not in used]
        if not rem:
            break
        rdeg = Counter()
        for i in rem:
            rdeg[edges[i][0]] += 1
            rdeg[edges[i][1]] += 1
        best = None
        for i in rem:
            for end in (0, 1):
                node = edges[i][end]
                x, y = npos(node)
                key = (0 if rdeg[node] == 1 else 1,
                       x if pos is None else math.hypot(x - pos[0], y - pos[1]))
                if best is None or key < best[0]:
                    best = (key, i, end)
        _, i, end = best
        stroke = []
        while True:
            used.add(i)
            stroke.extend(pts_from(i, end))
            node = edges[i][1] if end == 0 else edges[i][0]
            din = (stroke[-1][0] - stroke[max(0, len(stroke) - 6)][0],
                   stroke[-1][1] - stroke[max(0, len(stroke) - 6)][1])
            cands = [(j, e) for j, e in inc[node] if j not in used]
            if not cands:
                break
            nin = math.hypot(*din) or 1.0

            def cosang(c):
                d = out_dir(*c)
                n = math.hypot(*d) or 1.0
                return (din[0] * d[0] + din[1] * d[1]) / (nin * n)

            i, end = max(cands, key=cosang)
        paths.append(stroke)
        pos = stroke[-1]

    for loop in closed:
        paths.append([(c[1], c[0]) for c in loop])

    # lone pixels (i-dots) -> tiny dash so the pen touches the paper
    for k, m in enumerate(nodes):
        if all(deg[p] == 0 for p in m):
            x, y = npos(k)
            paths.append([(x, y), (x + 0.6, y)])

    result = []
    for p in paths:
        p = rdp(smooth(p, smooth_w), eps)
        # cosmetic: start strokes at the top-left end like a hand would
        if len(p) > 1 and (p[-1][0] - p[0][0]) + 0.5 * (p[-1][1] - p[0][1]) < 0:
            p = p[::-1]
        result.append(p)
    return result


# --------------------------------------------------------------------------
# Output: SVG preview + G-code
# --------------------------------------------------------------------------


def strokes_to_svg(strokes, paper_w, paper_h, path, width_mm=0.4):
    d = []
    for s in strokes:
        if len(s) < 2:
            continue
        d.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in s))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{paper_w}mm" height="{paper_h}mm" '
           f'viewBox="0 0 {paper_w} {paper_h}">\n'
           f'<rect width="{paper_w}" height="{paper_h}" fill="white"/>\n'
           f'<path d="{" ".join(d)}" fill="none" stroke="#111" stroke-width="{width_mm}" '
           f'stroke-linecap="round" stroke-linejoin="round"/>\n</svg>\n')
    with open(path, "w") as f:
        f.write(svg)


def load_config(path):
    with open(path) as f:
        return json.load(f)


def config_problems(cfg):
    """Return a list of reasons why G-code must NOT be written yet."""
    bad = []
    if not cfg.get("header_verified"):
        bad.append("header_verified is false: put a pen-safe start sequence in gcode/header.gcode "
                   "(no homing/probing that touches the bed with the pen; see README step 1), "
                   "then set header_verified to true")
    if cfg.get("pen_offset_mm") is None:
        bad.append("pen_offset_mm is null: measure pen-tip minus nozzle position as [dx, dy]")
    if cfg.get("z_down") is None or cfg.get("z_up") is None:
        bad.append("z_down / z_up are null: calibrate them with calibrate.py first")
    elif cfg["z_up"] - cfg["z_down"] < 1.0:
        bad.append("z_up must be at least 1 mm above z_down")
    if cfg.get("paper_origin_mm") is None:
        bad.append("paper_origin_mm is null: bed position of the paper's front-left corner")
    return bad


def read_block(path):
    with open(path) as f:
        return f.read().rstrip() + "\n"


def strokes_to_gcode(strokes, cfg, paper_h, base_dir="."):
    """Convert paper-space strokes (mm, y down) to G-code. Raises ValueError
    if any commanded position leaves the configured bounds."""
    import os
    ox, oy = cfg["paper_origin_mm"]
    pdx, pdy = cfg["pen_offset_mm"]
    zu, zd = cfg["z_up"], cfg["z_down"]
    fd, ft, fz = cfg["feed_draw"], cfg["feed_travel"], cfg["feed_z"]
    xmin, ymin, xmax, ymax = cfg["bounds_mm"]

    def bed(p):
        x = ox + p[0] - pdx
        y = oy + (paper_h - p[1]) - pdy
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            raise ValueError(f"point ({x:.1f},{y:.1f}) outside bounds {cfg['bounds_mm']}; "
                             "use a smaller paper/margin or move paper_origin_mm")
        return x, y

    out = [read_block(os.path.join(base_dir, cfg["header_file"])),
           "; ---- handwriting plot ----", "G90", f"G1 Z{zu:.2f} F{fz}"]
    for s in strokes:
        if len(s) < 2:
            continue
        x, y = bed(s[0])
        out.append(f"G1 X{x:.3f} Y{y:.3f} F{ft}")
        out.append(f"G1 Z{zd:.2f} F{fz}")
        for p in s[1:]:
            x, y = bed(p)
            out.append(f"G1 X{x:.3f} Y{y:.3f} F{fd}")
        out.append(f"G1 Z{zu:.2f} F{fz}")
    out.append("; ---- end ----")
    out.append(read_block(os.path.join(base_dir, cfg["footer_file"])))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Glyph normalisation: people rarely write exactly on the printed baseline
# --------------------------------------------------------------------------
_XH_LETTERS = "acemnorsuvwxz"
_DESC_BODY = "gpqy"           # descenders: line up the top of the bowl with x-height


def _ext(glyph):
    ys = [p[1] for s in glyph for p in s]
    return min(ys), max(ys)


def _shift(glyph, dy, scale=1.0):
    return [[[round(p[0] * scale, 3), round((p[1] + dy) * scale, 3)] for p in s] for s in glyph]


def normalize_glyphs(glyphs):
    """Re-seat every glyph on a common baseline and rescale so a lowercase
    letter is 1.0 high. Returns (new_glyphs, info)."""
    import statistics as st
    heights = [(_ext(v)[1] - _ext(v)[0]) for c in _XH_LETTERS for v in glyphs.get(c, [])]
    if not heights:
        return glyphs, {}
    xh = st.median(heights)
    caps = [(_ext(v)[1] - _ext(v)[0]) for c in "ABCDEFGHIJKLMNOPRSTUVWXYZ" for v in glyphs.get(c, [])]
    cap_h = st.median(caps) if caps else 2 * xh
    i_h = st.median([(_ext(v)[1] - _ext(v)[0]) for v in glyphs.get("i", [])] or [1.4 * xh])
    out = {}
    for c, vs in glyphs.items():
        new = []
        for v in vs:
            lo, hi = _ext(v)
            if c in _DESC_BODY:
                dy = xh - hi
            elif c == "j":
                dy = i_h - hi
            elif c in "\"'":
                dy = cap_h - hi
            elif c in ",;":
                dy = -0.3 * xh - lo
            elif c in "()":
                dy = -0.35 * xh - lo
            elif c == "-":
                dy = 0.55 * xh - (lo + hi) / 2
            else:
                dy = -lo
            new.append(_shift(v, dy, 1.0 / xh))
        out[c] = new
    return out, {"xheight_raw": round(xh, 3), "cap_height": round(cap_h / xh, 2)}
