import json
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import api_error
from app.core.money import cashier_rules_for_tier
from app.core.vip import normalize_vip_tier, vip_tier_index
from app.models import (
    GameRound,
    ManagerAction,
    ManagerBetPreset,
    ManagerMessage,
    ManagerTicket,
    Transaction,
    User,
)
from app.schemas import (
    GameControlResponse,
    ManagerActionPublic,
    ManagerBetPresetPublic,
    ManagerMessagePublic,
    ManagerStateResponse,
    ManagerTicketPublic,
)
from app.services.game_control import as_utc, get_or_create_settings, pause_until, utc_now


MANAGER_TIERS = {
    "silver": {"max_bet_cents": 15_000, "max_games": 1, "exception_cap_cents": 25_000},
    "gold": {"max_bet_cents": 25_000, "max_games": 2, "exception_cap_cents": 50_000},
    "platinum": {"max_bet_cents": 50_000, "max_games": 4, "exception_cap_cents": 50_000},
}
MANAGER_GAME_IDS = {
    "dragons-fortune",
    "lucky-bamboo",
    "solar-wilds",
    "neon-pyramids",
    "midnight-vault",
    "texas-holdem",
    "arctic-protocol",
    "roulette",
}
GAME_ALIASES = {
    "dragons-fortune": ("kawaui", "кавай", "fortune", "удач"),
    "lucky-bamboo": ("bamboo", "бамбук"),
    "solar-wilds": ("eclipse", "затмен", "охота"),
    "neon-pyramids": ("pyramid", "пирамид", "тетрис"),
    "midnight-vault": ("vault", "хранилищ", "plinko", "плинко"),
    "texas-holdem": ("texas", "holdem", "покер", "техас"),
    "arctic-protocol": ("arctic", "protocol", "арктич", "протокол"),
    "roulette": ("roulette", "рулет"),
}


