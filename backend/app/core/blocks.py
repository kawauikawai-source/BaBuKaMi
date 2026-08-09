from decimal import Decimal
from random import SystemRandom


BLOCKS_GAME_ID = "neon-pyramids"
BLOCKS_METHOD_ID = "neon-pyramids"
BLOCKS_TITLE = "Neon Pyramids"
BLOCKS_TITLE_KEY = "tx_neon_pyramids_title"
ALLOWED_BLOCKS_BET_CENTS = {500, 1_000, 2_500, 10_000}
BOARD_WIDTH = 10
NEXT_QUEUE_SIZE = 5
DEFAULT_BLOCKS_DIFFICULTY = "level1"
ALLOWED_BLOCKS_DIFFICULTIES = {"level1", "level2", "level3"}
BLOCKS_DIFFICULTY_CONFIGS = {
    "level1": {
        "board_height": 15,
        "tick_ms": 650,
        "min_tick_ms": 360,
        "pressure_step_pieces": 8,
        "pressure_tick_drop_ms": 35,
        "starting_multiplier_cents": 10,
        "line_clear_bonus_cents": {1: 12, 2: 34, 3: 80, 4: 160},
        "combo_bonus_cap_cents": 20,
        "survival_bonus_cents": 2,
    },
    "level2": {
        "board_height": 15,
        "tick_ms": 520,
        "min_tick_ms": 300,
        "pressure_step_pieces": 7,
        "pressure_tick_drop_ms": 35,
        "starting_multiplier_cents": 25,
        "line_clear_bonus_cents": {1: 16, 2: 45, 3: 105, 4: 220},
        "combo_bonus_cap_cents": 30,
        "survival_bonus_cents": 3,
    },
    "level3": {
        "board_height": 15,
        "tick_ms": 430,
        "min_tick_ms": 240,
        "pressure_step_pieces": 6,
        "pressure_tick_drop_ms": 35,
        "starting_multiplier_cents": 40,
        "line_clear_bonus_cents": {1: 22, 2: 62, 3: 145, 4: 320},
        "combo_bonus_cap_cents": 45,
        "survival_bonus_cents": 5,
    },
}
BLOCKS_CASHOUT_MIN_MULTIPLIER_CENTS = 100

RNG = SystemRandom()

