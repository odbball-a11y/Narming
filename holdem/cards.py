"""Cards and the 52-card deck.

Cards are two-character strings: rank then suit, e.g. "As", "Td", "7c".
"""

import random

RANKS = "23456789TJQKA"
SUITS = "cdhs"
SUIT_SYMBOLS = {"c": "♣", "d": "♦", "h": "♥", "s": "♠"}

FULL_DECK = [r + s for r in RANKS for s in SUITS]


def rank_value(card: str) -> int:
    """0 for a deuce up to 12 for an ace."""
    return RANKS.index(card[0])


def validate(card: str) -> str:
    if len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
        raise ValueError(f"not a card: {card!r}")
    return card


def shuffled_deck(rng: random.Random) -> list[str]:
    deck = list(FULL_DECK)
    rng.shuffle(deck)
    return deck


def pretty(card: str) -> str:
    return card[0] + SUIT_SYMBOLS[card[1]]


def pretty_cards(cards) -> str:
    return " ".join(pretty(c) for c in cards) if cards else "—"