def parse_json(value: str, fallback: dict | None = None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else (fallback or {})
    except (TypeError, ValueError):
        return fallback or {}


def require_manager_access(user: User) -> dict[str, int]:
    tier = normalize_vip_tier(user.vip_tier)
    rules = MANAGER_TIERS.get(tier)
    if rules is None or vip_tier_index(tier) < vip_tier_index("silver"):
        raise api_error("err_manager_vip_required", status_code=403)
    return rules


def message_public(message: ManagerMessage) -> ManagerMessagePublic:
    return ManagerMessagePublic(
        id=message.id,
        role=message.role,
        language=message.language,
        intent=message.intent,
        text=message.text,
        metadata=parse_json(message.metadata_json),
        is_unread=message.role == "admin" and message.read_at is None,
        created_at=message.created_at,
    )


def action_public(action: ManagerAction) -> ManagerActionPublic:
    return ManagerActionPublic(
        id=action.id,
        kind=action.kind,
        status=action.status,
        payload=parse_json(action.payload_json),
        expires_at=action.expires_at,
        created_at=action.created_at,
    )


def ticket_public(ticket: ManagerTicket, user: User | None = None) -> ManagerTicketPublic:
    owner = user or ticket.user
    return ManagerTicketPublic(
        id=ticket.id,
        category=ticket.category,
        status=ticket.status,
        subject=ticket.subject,
        payload=parse_json(ticket.payload_json),
        admin_response=ticket.admin_response,
        user_id=ticket.user_id,
        user_name=owner.name if owner else "",
        user_email=owner.email if owner else "",
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
    )


def active_presets(db: Session, user_id: int) -> list[ManagerBetPreset]:
    now = utc_now()
    return list(
        db.scalars(
            select(ManagerBetPreset)
            .where(
                ManagerBetPreset.user_id == user_id,
                (ManagerBetPreset.expires_at.is_(None)) | (ManagerBetPreset.expires_at > now),
            )
            .order_by(ManagerBetPreset.game_id)
        ).all()
    )


def effective_custom_bet_cents(db: Session, user_id: int, game_id: str) -> int | None:
    preset = db.scalar(
        select(ManagerBetPreset).where(
            ManagerBetPreset.user_id == user_id,
            ManagerBetPreset.game_id == game_id,
        )
    )
    if not preset:
        return None
    expires = as_utc(preset.expires_at)
    if expires and expires <= utc_now():
        db.delete(preset)
        db.flush()
        return None
    return int(preset.bet_cents)


def is_allowed_manager_bet(db: Session, user: User, game_id: str, bet_cents: int, base_bets: set[int]) -> bool:
    if bet_cents in base_bets:
        return True
    return effective_custom_bet_cents(db, user.id, game_id) == bet_cents


def game_control_response(db: Session, user_id: int) -> GameControlResponse:
    settings = get_or_create_settings(db, user_id)
    now = utc_now()
    paused = as_utc(settings.paused_until)
    limit = settings.daily_bet_limit_cents
    spent = int(settings.daily_bet_spent_cents or 0)
    return GameControlResponse(
        daily_bet_limit_cents=limit,
        daily_bet_spent_cents=spent,
        daily_bet_remaining_cents=None if limit is None else max(limit - spent, 0),
        reminder_minutes=settings.reminder_minutes,
        paused_until=paused,
        is_paused=bool(paused and paused > now),
        server_time=now,
    )


def manager_state(db: Session, user: User) -> ManagerStateResponse:
    rules = require_manager_access(user)
    presets = active_presets(db, user.id)
    unread = db.scalar(
        select(func.count(ManagerMessage.id)).where(
            ManagerMessage.user_id == user.id,
            ManagerMessage.role == "admin",
            ManagerMessage.read_at.is_(None),
        )
    ) or 0
    pending_withdrawals = db.scalar(
        select(func.count(Transaction.id)).where(
            Transaction.user_id == user.id,
            Transaction.type == "withdraw",
            Transaction.status == "pending",
        )
    ) or 0
    active_rounds = db.scalar(
        select(func.count(GameRound.id)).where(GameRound.user_id == user.id, GameRound.status == "active")
    ) or 0
    open_tickets = db.scalar(
        select(func.count(ManagerTicket.id)).where(
            ManagerTicket.user_id == user.id,
            ManagerTicket.status.in_(("open", "in_progress")),
        )
    ) or 0
    return ManagerStateResponse(
        line_status="online",
        vip_tier=normalize_vip_tier(user.vip_tier),
        max_bet_cents=rules["max_bet_cents"],
        max_games=rules["max_games"],
        unread_count=int(unread),
        balance_cents=user.balance_cents,
        vip_points=user.vip_points,
        pending_withdrawals=int(pending_withdrawals),
        active_rounds=int(active_rounds),
        cashier_rules=cashier_rules_for_tier(user.vip_tier),
        game_control=game_control_response(db, user.id),
        bet_presets=[
            ManagerBetPresetPublic(
                game_id=item.game_id,
                bet_cents=item.bet_cents,
                source=item.source,
                expires_at=item.expires_at,
            )
            for item in presets
        ],
        open_tickets=int(open_tickets),
    )


def add_message(
    db: Session,
    user: User,
    *,
    role: str,
    language: str,
    intent: str,
    text: str,
    metadata: dict | None = None,
) -> ManagerMessage:
    message = ManagerMessage(
        user_id=user.id,
        role=role,
        language="en" if language == "en" else "ru",
        intent=intent,
        text=text.strip()[:2000],
        metadata_json=json.dumps(metadata or {}, separators=(",", ":"), default=str),
    )
    db.add(message)
    db.flush()
    return message


def create_action(db: Session, user: User, kind: str, payload: dict) -> ManagerAction:
    action = ManagerAction(
        user_id=user.id,
        kind=kind,
        payload_json=json.dumps(payload, separators=(",", ":"), default=str),
        status="pending",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db.add(action)
    db.flush()
    return action


def create_ticket(db: Session, user: User, category: str, subject: str, payload: dict) -> ManagerTicket:
    ticket = ManagerTicket(
        user_id=user.id,
        category=category,
        status="open",
        subject=subject[:255],
        payload_json=json.dumps(payload, separators=(",", ":"), default=str),
    )
    db.add(ticket)
    db.flush()
    return ticket


def detect_game(text: str, payload: dict) -> str | None:
    requested = str(payload.get("game_id") or "").strip().lower()
    if requested in MANAGER_GAME_IDS:
        return requested
    lowered = text.lower()
    for game_id, aliases in GAME_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return game_id
    return None


def detect_amount_cents(text: str, payload: dict) -> int | None:
    if payload.get("amount_cents") is not None:
        try:
            return int(payload["amount_cents"])
        except (TypeError, ValueError):
            return None
    matches = re.findall(r"(?<!\d)(\d{3,4})(?:[.,]\d{1,2})?\s*(?:€|eur|евро)?", text.lower())
    return int(matches[-1]) * 100 if matches else None


def infer_intent(text: str, explicit: str | None) -> str:
    if explicit:
        return explicit.strip().lower()[:64]
    lowered = text.lower()
    if any(word in lowered for word in ("ставк", "bet", "chip", "фишк", "номинал")):
        return "bets"
    if any(word in lowered for word in ("пауз", "лимит", "напомин", "pause", "limit", "remind")):
        return "control"
    if any(word in lowered for word in ("завис", "раунд", "round", "stuck", "игр", "game")):
        return "games"
    if any(word in lowered for word in ("вывод", "депозит", "касс", "промокод", "withdraw", "deposit", "fee", "promo")):
        return "cashier"
    if any(word in lowered for word in ("заяв", "ticket", "support")):
        return "tickets"
    if any(word in lowered for word in ("баланс", "vip", "аккаунт", "balance", "account")):
        return "account"
    return "general"


def localized(language: str, ru: str, en: str) -> str:
    return en if language == "en" else ru


def build_reply(
    db: Session,
    user: User,
    *,
    text: str,
    language: str,
    explicit_intent: str | None,
    payload: dict,
) -> tuple[str, str, ManagerAction | None, ManagerTicket | None]:
    rules = require_manager_access(user)
    intent = infer_intent(text, explicit_intent)
    action = None
    ticket = None

    if intent in {"set_bet", "bets"}:
        game_id = detect_game(text, payload)
        amount_cents = detect_amount_cents(text, payload)
        reset = bool(payload.get("reset")) or any(word in text.lower() for word in ("сброс", "reset", "верни 100"))
        if not game_id:
            return intent, localized(language, "Назовите игру. Начальство требует точный адрес даже для хороших идей.", "Name the game. Management requires an exact address even for good ideas."), None, None
        if reset:
            action = create_action(db, user, "bet_reset", {"game_id": game_id})
            return intent, localized(language, "Подготовил возврат стандартной фишки €100. Нужна ваша подпись.", "I prepared a return to the standard €100 chip. Your confirmation is required."), action, None
        if amount_cents is None:
            return intent, localized(language, "Укажите номинал больше €100 и кратный €5.", "Enter an amount above €100 in €5 increments."), None, None
        if amount_cents <= 10_000 or amount_cents % 500:
            return intent, localized(language, "Такой номинал терминал не примет: нужно больше €100 и шаг €5.", "The terminal will not accept that amount: it must exceed €100 in €5 increments."), None, None
        if amount_cents > rules["exception_cap_cents"]:
            return intent, localized(language, "Даже начальство не имеет такого рычага. Абсолютный предел — €500.", "Even management does not have that lever. The absolute limit is €500."), None, None
        if amount_cents > rules["max_bet_cents"]:
            subject = localized(language, f"Запрос ставки €{amount_cents // 100} для {game_id}", f"€{amount_cents // 100} bet request for {game_id}")
            ticket = create_ticket(db, user, "bet_exception", subject, {"game_id": game_id, "bet_cents": amount_cents})
            return intent, localized(language, "Моих прав недостаточно. Передал наверх; если Кавай не уснул на папке, ответ придёт сюда.", "My clearance is insufficient. I escalated it; if Kawaui does not fall asleep on the file, the reply will appear here."), None, ticket
        action = create_action(db, user, "bet_set", {"game_id": game_id, "bet_cents": amount_cents})
        return intent, localized(language, f"Готов заменить фишку €100 на €{amount_cents // 100} в этой игре. Изменение коснётся только новых раундов.", f"Ready to replace the €100 chip with €{amount_cents // 100} for this game. Only new rounds are affected."), action, None

    if intent == "control":
        lowered = text.lower()
        kind = str(payload.get("kind") or "")
        if kind == "pause" or any(word in lowered for word in ("пауз", "pause")):
            duration = int(payload.get("duration_minutes") or (60 if "60" in lowered or "час" in lowered else 15))
            duration = duration if duration in {15, 60, 1440} else 15
            action = create_action(db, user, "control_pause", {"duration_minutes": duration})
            return intent, localized(language, f"Пауза на {duration} минут закроет новые ставки. Активный раунд можно завершить.", f"A {duration}-minute pause blocks new bets. You may finish an active round."), action, None
        if kind == "reminder" or any(word in lowered for word in ("напомин", "remind")):
            minutes = int(payload.get("reminder_minutes") or 30)
            if minutes not in {0, 15, 30, 60}:
                minutes = 30
            action = create_action(db, user, "control_reminder", {"reminder_minutes": minutes})
            return intent, localized(language, f"Напоминание будет появляться каждые {minutes} минут.", f"The reminder will appear every {minutes} minutes."), action, None
        amount = payload.get("daily_bet_limit_cents")
        if amount is not None:
            amount = int(amount)
            current = get_or_create_settings(db, user.id).daily_bet_limit_cents
            action = create_action(db, user, "control_daily_limit", {
                "daily_bet_limit_cents": amount,
                "raising": current is not None and amount > current,
            })
            warning = localized(language, " Повышение лимита увеличивает возможные потери.", " Raising the limit increases potential losses.") if current is not None and amount > current else ""
            return intent, localized(language, f"Подготовил дневной лимит €{amount / 100:.2f}.", f"Prepared a daily limit of €{amount / 100:.2f}.") + warning, action, None
        return intent, localized(language, "Могу поставить паузу, изменить напоминание или дневной лимит. Начальство просит формулировать одно действие за раз.", "I can set a pause, reminder, or daily limit. Management asks for one action at a time."), None, None

    if intent == "games":
        rules_requested = any(word in text.lower() for word in ("правил", "как играть", "rules", "how to play"))
        game_id = detect_game(text, payload)
        if rules_requested:
            rules_text = {
                "dragons-fortune": ("Множитель начинается с 0.80x и растёт до серверного падения. CASHOUT фиксирует текущую выплату; после падения ставка сгорает.", "The multiplier starts at 0.80x and grows until the server crash. CASHOUT locks the current payout; after the crash the bet is lost."),
                "lucky-bamboo": ("Сервер собирает сетку 5x3 и оплачивает совпавшие линии. Одна ставка запускает один завершённый спин.", "The server builds a 5x3 grid and pays matching lines. One bet starts one completed spin."),
                "solar-wilds": ("Открывайте безопасные солнца и забирайте растущий множитель до встречи с затмением.", "Reveal safe suns and cash out the growing multiplier before hitting an eclipse."),
                "neon-pyramids": ("Ставка запускает активный раунд. Собирайте линии, доведите множитель до 1.00x и заберите выплату до перегрузки стакана.", "A bet starts an active round. Clear lines, reach 1.00x, and cash out before the board tops out."),
                "midnight-vault": ("Сервер заранее определяет путь и карман каждого шара. Итоговая выплата равна сумме множителей упавших шаров.", "The server determines every ball path and pocket. The final payout is the sum of the landed multipliers."),
                "texas-holdem": ("Ante открывает две карты и flop. CALL добавляет 2x ante и ведёт к сравнению рук; FOLD завершает раунд потерей ante.", "The ante reveals two cards and the flop. CALL adds 2x ante and reaches showdown; FOLD ends the round and loses the ante."),
                "arctic-protocol": ("Пройдите шесть серверных ситуаций. Ошибка или тайм-аут сжигают ставку, шесть верных решений выплачивают 6.00x.", "Survive six server scenarios. A wrong answer or timeout loses the bet; six correct decisions pay 6.00x."),
                "roulette": ("Поставьте фишки на число, цвет или группу. Европейское колесо содержит один zero, а сервер рассчитывает каждую ставку отдельно.", "Place chips on a number, color, or group. The European wheel has one zero and the server settles each bet independently."),
            }
            if game_id in rules_text:
                return intent, localized(language, *rules_text[game_id]), None, None
            return intent, localized(language, "Назовите игру, и я открою её короткий протокол. Полный устав всё ещё лежит под подписью Кавая.", "Name the game and I will open its short protocol. The full rulebook is still under Kawaui's signature."), None, None
        active = list(db.scalars(select(GameRound).where(GameRound.user_id == user.id, GameRound.status == "active")).all())
        if active and any(word in text.lower() for word in ("завис", "stuck", "восстанов")):
            ids = [item.id for item in active]
            ticket = create_ticket(db, user, "technical", localized(language, "Проверка активного раунда", "Active round inspection"), {"round_ids": ids})
            return intent, localized(language, f"Нашёл активных сессий: {len(ids)}. Создал техническую заявку без вмешательства в результат.", f"Active sessions found: {len(ids)}. I created a technical ticket without altering any result."), None, ticket
        recent = list(
            db.scalars(
                select(GameRound)
                .where(GameRound.user_id == user.id)
                .order_by(GameRound.created_at.desc(), GameRound.id.desc())
                .limit(3)
            ).all()
        )
        recent_text = ", ".join(f"{item.game_id}: {item.status}" for item in recent) or localized(language, "нет", "none")
        return intent, localized(
            language,
            f"Активных сессий: {len(active)}. Последние раунды: {recent_text}. Результаты и RTP я не переписываю — этот ключ Кавай носит с собой.",
            f"Active sessions: {len(active)}. Recent rounds: {recent_text}. I cannot rewrite outcomes or RTP; Kawaui carries that key.",
        ), None, None

    if intent == "cashier":
        cash = cashier_rules_for_tier(user.vip_tier)
        pending = db.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user.id, Transaction.type == "withdraw", Transaction.status == "pending")) or 0
        return intent, localized(
            language,
            f"Ваш лимит депозита: €{cash['deposit_min_cents']//100}–€{cash['deposit_max_cents']//100}. Вывод: €{cash['withdraw_min_cents']//100}–€{cash['withdraw_max_cents']//100}, комиссия {cash['withdraw_fee_bps']/100:.0f}%. Ожидающих выводов: {pending}. Промокоды проверяются кассой до начисления; обходить срок и лимит мне запрещено.",
            f"Your deposit range is €{cash['deposit_min_cents']//100}–€{cash['deposit_max_cents']//100}. Withdrawal: €{cash['withdraw_min_cents']//100}–€{cash['withdraw_max_cents']//100}, fee {cash['withdraw_fee_bps']/100:.0f}%. Pending withdrawals: {pending}. Cashier validates promos before credit; I cannot bypass dates or limits.",
        ), None, None

    if intent == "tickets":
        count = db.scalar(select(func.count(ManagerTicket.id)).where(ManagerTicket.user_id == user.id, ManagerTicket.status.in_(("open", "in_progress")))) or 0
        return intent, localized(language, f"Открытых заявок: {count}. Ответ начальства появится в этом канале.", f"Open tickets: {count}. Management replies will appear in this channel."), None, None

    if intent == "account":
        return intent, localized(language, f"Баланс €{user.balance_cents/100:.2f}, статус {normalize_vip_tier(user.vip_tier).title()}, VIP-очки {user.vip_points}. Всё совпадает, что для этого дома уже достижение.", f"Balance €{user.balance_cents/100:.2f}, status {normalize_vip_tier(user.vip_tier).title()}, VIP points {user.vip_points}. Everything matches, which is already an achievement in this house."), None, None

    return intent, localized(language, "На линии Оператор 08. Могу проверить аккаунт, ставки, Контроль игры, игровые сессии, кассу и заявки.", "Operator 08 on the line. I can inspect your account, bets, Game Control, sessions, cashier, and tickets."), None, None


