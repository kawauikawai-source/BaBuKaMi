from dataclasses import dataclass
from secrets import randbelow


RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}
VALID_NUMBERS = set(range(37))
BET_PAYOUTS = {
    "straight": 35,
    "split": 17,
    "street": 11,
    "corner": 8,
    "six_line": 5,
    "dozen": 2,
    "column": 2,
    "color": 1,
    "parity": 1,
    "range": 1,
}

@dataclass(frozen=True)
class RouletteOutcome:
    number: int
    color: str
    parity: str
    range: str
    dozen: str
    column: str


@dataclass(frozen=True)
class EvaluatedBet:
    type: str
    selection: str
    amount_cents: int
    win_cents: int
    payout: int
    won: bool


def spin_number() -> int:
    # Every spin is an independent draw from the operating system CSPRNG.
    return randbelow(37)


def describe_outcome(number: int) -> RouletteOutcome:
    if number not in VALID_NUMBERS:
        raise ValueError("Invalid roulette number")

    color = "green" if number == 0 else "red" if number in RED_NUMBERS else "black"
    parity = "zero" if number == 0 else "even" if number % 2 == 0 else "odd"
    number_range = "zero" if number == 0 else "low" if number <= 18 else "high"
    dozen = "zero" if number == 0 else str(((number - 1) // 12) + 1)
    column = "zero" if number == 0 else str(((number - 1) % 3) + 1)
    return RouletteOutcome(number=number, color=color, parity=parity, range=number_range, dozen=dozen, column=column)


def normalize_bet_type(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def parse_numbers(selection: str) -> list[int]:
    parts = [part.strip() for part in selection.replace(",", "-").split("-") if part.strip()]
    if not parts:
        raise ValueError("Invalid roulette selection")
    numbers = [int(part) for part in parts]
    if any(number not in VALID_NUMBERS for number in numbers):
        raise ValueError("Invalid roulette selection")
    return numbers


def street_numbers(row: int) -> set[int]:
    start = ((row - 1) * 3) + 1
    return {start, start + 1, start + 2}


def six_line_numbers(row: int) -> set[int]:
    return street_numbers(row) | street_numbers(row + 1)


def validate_number_group(numbers: list[int], expected_size: int) -> set[int]:
    unique = set(numbers)
    if len(numbers) != expected_size or len(unique) != expected_size:
        raise ValueError("Invalid roulette selection")
    return unique


def covered_numbers(bet_type: str, selection: str) -> set[int]:
    value = selection.strip().lower()

    if bet_type == "straight":
        return validate_number_group(parse_numbers(value), 1)

    if bet_type == "split":
        numbers = validate_number_group(parse_numbers(value), 2)
        a, b = sorted(numbers)
        same_row = (a - 1) // 3 == (b - 1) // 3 and abs(a - b) == 1 and a != 0
        same_column = a != 0 and b != 0 and abs(a - b) == 3
        zero_split = numbers in ({0, 1}, {0, 2}, {0, 3})
        if not (same_row or same_column or zero_split):
            raise ValueError("Invalid roulette selection")
        return numbers

    if bet_type == "street":
        row = int(value)
        if row < 1 or row > 12:
            raise ValueError("Invalid roulette selection")
        return street_numbers(row)

    if bet_type == "corner":
        numbers = validate_number_group(parse_numbers(value), 4)
        a = min(numbers)
        if a < 1 or a > 32 or a % 3 == 0:
            raise ValueError("Invalid roulette selection")
        valid = {a, a + 1, a + 3, a + 4}
        if numbers != valid:
            raise ValueError("Invalid roulette selection")
        return numbers

    if bet_type == "six_line":
        row = int(value)
        if row < 1 or row > 11:
            raise ValueError("Invalid roulette selection")
        return six_line_numbers(row)

    if bet_type == "dozen":
        if value not in {"1", "2", "3"}:
            raise ValueError("Invalid roulette selection")
        start = ((int(value) - 1) * 12) + 1
        return set(range(start, start + 12))

    if bet_type == "column":
        if value not in {"1", "2", "3"}:
            raise ValueError("Invalid roulette selection")
        column = int(value)
        return {number for number in range(1, 37) if ((number - 1) % 3) + 1 == column}

    if bet_type == "color":
        if value == "red":
            return set(RED_NUMBERS)
        if value == "black":
            return set(BLACK_NUMBERS)
        raise ValueError("Invalid roulette selection")

    if bet_type == "parity":
        if value == "even":
            return {number for number in range(1, 37) if number % 2 == 0}
        if value == "odd":
            return {number for number in range(1, 37) if number % 2 == 1}
        raise ValueError("Invalid roulette selection")

    if bet_type == "range":
        if value == "low":
            return set(range(1, 19))
        if value == "high":
            return set(range(19, 37))
        raise ValueError("Invalid roulette selection")

    raise ValueError("Invalid roulette bet type")


def evaluate_bet(bet_type: str, selection: str, amount_cents: int, outcome: RouletteOutcome) -> EvaluatedBet:
    normalized_type = normalize_bet_type(bet_type)
    if normalized_type not in BET_PAYOUTS:
        raise ValueError("Invalid roulette bet type")

    covered = covered_numbers(normalized_type, selection)
    payout = BET_PAYOUTS[normalized_type]
    won = outcome.number in covered
    win_cents = amount_cents * (payout + 1) if won else 0
    return EvaluatedBet(
        type=normalized_type,
        selection=selection.strip().lower(),
        amount_cents=amount_cents,
        win_cents=win_cents,
        payout=payout,
        won=won,
    )
