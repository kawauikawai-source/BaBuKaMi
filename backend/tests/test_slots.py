import unittest
from itertools import product

from app.core.slots import LINE_COUNT, PAYLINES, SYMBOLS, evaluate_grid, spin_lucky_bamboo


class SlotRulesTest(unittest.TestCase):
    def test_evaluate_grid_pays_visible_horizontal_runs(self):
        grid = [
            ["bamboo", "bamboo", "bamboo", "jade", "coin"],
            ["coin", "coin", "coin", "coin", "coin"],
            ["jade", "lotus", "lantern", "panda", "jade"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 1_000)

        self.assertGreaterEqual(total_win_cents, 100)
        self.assertTrue(any(line["line"] == 1 and line["symbol"] == "bamboo" for line in winning_lines))
        self.assertTrue(any(line["line"] == 2 and line["symbol"] == "coin" for line in winning_lines))

    def test_horizontal_run_can_start_after_first_reel(self):
        grid = [
            ["jade", "coin", "bamboo", "bamboo", "bamboo"],
            ["coin", "jade", "bamboo", "panda", "lantern"],
            ["jade", "panda", "coin", "lantern", "bamboo"],
        ]

        winning_lines, _ = evaluate_grid(grid, 500)

        self.assertEqual(len(winning_lines), 1)
        self.assertEqual(winning_lines[0]["positions"], [
            {"row": 0, "reel": 2},
            {"row": 0, "reel": 3},
            {"row": 0, "reel": 4},
        ])

    def test_scattered_and_diagonal_symbols_do_not_create_hidden_line(self):
        grid = [
            ["bamboo", "coin", "jade", "lotus", "panda"],
            ["coin", "bamboo", "lotus", "jade", "lantern"],
            ["jade", "lotus", "bamboo", "coin", "panda"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 500)

        self.assertEqual(winning_lines, [])
        self.assertEqual(total_win_cents, 0)

    def test_three_lotus_pays_multiplier_against_line_bet(self):
        grid = [
            ["lotus", "lotus", "lotus", "jade", "coin"],
            ["coin", "jade", "bamboo", "panda", "lantern"],
            ["jade", "panda", "coin", "lantern", "bamboo"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 500)

        self.assertEqual(total_win_cents, 1_500)
        self.assertEqual(winning_lines[0]["symbol"], "lotus")
        self.assertEqual(winning_lines[0]["count"], 3)
        self.assertEqual(winning_lines[0]["multiplier"], 9)
        self.assertEqual(winning_lines[0]["win_cents"], 1_500)

    def test_four_lanterns_show_payout_and_net_as_separate_values(self):
        grid = [
            ["lantern", "lantern", "lantern", "lantern", "jade"],
            ["coin", "jade", "panda", "coin", "lantern"],
            ["bamboo", "coin", "lotus", "coin", "jade"],
        ]

        winning_lines, total_win_cents = evaluate_grid(grid, 2_500)
        net_cents = total_win_cents - 2_500

        self.assertEqual(total_win_cents, 16_666)
        self.assertEqual(net_cents, 14_166)
        self.assertEqual(winning_lines[0]["symbol"], "lantern")
        self.assertEqual(winning_lines[0]["count"], 4)
        self.assertEqual(winning_lines[0]["multiplier"], 20)

    def test_paytable_targets_roughly_96_percent_rtp(self):
        total_weight = sum(symbol.weight for symbol in SYMBOLS)
        probabilities = {symbol.id: symbol.weight / total_weight for symbol in SYMBOLS}
        payouts = {symbol.id: symbol.payouts for symbol in SYMBOLS}
        row_ev = 0.0
        for row in product(probabilities, repeat=5):
            probability = 1.0
            for symbol_id in row:
                probability *= probabilities[symbol_id]
            run_payouts = []
            start = 0
            while start < len(row):
                end = start + 1
                while end < len(row) and row[end] == row[start]:
                    end += 1
                if end - start >= 3:
                    run_payouts.append(payouts[row[start]][end - start])
                start = end
            if run_payouts:
                row_ev += probability * max(run_payouts)

        rtp_percent = row_ev * (len(PAYLINES) / LINE_COUNT) * 100
        self.assertAlmostEqual(rtp_percent, 96.30, places=1)

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
