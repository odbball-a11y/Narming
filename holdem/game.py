"""Heads-up no-limit Texas hold'em rules engine.

Rules implemented:
* The button posts the small blind and acts first preflop; the big blind acts
  first on every later street.
* Bet and raise amounts are "raise to" totals for the current street.
* The minimum raise is the size of the last full bet or raise (at least one big
  blind). A player may always move all-in for less.
* An all-in that is too small to be a full raise does not let the other player
  re-raise (heads-up, that player can only call or fold anyway).
* Uncalled chips go back to the player who bet them.
* If a player is all-in and no more betting is possible, the board is run out.
* Split pots give the odd chip to the big blind (the first seat left of the
  button).
* Short stacks post whatever they have for the blinds.
"""

import random
import secrets
import time

from .cards import shuffled_deck
from .evaluator import best_hand, describe
from .structure import BlindStructure

STREETS = ["preflop", "flop", "turn", "river"]
CARDS_DEALT = {"flop": 3, "turn": 1, "river": 1}


class IllegalAction(Exception):
    pass


class Hand:
    """A single hand between seats 0 and 1."""

    def __init__(self, stacks, button, small_blind, big_blind, deck, hand_no=1):
        if len(deck) != 52:
            raise ValueError("deck must hold 52 cards")
        self.hand_no = hand_no
        self.button = button
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.start_stacks = list(stacks)
        self.stacks = list(stacks)  # chips still behind
        self.deck = list(deck)
        self.board = []
        self.street = "preflop"
        self.committed = [0, 0]  # chips put in on this street
        self.total = [0, 0]  # chips put in this hand
        self.has_acted = [False, False]
        self.last_raise = big_blind
        self.folded = None
        self.result = None
        self.log = []

        # Deal one at a time starting left of the button (the big blind).
        bb_seat = 1 - button
        self.hole = [[], []]
        for _ in range(2):
            for seat in (bb_seat, button):
                self.hole[seat].append(self.deck.pop())

        self._post(button, small_blind, "small blind")
        self._post(bb_seat, big_blind, "big blind")
        self.to_act = button
        self._advance()

    # ------------------------------------------------------------------ state

    @property
    def current_bet(self) -> int:
        return max(self.committed)

    @property
    def pot(self) -> int:
        return sum(self.total)

    @property
    def finished(self) -> bool:
        return self.result is not None

    def to_call(self, seat=None) -> int:
        seat = self.to_act if seat is None else seat
        return min(self.current_bet - self.committed[seat], self.stacks[seat])

    def legal_actions(self) -> dict:
        """What the player to act may do.

        Returns {"fold": bool, "check": bool, "call": int|None,
                 "raise": (min_to, max_to)|None, "raise_word": "bet"|"raise"}.
        """
        if self.finished:
            return {}
        p, o = self.to_act, 1 - self.to_act
        owed = self.current_bet - self.committed[p]
        legal = {
            "fold": owed > 0,
            "check": owed == 0,
            "call": min(owed, self.stacks[p]) if owed > 0 else None,
            "raise": None,
            "raise_word": "bet" if self.current_bet == 0 else "raise",
        }
        if self.stacks[o] > 0 and self.stacks[p] > owed:
            max_to = self.committed[p] + self.stacks[p]
            min_to = min(self.current_bet + self.last_raise, max_to)
            legal["raise"] = (min_to, max_to)
        return legal

    # ---------------------------------------------------------------- actions

    def act(self, action: str, amount=None):
        """Apply an action for the player to act.

        action: fold | check | call | bet | raise | allin
        amount: for bet/raise, the total to raise to on this street.
        """
        if self.finished:
            raise IllegalAction("the hand is over")
        action = action.lower()
        p = self.to_act
        legal = self.legal_actions()

        if action in ("allin", "all-in", "shove", "jam"):
            if legal["raise"]:
                action, amount = "raise", legal["raise"][1]
            elif legal["call"]:
                action = "call"
            else:
                action = "check"

        if action == "fold":
            if not legal["fold"]:
                raise IllegalAction("nothing to call - check instead of folding")
            self.folded = p
            self._log(p, "folds")
        elif action == "check":
            if not legal["check"]:
                raise IllegalAction(f"cannot check, {legal['call']} to call")
            self.has_acted[p] = True
            self._log(p, "checks")
        elif action == "call":
            if legal["call"] is None:
                raise IllegalAction("nothing to call - check instead")
            amt = legal["call"]
            self._put_in(p, amt)
            self.has_acted[p] = True
            self._log(p, f"calls {amt}" + (" (all-in)" if self.stacks[p] == 0 else ""))
        elif action in ("bet", "raise"):
            if not legal["raise"]:
                raise IllegalAction("raising is not allowed here")
            if amount is None:
                raise IllegalAction("say how much to raise to, e.g. 'raise 12'")
            amount = int(amount)
            lo, hi = legal["raise"]
            if not lo <= amount <= hi:
                raise IllegalAction(f"{legal['raise_word']} must be to between {lo} and {hi}")
            size = amount - self.current_bet
            if size >= self.last_raise:
                self.last_raise = size  # a full raise re-opens the action
            word = legal["raise_word"]
            self._put_in(p, amount - self.committed[p])
            self.has_acted = [False, False]
            self.has_acted[p] = True
            self._log(p, f"{word}s to {amount}" + (" (all-in)" if self.stacks[p] == 0 else ""))
        else:
            raise IllegalAction(f"unknown action {action!r}")

        self.to_act = 1 - p
        self._advance()

    # -------------------------------------------------------------- internals

    def _log(self, seat, text):
        self.log.append({"street": self.street, "seat": seat, "text": text})

    def _put_in(self, seat, amount):
        amount = min(amount, self.stacks[seat])
        self.stacks[seat] -= amount
        self.committed[seat] += amount
        self.total[seat] += amount

    def _post(self, seat, blind, name):
        amount = min(blind, self.stacks[seat])
        self._put_in(seat, amount)
        self._log(seat, f"posts {name} {amount}" + (" (all-in)" if self.stacks[seat] == 0 else ""))

    def _round_complete(self) -> bool:
        active = [s for s in (0, 1) if self.stacks[s] > 0]
        for s in active:
            if self.committed[s] < self.current_bet:
                return False
            if len(active) == 2 and not self.has_acted[s]:
                return False
        return True

    def _deal_next_street(self):
        self.street = STREETS[STREETS.index(self.street) + 1]
        self.deck.pop()  # burn
        for _ in range(CARDS_DEALT[self.street]):
            self.board.append(self.deck.pop())
        self.committed = [0, 0]
        self.has_acted = [False, False]
        self.last_raise = self.big_blind
        self.to_act = 1 - self.button
        self.log.append({"street": self.street, "seat": None, "text": " ".join(self.board)})

    def _advance(self):
        while not self.finished:
            if self.folded is not None:
                self._finish()
                return
            if not self._round_complete():
                if self.stacks[self.to_act] == 0:
                    self.to_act = 1 - self.to_act
                return
            if self.street == "river":
                self._finish()
                return
            self._deal_next_street()
            # if fewer than two players can bet, the loop keeps dealing

    def _finish(self):
        # Return any uncalled chips.
        a, b = self.total
        if a != b:
            hi = 0 if a > b else 1
            excess = abs(a - b)
            self.total[hi] -= excess
            self.committed[hi] -= excess
            self.stacks[hi] += excess
            self._log(hi, f"uncalled {excess} returned")
        pot = self.pot
        result = {"pot": pot, "winnings": [0, 0], "showdown": False, "hands": [None, None]}

        if self.folded is not None:
            winner = 1 - self.folded
            result["winnings"][winner] = pot
            result["winners"] = [winner]
            self._log(winner, f"wins {pot}")
        else:
            result["showdown"] = True
            scores = [best_hand(self.hole[s] + self.board) for s in (0, 1)]
            result["hands"] = [describe(sc) for sc in scores]
            for s in (0, 1):
                self._log(s, f"shows {' '.join(self.hole[s])} ({result['hands'][s]})")
            if scores[0] == scores[1]:
                half, odd = divmod(pot, 2)
                result["winnings"] = [half, half]
                result["winnings"][1 - self.button] += odd
                result["winners"] = [0, 1]
                self._log(None, f"split pot {pot}")
            else:
                winner = 0 if scores[0] > scores[1] else 1
                result["winnings"][winner] = pot
                result["winners"] = [winner]
                self._log(winner, f"wins {pot}")

        for s in (0, 1):
            self.stacks[s] += result["winnings"][s]
        self.result = result

    # ---------------------------------------------------------- persistence

    def to_dict(self) -> dict:
        return dict(vars(self))

    @classmethod
    def from_dict(cls, data: dict) -> "Hand":
        hand = cls.__new__(cls)
        hand.__dict__.update(data)
        return hand


