from dataclasses import dataclass

from app.models import User


VIP_TIERS = ("bronze", "silver", "gold", "platinum")


@dataclass(frozen=True)
class VipTierRule:
    tier: str
    min_points: int
    max_points: int | None
    next_tier: str | None = None
    next_price_cents: int = 0
    purchase_threshold: int | None = None


VIP_RULES: dict[str, VipTierRule] = {
    "bronze": VipTierRule("bronze", 0, 999, "silver", 1_000, 999),
    "silver": VipTierRule("silver", 1_000, 4_999, "gold", 2_500, 4_999),
    "gold": VipTierRule("gold", 5_000, 19_999, "platinum", 5_000, 19_999),
    "platinum": VipTierRule("platinum", 20_000, None),
}


def normalize_vip_tier(value: str | None) -> str:
    tier = str(value or "").strip().lower()
    return tier if tier in VIP_RULES else "bronze"


def vip_rule(value: str | None) -> VipTierRule:
    return VIP_RULES[normalize_vip_tier(value)]


def vip_tier_index(value: str | None) -> int:
    return VIP_TIERS.index(normalize_vip_tier(value))


def next_vip_rule(value: str | None) -> VipTierRule | None:
    next_tier = vip_rule(value).next_tier
    return VIP_RULES[next_tier] if next_tier else None


def award_vip_bet_points(user: User, total_bet_cents: int) -> int:
    earned = max(0, int(total_bet_cents) // 100)
    if earned <= 0:
        return 0

    rule = vip_rule(user.vip_tier)
    before = int(user.vip_points or 0)
    if rule.max_points is None:
        after = before + earned
    elif before >= rule.max_points:
        after = before
    else:
        after = min(rule.max_points, before + earned)
    user.vip_points = after
    return max(0, after - before)
