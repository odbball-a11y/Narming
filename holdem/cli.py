"""Command-line front end.

    python -m holdem structures               # list the blind structures
    python -m holdem play                     # you vs the bot in this terminal
    python -m holdem play --hotseat           # two people sharing one terminal
    python -m holdem table new Alice Bob      # turn-by-turn play through a save file
    python -m holdem table show --as Alice
    python -m holdem table act --as Alice raise 12
    python -m holdem table deal
"""

import argparse
import json
import os
import sys

from .bot import HeuristicBot
from .cards import pretty_cards
from .game import IllegalAction, Table
from .structure import PRESETS, BlindStructure, parse_levels, preset

HELP = (
    "actions: f(old)  x/check  c(all)  b(et) N  r(aise) N  a(ll-in)  "
    "| N is the total to bet/raise TO this street | h(istory)  q(uit)"
)


# ------------------------------------------------------------------ rendering

def render(view: dict) -> str:
    lines = []
    if "street" not in view:
        stacks = ", ".join(f"{n} {s}" for n, s in view["stacks"].items())
        return f"No hand dealt yet. Stacks: {stacks}"
    lines.append(f"── Hand #{view['hand_no']}  {level_line(view['level'])}  button: {view['button']} ──")
    for line in view["log"]:
        lines.append("  " + line)
    lines.append("")
    opp = view["opponent"]
    opp_cards = pretty_cards(view["opponent_cards"]) if view["opponent_cards"] else "[hidden]"
    lines.append(f"  Board : {pretty_cards(view['board'])}")
    lines.append(f"  Pot   : {view['pot']}")
    lines.append(f"  {opp:<6}: {opp_cards:<10} stack {view['stacks'][opp]:>5}   in {view['committed'][opp]}")
    you = view["you"]
    lines.append(f"  {you:<6}: {pretty_cards(view['your_cards']):<10} stack {view['stacks'][you]:>5}   in {view['committed'][you]}")
    if view["result"]:
        r = view["result"]
        names = [view["you"], view["opponent"]] if view["seat"] == 0 else [view["opponent"], view["you"]]
        won = " and ".join(names[w] for w in r["winners"])
        how = "split" if len(r["winners"]) == 2 else "wins"
        lines.append(f"  → {won} {how} the pot of {r['pot']}")
    elif view["your_turn"]:
        lines.append("  Your move: " + describe_legal(view["legal"]))
    else:
        lines.append(f"  Waiting for {view['to_act']}.")
    if view["match_over"]:
        lines.append(f"  ★ Match over: {view['winner']} has all the chips.")
    return "\n".join(lines)


def level_line(info: dict) -> str:
    sb, bb = info["blinds"]
    text = f"Level {info['level']} · {sb}/{bb}"
    if info["next_blinds"]:
        nsb, nbb = info["next_blinds"]
        if info["hands_left"] is not None:
            n = info["hands_left"]
            when = "from the next hand" if n == 0 else f"after {n} hand{'s' if n != 1 else ''}"
        else:
            secs = info["seconds_left"]
            when = "from the next hand" if secs == 0 else f"in {secs // 60}:{secs % 60:02d}"
        text += f" (→ {nsb}/{nbb} {when})"
    return text


def describe_legal(legal: dict) -> str:
    opts = []
    if legal["check"]:
        opts.append("check")
    if legal["call"]:
        opts.append(f"call {legal['call']}")
    if legal["raise"]:
        lo, hi = legal["raise"]
        word = legal["raise_word"]
        opts.append(f"{word} to {lo}-{hi}" if lo < hi else f"all-in {hi}")
    if legal["fold"]:
        opts.append("fold")
    return " | ".join(opts)


def parse_action(text: str):
    """'r 12' -> ('raise', 12); 'c' -> ('call', None)."""
    parts = text.strip().lower().split()
    if not parts:
        raise IllegalAction("type an action")
    word = parts[0]
    aliases = {"f": "fold", "x": "check", "k": "check", "c": "call", "b": "bet",
               "r": "raise", "a": "allin", "shove": "allin", "all-in": "allin"}
    word = aliases.get(word, word)
    amount = None
    if word in ("bet", "raise"):
        if len(parts) < 2 or not parts[1].isdigit():
            raise IllegalAction(f"say how much: '{word} 20' means {word} to 20 total")
        amount = int(parts[1])
    return word, amount


# --------------------------------------------------------------- interactive

def play(args):
    names = [args.name, "Bot" if not args.hotseat else args.opponent]
    structure = build_structure(args)
    table = Table(names, seed=args.seed, structure=structure)
    bot = None if args.hotseat else HeuristicBot(seed=args.seed)
    print(f"Heads-up NLHE: {names[0]} vs {names[1]}")
    print(structure.describe())
    print(HELP)

    while not table.match_over:
        before = table.level
        table.deal()
        if table.level != before:
            print(f"\n*** Blinds go up: level {table.level + 1}, {table.small_blind}/{table.big_blind} ***")
        last_viewer = None
        while not table.hand.finished:
            seat = table.hand.to_act
            if bot is not None and seat == 1:
                action, amount = bot.decide(table.hand, 1)
                table.act(1, action, amount)
                continue
            if args.hotseat and last_viewer != seat:
                clear()
                input(f"Pass to {names[seat]} and press Enter...")
                last_viewer = seat
            print("\n" + render(table.view(seat)))
            try:
                text = input(f"{names[seat]}> ")
            except EOFError:
                return
            if text.strip().lower() in ("q", "quit", "exit"):
                return
            if text.strip().lower() in ("h", "history"):
                print_history(table)
                continue
            if text.strip().lower() in ("?", "help"):
                print(HELP)
                continue
            try:
                action, amount = parse_action(text)
                table.act(seat, action, amount)
            except IllegalAction as e:
                print(f"  ! {e}")
        if args.hotseat:
            clear()
        print("\n" + render(table.view(0)))
        if not table.match_over:
            try:
                input("Enter for the next hand (Ctrl-D to stop)... ")
            except EOFError:
                return
    print(f"\n{table.names[table.winner]} wins the match after {table.hand_no} hands.")


