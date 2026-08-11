from decimal import Decimal, ROUND_HALF_UP


DEPOSIT_MIN_CENTS = 2_000
CRYPTO_DEPOSIT_MIN_CENTS = 2_000
DEPOSIT_MAX_CENTS = 100_000
WITHDRAW_MIN_CENTS = 18_000
WITHDRAW_MAX_CENTS = 50_000
ADMIN_BALANCE_MAX_CENTS = 1_000_000

VIP_CASHIER_RULES = {
    "bronze": {
        "deposit_min_cents": 2_000,
        "deposit_max_cents": 100_000,
        "withdraw_min_cents": 18_000,
        "withdraw_max_cents": 50_000,
        "withdraw_fee_bps": 5_000,
        "withdraw_processing_hours": 24,
    },
    "silver": {
        "deposit_min_cents": 2_000,
        "deposit_max_cents": 150_000,
        "withdraw_min_cents": 15_000,
        "withdraw_max_cents": 75_000,
        "withdraw_fee_bps": 3_000,
        "withdraw_processing_hours": 12,
    },
    "gold": {
        "deposit_min_cents": 2_000,
        "deposit_max_cents": 250_000,
        "withdraw_min_cents": 10_000,
        "withdraw_max_cents": 150_000,
        "withdraw_fee_bps": 1_500,
        "withdraw_processing_hours": 4,
    },
    "platinum": {
        "deposit_min_cents": 2_000,
        "deposit_max_cents": 500_000,
        "withdraw_min_cents": 5_000,
        "withdraw_max_cents": 500_000,
        "withdraw_fee_bps": 500,
        "withdraw_processing_hours": 1,
    },
}

DEPOSIT_METHODS = {"card", "usdt", "promo", "kawaui-studio"}
CARD_DEPOSIT_METHODS = {"card"}
SUSPENDED_DEPOSIT_METHODS = {"usdt"}
WITHDRAW_METHODS = {"card", "usdt", "kawaui-studio"}
SUSPENDED_WITHDRAW_METHODS = {"card", "usdt"}
GAME_BET_LIMITS_CENTS = {
    "roulette": (100, 99_999_999),
    # Routes validate that values above the standard EUR 100 chip belong to
    # the current user's active Operator 08 preset.
    "lucky-bamboo": (500, 50_000),
    "midnight-vault": (500, 50_000),
    "solar-wilds": (500, 50_000),
    "neon-pyramids": (500, 50_000),
    "texas-holdem": (500, 50_000),
    "dragons-fortune": (500, 50_000),
    "arctic-protocol": (500, 50_000),
}


def amount_to_cents(amount: Decimal) -> int:
    return int((amount * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cashier_rules_for_tier(vip_tier: str | None) -> dict[str, int]:
    return VIP_CASHIER_RULES.get(str(vip_tier or "bronze").strip().lower(), VIP_CASHIER_RULES["bronze"])


def deposit_min_cents(method_id: str, vip_tier: str | None = None) -> int:
    rules = cashier_rules_for_tier(vip_tier)
    return rules["deposit_min_cents"] if method_id in CARD_DEPOSIT_METHODS else max(
        rules["deposit_min_cents"],
        CRYPTO_DEPOSIT_MIN_CENTS,
    )


def withdrawal_fee_cents(amount_cents: int, vip_tier: str | None) -> int:
    fee_bps = cashier_rules_for_tier(vip_tier)["withdraw_fee_bps"]
    return (amount_cents * fee_bps + 5_000) // 10_000


def cents_to_amount(cents: int) -> Decimal:
    return Decimal(cents) / Decimal(100)
