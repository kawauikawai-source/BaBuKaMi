import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, GameRound, PromoCode, PromoRedemption, Transaction, User
from app.routers import auth as auth_router


class AdminWithdrawalsApiTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(bind=self.engine)

        with self.SessionLocal() as db:
            self.user = User(
                email="player@example.com",
                name="Player",
                provider="local",
                email_verified=True,
                balance_cents=100_000,
                created_at=datetime.now(UTC),
            )
            self.admin = User(
                email="admin@example.com",
                name="Admin",
                provider="local",
                email_verified=True,
                is_admin=True,
                created_at=datetime.now(UTC),
            )
            db.add_all([self.user, self.admin])
            db.commit()
            db.refresh(self.user)
            db.refresh(self.admin)
            self.user_id = self.user.id
            self.admin_id = self.admin.id

        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
        self.current_user_id = self.user_id
        self.app.dependency_overrides[get_current_user] = self.override_current_user
        self.client = TestClient(self.app)
        self.telegram_settings = {
            "telegram_client_id": auth_router.settings.telegram_client_id,
            "telegram_client_secret": auth_router.settings.telegram_client_secret,
            "telegram_redirect_uri": auth_router.settings.telegram_redirect_uri,
            "telegram_success_redirect": auth_router.settings.telegram_success_redirect,
            "telegram_scopes": auth_router.settings.telegram_scopes,
        }

    def tearDown(self):
        for key, value in self.telegram_settings.items():
            setattr(auth_router.settings, key, value)
        self.app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def override_db(self):
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_current_user(self):
        with self.SessionLocal() as db:
            return db.get(User, self.current_user_id)

    def create_withdrawal(self):
        self.current_user_id = self.user_id
        response = self.client.post("/api/cashier/withdraw", json={"amount": "200.00", "method_id": "kawaui-studio"})
        self.assertEqual(response.status_code, 201)
        return response.json()["transaction"]["id"]

    def audit_actions(self):
        with self.SessionLocal() as db:
            return [row.action for row in db.query(AuditLog).order_by(AuditLog.id).all()]

    def test_deposit_creates_transaction_and_audit_log(self):
        response = self.client.post("/api/cashier/deposit", json={"amount": "50.00", "method_id": "card"})
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["transaction"]["type"], "deposit")
        self.assertEqual(payload["transaction"]["amount_cents"], 5_000)
        self.assertIn("cashier.deposit", self.audit_actions())

    def test_deposit_idempotency_replays_same_response(self):
        headers = {"Idempotency-Key": "deposit-once"}
        body = {"amount": "50.00", "method_id": "card"}

        first = self.client.post("/api/cashier/deposit", json=body, headers=headers)
        second = self.client.post("/api/cashier/deposit", json=body, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["transaction"]["id"], second.json()["transaction"]["id"])
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transactions = db.query(Transaction).filter(Transaction.type == "deposit").all()
            self.assertEqual(user.balance_cents, 105_000)
            self.assertEqual(len(transactions), 1)

    def test_idempotency_key_conflict_rejects_different_body(self):
        headers = {"Idempotency-Key": "deposit-conflict"}

        first = self.client.post("/api/cashier/deposit", json={"amount": "50.00", "method_id": "card"}, headers=headers)
        second = self.client.post("/api/cashier/deposit", json={"amount": "60.00", "method_id": "card"}, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_idempotency_conflict")
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 105_000)

    def test_withdraw_creates_pending_and_reserves_balance(self):
        tx_id = self.create_withdrawal()

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 80_000)
            transaction = db.get(Transaction, tx_id)
            self.assertEqual(transaction.fee_cents, 10_000)
            self.assertEqual(transaction.payout_cents, 10_000)

        response = self.client.get("/api/admin/withdrawals?status=pending")
        self.assertEqual(response.status_code, 403)

        self.current_user_id = self.admin_id
        response = self.client.get("/api/admin/withdrawals?status=pending")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["transaction"]["id"], tx_id)
        self.assertEqual(payload[0]["transaction"]["status"], "pending")
        self.assertIn("cashier.withdraw.request", self.audit_actions())

    def test_withdraw_idempotency_replays_and_reserves_once(self):
        headers = {"Idempotency-Key": "withdraw-once"}
        body = {"amount": "200.00", "method_id": "kawaui-studio"}

        first = self.client.post("/api/cashier/withdraw", json=body, headers=headers)
        second = self.client.post("/api/cashier/withdraw", json=body, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["transaction"]["id"], second.json()["transaction"]["id"])
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transactions = db.query(Transaction).filter(Transaction.type == "withdraw").all()
            self.assertEqual(user.balance_cents, 80_000)
            self.assertEqual(len(transactions), 1)

    def test_vip_cashier_limits_and_commission_are_tier_specific(self):
        too_small = self.client.post("/api/cashier/withdraw", json={"amount": "179.00", "method_id": "kawaui-studio"})
        too_large = self.client.post("/api/cashier/withdraw", json={"amount": "501.00", "method_id": "kawaui-studio"})
        self.assertEqual(too_small.status_code, 422)
        self.assertEqual(too_small.json()["detail"]["amount"], "180")
        self.assertEqual(too_large.status_code, 422)
        self.assertEqual(too_large.json()["detail"]["amount"], "500")

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_tier = "gold"
            db.commit()

        response = self.client.post("/api/cashier/withdraw", json={"amount": "1000.00", "method_id": "kawaui-studio"})
        self.assertEqual(response.status_code, 201)
        transaction = response.json()["transaction"]
        self.assertEqual(transaction["fee_cents"], 15_000)
        self.assertEqual(transaction["payout_cents"], 85_000)

    def test_vip_deposit_maximum_grows_with_tier(self):
        bronze = self.client.post("/api/cashier/deposit", json={"amount": "1001.00", "method_id": "card"})
        self.assertEqual(bronze.status_code, 422)
        self.assertEqual(bronze.json()["detail"]["amount"], "1000")

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_tier = "platinum"
            db.commit()

        platinum = self.client.post("/api/cashier/deposit", json={"amount": "5000.00", "method_id": "card"})
        self.assertEqual(platinum.status_code, 201)

    def test_approve_pending_withdrawal_does_not_change_balance(self):
        tx_id = self.create_withdrawal()
        self.current_user_id = self.admin_id

        response = self.client.post(f"/api/admin/withdrawals/{tx_id}/approve")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transaction"]["status"], "completed")
        self.assertIn("withdraw.approve", self.audit_actions())

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 80_000)

        repeat = self.client.post(f"/api/admin/withdrawals/{tx_id}/approve")
        self.assertEqual(repeat.status_code, 409)

    def test_reject_pending_withdrawal_refunds_balance(self):
        tx_id = self.create_withdrawal()
        self.current_user_id = self.admin_id

        response = self.client.post(f"/api/admin/withdrawals/{tx_id}/reject")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transaction"]["status"], "rejected")
        self.assertIn("withdraw.reject", self.audit_actions())

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 100_000)

        repeat = self.client.post(f"/api/admin/withdrawals/{tx_id}/reject")
        self.assertEqual(repeat.status_code, 409)

    def test_admin_can_list_users_and_credit_balance(self):
        self.current_user_id = self.admin_id

        users_response = self.client.get("/api/admin/users?q=player")
        self.assertEqual(users_response.status_code, 200)
        users = users_response.json()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["email"], "player@example.com")

        response = self.client.post(
            f"/api/admin/users/{self.user_id}/balance",
            json={"amount": "250.50", "note": "Manual test credit"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["balance_cents"], 125_050)
        self.assertEqual(payload["transaction"]["type"], "deposit")
        self.assertEqual(payload["transaction"]["amount_cents"], 25_050)
        self.assertIn("admin.balance.credit", self.audit_actions())

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 125_050)
            self.assertEqual(user.vip_points, 0)

    def test_admin_can_debit_balance_without_overdraft(self):
        self.current_user_id = self.admin_id

        response = self.client.post(
            f"/api/admin/users/{self.user_id}/balance",
            json={"amount": "-50.00", "note": "Manual test debit"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["balance_cents"], 95_000)
        self.assertEqual(payload["transaction"]["type"], "withdraw")
        self.assertEqual(payload["transaction"]["amount_cents"], -5_000)
        self.assertIn("admin.balance.debit", self.audit_actions())

        overdraft = self.client.post(
            f"/api/admin/users/{self.user_id}/balance",
            json={"amount": "-999999.00", "note": "Too much"},
        )
        self.assertEqual(overdraft.status_code, 422)

    def test_admin_balance_idempotency_replays_once(self):
        self.current_user_id = self.admin_id
        headers = {"Idempotency-Key": "admin-credit-once"}
        body = {"amount": "25.00", "note": "Bonus"}

        first = self.client.post(f"/api/admin/users/{self.user_id}/balance", json=body, headers=headers)
        second = self.client.post(f"/api/admin/users/{self.user_id}/balance", json=body, headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["transaction"]["id"], second.json()["transaction"]["id"])
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transactions = db.query(Transaction).filter(Transaction.method_id == "admin").all()
            self.assertEqual(user.balance_cents, 102_500)
            self.assertEqual(len(transactions), 1)

    def test_non_admin_cannot_adjust_balance(self):
        response = self.client.post(
            f"/api/admin/users/{self.user_id}/balance",
            json={"amount": "10.00", "note": "Nope"},
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_user_detail_history_rounds_and_audit_endpoints(self):
        self.current_user_id = self.user_id
        spin = self.client.post(
            "/api/games/roulette/spin",
            json={"bets": [{"type": "color", "selection": "red", "amount": "1.00"}]},
        )
        self.assertEqual(spin.status_code, 201)

        self.current_user_id = self.admin_id
        detail = self.client.get(f"/api/admin/users/{self.user_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["email"], "player@example.com")

        transactions = self.client.get(f"/api/admin/users/{self.user_id}/transactions?type=game")
        self.assertEqual(transactions.status_code, 200)
        self.assertEqual(transactions.json()[0]["type"], "game")

        rounds = self.client.get(f"/api/admin/users/{self.user_id}/game-rounds?game_id=european-roulette&status=completed")
        self.assertEqual(rounds.status_code, 200)
        self.assertEqual(rounds.json()[0]["game_id"], "european-roulette")

        audit = self.client.get("/api/admin/audit?action=game.roulette.spin")
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.json()[0]["action"], "game.roulette.spin")

    def test_admin_can_view_user_promo_redemptions(self):
        with self.SessionLocal() as db:
            promo = PromoCode(
                code="ADMINV2",
                title="Admin V2",
                reward_type="fixed",
                amount_cents=5_000,
                usage_limit=100,
                per_user_limit=1,
                is_active=True,
                created_by_user_id=self.admin_id,
            )
            tx = Transaction(
                user_id=self.user_id,
                type="deposit",
                status="completed",
                amount_cents=5_000,
                method_id="promo",
            )
            other_tx = Transaction(
                user_id=self.admin_id,
                type="deposit",
                status="completed",
                amount_cents=5_000,
                method_id="promo",
            )
            db.add_all([promo, tx, other_tx])
            db.flush()
            db.add_all([
                PromoRedemption(
                    promo_code_id=promo.id,
                    user_id=self.user_id,
                    transaction_id=tx.id,
                    bonus_cents=5_000,
                    deposit_cents=0,
                ),
                PromoRedemption(
                    promo_code_id=promo.id,
                    user_id=self.admin_id,
                    transaction_id=other_tx.id,
                    bonus_cents=5_000,
                    deposit_cents=0,
                ),
            ])
            db.commit()

        forbidden = self.client.get(f"/api/admin/users/{self.user_id}/promo-redemptions")
        self.assertEqual(forbidden.status_code, 403)

        self.current_user_id = self.admin_id
        response = self.client.get(f"/api/admin/users/{self.user_id}/promo-redemptions?limit=10&offset=0")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["promo_code"], "ADMINV2")
        self.assertEqual(payload[0]["promo_title"], "Admin V2")
        self.assertEqual(payload[0]["bonus_cents"], 5_000)

    def test_admin_pagination_for_users_withdrawals_and_audit(self):
        with self.SessionLocal() as db:
            db.add_all([
                User(email="page-a@example.com", name="Page A", provider="local", email_verified=True),
                User(email="page-b@example.com", name="Page B", provider="local", email_verified=True),
                Transaction(user_id=self.user_id, type="withdraw", status="pending", amount_cents=-1_000, method_id="card"),
                Transaction(user_id=self.user_id, type="withdraw", status="pending", amount_cents=-2_000, method_id="card"),
                AuditLog(actor_user_id=self.admin_id, target_user_id=self.user_id, action="test.page.one"),
                AuditLog(actor_user_id=self.admin_id, target_user_id=self.user_id, action="test.page.two"),
            ])
            db.commit()

        self.current_user_id = self.admin_id
        users_page_1 = self.client.get("/api/admin/users?limit=1&offset=0")
        users_page_2 = self.client.get("/api/admin/users?limit=1&offset=1")
        withdrawals_page_1 = self.client.get("/api/admin/withdrawals?status=pending&limit=1&offset=0")
        withdrawals_page_2 = self.client.get("/api/admin/withdrawals?status=pending&limit=1&offset=1")
        audit_page_1 = self.client.get("/api/admin/audit?limit=1&offset=0")
        audit_page_2 = self.client.get("/api/admin/audit?limit=1&offset=1")

        for response in [users_page_1, users_page_2, withdrawals_page_1, withdrawals_page_2, audit_page_1, audit_page_2]:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 1)

        self.assertNotEqual(users_page_1.json()[0]["id"], users_page_2.json()[0]["id"])
        self.assertNotEqual(
            withdrawals_page_1.json()[0]["transaction"]["id"],
            withdrawals_page_2.json()[0]["transaction"]["id"],
        )
        self.assertNotEqual(audit_page_1.json()[0]["id"], audit_page_2.json()[0]["id"])

    def test_admin_selected_user_history_pagination(self):
        with self.SessionLocal() as db:
            db.add_all([
                Transaction(user_id=self.user_id, type="deposit", status="completed", amount_cents=1_000, method_id="card"),
                Transaction(user_id=self.user_id, type="deposit", status="completed", amount_cents=2_000, method_id="card"),
                GameRound(user_id=self.user_id, game_id="lucky-bamboo", total_bet_cents=500, total_win_cents=0, net_cents=-500),
                GameRound(user_id=self.user_id, game_id="solar-wilds", total_bet_cents=500, total_win_cents=800, net_cents=300),
            ])
            db.commit()

        self.current_user_id = self.admin_id
        transactions_page_1 = self.client.get(f"/api/admin/users/{self.user_id}/transactions?limit=1&offset=0")
        transactions_page_2 = self.client.get(f"/api/admin/users/{self.user_id}/transactions?limit=1&offset=1")
        rounds_page_1 = self.client.get(f"/api/admin/users/{self.user_id}/game-rounds?limit=1&offset=0")
        rounds_page_2 = self.client.get(f"/api/admin/users/{self.user_id}/game-rounds?limit=1&offset=1")

        for response in [transactions_page_1, transactions_page_2, rounds_page_1, rounds_page_2]:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()), 1)

        self.assertNotEqual(transactions_page_1.json()[0]["id"], transactions_page_2.json()[0]["id"])
        self.assertNotEqual(rounds_page_1.json()[0]["id"], rounds_page_2.json()[0]["id"])

    def test_telegram_oidc_status_and_login_redirect_use_pkce(self):
        auth_router.settings.telegram_client_id = "123456"
        auth_router.settings.telegram_client_secret = "telegram-secret"
        auth_router.settings.telegram_redirect_uri = "https://example.test/api/auth/telegram/callback"

        status_response = self.client.get("/api/auth/telegram/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertTrue(status_response.json()["enabled"])
        self.assertEqual(status_response.json()["login_url"], "/api/auth/telegram/login")

        response = self.client.get("/api/auth/telegram/login", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        location = response.headers["location"]
        parsed = urlparse(location)
        query = parse_qs(parsed.query)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", auth_router.TELEGRAM_AUTH_URL)
        self.assertEqual(query["client_id"], ["123456"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["redirect_uri"], ["https://example.test/api/auth/telegram/callback"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("code_challenge", query)
        self.assertIn("state", query)
        self.assertIn("nonce", query)

    def test_telegram_oidc_callback_creates_user_and_session(self):
        auth_router.settings.telegram_client_id = "123456"
        auth_router.settings.telegram_client_secret = "telegram-secret"
        auth_router.settings.telegram_redirect_uri = "https://example.test/api/auth/telegram/callback"
        auth_router.settings.telegram_success_redirect = "http://127.0.0.1:5500/index.html"
        login = self.client.get("/api/auth/telegram/login", follow_redirects=False)
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        with (
            patch("app.routers.auth.exchange_telegram_code", new=AsyncMock(return_value={"id_token": "telegram-id-token"})),
            patch(
                "app.routers.auth.validate_telegram_id_token",
                return_value={"sub": "987654321", "name": "Telegram User", "preferred_username": "tguser"},
            ),
        ):
            callback = self.client.get(f"/api/auth/telegram/callback?code=ok&state={state}", follow_redirects=False)

        self.assertEqual(callback.status_code, 307)
        self.assertIn("access_token=", callback.headers["location"])
        self.assertIn("bk_refresh_token", callback.headers.get("set-cookie", ""))
        with self.SessionLocal() as db:
            user = db.query(User).filter(User.telegram_sub == "987654321").one()
            self.assertEqual(user.provider, "telegram")
            self.assertEqual(user.email, "telegram-987654321@users.telegram.bambiku.dev")
            self.assertEqual(user.name, "Telegram User")

    def test_lucky_bamboo_spin_creates_round_transaction_and_audit(self):
        self.current_user_id = self.user_id

        response = self.client.post("/api/games/slots/lucky-bamboo/spin", json={"bet": "5.00"})
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(len(payload["grid"]), 3)
        self.assertEqual(len(payload["grid"][0]), 5)
        self.assertEqual(payload["total_bet_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "lucky-bamboo").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "lucky-bamboo").one()
            self.assertEqual(user.balance_cents, 100_000 + payload["net_cents"])
            self.assertIsNone(round_item.result_number)
            self.assertIsNone(round_item.result_color)
            self.assertIn('"grid"', round_item.result_json)
            self.assertEqual(transaction.type, "game")
            self.assertEqual(transaction.amount_cents, payload["net_cents"])

        self.assertIn("game.slots.spin", self.audit_actions())

    def test_lucky_bamboo_spin_rejects_insufficient_balance(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.add(user)
            db.commit()

        self.current_user_id = self.user_id
        response = self.client.post("/api/games/slots/lucky-bamboo/spin", json={"bet": "5.00"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_slot_balance")

    def test_solar_mines_start_creates_active_round_and_hides_mines(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            response = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["mine_count"], 5)
        self.assertEqual(payload["revealed_cells"], [])
        self.assertIsNone(payload["mines"])
        self.assertEqual(payload["total_bet_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "solar-wilds").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "solar-wilds").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(round_item.status, "active")
            self.assertIn('"mines":[1,2,3,5,6]', round_item.result_json)
            self.assertEqual(transaction.status, "pending")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.mines.start", self.audit_actions())

    def test_solar_mines_rejects_second_active_round_and_insufficient_balance(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            first = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
            second = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_mines_active_round")

        with self.SessionLocal() as db:
            db.query(GameRound).delete()
            db.query(Transaction).delete()
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.add(user)
            db.commit()

        response = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_mines_balance")

    def test_solar_mines_active_round_recovers_after_page_refresh(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            start = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
        round_id = start.json()["round_id"]

        active = self.client.get("/api/games/mines/solar-wilds/active")

        self.assertEqual(active.status_code, 200)
        payload = active.json()
        self.assertEqual(payload["round_id"], round_id)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["mine_count"], 5)
        self.assertIsNone(payload["mines"])
        self.assertEqual(payload["revealed_cells"], [])

    def test_solar_mines_safe_reveal_keeps_balance_and_duplicate_reveal_conflicts(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            start = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
        round_id = start.json()["round_id"]

        reveal = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/reveal", json={"cell": 4})
        self.assertEqual(reveal.status_code, 200)
        payload = reveal.json()
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["revealed_cells"], [4])
        self.assertIsNone(payload["mines"])
        self.assertGreater(payload["potential_win_cents"], 500)

        duplicate = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/reveal", json={"cell": 4})
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["detail"]["code"], "err_mines_cell_revealed")

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "solar-wilds").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(transaction.status, "pending")

    def test_solar_mines_mine_reveal_settles_loss_and_reveals_mines(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            start = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
        round_id = start.json()["round_id"]

        response = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/reveal", json={"cell": 1})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["mines"], [1, 2, 3, 5, 6])
        self.assertEqual(payload["net_cents"], -500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "solar-wilds").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(user.games_played, 1)
            self.assertEqual(round_item.status, "lost")
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.mines.lost", self.audit_actions())

    def test_solar_mines_cashout_pays_after_safe_reveal(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_mines", return_value=[1, 2, 3, 5, 6]):
            start = self.client.post("/api/games/mines/solar-wilds/start", json={"bet": "5.00", "mine_count": 5})
        round_id = start.json()["round_id"]

        no_reveal = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/cashout")
        self.assertEqual(no_reveal.status_code, 409)
        self.assertEqual(no_reveal.json()["detail"]["code"], "err_mines_no_reveals")

        reveal = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/reveal", json={"cell": 4})
        cashout = self.client.post(f"/api/games/mines/solar-wilds/rounds/{round_id}/cashout")
        self.assertEqual(reveal.status_code, 200)
        self.assertEqual(cashout.status_code, 200)
        payload = cashout.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["mines"], [1, 2, 3, 5, 6])
        self.assertGreater(payload["total_win_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "solar-wilds").one()
            self.assertEqual(user.balance_cents, 99_500 + payload["total_win_cents"])
            self.assertEqual(user.games_played, 1)
            self.assertEqual(round_item.status, "completed")
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, payload["net_cents"])

        actions = self.audit_actions()
        self.assertIn("game.mines.start", actions)
        self.assertIn("game.mines.cashout", actions)

    def test_dragon_crash_start_creates_active_round_and_pending_transaction(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=300):
            response = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["status"], "active")
        self.assertIsNone(payload["crash_multiplier"])
        self.assertEqual(payload["total_bet_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "dragons-fortune").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "dragons-fortune").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(round_item.status, "active")
            self.assertIsNone(round_item.settled_at)
            self.assertIn('"crash_multiplier_cents":300', round_item.result_json)
            self.assertEqual(transaction.status, "pending")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.crash.start", self.audit_actions())

    def test_dragon_crash_rejects_second_active_round(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=300):
            first = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
            second = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_crash_active_round")

    def test_dragon_crash_cashout_before_crash_completes_round(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=300):
            start = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
        round_id = start.json()["round_id"]

        with patch("app.routers.games.current_multiplier_cents", return_value=200):
            response = self.client.post(f"/api/games/crash/dragons-fortune/rounds/{round_id}/cashout")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["cashout_multiplier"], "2.00")
        self.assertEqual(payload["total_win_cents"], 1000)
        self.assertEqual(payload["net_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "dragons-fortune").one()
            self.assertEqual(user.balance_cents, 100_500)
            self.assertEqual(user.games_played, 1)
            self.assertEqual(user.total_won_cents, 500)
            self.assertEqual(round_item.status, "completed")
            self.assertIsNotNone(round_item.settled_at)
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, 500)

        actions = self.audit_actions()
        self.assertIn("game.crash.start", actions)
        self.assertIn("game.crash.cashout", actions)

    def test_dragon_crash_cashout_after_crash_settles_loss(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=150):
            start = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
        round_id = start.json()["round_id"]

        with patch("app.routers.games.current_multiplier_cents", return_value=200):
            response = self.client.post(f"/api/games/crash/dragons-fortune/rounds/{round_id}/cashout")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["crash_multiplier"], "1.50")
        self.assertEqual(payload["net_cents"], -500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "dragons-fortune").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(user.games_played, 1)
            self.assertEqual(round_item.status, "lost")
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.crash.lost", self.audit_actions())

    def test_dragon_crash_rejects_repeated_cashout(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=300):
            start = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
        round_id = start.json()["round_id"]

        with patch("app.routers.games.current_multiplier_cents", return_value=200):
            first = self.client.post(f"/api/games/crash/dragons-fortune/rounds/{round_id}/cashout")
            second = self.client.post(f"/api/games/crash/dragons-fortune/rounds/{round_id}/cashout")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_crash_round_settled")

    def test_dragon_crash_status_after_crash_auto_settles_loss(self):
        self.current_user_id = self.user_id
        with patch("app.routers.games.generate_crash_multiplier_cents", return_value=150):
            start = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
        round_id = start.json()["round_id"]

        with patch("app.routers.games.current_multiplier_cents", return_value=200):
            response = self.client.get(f"/api/games/crash/dragons-fortune/rounds/{round_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "lost")

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            self.assertEqual(round_item.status, "lost")

        self.assertIn("game.crash.lost", self.audit_actions())

    def test_dragon_crash_rejects_insufficient_balance(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.add(user)
            db.commit()

        self.current_user_id = self.user_id
        response = self.client.post("/api/games/crash/dragons-fortune/start", json={"bet": "5.00"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_crash_balance")


if __name__ == "__main__":
    unittest.main()