def print_history(table):
    for h in table.history[-10:]:
        net = ", ".join(f"{table.names[s]} {h['net'][s]:+d}" for s in (0, 1))
        blinds = "/".join(map(str, h.get("blinds", [])))
        print(f"  #{h['hand_no']} ({blinds}): pot {h['pot']}, board {pretty_cards(h['board'])} → {net}")


def clear():
    print("\033[2J\033[H", end="")


def build_structure(args) -> BlindStructure:
    d = preset(args.structure).to_dict()
    changed = False
    if args.stack:
        d["starting_stack"], changed = args.stack, True
    if args.levels:
        d["levels"], changed = parse_levels(args.levels), True
    if args.hands_per_level:
        d.update(hands_per_level=args.hands_per_level, minutes_per_level=None)
        changed = True
    elif args.minutes_per_level:
        d.update(minutes_per_level=args.minutes_per_level, hands_per_level=None)
        changed = True
    elif args.fixed:
        d.update(minutes_per_level=None, hands_per_level=None)
        changed = True
    if changed:
        d["name"] = "Custom"
    try:
        return BlindStructure.from_dict(d)
    except ValueError as e:
        sys.exit(f"! {e}")


# ----------------------------------------------------------- save-file table

def load(path) -> Table:
    if not os.path.exists(path):
        sys.exit(f"no table at {path} - create one with 'table new'")
    with open(path) as f:
        return Table.from_dict(json.load(f))


def save(table, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(table.to_dict(), f, indent=1)
    os.replace(tmp, path)


def table_cmd(args):
    if args.cmd == "new":
        table = Table(args.players, seed=args.seed, structure=build_structure(args))
        table.deal()
        save(table, args.file)
        print(f"Table created at {args.file}. Hand #1 dealt; {table.names[table.hand.to_act]} to act.")
        return
    table = load(args.file)
    try:
        if args.cmd == "deal":
            table.deal()
            save(table, args.file)
            print(f"Hand #{table.hand_no} dealt at {level_line(table.level_info())}; "
                  f"{table.names[table.hand.to_act]} to act.")
        elif args.cmd == "act":
            action, amount = parse_action(" ".join(args.action))
            table.act(args.who, action, amount)
            save(table, args.file)
            print(render(table.view(args.who)))
        elif args.cmd == "show":
            v = table.view(args.who)
            print(json.dumps(v, indent=1) if args.json else render(v))
        elif args.cmd == "history":
            print_history(table)
        elif args.cmd == "structure":
            print(table.blind_structure().describe())
            print("Now: " + level_line(table.level_info()))
    except (IllegalAction, ValueError) as e:
        sys.exit(f"! {e}")


# --------------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(prog="holdem", description="Heads-up no-limit hold'em")
    sub = p.add_subparsers(dest="mode", required=True)

    def stakes(sp):
        g = sp.add_argument_group("blind structure")
        g.add_argument("--structure", default="standard", choices=sorted(PRESETS),
                       help="preset to start from (default standard; see 'structures')")
        g.add_argument("--stack", type=int, help="starting chips for each player")
        g.add_argument("--levels", help="blind levels, e.g. 10/20,15/30,25/50")
        pace = g.add_mutually_exclusive_group()
        pace.add_argument("--hands-per-level", type=int, help="blinds go up every N hands")
        pace.add_argument("--minutes-per-level", type=float, help="blinds go up every N minutes")
        pace.add_argument("--fixed", action="store_true", help="blinds never go up")
        sp.add_argument("--seed", help="seed for reproducible shuffles")

    pp = sub.add_parser("play", help="play interactively")
    pp.add_argument("--name", default="Hero")
    pp.add_argument("--hotseat", action="store_true", help="two humans, one terminal")
    pp.add_argument("--opponent", default="Player2", help="second name in hotseat mode")
    stakes(pp)

    sub.add_parser("structures", help="show the preset blind structures")

    tp = sub.add_parser("table", help="turn-by-turn play through a JSON save file")
    tp.add_argument("--file", default="table.json")
    tsub = tp.add_subparsers(dest="cmd", required=True)
    tn = tsub.add_parser("new")
    tn.add_argument("players", nargs=2)
    stakes(tn)
    tsub.add_parser("deal")
    tsub.add_parser("history")
    tsub.add_parser("structure", help="show this table's blind structure and current level")
    ts = tsub.add_parser("show")
    ts.add_argument("--as", dest="who", required=True)
    ts.add_argument("--json", action="store_true")
    ta = tsub.add_parser("act")
    ta.add_argument("--as", dest="who", required=True)
    ta.add_argument("action", nargs="+", help="e.g. call | check | fold | raise 12 | allin")

    args = p.parse_args(argv)
    if args.mode == "structures":
        print("\n\n".join(st.describe() for st in PRESETS.values()))
        return
    if args.mode == "play":
        play(args)
    else:
        table_cmd(args)


if __name__ == "__main__":
    main()
