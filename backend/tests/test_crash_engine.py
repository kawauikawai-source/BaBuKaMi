import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.core import crash


class FakeCrashRng:
    def __init__(self, random_values, randint_value=117):
        self.random_values = list(random_values)
        self.randint_value = randint_value
        self.randint_args = None

    def random(self):
        return self.random_values.pop(0)

    def randint(self, start, end):
        self.randint_args = (start, end)
        return self.randint_value


class CrashEngineTest(unittest.TestCase):
    def test_crash_balance_constants_target_roughly_96_percent(self):
        self.assertEqual(crash.EARLY_CRASH_CHANCE, 0.03)
        self.assertEqual(crash.CRASH_HOUSE_FACTOR, 0.96)
        self.assertEqual(crash.LOW_CRASH_RELIEF_CHANCE, 0.05)

    def test_early_crash_uses_three_percent_branch(self):
        fake_rng = FakeCrashRng([0.019], randint_value=112)

        with patch.object(crash, "RNG", fake_rng):
            multiplier = crash.generate_crash_multiplier_cents()

        self.assertEqual(multiplier, 112)
        self.assertEqual(fake_rng.randint_args, (108, 128))

    def test_main_crash_formula_uses_raised_house_factor(self):
        fake_rng = FakeCrashRng([0.5, 0.48])

        with patch.object(crash, "RNG", fake_rng):
            multiplier = crash.generate_crash_multiplier_cents()

        self.assertEqual(multiplier, 200)

    def test_main_crash_formula_keeps_min_and_max_bounds(self):
        with patch.object(crash, "RNG", FakeCrashRng([0.5, 0.0001])):
            self.assertEqual(crash.generate_crash_multiplier_cents(), crash.MAX_CRASH_MULTIPLIER_CENTS)

        with patch.object(crash, "RNG", FakeCrashRng([0.5, 0.999, 0.99])):
            self.assertEqual(crash.generate_crash_multiplier_cents(), crash.MIN_CRASH_MULTIPLIER_CENTS)

    def test_low_crash_relief_softens_some_sub_one_point_five_results(self):
        fake_rng = FakeCrashRng([0.5, 0.9, 0.01], randint_value=168)

        with patch.object(crash, "RNG", fake_rng):
            multiplier = crash.generate_crash_multiplier_cents()

        self.assertEqual(multiplier, 168)
        self.assertEqual(fake_rng.randint_args, (150, 210))

    def test_live_multiplier_starts_below_cashout_threshold(self):
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        self.assertEqual(crash.current_multiplier_cents(started_at, started_at), 80)
        one_x_at = started_at + timedelta(seconds=crash.seconds_until_multiplier(100))
        self.assertEqual(crash.current_multiplier_cents(started_at, one_x_at), 100)


if __name__ == "__main__":
    unittest.main()
