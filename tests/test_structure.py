import json
import unittest

from holdem.bot import HeuristicBot
from holdem.game import Table
from holdem.structure import PRESETS, BlindStructure, parse_levels, preset


def quick(levels=((1, 2), (2, 4)), stack=200, **pace):
    return BlindStructure("Test", stack, list(levels), **pace)


def fold_hand(t):
    t.act(t.hand.to_act, "fold")


class StructureTests(unittest.TestCase):
    def test_presets_are_valid(self):
        for name in PRESETS:
            st = preset(name)
            self.assertGreaterEqual(st.starting_stack, st.levels[0][1])
        self.assertFalse(preset("cash").increases)

    def test_doubling_after_last_level(self):
        st = quick(hands_per_level=5)
        self.assertEqual(st.blinds(1), (2, 4))
        self.assertEqual(st.blinds(2), (4, 8))
        self.assertEqual(st.blinds(4), (16, 32))

    def test_level_for_hands_and_minutes(self):
        st = quick(hands_per_level=3)
        self.assertEqual([st.level_for(n) for n in range(1, 8)], [0, 0, 0, 1, 1, 1, 2])
        st = quick(minutes_per_level=10)
        self.assertEqual(st.level_for(50, 599), 0)
        self.assertEqual(st.level_for(1, 600), 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            quick(levels=[(2, 1)])
        with self.assertRaises(ValueError):
            quick(levels=[(5, 10), (2, 4)])
        with self.assertRaises(ValueError):
            quick(hands_per_level=5, minutes_per_level=5)
        with self.assertRaises(ValueError):
            quick(stack=1)
        with self.assertRaises(ValueError):
            parse_levels("10-20")
        self.assertEqual(parse_levels("10/20, 15/30"), [(10, 20), (15, 30)])


class TableLevelTests(unittest.TestCase):
    def test_blinds_rise_every_n_hands(self):
        t = Table(["A", "B"], seed=1, structure=quick(hands_per_level=2))
        seen = []
        for _ in range(5):
            t.deal()
            seen.append((t.small_blind, t.big_blind, t.hand.big_blind))
            fold_hand(t)
        self.assertEqual([s[:2] for s in seen], [(1, 2), (1, 2), (2, 4), (2, 4), (4, 8)])
        self.assertTrue(all(s[1] == s[2] for s in seen))

    def test_min_raise_follows_the_level(self):
        t = Table(["A", "B"], seed=1, structure=quick(hands_per_level=1))
        t.deal(); fold_hand(t)
        t.deal()  # level 2: 2/4
        self.assertEqual(t.hand.committed[t.hand.button], 2)
        self.assertEqual(t.hand.legal_actions()["raise"][0], 8)

    def test_hands_left_countdown(self):
        t = Table(["A", "B"], seed=1, structure=quick(hands_per_level=3))
        self.assertEqual(t.level_info()["hands_left"], 3)
        t.deal()
        self.assertEqual(t.level_info()["hands_left"], 3)  # counts the hand in progress
        fold_hand(t)
        self.assertEqual(t.level_info()["hands_left"], 2)
        for _ in range(2):
            t.deal(); fold_hand(t)
        info = t.level_info()
        self.assertEqual((info["hands_left"], info["next_blinds"]), (0, [2, 4]))

    def test_minutes_with_a_clock(self):
        now = [1000.0]
        t = Table(["A", "B"], seed=1, structure=quick(minutes_per_level=5), clock=lambda: now[0])
        t.deal(); fold_hand(t)
        now[0] += 200
        self.assertEqual(t.level_info()["seconds_left"], 100)
        t.deal(); fold_hand(t)
        self.assertEqual(t.big_blind, 2)
        now[0] += 101
        t.deal()
        self.assertEqual((t.level, t.big_blind), (1, 4))

    def test_level_never_goes_back(self):
        now = [0.0]
        t = Table(["A", "B"], seed=1, structure=quick(minutes_per_level=1), clock=lambda: now[0])
        t.deal(); fold_hand(t)
        now[0] += 130
        t.deal(); fold_hand(t)
        self.assertEqual(t.level, 2)
        now[0] -= 100  # a clock that jumps back must not lower the blinds
        t.deal()
        self.assertEqual(t.level, 2)

    def test_starting_stack_override_and_fixed_default(self):
        t = Table(["A", "B"], starting_stack=999, structure=preset("turbo"))
        self.assertEqual(t.stacks, [999, 999])
        t = Table(["A", "B"])
        self.assertEqual((t.stacks, t.big_blind), ([200, 200], 2))
        self.assertIsNone(t.level_info()["next_blinds"])

    def test_save_and_load_keeps_structure(self):
        t = Table(["A", "B"], seed=1, structure=quick(hands_per_level=1))
        t.deal(); fold_hand(t); t.deal()
        t2 = Table.from_dict(json.loads(json.dumps(t.to_dict())))
        self.assertEqual(t2.level, 1)
        fold_hand(t2); t2.deal()
        self.assertEqual(t2.big_blind, 8)

    def test_turbo_matches_finish_and_conserve_chips(self):
        bots = [HeuristicBot(seed=1, iterations=30), HeuristicBot(seed=2, iterations=30)]
        for m in range(4):
            t = Table(["A", "B"], seed=m, structure=preset("turbo"))
            while not t.match_over:
                t.deal()
                while not t.hand.finished:
                    s = t.hand.to_act
                    t.act(s, *bots[s].decide(t.hand, s))
                self.assertEqual(sum(t.stacks), 3000)
            self.assertLess(t.hand_no, 400)


if __name__ == "__main__":
    unittest.main()
