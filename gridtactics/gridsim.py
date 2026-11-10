"""Grid Tactics - headless rules model + heuristic bots, for measuring game length."""
import random, statistics
from collections import deque

W, H = 8, 10
WALLS = {(1, 3), (2, 3), (5, 6), (6, 6)}
HIGH = {(4, 4), (5, 4)}
CPS = [(0, 5), (7, 4)]
BASE = {0: (4, 9), 1: (3, 0)}          # player 0 = Blue (bottom), 1 = Orange (top)

UNITS = {  # hp, dmg, rmin, rmax, move, cost, move_and_attack
    "B": dict(hp=6, dmg=2, rmin=1, rmax=1, move=3, cost=2, both=True),
    "S": dict(hp=5, dmg=2, rmin=1, rmax=2, move=2, cost=3, both=True),
    "A": dict(hp=4, dmg=2, rmin=2, rmax=4, move=2, cost=4, both=False),
}

def md(a, b): return abs(a[0]-b[0]) + abs(a[1]-b[1])
def nbrs(p):
    x, y = p
    for q in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
        if 0 <= q[0] < W and 0 <= q[1] < H and q not in WALLS:
            yield q

def bfs_static(src):
    d = {src: 0}; q = deque([src])
    while q:
        p = q.popleft()
        for n in nbrs(p):
            if n not in d: d[n] = d[p]+1; q.append(n)
    return d
DIST_TO = {pl: bfs_static(BASE[pl]) for pl in (0, 1)}

class U:
    __slots__ = ("k", "o", "p", "hp", "st", "moved", "_start")
    def __init__(s, k, o, p, table=UNITS):
        s.k, s.o, s.p, s.st = k, o, p, table[k]; s.hp = s.st["hp"]; s.moved = False
    def rmax(s, at=None):
        at = at or s.p
        return s.st["rmax"] + (1 if at in HIGH and s.k != "B" else 0)

