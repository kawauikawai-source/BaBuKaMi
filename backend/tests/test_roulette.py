import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.core.roulette import describe_outcome, evaluate_bet
from app.routers.games import aggregate_roulette_bets


def request_bet(bet_type: str, selection: str, amount: str = "1.00") -> SimpleNamespace:
    return SimpleNamespace(type=bet_type, selection=selection, amount=Decimal(amount))


class RouletteRulesTest(unittest.TestCase):
    def test_ui_generated_bets_are_accepted_by_backend_rules(self):
        bets = [("straight", str(number)) for number in [0, *range(1, 37)]]
        bets += [
            ("range", "low"),
            ("parity", "even"),
            ("color", "red"),
            ("color", "black"),
            ("parity", "odd"),
            ("range", "high"),
            *[("dozen", str(value)) for value in range(1, 4)],
            *[("column", str(value)) for value in range(1, 4)],
            *[("street", str(value)) for value in range(1, 13)],
            *[("six_line", str(value)) for value in range(1, 12)],
        ]

        pairs = [[0, 1], [0, 2], [0, 3]]
        for row in range(12):
            base = row * 3 + 1
            pairs.extend([[base, base + 1], [base + 1, base + 2]])
            if row < 11:
                pairs.extend([[base, base + 3], [base + 1, base + 4], [base + 2, base + 5]])
        bets += [("split", "-".join(map(str, pair))) for pair in pairs]

        corners = []
        for row in range(11):
            base = row * 3 + 1
            corners.extend([[base, base + 1, base + 3, base + 4], [base + 1, base + 2, base + 4, base + 5]])
        bets += [("corner", "-".join(map(str, corner))) for corner in corners]

        outcome = describe_outcome(0)
        for bet_type, selection in bets:
            with self.subTest(bet_type=bet_type, selection=selection):
                evaluate_bet(bet_type, selection, 100, outcome)

    def test_duplicate_equivalent_bets_are_aggregated(self):
        evaluated = aggregate_roulette_bets(
            [
                request_bet("split", "1-2", "50.00"),
                request_bet("split", "2-1", "50.00"),
            ],
            describe_outcome(1),
        )

        self.assertEqual(len(evaluated), 1)
        self.assertEqual(evaluated[0].selection, "1-2")
        self.assertEqual(evaluated[0].amount_cents, 10_000)
        self.assertTrue(evaluated[0].won)

    def test_straight_payout_and_net_are_separate_values(self):
        evaluated = evaluate_bet("straight", "17", 500, describe_outcome(17))
        total_win_cents = evaluated.win_cents
        net_cents = total_win_cents - evaluated.amount_cents

        self.assertEqual(evaluated.payout, 35)
        self.assertEqual(total_win_cents, 18_000)
        self.assertEqual(net_cents, 17_500)

    def test_aggregated_position_can_exceed_chip_value_for_all_in(self):
        evaluated = aggregate_roulette_bets(
            [
                request_bet("straight", "17", "60.00"),
                request_bet("straight", "17", "50.00"),
            ],
            describe_outcome(17),
        )

        self.assertEqual(len(evaluated), 1)
        self.assertEqual(evaluated[0].amount_cents, 11_000)


if __name__ == "__main__":
    unittest.main()
