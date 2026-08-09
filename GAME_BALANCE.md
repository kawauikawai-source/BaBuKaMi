# Bambiku Game Balance Snapshot

This project is a production-demo casino. Balances are demo-value, but game
math should still be controlled and documented.

## European Roulette

- Engine: `backend/app/core/roulette.py`
- Type: instant server-side table game.
- Bets: standard European single-zero wheel, numbers `0-36`.
- Payouts include returned stake: straight pays `35:1`, color/parity/range
  pays `1:1`, dozen/column pays `2:1`.
- Baseline RTP for standard European roulette bets is about `97.30%`.
- Notes: backend result is the only source of truth; frontend only animates.

## Lucky Bamboo

- Engine: `backend/app/core/slots.py`
- Type: instant server-side 5x3 slot, 10 paylines.
- Current simulation check: `200,000` spins at EUR 10 produced about `96.2%`
  RTP with about `30.4%` hit frequency.
- Notes: the exact short-session result is volatile because line wins can stack
  on the same spin.

## Kawaui Fortune

- Engine: `backend/app/core/crash.py`
- Type: active server-side crash round.
- Start multiplier: `0.80x`.
- Cashout unlock: `1.00x`.
- Current tuning:
  - `CRASH_HOUSE_FACTOR = 0.96`
  - `EARLY_CRASH_CHANCE = 3%`
  - `LOW_CRASH_RELIEF_CHANCE = 5%`
  - cap: `50.00x`
- Current simulation check:
  - cashout at `1.20x`: about `95.9%` RTP
  - cashout at `1.50x`: about `95.9%` RTP
  - cashout at `2.00x`: about `94.0%` RTP
  - `10x+` appears about `9.2%`, `20x+` about `4.6%`, `50x` about `1.8%`
- Notes: `1.00x` is intentionally only an unlock point; the real UX relies on
  reaction time and the game starting below `1.00x`.

## Eclipse Hunt

- Engine: `backend/app/core/mines.py`
- Type: active server-side mines round.
- Grid: `20` cells.
- Eclipse counts: `5 / 7 / 10 / 12`.
- Multiplier formula uses inverse survival probability with `HOUSE_FACTOR =
  0.96`, floored to cents.
- Expected value before rounding is about `96%` for each cashout depth.
- Notes: active responses hide eclipse positions until cashout/loss.

## Neon Pyramids

- Engine: `backend/app/core/blocks.py`
- Type: skill game with server-side board validation.
- Board: `10x15` for all levels.
- Levels change speed, starting multiplier and line-clear rewards.
- Cashout unlock: at least one line cleared and multiplier `>= 1.00x`.
- Notes: no fixed RTP is claimed because result depends on player skill,
  survival, placement quality and cashout timing. Server now settles impossible
  top-out active rounds from active/status endpoints.

## Midnight Vault

- Engine: `backend/app/core/plinko.py`
- Type: instant server-side Plinko.
- Rows: `8 / 12 / 16`.
- Risk: `low / medium / high`.
- Current exact expectation from pocket tables:
  - low: about `95.4-95.6%`
  - medium: about `95.3-95.5%`
  - high: about `95.4-95.8%`
- Notes: frontend canvas physics follows the server path; it never decides the
  final pocket.

## Arctic Protocol

- Engine: `backend/app/core/survival.py`
- Type: six-stage server-side survival decision game.
- Bets: `EUR 5 / 10 / 25 / 100`.
- Every stage has one correct answer determined by the visible scenario profile.
- A wrong answer or a 15-second timeout loses the reserved bet.
- Six correct answers pay exactly `6.00x`; there is no early cashout.
- This is a skill game and does not claim a fixed RTP. Break-even occurs when
  players complete all six stages in about `16.67%` of rounds.

## Texas Hold'em

- Engine: `backend/app/core/holdem.py`
- Type: casino-vs-dealer table game.
- Flow: ante, flop visible, then `CALL 2x` or `FOLD`.
- Dealer qualifies with pair of 4s or better.
- Notes: exact RTP depends on player strategy. It should get a strategy
  simulation before being treated as production-balanced.

## Next Balance Work

- Add repeatable simulation scripts for Lucky Bamboo, Kawaui Fortune and Texas
  Hold'em.
- Add telemetry in admin for average bet, average net, hit frequency and active
  round cleanup counts.
- Revisit Plinko target if the desired final RTP is closer to `96.0%` than the
  current `95.3-95.8%` after flooring.
