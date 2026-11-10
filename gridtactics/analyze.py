"""Fun/strategy proxies for a rule set: how games end, style matchups, comebacks, unit choice."""
import random, statistics, sys
from collections import Counter, defaultdict
import gridsim as g

FINAL = {**g.BASE_CFG, "capture": "instant", "recruit_until": 20, "army_cap": 6}

def value(game, pl):
    return sum(u.st["cost"] * u.hp / u.st["hp"] for u in game.units if u.o == pl)

def play(cfg, s0, s1, recruit_pool=None):
    game = g.Game(cfg); st = (g.STYLES[s0], g.STYLES[s1]); lead10 = None
    if recruit_pool:                      # force player 0 to recruit only from this pool
        orig = game.recruit
        def rec(pl, style):
            if pl != 0: return orig(pl, style)
            occ = game.occ(); spawn = [n for n in g.nbrs(g.BASE[pl]) if n not in occ]
            k = random.choice(recruit_pool)
            if not spawn or game.gold[pl] < g.UNITS[k]["cost"]: return False
            game.gold[pl] -= g.UNITS[k]["cost"]
            game.units.append(g.U(k, pl, min(spawn, key=lambda p: g.DIST_TO[1-pl].get(p, 99))))
            return True
        game.recruit = rec
    for rnd in range(1, cfg["max_rounds"] + 1):
        game.round = rnd
        if rnd == 10: lead10 = value(game, 0) - value(game, 1)
        for pl in (0, 1):
            w = game.play_turn(pl, st[pl])
            if w is not None:
                how = "capture" if any(u.o == w and u.p == g.BASE[1-w] for u in game.units) else "elimination"
                return w, rnd, how, lead10
    return None, cfg["max_rounds"], "unfinished", lead10

if __name__ == "__main__":
    random.seed(1); n = int(sys.argv[1]) if len(sys.argv) > 1 else 270
    pairs = [(a, b) for a in g.STYLES for b in g.STYLES]
    ends = Counter(); matrix = defaultdict(lambda: [0, 0]); comeback = [0, 0]
    for i in range(n):
        s0, s1 = pairs[i % len(pairs)]
        w, r, how, lead = play(FINAL, s0, s1); ends[how] += 1
        if w is not None:
            matrix[(s0, s1)][w] += 1
            if lead is not None and abs(lead) >= 3 and r > 10:
                comeback[1] += 1; comeback[0] += (lead > 0) != (w == 0)
    print("how games end:", {k: f"{v/n:.0%}" for k, v in ends.items()})
    print(f"behind by 3+ gold of army at round 10 and still won: {comeback[0]}/{comeback[1]}")
    print("style win rate (row = player 0, as either seat it's symmetric enough):")
    for a in g.STYLES:
        print(f"  {a:10s}", "  ".join(f"vs {b[:4]} {m[0]/max(1,sum(m)):.0%}" for b in g.STYLES for m in [matrix[(a, b)]]))
    print("player 0 recruits from a fixed pool vs a normal counter-picking opponent (balanced vs balanced):")
    for pool in (["B"], ["S"], ["A"], ["B", "S", "A"]):
        res = Counter(play(FINAL, "balanced", "balanced", pool)[0] for _ in range(n // 3))
        print(f"  {''.join(pool):4s} wins {res[0]/max(1, res[0]+res[1]):.0%}  unfinished {res[None]/(n//3):.0%}")
