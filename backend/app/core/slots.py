from dataclasses import dataclass
from random import SystemRandom


SLOT_GAME_ID = "lucky-bamboo"
SLOT_METHOD_ID = "lucky-bamboo"
SLOT_TITLE = "Lucky Bamboo"
SLOT_TITLE_KEY = "tx_lucky_bamboo_title"
ALLOWED_BET_CENTS = {500, 1_000, 2_500, 10_000}
REEL_COUNT = 5
ROW_COUNT = 3
LINE_COUNT = 10
PAYLINES = [
    [1, 1, 1, 1, 1],
    [0, 0, 0, 0, 0],
    [2, 2, 2, 2, 2],
    [0, 1, 2, 1, 0],
    [2, 1, 0, 1, 2],
    [0, 0, 1, 2, 2],
    [2, 2, 1, 0, 0],
    [1, 0, 0, 0, 1],
    [1, 2, 2, 2, 1],
    [0, 1, 1, 1, 2],
]


@dataclass(frozen=True)
class SlotSymbol:
    id: str
    label: str
    weight: int
    payouts: dict[int, int]


SYMBOLS = [
    SlotSymbol("bamboo", "Bamboo", 6, {3: 36, 4: 160, 5: 730}),
    SlotSymbol("panda", "Panda", 8, {3: 27, 4: 110, 5: 455}),
    SlotSymbol("coin", "Coin", 10, {3: 23, 4: 82, 5: 320}),
    SlotSymbol("lotus", "Lotus", 13, {3: 18, 4: 55, 5: 205}),
    SlotSymbol("lantern", "Lantern", 16, {3: 14, 4: 41, 5: 128}),
    SlotSymbol("jade", "Jade", 20, {3: 9, 4: 27, 5: 82}),
]

RNG = SystemRandom()


def spin_grid() -> list[list[str]]:
    population = [symbol.id for symbol in SYMBOLS]
    weights = [symbol.weight for symbol in SYMBOLS]
    reels = [RNG.choices(population, weights=weights, k=ROW_COUNT) for _ in range(REEL_COUNT)]
    return [[reels[reel][row] for reel in range(REEL_COUNT)] for row in range(ROW_COUNT)]


def symbol_by_id(symbol_id: str) -> SlotSymbol:
    for symbol in SYMBOLS:
        if symbol.id == symbol_id:
            return symbol
    raise ValueError("Invalid slot symbol")


def evaluate_grid(grid: list[list[str]], bet_cents: int) -> tuple[list[dict], int]:
    winning_lines = []
    total_win_cents = 0
    line_bet_cents = bet_cents // LINE_COUNT

    for index, line in enumerate(PAYLINES, start=1):
        first_symbol = grid[line[0]][0]
        match_count = 1
        for reel_index in range(1, REEL_COUNT):
            if grid[line[reel_index]][reel_index] != first_symbol:
                break
            match_count += 1

        if match_count < 3:
            continue

        symbol = symbol_by_id(first_symbol)
        multiplier = symbol.payouts.get(match_count, 0)
        if multiplier <= 0:
            continue

        win_cents = line_bet_cents * multiplier
        total_win_cents += win_cents
        winning_lines.append(
            {
                "line": index,
                "symbol": first_symbol,
                "count": match_count,
                "multiplier": multiplier,
                "win_cents": win_cents,
                "positions": [{"row": line[reel], "reel": reel} for reel in range(match_count)],
            }
        )

    return winning_lines, total_win_cents


def spin_lucky_bamboo(bet_cents: int, *, validate_bet: bool = True) -> dict:
    if validate_bet and bet_cents not in ALLOWED_BET_CENTS:
        raise ValueError("Invalid slot bet")

    grid = spin_grid()
    winning_lines, total_win_cents = evaluate_grid(grid, bet_cents)
    return {
        "grid": grid,
        "winning_lines": winning_lines,
        "total_bet_cents": bet_cents,
        "total_win_cents": total_win_cents,
        "net_cents": total_win_cents - bet_cents,
        "summary": {
            "winning_lines": len(winning_lines),
            "best_symbol": winning_lines[0]["symbol"] if winning_lines else "",
        },
    }
