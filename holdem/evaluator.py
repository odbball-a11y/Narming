"""Poker hand evaluation.

`best_hand(cards)` takes 5 to 7 cards and returns a comparable score tuple:
a higher tuple is a stronger hand, equal tuples split the pot.
"""

from collections import Counter
from itertools import combinations

from .cards import RANKS, rank_value

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)

CATEGORY_NAMES = [
    "high card",
    "pair",
    "two pair",
    "three of a kind",
    "straight",
    "flush",
    "full house",
    "four of a kind",
    "straight flush",
]

WHEEL = [12, 3, 2, 1, 0]  # A-5-4-3-2


def rank5(cards) -> tuple:
    """Score exactly five cards."""
    ranks = sorted((rank_value(c) for c in cards), reverse=True)
    is_flush = len({c[1] for c in cards}) == 1

    unique = sorted(set(ranks), reverse=True)
    straight_high = None
    if len(unique) == 5:
        if unique[0] - unique[4] == 4:
            straight_high = unique[0]
        elif unique == WHEEL:
            straight_high = 3  # five-high

    if straight_high is not None and is_flush:
        return (STRAIGHT_FLUSH, straight_high)

    # Group ranks by count, then by rank: e.g. full house KKK44 -> [(K,3),(4,2)]
    groups = sorted(Counter(ranks).items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    counts = [n for _, n in groups]
    ordered = [r for r, _ in groups]

    if counts[0] == 4:
        return (QUADS, *ordered)
    if counts[:2] == [3, 2]:
        return (FULL_HOUSE, *ordered)
    if is_flush:
        return (FLUSH, *ranks)
    if straight_high is not None:
        return (STRAIGHT, straight_high)
    if counts[0] == 3:
        return (TRIPS, *ordered)
    if counts[:2] == [2, 2]:
        return (TWO_PAIR, *ordered)
    if counts[0] == 2:
        return (PAIR, *ordered)
    return (HIGH_CARD, *ranks)


def best_hand(cards) -> tuple:
    cards = list(cards)
    if not 5 <= len(cards) <= 7:
        raise ValueError("need 5 to 7 cards")
    return max(rank5(combo) for combo in combinations(cards, 5))


def describe(score: tuple) -> str:
    cat = score[0]
    name = CATEGORY_NAMES[cat]
    r = lambda i: RANKS[i]  # noqa: E731
    if cat in (STRAIGHT, STRAIGHT_FLUSH):
        return f"{name}, {r(score[1])}-high"
    if cat in (QUADS, TRIPS, PAIR):
        return f"{name}, {r(score[1])}s"
    if cat == FULL_HOUSE:
        return f"{name}, {r(score[1])}s full of {r(score[2])}s"
    if cat == TWO_PAIR:
        return f"{name}, {r(score[1])}s and {r(score[2])}s"
    return f"{name}, {r(score[1])}-high"