class Table:
    """A heads-up match: two players, alternating button, until one is broke.

    Pass a `structure` (see holdem.structure) for blinds that go up; without
    one, the table plays fixed `small_blind`/`big_blind` blinds. A
    `starting_stack` given alongside a structure overrides the structure's.
    """

    def __init__(self, names, starting_stack=None, small_blind=1, big_blind=2, seed=None,
                 structure=None, clock=None):
        if len(names) != 2:
            raise ValueError("heads-up needs exactly two players")
        if structure is None:
            structure = BlindStructure.fixed(small_blind, big_blind, starting_stack or 200)
        elif starting_stack:
            structure = BlindStructure.from_dict({**structure.to_dict(), "starting_stack": starting_stack})
        self.names = list(names)
        self.structure = structure.to_dict()
        self.stacks = [structure.starting_stack] * 2
        self.level = 0
        self.small_blind, self.big_blind = structure.blinds(0)
        self.seed = seed if seed is not None else secrets.token_hex(8)
        self.started_at = None  # wall-clock time of the first deal
        self.button = 1  # flips to seat 0 on the first hand
        self.hand_no = 0
        self.hand = None
        self.history = []
        self._clock = clock

    # The clock is injectable for tests; it is not saved with the table.
    def _now(self) -> float:
        clock = getattr(self, "_clock", None)
        return clock() if clock else time.time()

    def blind_structure(self) -> BlindStructure:
        return BlindStructure.from_dict(self.structure)

    def elapsed(self) -> float:
        return 0.0 if self.started_at is None else self._now() - self.started_at

    def level_info(self) -> dict:
        """Current level, and what comes next and when.

        hands_left counts the hand in progress, if any. 0 means the next hand
        is dealt at the next level. seconds_left can be 0 for the same reason.
        """
        st = self.blind_structure()
        info = {
            "structure": st.name,
            "level": self.level + 1,
            "blinds": [self.small_blind, self.big_blind],
            "next_blinds": list(st.blinds(self.level + 1)) if st.increases else None,
            "hands_left": None,
            "seconds_left": None,
        }
        if st.hands_per_level:
            last_hand_of_level = (self.level + 1) * st.hands_per_level
            in_progress = self.hand is not None and not self.hand.finished
            info["hands_left"] = max(0, last_hand_of_level - self.hand_no + (1 if in_progress else 0))
        elif st.minutes_per_level:
            end = (self.level + 1) * st.minutes_per_level * 60
            info["seconds_left"] = max(0, round(end - self.elapsed()))
        return info

    def seat_of(self, who) -> int:
        if isinstance(who, int) and who in (0, 1):
            return who
        for i, name in enumerate(self.names):
            if str(who).lower() == name.lower():
                return i
        raise ValueError(f"no player called {who!r}")

    @property
    def match_over(self) -> bool:
        return min(self.stacks) == 0

    @property
    def winner(self):
        if not self.match_over:
            return None
        return 0 if self.stacks[0] > 0 else 1

    def deal(self) -> Hand:
        if self.hand is not None and not self.hand.finished:
            raise IllegalAction("the current hand is not finished")
        if self.match_over:
            raise IllegalAction(f"the match is over - {self.names[self.winner]} won")
        if self.started_at is None:
            self.started_at = self._now()
        self.hand_no += 1
        self.button = 1 - self.button
        st = self.blind_structure()
        self.level = max(self.level, st.level_for(self.hand_no, self.elapsed()))
        self.small_blind, self.big_blind = st.blinds(self.level)
        rng = random.Random(f"{self.seed}:{self.hand_no}")
        self.hand = Hand(self.stacks, self.button, self.small_blind, self.big_blind,
                         shuffled_deck(rng), self.hand_no)
        self._sync()
        return self.hand

    def act(self, who, action, amount=None):
        if self.hand is None or self.hand.finished:
            raise IllegalAction("no hand in progress - deal first")
        seat = self.seat_of(who)
        if seat != self.hand.to_act:
            raise IllegalAction(f"it is {self.names[self.hand.to_act]}'s turn")
        self.hand.act(action, amount)
        self._sync()

    def _sync(self):
        h = self.hand
        if h.finished and (not self.history or self.history[-1]["hand_no"] != h.hand_no):
            self.stacks = list(h.stacks)
            self.history.append({
                "hand_no": h.hand_no,
                "button": h.button,
                "hole": h.hole if h.result["showdown"] else None,
                "board": h.board,
                "pot": h.result["pot"],
                "blinds": [h.small_blind, h.big_blind],
                "winners": h.result["winners"],
                "net": [h.stacks[s] - h.start_stacks[s] for s in (0, 1)],
            })

    def view(self, who) -> dict:
        """Everything `who` is allowed to see."""
        seat = self.seat_of(who)
        opp = 1 - seat
        v = {
            "you": self.names[seat],
            "opponent": self.names[opp],
            "seat": seat,
            "stacks": {self.names[s]: self.stacks[s] for s in (0, 1)},
            "blinds": [self.small_blind, self.big_blind],
            "level": self.level_info(),
            "hand_no": self.hand_no,
            "match_over": self.match_over,
            "winner": self.names[self.winner] if self.match_over else None,
        }
        h = self.hand
        if h is None:
            return v
        shown = h.finished and h.result["showdown"]
        v.update({
            "button": self.names[h.button],
            "street": h.street,
            "board": h.board,
            "your_cards": h.hole[seat],
            "opponent_cards": h.hole[opp] if shown else None,
            "stacks": {self.names[s]: h.stacks[s] for s in (0, 1)},
            "committed": {self.names[s]: h.committed[s] for s in (0, 1)},
            "pot": h.pot,
            "to_act": None if h.finished else self.names[h.to_act],
            "your_turn": not h.finished and h.to_act == seat,
            "legal": h.legal_actions() if not h.finished and h.to_act == seat else None,
            "log": [
                ((self.names[e["seat"]] + " ") if e["seat"] is not None else f"*** {e['street'].upper()}: ")
                + e["text"]
                for e in h.log
            ],
            "result": h.result,
        })
        return v

    def to_dict(self) -> dict:
        d = {k: v for k, v in vars(self).items() if not k.startswith("_")}
        d["hand"] = self.hand.to_dict() if self.hand else None
        return d

    @classmethod
    def from_dict(cls, data: dict, clock=None) -> "Table":
        t = cls.__new__(cls)
        t.__dict__.update(data)
        t.hand = Hand.from_dict(data["hand"]) if data["hand"] else None
        t._clock = clock
        return t
