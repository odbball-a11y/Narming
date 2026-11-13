"""Make a house rival: train a workshop racer until it stops improving, then publish it.

    python house_rival.py "Zappy Zoe" --aggression 0.5 --caution 0.5 --hours 9

It trains from the graduate (with track notes) in rounds of --chunk generations
against scripted cars, itself and the house rivals, on all five tracks.  After
each round it looks at the last generations' test results (pace alone and
place in the race from last against three scripted cars, every track): when
the best rolling average has not improved for --patience generations, training
has reached a plateau and the racer is published as a house rival.  It also
stops (and publishes) at --hours or --max-generations.  Run it again to carry
on; it picks up the same racer.
"""
from __future__ import annotations

import argparse
import sys
import time

from ai import migrate, stable
from sim import cartraits

WINDOW = 25          # generations averaged for the trend


def score(entry: dict) -> float | None:
    """Lower is better: race place (1-4) plus pace (lap time / scripted lap) x 10."""
    pace = stable.pace(entry["exam"])
    if pace is None:
        return None
    return stable.exam_average(entry["exam"])["race_place"] + 10.0 * pace


def trend(history: list[dict]) -> list[float]:
    values = [score(h) for h in history]
    out = []
    for k in range(len(values)):
        window = [v for v in values[max(0, k - WINDOW + 1):k + 1] if v is not None]
        out.append(sum(window) / len(window) if window else float("inf"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("--aggression", type=float, default=0.5)
    ap.add_argument("--caution", type=float, default=0.5)
    ap.add_argument("--hours", type=float, default=9.0)
    ap.add_argument("--chunk", type=int, default=20, help="generations per round")
    ap.add_argument("--patience", type=int, default=80, help="generations without improvement = plateau")
    ap.add_argument("--min-generations", type=int, default=100)
    ap.add_argument("--max-generations", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    migrate.ensure()
    root = stable.WORKSHOP_DIR
    deadline = time.time() + args.hours * 3600
    racer = next((d for d in stable.list_racers(root, include_dead=True)
                  if stable.load(d)["name"].lower() == args.name.lower()), None)
    options = {o["name"]: o for o in stable.partner_options(root, include_house=True)}
    partners = [o for o in options.values() if o["kind"] in ("scripted", "self")]
    partners += [o for o in options.values() if o.get("key", "").startswith("house:")]
    if racer is None:
        racer = stable.create(root, args.name, args.aggression, args.caution,
                              [p for p in partners if p["kind"] != "self"], args.chunk,
                              traits=cartraits.default())
        print(f"created {args.name} in the workshop: {cartraits.describe(cartraits.default())}, "
              f"aggression {args.aggression}, caution {args.caution}", flush=True)
    while True:
        stable.train(racer, workers=args.workers)
        history = stable.history(racer)
        t = trend(history)
        best_at = min(range(len(t)), key=lambda k: t[k]) if t else 0
        gens = len(history)
        since = gens - 1 - best_at
        last = history[-1]
        print(f"{time.strftime('%H:%M')} gen {gens}: trend {t[-1]:.2f} (best {t[best_at]:.2f} at gen {best_at + 1}, "
              f"{since} since)  pace {stable.pace_text(stable.pace(last['exam']))}  "
              f"place {stable.exam_average(last['exam'])['race_place']:.1f}", flush=True)
        if gens >= args.min_generations and since >= args.patience:
            print(f"plateau: no improvement for {since} generations", flush=True)
            break
        if gens >= args.max_generations or time.time() >= deadline:
            print("time or generation limit reached", flush=True)
            break
        stable.upskill(racer, args.aggression, args.caution, partners, args.chunk)
    path = stable.publish(racer)
    print(f"published {args.name} as a house rival: {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
