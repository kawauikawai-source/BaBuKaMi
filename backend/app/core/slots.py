from dataclasses import dataclass
from random import SystemRandom


SLOT_GAME_ID = "lucky-bamboo"
SLOT_METHOD_ID = "lucky-bamboo"
SLOT_TITLE = "Lucky Bamboo"
SLOT_TITLE_KEY = "tx_lucky_bamboo_title"
ALLOWED_BET_CENTS = {500, 1_000, 2_500, 10_000}
REEL_COUNT = 5
ROW_COUNT = 3
LINE_COUNT = 5
PAYLINES = [
    [0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1],
    [2, 2, 2, 2, 2],
    [0, 1, 2, 1, 0],
    [2, 1, 0, 1, 2],
]


@dataclass(frozen=True)
class SlotSymbol:
    id: str
    label: str
    weight: int
    payouts: dict[int, int]


SYMBOLS = [
    SlotSymbol("bamboo", "Bamboo", 6, {3: 16, 4: 76, 5: 348}),
    SlotSymbol("panda", "Panda", 8, {3: 13, 4: 48, 5: 217}),
    SlotSymbol("coin", "Coin", 10, {3: 11, 4: 39, 5: 153}),
    SlotSymbol("lotus", "Lotus", 13, {3: 9, 4: 26, 5: 98}),
    SlotSymbol("lantern", "Lantern", 16, {3: 7, 4: 20, 5: 61}),
    SlotSymbol("jade", "Jade", 20, {3: 4, 4: 13, 5: 39}),
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
    if len(grid) != ROW_COUNT or any(len(row) != REEL_COUNT for row in grid):
        raise ValueError("Invalid slot grid")

    winning_lines = []
    total_win_cents = 0

    for line_index, payline in enumerate(PAYLINES):
        line_symbols = [grid[row_index][reel_index] for reel_index, row_index in enumerate(payline)]
        reel_index = 0
        while reel_index < REEL_COUNT:
            run_end = reel_index + 1
            while run_end < REEL_COUNT and line_symbols[run_end] == line_symbols[reel_index]:
                run_end += 1
            match_count = run_end - reel_index
            if match_count >= 3:
                symbol = symbol_by_id(line_symbols[reel_index])
                multiplier = symbol.payouts.get(match_count, 0)
                if multiplier > 0:
                    win_cents = bet_cents * multiplier // LINE_COUNT
                    total_win_cents += win_cents
                    winning_lines.append(
                        {
                            "line": line_index + 1,
                            "symbol": symbol.id,
                            "count": match_count,
                            "multiplier": multiplier,
                            "win_cents": win_cents,
                            "positions": [
                                {"row": payline[reel], "reel": reel}
                                for reel in range(reel_index, run_end)
                            ],
                        }
                    )
            reel_index = run_end

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
