# Grid Tactics (rules prototype)

A two-player tactics game on an 8x10 grid, still in rules design. Nothing playable yet.

- `gridsim.py`: the rules engine plus heuristic bots in three styles. `python3 gridsim.py 270` compares rule sets by game length.
  Note: its median and 80% range count finished games only.
- `analyze.py`: proxies for strategic depth under the current candidate rules: how games end, style matchups,
  comeback rate, and whether recruiting a single unit type beats a mixed army.
