"""A simple sparring opponent.

It estimates its equity against a random hand by Monte Carlo, then bets for
value, calls when the price is right, folds otherwise, and bluffs now and then.
It is a practice partner, not a solver.
"""

import random

from .cards import FULL_DECK
from .evaluator import best_hand


def equity(hole, board, iterations=400, rng=None) -> float:
    rng = rng or random.Random()
    known = set(hole) | set(board)
    deck = [c for c in FULL_DECK if c not in known]
    need = 5 - len(board)
    score = 0.0
    for _ in range(iterations):
        draw = rng.sample(deck, 2 + need)
        opp, runout = draw[:2], board + draw[2:]
        mine, theirs = best_hand(hole + runout), best_hand(opp + runout)
        score += 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0
    return score / iterations


class HeuristicBot:
    def __init__(self, seed=None, iterations=400, aggression=1.0):
        self.rng = random.Random(seed)
        self.iterations = iterations
        self.aggression = aggression

    def decide(self, hand, seat):
        """Return (action, amount) for `seat`, which must be the player to act."""
        legal = hand.legal_actions()
        eq = equity(hand.hole[seat], hand.board, self.iterations, self.rng)
        owed = legal["call"] or 0
        pot = hand.pot
        raise_range = legal["raise"]

        def raise_to(fraction):
            lo, hi = raise_range
            target = hand.current_bet + int(fraction * (pot + owed))
            return ("raise", max(lo, min(hi, target)))

        # Strong: build the pot.
        if raise_range and eq > 0.72 - 0.05 * (self.aggression - 1):
            if eq > 0.9 and self.rng.random() < 0.25:
                return ("raise", raise_range[1])
            return raise_to(self.rng.choice([0.6, 0.75, 1.0]))

        if owed == 0:
            # Medium hands and the occasional bluff bet.
            if raise_range and (eq > 0.58 and self.rng.random() < 0.5
                                or self.rng.random() < 0.12 * self.aggression):
                return raise_to(self.rng.choice([0.5, 0.66]))
            return ("check", None)

        pot_odds = owed / (pot + owed)
        # Facing a big bet, a random-hand equity overstates our chances.
        needed = pot_odds + 0.05 + 0.15 * min(1.0, owed / max(pot - owed, 1))
        if eq >= needed:
            return ("call", None)
        if raise_range and self.rng.random() < 0.04 * self.aggression:
            return raise_to(0.75)
        return ("fold", None)