class Game:
    def __init__(s, cfg):
        s.cfg = cfg
        s.units = []
        s.mech = cfg.get("mech") or {}
        s.ut = {k: dict(v) for k, v in UNITS.items()}
        if s.mech.get("spear_rmax"): s.ut["S"]["rmax"] = s.mech["spear_rmax"]
        for k, c in (cfg.get("cost") or {}).items(): s.ut[k]["cost"] = c
        for k, o in (cfg.get("stats") or {}).items(): s.ut[k].update(o)   # e.g. {"B": {"hp": 5}}
        s.no_score = set(cfg.get("no_score") or ())     # unit kinds that can't score control points
        s.pool = [dict(cfg["pool"]) for _ in (0, 1)] if cfg.get("pool") else None
        s.force = cfg.get("force_recruit") or {}          # {player: [unit kinds]} for tests
        if s.pool:
            for pl, ks in s.force.items(): s.pool[pl] = {ks[0]: sum(cfg["pool"].values())}
        s.vp = list(cfg.get("start_vp") or (0, 0)); s.how = None
        s.gold = [cfg["start_gold"]]*2
        s.cp_owner = {c: None for c in CPS}
        for pl in (0, 1):
            bx, by = BASE[pl]; dy = -1 if pl == 0 else 1
            for k, dx in zip(cfg["start_army"], (-1, 0, 1)):
                s.units.append(U(k, pl, (bx+dx, by+dy), s.ut))
        s.turn = 0; s.round = 0
        s.bhp = [cfg.get("base_hp") or 0]*2

    def occ(s): return {u.p: u for u in s.units}

    def reach(s, u):
        occ = s.occ(); enemies = [e.p for e in s.units if e.o != u.o]
        zoc = {n for e in enemies for n in nbrs(e)}
        d = {u.p: 0}; q = deque([u.p])
        while q:
            p = q.popleft()
            if p != u.p and p in zoc: continue          # zone of control stops movement
            if d[p] == u.st["move"]: continue
            for n in nbrs(p):
                if n in d or n in occ: continue
                d[n] = d[p]+1; q.append(n)
        return d

    def threat_at(s, pos, owner):
        """Rough damage an enemy could deal to `pos` next turn."""
        t = 0
        for e in s.units:
            if e.o == owner: continue
            if md(e.p, pos) <= e.st["move"]*(1 if e.st["both"] else 0) + e.rmax():
                t += e.st["dmg"]
        return t

    def dmg(s, a, d, moved=0):
        x = a.st["dmg"]
        if a.k == "B" and moved >= 2: x += s.mech.get("charge", 0)          # Bruiser charge
        if a.k == "A" and not d.moved: x += s.mech.get("still_bonus", 0)   # Archer vs a unit that stood still
        return x

    def hit(s, d, amount):
        d.hp -= amount
        if d.hp <= 0: s.units.remove(d); return True
        return False

    def act(s, u, dest, tgt, moved=0):
        u.p = dest; u.moved = dest != u._start
        # Spearman first strike on anything that ends its move adjacent
        if dest != u._start:
            for sp in [e for e in s.units if e.o != u.o and e.k == "S" and md(e.p, dest) == 1]:
                if s.hit(u, sp.st["dmg"]): return
        if tgt and tgt in s.units:
            killed = s.hit(tgt, s.dmg(u, tgt, moved))
            if not killed and tgt.st["rmin"] <= md(tgt.p, u.p) <= tgt.rmax():
                s.hit(u, s.dmg(tgt, u))                    # counter-attack

    def score(s, u, dest, tgt, style, moved=0):
        me, foe = u.o, 1-u.o
        sc = 0.0
        vpt = s.cfg.get("vp_target")
        if tgt:
            dmg = s.dmg(u, tgt, moved)
            if dmg >= tgt.hp: sc += 30 + tgt.st["cost"]*6
            else:
                sc += dmg*8
                if tgt.st["rmin"] <= md(tgt.p, dest) <= tgt.rmax(): sc -= s.dmg(tgt, u)*5
            if tgt.p == BASE[me]: sc += 120                # evict a capturer
            if vpt and tgt.p in s.cp_owner: sc += 15 + 4*s.vp[foe]   # contest a scoring point
        if vpt and dest in s.cp_owner and u.k not in s.no_score: sc += 18 + 3*s.vp[me]
        if vpt and s.cfg.get("vp_contest") and any(e.o == foe and e.p in s.cp_owner and md(e.p, dest) == 1 for e in s.units):
            sc += 10 + 3*s.vp[foe]                         # block a point the enemy is scoring
        if s.cfg.get("base_hp") and md(dest, BASE[foe]) <= 1: sc += 35
        if dest == BASE[foe]: sc += 150 if s.threat_at(dest, me) < u.hp else 40
        sc -= DIST_TO[foe].get(dest, 30) * style["aggr"]
        if dest in s.cp_owner and s.cp_owner[dest] != me: sc += 12
        sc -= s.threat_at(dest, me) * style["risk"] * (1.6 if u.k == "A" else 1)
        intr = [e for e in s.units if e.o == foe and DIST_TO[me].get(e.p, 99) <= 3]
        if intr: sc -= min(md(dest, e.p) for e in intr) * style["defend"]
        return sc + random.random()*style["noise"]

    def best_action(s, u, style):
        u._start = u.p
        foes = [e for e in s.units if e.o != u.o]
        best = (-1e9, u.p, None, 0)
        dests = s.reach(u)
        for dest, dist in dests.items():
            can_attack = u.st["both"] or dest == u.p
            tg = [None] + ([e for e in foes if u.st["rmin"] <= md(e.p, dest) <= u.rmax(dest)] if can_attack else [])
            for t in tg:
                v = s.score(u, dest, t, style, dist)
                if v > best[0]: best = (v, dest, t, dist)
        return best

    def recruit(s, pl, style):
        occ = s.occ(); spawn = [n for n in nbrs(BASE[pl]) if n not in occ]
        if not spawn: return False
        foes = [e.k for e in s.units if e.o != pl]
        avail = s.available(pl)
        if pl in s.force: choices = [k for k in s.force[pl] if k in avail]
        else:
            # counter-pick: B beats A, A beats S, S beats B
            want = {"A": "B", "S": "A", "B": "S"}
            choices = [k for k in [want[k] for k in foes] + ["B", "S", "A"] if k in avail]
        if not choices: return False
        k = random.choice(choices)
        if s.gold[pl] < s.ut[k]["cost"]:
            k = "B" if "B" in choices and s.gold[pl] >= 2 else None
        if not k: return False
        s.gold[pl] -= s.ut[k]["cost"]
        if s.pool: s.pool[pl][k] -= 1
        s.units.append(U(k, pl, min(spawn, key=lambda p: DIST_TO[1-pl].get(p, 99)), s.ut))
        return True

    def scoring(s, pl):
        """Points this player scores now: control points they stand on (optionally not while an enemy is adjacent)."""
        held = [u.p for u in s.units if u.o == pl and u.p in s.cp_owner and u.k not in s.no_score]
        if s.cfg.get("vp_contest"):
            held = [c for c in held if not any(e.o != pl and md(e.p, c) == 1 for e in s.units)]
        return len(held)

    def available(s, pl):
        if s.pool: return [k for k, n in s.pool[pl].items() if n > 0]
        return ["B", "S", "A"]

    def can_recruit_ever(s, pl):
        rc = s.cfg.get("recruit_until")
        if rc is not None and s.round > rc: return False
        return any(s.gold[pl] + s.cfg["income"] >= s.ut[k]["cost"] for k in s.available(pl))

    def play_turn(s, pl, style):
        # capture check: survived a full enemy turn on their base
        cap = s.cfg.get("capture", "survive")
        if cap == "survive" and any(u.o == pl and u.p == BASE[1-pl] for u in s.units): s.how = "capture"; return pl
        for u in s.units:
            if u.o == pl: u.moved = False
        if s.cfg.get("vp_target") and s.cfg.get("vp_timing") == "start":   # point must survive the enemy turn
            s.vp[pl] += s.scoring(pl)
            if s.vp[pl] >= s.cfg["vp_target"]: s.how = "points"; return pl
        if s.cfg.get("base_hp"):
            sieg = [u for u in s.units if u.o == pl and md(u.p, BASE[1-pl]) <= 1]
            s.bhp[1-pl] -= sum(u.st["dmg"] for u in sieg)
            if s.bhp[1-pl] <= 0: s.how = "siege"; return pl
        for c in CPS:
            here = [u for u in s.units if u.p == c]
            if here: s.cp_owner[c] = here[0].o
        s.gold[pl] += s.cfg["income"] + sum(1 for c in CPS if s.cp_owner[c] == pl)
        actions = s.cfg["actions"]
        mine = [u for u in s.units if u.o == pl]
        rc = s.cfg.get("recruit_until")
        if (rc is None or s.round <= rc) and len(mine) < s.cfg["army_cap"] and (len(mine) < 3 or random.random() < 0.7):
            if s.recruit(pl, style): actions -= 1
        cand = [u for u in s.units if u.o == pl]
        done = set()
        for _ in range(actions):
            live = [u for u in s.units if u.o == pl and id(u) not in done]
            if not live: break
            (v, dest, t, dist), u = max(((s.best_action(u, style), u) for u in live), key=lambda x: x[0][0])
            s.act(u, dest, t, dist); done.add(id(u))
        if s.cfg.get("capture") == "instant" and any(u.o == pl and u.p == BASE[1-pl] for u in s.units):
            s.how = "capture"; return pl
        if s.cfg.get("vp_target") and s.cfg.get("vp_timing") != "start":
            s.vp[pl] += s.scoring(pl)
            if s.vp[pl] >= s.cfg["vp_target"]: s.how = "points"; return pl
        if not any(u.o == 1-pl for u in s.units) and not s.can_recruit_ever(1-pl):
            s.how = "elimination"; return pl
        return None

