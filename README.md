# Heads-up No-Limit Hold'em

A small poker environment for two players. It needs Python 3.10+ and nothing else.

## Play

```bash
python -m holdem play                     # you against the built-in bot
python -m holdem play --hotseat --name Ann --opponent Ben   # two people, one keyboard
python -m holdem play --stack 100 --sb 5 --bb 10 --seed 42  # custom stakes, fixed shuffles
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

## Turn-by-turn play through a save file

Each command loads `table.json`, applies one action and saves it. Use this to play
over chat, from scripts, or with an AI agent. A player's view never shows the
other player's hole cards until showdown.

```bash
python -m holdem table new Alice Bob --stack 200 --sb 1 --bb 2
python -m holdem table show --as Alice          # add --json for machine-readable output
python -m holdem table act --as Alice raise 6
python -m holdem table act --as Bob call
python -m holdem table deal                     # start the next hand once one ends
python -m holdem table history
```

Use `--file other.json` (before the subcommand) to run several tables.

## Rules implemented

- The button posts the small blind and acts first preflop; the big blind acts first on the flop, turn and river.
- Minimum raise = the last full bet or raise, never less than one big blind; an all-in for less is always allowed.
- An all-in too short to be a full raise doesn't reopen the betting.
- Uncalled chips are returned. Once nobody can bet any more, the board is run out.
- In a split pot the odd chip goes to the big blind. A player too short for a blind posts what they have.
- The button alternates every hand. The match ends when one player has all the chips.

## Code

- `holdem/game.py`: the rules engine (`Hand` for one hand, `Table` for a match), which can be saved to JSON
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
