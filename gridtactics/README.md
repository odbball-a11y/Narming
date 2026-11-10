# Grid Tactics (rules prototype)

A two-player tactics game on an 8x10 grid, still in rules design. Nothing playable yet.

- `gridsim.py`: the rules engine plus heuristic bots in three styles. `python3 gridsim.py 270` compares the
  original rule sets by game length (its median and 80% range count finished games only).
- `rules.html`: the player-facing rulebook for the current draft rules (0.3).
- `analyze.py`: runs the rule variants listed in `VARIANTS` and reports game length (unfinished games counted),
  first-player win rate, how games end, win rate by bot style, comeback rate, and one-unit-type armies vs mixed.

Rule options (config keys): `actions`, `capture="instant"`, `recruit_until`, `army_cap`,
`pool` (finite reinforcements per type), `vp_target` / `vp_timing="start"` / `vp_contest` (control-point scoring),
`mech` (`charge`: Bruiser bonus after moving 2+, `spear_rmax`, `still_bonus`: Archer bonus vs a unit that stood still).
