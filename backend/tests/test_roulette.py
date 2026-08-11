import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.core.roulette import (
    BLACK_NUMBERS,
    RED_NUMBERS,
    VALID_NUMBERS,
    describe_outcome,
    evaluate_bet,
    roulette_total_bet_limit_cents,
    spin_number,
)
from app.routers.games import aggregate_roulette_bets


def request_bet(bet_type: str, selection: str, amount: str = "1.00") -> SimpleNamespace:
    return SimpleNamespace(type=bet_type, selection=selection, amount=Decimal(amount))


class RouletteRulesTest(unittest.TestCase):
    @patch("app.core.roulette.randbelow", return_value=14)
    def test_spin_uses_independent_secure_draw(self, secure_draw):
        self.assertEqual(spin_number(), 14)
        secure_draw.assert_called_once_with(37)

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

    def test_colors_are_a_complete_standard_european_partition(self):
        self.assertFalse(RED_NUMBERS & BLACK_NUMBERS)
        self.assertEqual(RED_NUMBERS | BLACK_NUMBERS | {0}, VALID_NUMBERS)
        self.assertEqual(len(RED_NUMBERS), 18)
        self.assertEqual(len(BLACK_NUMBERS), 18)
        self.assertEqual(describe_outcome(0).color, "green")

    def test_every_standard_bet_has_european_roulette_return(self):
        # Across all 37 equally likely outcomes every standard bet returns
        # 36 stake units in total: an exact theoretical RTP of 36/37.
        bets = [
            ("straight", "17"),
            ("split", "17-20"),
            ("street", "6"),
            ("corner", "17-18-20-21"),
            ("six_line", "6"),
            ("dozen", "2"),
            ("column", "2"),
            ("color", "red"),
            ("parity", "even"),
            ("range", "high"),
        ]

        for bet_type, selection in bets:
            with self.subTest(bet_type=bet_type, selection=selection):
                total_return_cents = sum(
                    evaluate_bet(bet_type, selection, 100, describe_outcome(number)).win_cents
                    for number in range(37)
                )
                self.assertEqual(total_return_cents, 3_600)

    def test_zero_loses_every_even_money_bet(self):
        outcome = describe_outcome(0)
        for bet_type, selection in (
            ("color", "red"),
            ("color", "black"),
            ("parity", "even"),
            ("parity", "odd"),
            ("range", "low"),
            ("range", "high"),
        ):
            with self.subTest(bet_type=bet_type, selection=selection):
                self.assertFalse(evaluate_bet(bet_type, selection, 100, outcome).won)

    def test_total_bet_limit_follows_vip_tier_and_manager_override(self):
        self.assertEqual(roulette_total_bet_limit_cents("bronze"), 10_000)
        self.assertEqual(roulette_total_bet_limit_cents("silver"), 15_000)
        self.assertEqual(roulette_total_bet_limit_cents("gold"), 25_000)
        self.assertEqual(roulette_total_bet_limit_cents("platinum"), 50_000)
        self.assertEqual(roulette_total_bet_limit_cents("silver", 25_000), 25_000)
        self.assertEqual(roulette_total_bet_limit_cents("gold", 50_000), 50_000)

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
