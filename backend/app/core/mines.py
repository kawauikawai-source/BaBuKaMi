from math import floor
from random import SystemRandom


MINES_GAME_ID = "solar-wilds"
MINES_METHOD_ID = "solar-wilds"
MINES_TITLE = "Eclipse Hunt"
MINES_TITLE_KEY = "tx_solar_wilds_title"
ALLOWED_MINES_BET_CENTS = {500, 1_000, 2_500, 10_000}
ALLOWED_MINE_COUNTS = {5, 7, 10, 12}
GRID_CELLS = 20
HOUSE_FACTOR = 0.96

RNG = SystemRandom()


def validate_cell(cell: int) -> int:
    value = int(cell)
    if value < 0 or value >= GRID_CELLS:
        raise ValueError("Invalid mines cell")
    return value


def generate_mines(mine_count: int) -> list[int]:
    if mine_count not in ALLOWED_MINE_COUNTS:
        raise ValueError("Invalid mines count")
    return sorted(RNG.sample(range(GRID_CELLS), mine_count))


def multiplier_cents(mine_count: int, safe_reveals: int) -> int:
    if mine_count not in ALLOWED_MINE_COUNTS:
        raise ValueError("Invalid mines count")
    if safe_reveals <= 0:
        return 100
    safe_cells = GRID_CELLS - mine_count
    if safe_reveals > safe_cells:
        raise ValueError("Invalid reveal count")

    survival_probability = 1.0
    for index in range(safe_reveals):
        survival_probability *= (GRID_CELLS - mine_count - index) / (GRID_CELLS - index)

    raw_multiplier = (1 / survival_probability) * HOUSE_FACTOR
    return max(100, floor(raw_multiplier * 100))


def win_cents_for(bet_cents: int, mine_count: int, safe_reveals: int) -> int:
    return bet_cents * multiplier_cents(mine_count, safe_reveals) // 100
