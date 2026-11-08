import json
import random
import unittest

from holdem.bot import HeuristicBot, equity
from holdem.cards import FULL_DECK
from holdem.evaluator import (FLUSH, FULL_HOUSE, STRAIGHT, STRAIGHT_FLUSH, TWO_PAIR,
                              best_hand, describe)
from holdem.game import Hand, IllegalAction, Table


def rig(button_cards, bb_cards, board):
    """Build a deck so the hand deals exactly these cards (button = seat 0)."""
    order = [bb_cards[0], button_cards[0], bb_cards[1], button_cards[1]]
    rest = [c for c in FULL_DECK if c not in order + board]
    burns = rest[:3]
    filler = rest[3:]
    order += [burns[0], *board[:3], burns[1], board[3], burns[2], board[4]]
    deck = filler + list(reversed(order))  # deal pops from the end
    assert len(deck) == 52
    return deck


def hand(stacks=(200, 200), button_cards=("As", "Ks"), bb_cards=("7d", "2c"),
         board=("Qh", "Jd", "3c", "8s", "4h"), sb=1, bb=2):
    return Hand(list(stacks), 0, sb, bb, rig(list(button_cards), list(bb_cards), list(board)))


class EvaluatorTests(unittest.TestCase):
    def score(self, s):
        return best_hand(s.split())

    def test_categories(self):
        self.assertEqual(self.score("As Ks Qs Js Ts 2c 3d")[0], STRAIGHT_FLUSH)
        self.assertEqual(self.score("Ah 2d 3c 4s 5h Kd Qc")[:2], (STRAIGHT, 3))
        self.assertEqual(self.score("Ah Kh 2h 7h 9h Kd Ks")[0], FLUSH)
        self.assertEqual(self.score("Kh Kd Ks 4c 4d 9h 2s")[0], FULL_HOUSE)
        self.assertEqual(self.score("Kh Kd 4s 4c 9d 9h 2s")[:4], (TWO_PAIR, 11, 7, 2))

    def test_comparisons(self):
        self.assertGreater(self.score("Ah Ad 9c 8s 2h 3d 4c"), self.score("Kh Kd Ac Qs 2h 3d 4c"))
        # kicker decides
        self.assertGreater(self.score("Ah Ad Kc 8s 2h 3d 6c"), self.score("As Ac Qc 8d 2h 3d 6c"))
        # six-high straight beats the wheel
        self.assertGreater(self.score("2h 3d 4c 5s 6h Kd Kc"), self.score("Ah 2d 3c 4s 5h Kd Kc"))
        # board plays: tie
        self.assertEqual(self.score("2c 3d Ah Kh Qh Jh Th"), self.score("2s 4d Ah Kh Qh Jh Th"))

    def test_describe(self):
        self.assertEqual(describe(self.score("Kh Kd Ks 4c 4d 9h 2s")), "full house, Ks full of 4s")


class BettingTests(unittest.TestCase):
    def test_blinds_and_preflop_order(self):
        h = hand()
        self.assertEqual(h.committed, [1, 2])
        self.assertEqual(h.to_act, 0)  # button acts first preflop
        legal = h.legal_actions()
        self.assertEqual(legal["call"], 1)
        self.assertEqual(legal["raise"], (4, 200))
        self.assertFalse(legal["check"])

    def test_big_blind_option_and_postflop_order(self):
        h = hand()
        h.act("call")
        self.assertEqual(h.street, "preflop")
        self.assertEqual(h.to_act, 1)
        self.assertTrue(h.legal_actions()["check"])
        h.act("check")
        self.assertEqual(h.street, "flop")
        self.assertEqual(len(h.board), 3)
        self.assertEqual(h.to_act, 1)  # big blind first after the flop
        self.assertEqual(h.legal_actions()["raise"], (2, 198))

    def test_min_raise_tracks_last_raise(self):
        h = hand()
        h.act("raise", 6)  # raise of 4
        self.assertEqual(h.legal_actions()["raise"][0], 10)
        with self.assertRaises(IllegalAction):
            h.act("raise", 9)
        h.act("raise", 20)  # raise of 14
        self.assertEqual(h.legal_actions()["raise"][0], 34)

    def test_fold_awards_pot_and_returns_nothing_extra(self):
        h = hand()
        h.act("raise", 6)
        h.act("fold")
        self.assertTrue(h.finished)
        self.assertEqual(h.stacks, [202, 198])

    def test_cannot_fold_when_checking_is_free(self):
        h = hand()
        h.act("call")
        with self.assertRaises(IllegalAction):
            h.act("fold")

    def test_uncalled_bet_returned_on_showdown(self):
        # short stack calls all-in for less than the bet
        h = hand(stacks=(200, 50))
        h.act("raise", 120)
        h.act("call")  # 50 all-in
        self.assertTrue(h.finished)
        self.assertEqual(len(h.board), 5)  # ran it out
        self.assertEqual(sum(h.stacks), 250)
        # AK high vs 72o on Q J 3 8 4: button wins 100, keeps the uncalled 70
        self.assertEqual(h.stacks, [250, 0])

    def test_all_in_short_of_full_raise_cannot_be_reraised(self):
        h = hand(stacks=(200, 15))
        h.act("raise", 12)
        legal = h.legal_actions()
        self.assertEqual(legal["raise"], (15, 15))  # all-in only
        h.act("allin")
        legal = h.legal_actions()
        self.assertIsNone(legal["raise"])
        self.assertEqual(legal["call"], 3)

    def test_split_pot_odd_chip_to_big_blind(self):
        h = hand(stacks=(201, 201), button_cards=("2c", "3d"), bb_cards=("2d", "3c"),
                 board=("Ah", "Kh", "Qs", "Jd", "Tc"))
        h.act("allin")
        h.act("call")
        self.assertEqual(h.result["winners"], [0, 1])
        self.assertEqual(h.stacks, [201, 201])

    def test_short_big_blind_all_in_from_posting(self):
        h = Hand([100, 1], 0, 1, 2, rig(["As", "Ad"], ["7d", "2c"], ["Qh", "Jd", "3c", "8s", "4h"]))
        self.assertTrue(h.finished)
        self.assertEqual(h.stacks, [101, 0])

    def test_short_small_blind(self):
        h = hand(stacks=(3, 100))
        legal = h.legal_actions()
        self.assertEqual(legal["call"], 1)
        self.assertEqual(legal["raise"], (3, 3))