def execute_action(db: Session, user: User, action: ManagerAction) -> dict:
    if action.user_id != user.id:
        raise api_error("err_manager_action_not_found", status_code=404)
    if action.status != "pending":
        raise api_error("err_manager_action_settled", status_code=409)
    if as_utc(action.expires_at) <= utc_now():
        action.status = "expired"
        db.add(action)
        db.flush()
        raise api_error("err_manager_action_expired", status_code=409)

    rules = require_manager_access(user)
    payload = parse_json(action.payload_json)
    if action.kind == "bet_set":
        game_id = str(payload.get("game_id") or "")
        bet_cents = int(payload.get("bet_cents") or 0)
        if game_id not in MANAGER_GAME_IDS or bet_cents > rules["max_bet_cents"] or bet_cents <= 10_000 or bet_cents % 500:
            raise api_error("err_manager_bet_invalid")
        preset = db.scalar(select(ManagerBetPreset).where(ManagerBetPreset.user_id == user.id, ManagerBetPreset.game_id == game_id))
        if preset is None and len(active_presets(db, user.id)) >= rules["max_games"]:
            raise api_error("err_manager_game_limit", status_code=409, meta={"max_games": rules["max_games"]})
        if preset is None:
            preset = ManagerBetPreset(user_id=user.id, game_id=game_id, bet_cents=bet_cents)
        preset.bet_cents = bet_cents
        preset.source = "manager"
        preset.expires_at = None
        db.add(preset)
    elif action.kind == "bet_reset":
        preset = db.scalar(select(ManagerBetPreset).where(ManagerBetPreset.user_id == user.id, ManagerBetPreset.game_id == payload.get("game_id")))
        if preset:
            db.delete(preset)
    elif action.kind == "control_pause":
        settings = get_or_create_settings(db, user.id, lock=True)
        settings.paused_until = pause_until(int(payload["duration_minutes"]))
        db.add(settings)
    elif action.kind == "control_reminder":
        settings = get_or_create_settings(db, user.id, lock=True)
        settings.reminder_minutes = int(payload["reminder_minutes"])
        db.add(settings)
    elif action.kind == "control_daily_limit":
        settings = get_or_create_settings(db, user.id, lock=True)
        settings.daily_bet_limit_cents = max(0, int(payload["daily_bet_limit_cents"]))
        db.add(settings)
    else:
        raise api_error("err_manager_action_invalid")

    action.status = "completed"
    action.completed_at = utc_now()
    db.add(action)
    db.flush()
    return payload