STYLES = {
    "balanced":   dict(aggr=3.0, risk=2.0, defend=2.0, noise=4),
    "aggressive": dict(aggr=5.0, risk=1.0, defend=1.0, noise=4),
    "defensive":  dict(aggr=1.8, risk=3.5, defend=4.0, noise=4),
}
BASE_CFG = dict(actions=5, income=3, start_gold=4, start_army="BSA", army_cap=8, max_rounds=60)

def play(cfg, s0, s1):
    g = Game(cfg); st = (STYLES[s0], STYLES[s1])
    for rnd in range(1, cfg["max_rounds"]+1):
        g.round = rnd
        for pl in (0, 1):
            w = g.play_turn(pl, st[pl])
            if w is not None: return w, rnd
    return None, cfg["max_rounds"]

def run(cfg, pairs, n):
    rounds, wins, draws = [], [0, 0], 0
    for i in range(n):
        s0, s1 = pairs[i % len(pairs)]
        w, r = play(cfg, s0, s1)
        if w is None: draws += 1
        else: wins[w] += 1; rounds.append(r)
    q = statistics.quantiles(rounds, n=10) if len(rounds) > 10 else [0]*9
    return dict(n=n, median=statistics.median(rounds), p10=q[0], p90=q[8],
                mean=statistics.mean(rounds), first_win=wins[0]/max(1, sum(wins)),
                stalemate=draws/n, rounds=rounds)

if __name__ == "__main__":
    import json, sys
    random.seed(2)
    pairs = [(a, b) for a in STYLES for b in STYLES]
    variants = {
        "A. as designed": {},
        "B. instant capture": dict(capture="instant"),
        "F. instant + no recruits after rd 15": dict(capture="instant", recruit_until=15),
        "G. instant + no recruits after rd 20": dict(capture="instant", recruit_until=20),
        "H. instant + rd20 + army cap 6": dict(capture="instant", recruit_until=20, army_cap=6),
    }
    out = {}
    for name, ov in variants.items():
        r = run({**BASE_CFG, **ov}, pairs, int(sys.argv[1]))
        out[name] = r
        print(f"{name:34s} median {r['median']:4.0f}  p10 {r['p10']:4.0f}  p90 {r['p90']:4.0f}  "
              f"first-player win {r['first_win']:.0%}  stalemate {r['stalemate']:.0%}", flush=True)
    json.dump({k: v["rounds"] for k, v in out.items()}, open("rounds.json", "w"))
