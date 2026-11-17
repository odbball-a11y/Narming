"""Silverstone National-inspired layout from straights and arcs (clockwise; y down)."""
import json, math, sys
import numpy as np
sys.path.insert(0, ".")
W, VERGE = 9.6, 2.6
# (kind, value, radius): straight length, or arc turn in degrees (+ = right) with radius
PLAN = [("s", 70, None, "pit straight"), ("a", 145, 13, "Copse"), ("s", 4, None, ""),
        ("a", -40, 16, "Maggotts"), ("a", 85, 12, "Becketts"), ("a", -45, 12, "Chapel"), ("s", 3, None, ""),
        ("a", 45, 12, "onto the National Straight"), ("s", 100, None, "National Straight"), ("a", -50, 12, "Brooklands"),
        ("s", 2, None, ""), ("a", 180, 15, "Luffield"), ("s", 4, None, ""), ("a", 40, 22, "Woodcote"),
        ("s", 10, None, "")]


def walk(plan):
    x, y, h = 0.0, 0.0, math.pi           # heading west along the pit straight
    pts = [(x, y)]
    for kind, v, r, _ in plan:
        if kind == "s":
            n = max(1, int(round(v / 7.0)))
            for k in range(n):
                x += math.cos(h) * v / n; y += math.sin(h) * v / n; pts.append((x, y))
        else:
            turn = math.radians(v)
            n = max(2, int(round(abs(turn) * r / 4.5)))
            for k in range(n):
                dh = turn / n
                chord = 2 * r * math.sin(abs(dh) / 2)
                h += dh / 2; x += math.cos(h) * chord; y += math.sin(h) * chord; h += dh / 2
                pts.append((x, y))
    return np.array(pts), h


def close(plan):
    """Lengthen the pit straight (west) and the run from Copse to Maggotts so the lap closes."""
    pts, _ = walk(plan)
    err = pts[-1] - pts[0]
    plan = [list(p) for p in plan]
    i = 12
    heading = math.pi + sum(math.radians(p[1]) for p in plan[:i] if p[0] == "a")
    d1, d2 = np.array([-1.0, 0.0]), np.array([math.cos(heading), math.sin(heading)])
    a, b = np.linalg.solve(np.column_stack([d1, d2]), -err)
    plan[0][1] += a
    plan[i][1] += b
    return [tuple(p) for p in plan]


plan = close(PLAN)
pts, h = walk(plan)
pts = pts[:-1]                       # last point = first
lo, hi = pts.min(0), pts.max(0)
margin = W / 2 + VERGE + 2.5
box = (1 + margin, 159 - margin, 12 + margin, 89 - margin)
scale = min((box[1] - box[0]) / (hi[0] - lo[0]), (box[3] - box[2]) / (hi[1] - lo[1]))
c_src = (lo + hi) / 2
c_dst = np.array([(box[0] + box[1]) / 2, (box[2] + box[3]) / 2])
pts = (pts - c_src) * scale + c_dst
print("scale", round(scale, 3), "plan", [(p[3], round(p[1], 1)) for p in plan if p[0] == "s"])
data = {"name": "National", "laps": 3, "verge": VERGE, "checkpoints": 14,
        "comment": "Each point is [x, y, track width]. Inspired by Silverstone's National circuit, run clockwise: "
                   "the pit straight, the fast right at Copse, the Maggotts-Becketts S, the long Wellington Straight, "
                   "a heavy stop into Brooklands, the long tightening right of Luffield and the fast Woodcote back "
                   "onto the pit straight.",
        "points": [[round(float(x), 2), round(float(y), 2), W] for x, y in pts], "racing_line_offsets": None}
json.dump(data, open(sys.argv[1], "w"), indent=1)
