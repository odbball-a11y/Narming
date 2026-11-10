"""Measure a rule set: game length plus proxies for strategic depth.

Usage: python3 analyze.py [games_per_variant]
"""
import random, statistics, sys
from collections import Counter
from multiprocessing import Pool
import gridsim as g

FINAL = {**g.BASE_CFG, "capture": "instant", "recruit_until": 20, "army_cap": 6}
MECH = dict(charge=1, spear_rmax=1, still_bonus=1)
POOL = dict(B=2, S=2, A=2)
NO_CUTOFF = dict(recruit_until=None)

HELD = dict(vp_timing="start", **NO_CUTOFF)
CORE = dict(mech=MECH, pool=POOL)
VARIANTS = {
    "0. current final rules":                  {},
    "4+3. mechanics + pool":                   CORE,
    "4+3+2. VP 12 held":                       dict(**CORE, vp_target=12, **HELD),
    "4+3+2. VP 10 held + contest":             dict(**CORE, vp_target=10, vp_contest=True, **HELD),
    "4+3+2. VP 12 held + contest":             dict(**CORE, vp_target=12, vp_contest=True, **HELD),
    "all four, VP 10 held + contest":          dict(**CORE, actions=3, vp_target=10, vp_contest=True, **HELD),
    "all four, VP 12 held + contest":          dict(**CORE, actions=3, vp_target=12, vp_contest=True, **HELD),
}
PAIRS = [(a, b) for a in g.STYLES for b in g.STYLES]

def value(game, pl):
    return sum(u.st["cost"] * u.hp / u.st["hp"] for u in game.units if u.o == pl)

def play(cfg, s0, s1):
    game = g.Game(cfg); st = (g.STYLES[s0], g.STYLES[s1]); lead10 = None
    for rnd in range(1, cfg["max_rounds"] + 1):
        game.round = rnd
        if rnd == 10: lead10 = value(game, 0) - value(game, 1)
        for pl in (0, 1):
            w = game.play_turn(pl, st[pl])
            if w is not None: return w, rnd, game.how, lead10
    return None, cfg["max_rounds"], "unfinished", lead10

def measure(args):
    name, ov, n, seed = args
    random.seed(seed); cfg = {**FINAL, **ov}
    games = [(s0, s1, *play(cfg, s0, s1)) for i in range(n) for s0, s1 in [PAIRS[i % len(PAIRS)]]]
    done = [x for x in games if x[2] is not None]
    rounds = [x[3] for x in done]
    q = statistics.quantiles(rounds, n=10)
    style = {s: [0, 0] for s in g.STYLES}               # wins, games, either seat
    for s0, s1, w, *_ in done:
        style[s0][1] += 1; style[s1][1] += 1; style[(s0, s1)[w]][0] += 1
    srate = {s: v[0] / v[1] for s, v in style.items()}
    cb = [(l > 0) != (w == 0) for _, _, w, r, _, l in done if l is not None and abs(l) >= 3 and r > 10]
    # mono-unit armies: player 0 recruits one type only, vs a normal opponent, balanced vs balanced
    mono = {}
    for ks in ("B", "S", "A", "BSA"):
        c = {**cfg, "force_recruit": {0: list(ks)}} if ks != "BSA" else cfg
        res = Counter(play(c, "balanced", "balanced")[0] for _ in range(n // 2))
        mono[ks] = res[0] / max(1, res[0] + res[1])
    return dict(name=name,
                median_all=statistics.median([x[3] if x[2] is not None else 61 for x in games]),
                p10=q[0], p90=q[8], unfinished=1 - len(done) / n,
                first=sum(1 for x in done if x[2] == 0) / len(done),
                ends={k: v / n for k, v in Counter(x[4] for x in games).items()},
                style=srate, comeback=sum(cb) / max(1, len(cb)), mono=mono)

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 270
    with Pool() as p:
        results = p.map(measure, [(k, v, n, 1) for k, v in VARIANTS.items()])
    for r in results:
        ends = " ".join(f"{k} {v:.0%}" for k, v in sorted(r["ends"].items()))
        sty = " ".join(f"{k[:4]} {v:.0%}" for k, v in r["style"].items())
        mono = " ".join(f"{k} {v:.0%}" for k, v in r["mono"].items())
        print(f"{r['name']}\n   median {r['median_all']:.0f} (80%: {r['p10']:.0f}-{r['p90']:.0f})  unfinished {r['unfinished']:.0%}"
              f"  P1 wins {r['first']:.0%}  comeback {r['comeback']:.0%}\n   ends: {ends}\n   styles: {sty}\n   one-unit armies: {mono}", flush=True)