class TableTests(unittest.TestCase):
    def test_button_alternates_and_turn_enforced(self):
        t = Table(["Ann", "Ben"], seed="x")
        t.deal()
        self.assertEqual(t.hand.button, 0)
        with self.assertRaises(IllegalAction):
            t.act("Ben", "call")
        t.act("Ann", "fold")
        self.assertEqual(t.stacks, [199, 201])
        t.deal()
        self.assertEqual(t.hand.button, 1)
        self.assertEqual(t.hand.to_act, 1)

    def test_view_hides_opponent_cards(self):
        t = Table(["Ann", "Ben"], seed="x")
        t.deal()
        v = t.view("Ann")
        self.assertIsNone(v["opponent_cards"])
        self.assertEqual(v["your_cards"], t.hand.hole[0])
        self.assertTrue(v["your_turn"])
        self.assertIsNone(t.view("Ben")["legal"])

    def test_save_and_load_round_trip(self):
        t = Table(["Ann", "Ben"], seed="s")
        t.deal()
        t.act("Ann", "raise", 6)
        t2 = Table.from_dict(json.loads(json.dumps(t.to_dict())))
        t2.act("Ben", "call")
        self.assertEqual(t2.hand.street, "flop")

    def test_seed_reproducible(self):
        a, b = Table(["A", "B"], seed=7), Table(["A", "B"], seed=7)
        self.assertEqual(a.deal().hole, b.deal().hole)

    def test_bot_match_conserves_chips(self):
        rng = random.Random(1)
        bots = [HeuristicBot(seed=1, iterations=40), HeuristicBot(seed=2, iterations=40, aggression=1.5)]
        hands = 0
        for match in range(15):
            stack = rng.choice([20, 100, 300])
            t = Table(["A", "B"], starting_stack=stack, seed=match)
            while not t.match_over and t.hand_no < 400:
                t.deal()
                while not t.hand.finished:
                    s = t.hand.to_act
                    t.act(s, *bots[s].decide(t.hand, s))
                    if not t.hand.finished:
                        self.assertEqual(sum(t.hand.stacks) + t.hand.pot, 2 * stack)
                self.assertEqual(sum(t.stacks), 2 * stack)
                self.assertTrue(all(s >= 0 for s in t.stacks))
                hands += 1
        self.assertGreater(hands, 100)


class BotTests(unittest.TestCase):
    def test_equity_sanity(self):
        rng = random.Random(0)
        self.assertGreater(equity(["As", "Ad"], [], 300, rng), 0.75)
        self.assertLess(equity(["7d", "2c"], [], 300, rng), 0.42)
        self.assertEqual(equity(["As", "Ks"], ["Qs", "Js", "Ts"], 50, rng), 1.0)

    def test_bot_only_makes_legal_moves(self):
        for seed in range(30):
            t = Table(["A", "B"], starting_stack=60, seed=seed)
            bot = HeuristicBot(seed=seed, iterations=30)
            t.deal()
            while not t.hand.finished:
                s = t.hand.to_act
                t.act(s, *bot.decide(t.hand, s))  # raises if illegal


if __name__ == "__main__":
    unittest.main()
