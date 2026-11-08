# Heads-up No-Limit Hold'em

A small poker environment for two players. It needs Python 3.10+ and nothing else.

## Play in the browser

`web/index.html` is a self-contained table page (published at https://claude.ai/artifact/G9ajbsWNykxjABtsGvETVb).
It runs a JavaScript port of the same rules engine and bot, with bet presets, a raise slider,
pot odds, an optional equity readout and keyboard shortcuts (F / C / R / A / Enter).

## Play in the terminal

```bash
python -m holdem play                     # you against the built-in bot (Standard structure)
python -m holdem play --hotseat --name Ann --opponent Ben   # two people, one keyboard
python -m holdem play --structure turbo --seed 42           # another preset, fixed shuffles
```

At the prompt:

| type | means |
|---|---|
| `f` / `fold` | fold |
| `x` / `check` | check |
| `c` / `call` | call |
| `b 10` / `bet 10` | bet **to** 10 |
| `r 30` / `raise 30` | raise **to** 30 (the total for this street, not the amount added) |
| `a` / `allin` | move all-in |
| `h` | recent hand history |
| `q` | quit |

## Blind structure

A structure sets the starting chips, the blind levels, and when the blinds go up.
Blinds go up only between hands. After the last listed level they keep doubling,
so every match ends. `python -m holdem structures` prints the presets:

| preset | starting chips | blinds go up | levels |
|---|---|---|---|
| `turbo` | 1,500 | every 10 hands | 10/20, 20/40, 30/60, 50/100, 75/150, 100/200, 150/300, 200/400, 300/600, 500/1000 |
| `standard` (default) | 1,500 | every 20 hands | 10/20, 15/30, 20/40, 30/60, 40/80, 50/100, 75/150, 100/200, 150/300, 200/400, 300/600, 400/800, 500/1000, 700/1400, 1000/2000 |
| `deep` | 5,000 | every 25 hands | 10/20, 15/30, 20/40, 25/50, 30/60, 40/80, 50/100, 60/120, 80/160, 100/200, 125/250, 150/300, 200/400, 250/500, 300/600, 400/800, 500/1000 |
| `cash` | 200 | never | 1/2 |

Change any part of a preset:

```bash
python -m holdem play --structure standard --stack 3000                 # deeper stacks
python -m holdem play --levels 25/50,50/100,100/200 --hands-per-level 8 # your own levels
python -m holdem play --structure deep --minutes-per-level 10           # timed levels
python -m holdem play --structure cash --levels 5/10 --stack 1000        # fixed 5/10 game
```

The browser table has the same presets plus an editor for every value.

In code: `Table(names, structure=preset("turbo"))`, or build a `BlindStructure`
from `holdem.structure`. `Table.level_info()` reports the level, the current and
next blinds, and how many hands or seconds remain.

## Turn-by-turn play through a save file

Each command loads `table.json`, applies one action and saves it. Use this to play
over chat, from scripts, or with an AI agent. A player's view never shows the
other player's hole cards until showdown.

```bash
python -m holdem table new Alice Bob --structure turbo
python -m holdem table show --as Alice          # add --json for machine-readable output
python -m holdem table act --as Alice raise 6
python -m holdem table act --as Bob call
python -m holdem table deal                     # start the next hand once one ends
python -m holdem table history
python -m holdem table structure                # this table's levels and the current one
```

Use `--file other.json` (before the subcommand) to run several tables.

## Rules implemented

- The button posts the small blind and acts first preflop; the big blind acts first on the flop, turn and river.
- Minimum raise = the last full bet or raise, never less than one big blind; an all-in for less is always allowed.
- An all-in too short to be a full raise doesn't reopen the betting.
- Uncalled chips are returned. Once nobody can bet any more, the board is run out.
- In a split pot the odd chip goes to the big blind. A player too short for a blind posts what they have.
- Blinds follow the blind structure. Levels change only between hands, and the minimum bet follows the current big blind.
- The button alternates every hand. The match ends when one player has all the chips.

## Code

- `holdem/game.py`: the rules engine (`Hand` for one hand, `Table` for a match), which can be saved to JSON
- `holdem/structure.py`: blind structures and the presets
- `holdem/evaluator.py`: ranks the best 5-card hand out of 7 cards
- `holdem/bot.py`: `HeuristicBot`, which plays from its Monte Carlo equity against a random hand. It's a sparring partner, not a solver.
- `holdem/cli.py`: the terminal interface

```python
from holdem import Table
t = Table(["Ann", "Ben"], starting_stack=200, small_blind=1, big_blind=2)
t.deal()
t.act("Ann", "raise", 6)
print(t.view("Ben")["legal"])   # {'fold': True, 'check': False, 'call': 4, 'raise': (10, 200), ...}
```

## Tests

```bash
python -m unittest discover -s tests
```
