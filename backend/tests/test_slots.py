import unittest

from app.core.slots import LINE_COUNT, PAYLINES, SYMBOLS, evaluate_grid, spin_lucky_bamboo


class SlotRulesTest(unittest.TestCase):
    def test_evaluate_grid_pays_left_to_right_lines(self):
        grid = [
            ["bamboo", "bamboo", "bamboo", "jade", "coin"],
            ["coin", "coin", "coin", "coin", "coin"],
            ["jade", "lotus", "lantern", "panda", "jade"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 1_000)

        self.assertGreaterEqual(total_win_cents, 100)
        self.assertTrue(any(line["line"] == 1 and line["symbol"] == "coin" for line in winning_lines))
        self.assertTrue(any(line["line"] == 2 and line["symbol"] == "bamboo" for line in winning_lines))

    def test_three_lotus_pays_multiplier_against_line_bet(self):
        grid = [
            ["lotus", "lotus", "lotus", "jade", "coin"],
            ["coin", "jade", "bamboo", "panda", "lantern"],
            ["jade", "panda", "coin", "lantern", "bamboo"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 500)

        self.assertEqual(total_win_cents, 900)
        self.assertEqual(winning_lines[0]["symbol"], "lotus")
        self.assertEqual(winning_lines[0]["count"], 3)
        self.assertEqual(winning_lines[0]["multiplier"], 18)
        self.assertEqual(winning_lines[0]["win_cents"], 900)

    def test_four_lanterns_show_payout_and_net_as_separate_values(self):
        grid = [
            ["lantern", "lantern", "lantern", "lantern", "jade"],
            ["coin", "jade", "panda", "coin", "lantern"],
            ["bamboo", "coin", "lotus", "coin", "jade"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 2_500)
        net_cents = total_win_cents - 2_500

        self.assertEqual(total_win_cents, 10_250)
        self.assertEqual(net_cents, 7_750)
        self.assertEqual(winning_lines[0]["symbol"], "lantern")
        self.assertEqual(winning_lines[0]["count"], 4)
        self.assertEqual(winning_lines[0]["multiplier"], 41)

    def test_paytable_targets_roughly_96_percent_rtp(self):
        total_weight = sum(symbol.weight for symbol in SYMBOLS)
        line_ev = 0.0
        for symbol in SYMBOLS:
            probability = symbol.weight / total_weight
            line_ev += probability**3 * (1 - probability) * symbol.payouts[3]
            line_ev += probability**4 * (1 - probability) * symbol.payouts[4]
            line_ev += probability**5 * symbol.payouts[5]

        rtp_percent = line_ev * (len(PAYLINES) / LINE_COUNT) * 100
        self.assertAlmostEqual(rtp_percent, 96.30, places=2)

    def test_spin_lucky_bamboo_returns_5x3_grid_and_totals(self):
        result = spin_lucky_bamboo(500)

        self.assertEqual(len(result["grid"]), 3)
        self.assertTrue(all(len(row) == 5 for row in result["grid"]))
        self.assertEqual(result["total_bet_cents"], 500)
        self.assertEqual(result["net_cents"], result["total_win_cents"] - result["total_bet_cents"])

    def test_spin_lucky_bamboo_rejects_invalid_bet(self):
        with self.assertRaises(ValueError):
            spin_lucky_bamboo(300)


if __name__ == "__main__":
    unittest.main()
