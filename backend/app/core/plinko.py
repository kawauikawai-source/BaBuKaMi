from math import comb, floor
from random import SystemRandom


PLINKO_GAME_ID = "midnight-vault"
PLINKO_METHOD_ID = "midnight-vault"
PLINKO_TITLE = "Midnight Vault"
PLINKO_TITLE_KEY = "tx_midnight_vault_title"

ALLOWED_PLINKO_BET_CENTS = {500, 1_000, 2_500, 10_000}
ALLOWED_PLINKO_MODES = {"classic", "multi"}
ALLOWED_PLINKO_RISKS = {"low", "medium", "high"}
ALLOWED_PLINKO_ROWS = {8, 12, 16}
ALLOWED_PLINKO_MULTI_BALLS = {3, 5, 10}
TARGET_RTP_CENTS = 96

RNG = SystemRandom()


def _base_multiplier_cents(slot: int, rows: int, risk: str) -> int:
    center = rows / 2
    distance = abs(slot - center) / center if center else 0
    profiles = {
        "low": (42, 430, 2.0),
        "medium": (18, 1_850, 2.55),
        "high": (4, 9_200, 3.05),
    }
    min_cents, span_cents, power = profiles[risk]
    return min_cents + floor(span_cents * (distance**power))


def pocket_multipliers(rows: int, risk: str) -> list[int]:
    if rows not in ALLOWED_PLINKO_ROWS:
        raise ValueError("invalid_rows")
    if risk not in ALLOWED_PLINKO_RISKS:
        raise ValueError("invalid_risk")

    base = [_base_multiplier_cents(slot, rows, risk) for slot in range(rows + 1)]
    expected = sum((comb(rows, slot) / (2**rows)) * base[slot] for slot in range(rows + 1))
    scale = TARGET_RTP_CENTS / expected if expected else 1
    return [max(1, floor(value * scale)) for value in base]


def generate_path(rows: int) -> list[str]:
    return [RNG.choice(("L", "R")) for _ in range(rows)]


def split_bet_cents(total_bet_cents: int, ball_count: int) -> list[int]:
    base = total_bet_cents // ball_count
    remainder = total_bet_cents % ball_count
    return [base + (1 if index < remainder else 0) for index in range(ball_count)]


def drop_midnight_vault(bet_cents: int, mode: str, risk: str, rows: int, balls: int, *, validate_bet: bool = True) -> dict:
    if validate_bet and bet_cents not in ALLOWED_PLINKO_BET_CENTS:
        raise ValueError("invalid_bet")
    if mode not in ALLOWED_PLINKO_MODES:
        raise ValueError("invalid_mode")
    if rows not in ALLOWED_PLINKO_ROWS:
        raise ValueError("invalid_rows")
    if risk not in ALLOWED_PLINKO_RISKS:
        raise ValueError("invalid_risk")

    ball_count = 1 if mode == "classic" else int(balls)
    if mode == "multi" and ball_count not in ALLOWED_PLINKO_MULTI_BALLS:
        raise ValueError("invalid_balls")

    pockets = pocket_multipliers(rows, risk)
    ball_bets = split_bet_cents(bet_cents, ball_count)
    ball_results = []
    total_win_cents = 0

    for index, ball_bet_cents in enumerate(ball_bets, start=1):
        path = generate_path(rows)
        slot = path.count("R")
        multiplier_cents = pockets[slot]
        win_cents = ball_bet_cents * multiplier_cents // 100
        total_win_cents += win_cents
        ball_results.append(
            {
                "index": index,
                "bet_cents": ball_bet_cents,
                "path": path,
                "slot": slot,
                "multiplier_cents": multiplier_cents,
                "win_cents": win_cents,
            }
        )

    return {
        "mode": mode,
        "risk": risk,
        "rows": rows,
        "ball_count": ball_count,
        "pockets": pockets,
        "balls": ball_results,
        "total_bet_cents": bet_cents,
        "total_win_cents": total_win_cents,
        "net_cents": total_win_cents - bet_cents,
        "summary": {
            "mode": mode,
            "risk": risk,
            "rows": rows,
            "balls": ball_count,
            "best_multiplier_cents": max(ball["multiplier_cents"] for ball in ball_results),
        },
    }