PIECE_TYPES = ("I", "J", "L", "O", "S", "T", "Z")
PIECE_SHAPES = {
    "I": (
        ((0, 0), (0, 1), (0, 2), (0, 3)),
        ((0, 0), (1, 0), (2, 0), (3, 0)),
        ((0, 0), (0, 1), (0, 2), (0, 3)),
        ((0, 0), (1, 0), (2, 0), (3, 0)),
    ),
    "J": (
        ((0, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (2, 0), (1, 1), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (2, 1)),
        ((1, 0), (1, 1), (0, 2), (1, 2)),
    ),
    "L": (
        ((2, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (1, 2), (2, 2)),
        ((0, 0), (1, 0), (2, 0), (0, 1)),
        ((0, 0), (1, 0), (1, 1), (1, 2)),
    ),
    "O": (
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
        ((0, 0), (1, 0), (0, 1), (1, 1)),
    ),
    "S": (
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
        ((1, 0), (2, 0), (0, 1), (1, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 2)),
    ),
    "T": (
        ((1, 0), (0, 1), (1, 1), (2, 1)),
        ((1, 0), (1, 1), (2, 1), (1, 2)),
        ((0, 0), (1, 0), (2, 0), (1, 1)),
        ((1, 0), (0, 1), (1, 1), (1, 2)),
    ),
    "Z": (
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((1, 0), (0, 1), (1, 1), (0, 2)),
        ((0, 0), (1, 0), (1, 1), (2, 1)),
        ((1, 0), (0, 1), (1, 1), (0, 2)),
    ),
}


def difficulty_config(difficulty: str | None) -> dict:
    return BLOCKS_DIFFICULTY_CONFIGS.get(str(difficulty or DEFAULT_BLOCKS_DIFFICULTY), BLOCKS_DIFFICULTY_CONFIGS[DEFAULT_BLOCKS_DIFFICULTY])


def board_height_for(difficulty: str | None) -> int:
    return int(difficulty_config(difficulty)["board_height"])


def starting_multiplier_cents_for(difficulty: str | None) -> int:
    return int(difficulty_config(difficulty)["starting_multiplier_cents"])


def pressure_level_for(difficulty: str | None, pieces_placed: int | None = 0) -> int:
    config = difficulty_config(difficulty)
    step = max(1, int(config["pressure_step_pieces"]))
    return max(0, int(pieces_placed or 0) // step)


def tick_ms_for(difficulty: str | None, pieces_placed: int | None = 0) -> int:
    config = difficulty_config(difficulty)
    base_tick = int(config["tick_ms"])
    min_tick = int(config["min_tick_ms"])
    pressure_level = pressure_level_for(difficulty, pieces_placed)
    return max(min_tick, base_tick - pressure_level * int(config["pressure_tick_drop_ms"]))


def empty_board(difficulty: str | None = None) -> list[list[str]]:
    return [["" for _ in range(BOARD_WIDTH)] for _ in range(board_height_for(difficulty))]


def normalize_board(board: list[list[str]] | None, difficulty: str | None = None) -> list[list[str]]:
    board_height = board_height_for(difficulty)
    if not isinstance(board, list):
        return empty_board(difficulty)
    normalized = []
    for row in board[-board_height:]:
        if not isinstance(row, list) or len(row) != BOARD_WIDTH:
            return empty_board(difficulty)
        normalized.append([str(cell) if str(cell) in PIECE_TYPES else "" for cell in row])
    while len(normalized) < board_height:
        normalized.insert(0, ["" for _ in range(BOARD_WIDTH)])
    return normalized


def generate_piece_queue(count: int = 14) -> list[str]:
    queue: list[str] = []
    while len(queue) < count:
        bag = list(PIECE_TYPES)
        RNG.shuffle(bag)
        queue.extend(bag)
    return queue[:count]


def ensure_queue(queue: list[str] | None, count: int = NEXT_QUEUE_SIZE + 2) -> list[str]:
    source = queue if isinstance(queue, list) else []
    next_queue = [piece for piece in source if piece in PIECE_TYPES]
    if len(next_queue) < count:
        next_queue.extend(generate_piece_queue(count - len(next_queue)))
    return next_queue


def shape_cells(piece_type: str, rotation: int) -> tuple[tuple[int, int], ...]:
    if piece_type not in PIECE_SHAPES:
        raise ValueError("Invalid blocks piece")
    cells = PIECE_SHAPES[piece_type][int(rotation) % 4]
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    return tuple((x - min_x, y - min_y) for x, y in cells)


def can_place(board: list[list[str]], piece_type: str, rotation: int, x: int, y: int) -> bool:
    board_height = len(board)
    for dx, dy in shape_cells(piece_type, rotation):
        px = x + dx
        py = y + dy
        if px < 0 or px >= BOARD_WIDTH or py < 0 or py >= board_height:
            return False
        if board[py][px]:
            return False
    return True


def has_valid_x(piece_type: str, rotation: int, x: int) -> bool:
    cells = shape_cells(piece_type, rotation)
    width = max(dx for dx, _ in cells) + 1
    return 0 <= int(x) <= BOARD_WIDTH - width


def hard_drop_y(board: list[list[str]], piece_type: str, rotation: int, x: int) -> int | None:
    y = 0
    if not can_place(board, piece_type, rotation, x, y):
        return None
    while can_place(board, piece_type, rotation, x, y + 1):
        y += 1
    return y


def can_place_anywhere(board: list[list[str]], piece_type: str) -> bool:
    for rotation in range(4):
        cells = shape_cells(piece_type, rotation)
        width = max(dx for dx, _ in cells) + 1
        for x in range(0, BOARD_WIDTH - width + 1):
            if hard_drop_y(board, piece_type, rotation, x) is not None:
                return True
    return False


def place_piece(board: list[list[str]], piece_type: str, rotation: int, x: int, difficulty: str | None = None) -> tuple[list[list[str]], int, int]:
    next_board = [row[:] for row in normalize_board(board, difficulty)]
    board_height = len(next_board)
    y = hard_drop_y(next_board, piece_type, rotation, x)
    if y is None:
        raise ValueError("Invalid blocks placement")
    for dx, dy in shape_cells(piece_type, rotation):
        next_board[y + dy][x + dx] = piece_type

    remaining_rows = [row for row in next_board if any(not cell for cell in row)]
    cleared = board_height - len(remaining_rows)
    for _ in range(cleared):
        remaining_rows.insert(0, ["" for _ in range(BOARD_WIDTH)])
    return remaining_rows, cleared, y


def place_piece_at_y(
    board: list[list[str]],
    piece_type: str,
    rotation: int,
    x: int,
    y: int,
    difficulty: str | None = None,
) -> tuple[list[list[str]], int, int]:
    next_board = [row[:] for row in normalize_board(board, difficulty)]
    drop_y = int(y)
    if not can_place(next_board, piece_type, rotation, x, drop_y):
        raise ValueError("Invalid blocks placement")
    if can_place(next_board, piece_type, rotation, x, drop_y + 1):
        raise ValueError("Blocks piece is not locked")

    board_height = len(next_board)
    for dx, dy in shape_cells(piece_type, rotation):
        next_board[drop_y + dy][x + dx] = piece_type

    remaining_rows = [row for row in next_board if any(not cell for cell in row)]
    cleared = board_height - len(remaining_rows)
    for _ in range(cleared):
        remaining_rows.insert(0, ["" for _ in range(BOARD_WIDTH)])
    return remaining_rows, cleared, drop_y


def multiplier_after_clear(current_multiplier_cents: int, cleared: int, combo: int, pieces_placed: int, difficulty: str | None = None) -> int:
    config = difficulty_config(difficulty)
    next_multiplier = max(int(config["starting_multiplier_cents"]), int(current_multiplier_cents))
    if cleared > 0:
        next_multiplier += config["line_clear_bonus_cents"].get(cleared, 0)
        if combo >= 2:
            next_multiplier += min((combo - 1) * 5, int(config["combo_bonus_cap_cents"]))
    if pieces_placed > 0 and pieces_placed % 10 == 0:
        next_multiplier += int(config["survival_bonus_cents"])
    return next_multiplier


def score_for_clear(cleared: int, combo: int, pieces_placed: int) -> int:
    if cleared <= 0:
        return 10
    line_score = {1: 120, 2: 340, 3: 760, 4: 1500}.get(cleared, 0)
    combo_score = max(combo - 1, 0) * 50
    survival_score = 40 if pieces_placed > 0 and pieces_placed % 10 == 0 else 0
    return line_score + combo_score + survival_score


def win_cents_for(bet_cents: int, multiplier_cents: int) -> int:
    return int(bet_cents) * int(multiplier_cents) // 100


def multiplier_amount(multiplier_cents: int) -> Decimal:
    return Decimal(int(multiplier_cents)) / Decimal(100)
