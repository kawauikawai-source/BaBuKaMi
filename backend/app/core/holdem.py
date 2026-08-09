from dataclasses import dataclass
from itertools import combinations
from random import SystemRandom


HOLDEM_GAME_ID = "texas-holdem"
HOLDEM_METHOD_ID = "texas-holdem"
HOLDEM_TITLE = "Texas Hold'em"
HOLDEM_TITLE_KEY = "tx_texas_holdem_title"
ALLOWED_HOLDEM_ANTE_CENTS = {500, 1_000, 2_500, 10_000}

RNG = SystemRandom()

SUITS = ("S", "H", "D", "C")
RANKS = tuple(range(2, 15))
RANK_LABELS = {
    14: "A",
    13: "K",
    12: "Q",
    11: "J",
    10: "T",
    9: "9",
    8: "8",
    7: "7",
    6: "6",
    5: "5",
    4: "4",
    3: "3",
    2: "2",
}
LABEL_RANKS = {value: key for key, value in RANK_LABELS.items()}
HAND_NAMES = {
    8: ("holdem_hand_straight_flush", "Straight flush"),
    7: ("holdem_hand_quads", "Four of a kind"),
    6: ("holdem_hand_full_house", "Full house"),
    5: ("holdem_hand_flush", "Flush"),
    4: ("holdem_hand_straight", "Straight"),
    3: ("holdem_hand_trips", "Three of a kind"),
    2: ("holdem_hand_two_pair", "Two pair"),
    1: ("holdem_hand_pair", "Pair"),
    0: ("holdem_hand_high_card", "High card"),
}


@dataclass(frozen=True)
class HandResult:
    category: int
    ranks: tuple[int, ...]
    cards: tuple[str, ...]

    @property
    def name_key(self) -> str:
        return HAND_NAMES[self.category][0]

    @property
    def name(self) -> str:
        return HAND_NAMES[self.category][1]

    @property
    def rank_value(self) -> tuple[int, ...]:
        return (self.category, *self.ranks)


def card_label(rank: int, suit: str) -> str:
    return f"{RANK_LABELS[int(rank)]}{suit}"


def parse_card(card: str) -> tuple[int, str]:
    value = str(card).strip().upper()
    if len(value) != 2 or value[0] not in LABEL_RANKS or value[1] not in SUITS:
        raise ValueError("Invalid Hold'em card")
    return LABEL_RANKS[value[0]], value[1]


def fresh_deck() -> list[str]:
    return [card_label(rank, suit) for suit in SUITS for rank in RANKS]


def shuffled_deck() -> list[str]:
    deck = fresh_deck()
    RNG.shuffle(deck)
    return deck


def straight_high(ranks: list[int]) -> int | None:
    unique = sorted(set(ranks), reverse=True)
    if 14 in unique:
        unique.append(1)
    for index in range(0, len(unique) - 4):
        window = unique[index : index + 5]
        if window[0] - window[4] == 4 and len(set(window)) == 5:
            return 5 if window[0] == 5 else window[0]
    return None


def evaluate_five(cards: tuple[str, ...]) -> tuple[int, tuple[int, ...]]:
    parsed = [parse_card(card) for card in cards]
    ranks = sorted((rank for rank, _ in parsed), reverse=True)
    suits = [suit for _, suit in parsed]
    counts = {rank: ranks.count(rank) for rank in set(ranks)}
    count_groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    is_flush = len(set(suits)) == 1
    straight = straight_high(ranks)

    if is_flush and straight:
        return 8, (straight,)
    if count_groups[0][1] == 4:
        quad = count_groups[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return 7, (quad, kicker)
    if count_groups[0][1] == 3 and count_groups[1][1] == 2:
        return 6, (count_groups[0][0], count_groups[1][0])
    if is_flush:
        return 5, tuple(ranks)
    if straight:
        return 4, (straight,)
    if count_groups[0][1] == 3:
        trip = count_groups[0][0]
        kickers = tuple(rank for rank in ranks if rank != trip)
        return 3, (trip, *kickers)
    pairs = [rank for rank, count in counts.items() if count == 2]
    if len(pairs) == 2:
        high_pair, low_pair = sorted(pairs, reverse=True)
        kicker = max(rank for rank in ranks if rank not in pairs)
        return 2, (high_pair, low_pair, kicker)
    if len(pairs) == 1:
        pair = pairs[0]
        kickers = tuple(rank for rank in ranks if rank != pair)
        return 1, (pair, *kickers)
    return 0, tuple(ranks)


def evaluate_best(cards: list[str]) -> HandResult:
    if len(cards) < 5:
        raise ValueError("Hold'em hand needs at least five cards")
    best_cards: tuple[str, ...] | None = None
    best_value: tuple[int, tuple[int, ...]] | None = None
    for combo in combinations(cards, 5):
        value = evaluate_five(tuple(combo))
        if best_value is None or (value[0], *value[1]) > (best_value[0], *best_value[1]):
            best_value = value
            best_cards = tuple(combo)
    assert best_value is not None and best_cards is not None
    return HandResult(category=best_value[0], ranks=best_value[1], cards=best_cards)


def compare_hands(player_cards: list[str], dealer_cards: list[str]) -> int:
    player = evaluate_best(player_cards)
    dealer = evaluate_best(dealer_cards)
    if player.rank_value > dealer.rank_value:
        return 1
    if player.rank_value < dealer.rank_value:
        return -1
    return 0


def dealer_qualifies(dealer_cards: list[str]) -> bool:
    hand = evaluate_best(dealer_cards)
    if hand.category > 1:
        return True
    if hand.category == 1:
        return hand.ranks[0] >= 4
    return False


def deal_holdem_round() -> dict:
    deck = shuffled_deck()
    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]
    community_cards = [deck.pop(), deck.pop(), deck.pop()]
    return {
        "deck": deck,
        "player_cards": player_cards,
        "dealer_cards": dealer_cards,
        "community_cards": community_cards,
    }


def complete_community_cards(result: dict) -> list[str]:
    deck = list(result.get("deck") or [])
    community = list(result.get("community_cards") or [])
    while len(community) < 5:
        if not deck:
            raise ValueError("Hold'em deck is empty")
        community.append(deck.pop())
    result["deck"] = deck
    result["community_cards"] = community
    return community


def public_hand(hand: HandResult) -> dict:
    return {
        "name": hand.name,
        "name_key": hand.name_key,
        "rank": hand.category,
        "cards": list(hand.cards),
    }
