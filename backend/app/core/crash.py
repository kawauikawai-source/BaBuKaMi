from datetime import UTC, datetime
from math import exp, log
from random import SystemRandom


CRASH_GAME_ID = "dragons-fortune"
CRASH_METHOD_ID = "dragons-fortune"
CRASH_TITLE = "Kawaui Fortune"
CRASH_TITLE_KEY = "tx_dragons_fortune_title"
ALLOWED_CRASH_BET_CENTS = {500, 1_000, 2_500, 10_000}
MIN_CRASH_MULTIPLIER_CENTS = 105
MAX_CRASH_MULTIPLIER_CENTS = 5_000
START_CRASH_MULTIPLIER_CENTS = 80
CASHOUT_MIN_MULTIPLIER_CENTS = 100
GROWTH_SECONDS = 8.0
EARLY_CRASH_CHANCE = 0.03
# Kawaui Fortune uses demo comfort shaping: the main curve targets about 96%
# for normal cashout points. The tiny relief branch only softens a few harsh
# sub-1.50x crashes, so early cashout targets do not become positive EV.
CRASH_HOUSE_FACTOR = 0.96
LOW_CRASH_RELIEF_CHANCE = 0.05
LOW_CRASH_RELIEF_THRESHOLD_CENTS = 150
LOW_CRASH_RELIEF_MIN_CENTS = 150
LOW_CRASH_RELIEF_MAX_CENTS = 210
MIN_MAIN_CRASH_ROLL = CRASH_HOUSE_FACTOR / (MAX_CRASH_MULTIPLIER_CENTS / 100)

RNG = SystemRandom()


def utc_now() -> datetime:
    return datetime.now(UTC)


def multiplier_amount(multiplier_cents: int) -> str:
    return f"{multiplier_cents / 100:.2f}"


def generate_crash_multiplier_cents() -> int:
    if RNG.random() < EARLY_CRASH_CHANCE:
        return RNG.randint(108, 128)
    roll = max(MIN_MAIN_CRASH_ROLL, RNG.random())
    multiplier = int((CRASH_HOUSE_FACTOR / roll) * 100)
    multiplier = max(MIN_CRASH_MULTIPLIER_CENTS, min(MAX_CRASH_MULTIPLIER_CENTS, multiplier))
    if multiplier < LOW_CRASH_RELIEF_THRESHOLD_CENTS and RNG.random() < LOW_CRASH_RELIEF_CHANCE:
        return RNG.randint(LOW_CRASH_RELIEF_MIN_CENTS, LOW_CRASH_RELIEF_MAX_CENTS)
    return multiplier


def elapsed_seconds(started_at: datetime, now: datetime | None = None) -> float:
    current = now or utc_now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return max(0.0, (current - started_at).total_seconds())


def current_multiplier_cents(started_at: datetime, now: datetime | None = None) -> int:
    elapsed = elapsed_seconds(started_at, now)
    return max(START_CRASH_MULTIPLIER_CENTS, int(round(START_CRASH_MULTIPLIER_CENTS * exp(elapsed / GROWTH_SECONDS))))


def seconds_until_multiplier(multiplier_cents: int) -> float:
    if multiplier_cents <= START_CRASH_MULTIPLIER_CENTS:
        return 0.0
    return log(multiplier_cents / START_CRASH_MULTIPLIER_CENTS) * GROWTH_SECONDS
