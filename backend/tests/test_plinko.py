import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.plinko import drop_midnight_vault, pocket_multipliers
from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, GameRound, Transaction, User


class MidnightVaultRulesTest(unittest.TestCase):
    def test_pockets_are_symmetric_and_roughly_96_percent_rtp(self):
        for risk in ["low", "medium", "high"]:
            with self.subTest(risk=risk):
                pockets = pocket_multipliers(12, risk)
                self.assertEqual(len(pockets), 13)
                self.assertEqual(pockets, list(reversed(pockets)))

                expected = 0.0
                for slot, multiplier_cents in enumerate(pockets):
                    probability = __import__("math").comb(12, slot) / (2**12)
                    expected += probability * multiplier_cents
                self.assertGreaterEqual(expected, 95)
                self.assertLessEqual(expected, 96)

    def test_multi_bet_is_split_between_balls(self):
        result = drop_midnight_vault(1_000, "multi", "medium", 8, 3)

        self.assertEqual(result["ball_count"], 3)
        self.assertEqual(sum(ball["bet_cents"] for ball in result["balls"]), 1_000)
        self.assertEqual(result["total_win_cents"], sum(ball["win_cents"] for ball in result["balls"]))
        self.assertEqual(result["net_cents"], result["total_win_cents"] - 1_000)


class MidnightVaultApiTest(unittest.TestCase):
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
            db.add(self.user)
            db.commit()
            db.refresh(self.user)
            self.user_id = self.user.id

        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
        self.app.dependency_overrides[get_current_user] = self.override_current_user
        self.client = TestClient(self.app)

    def tearDown(self):
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
            return db.get(User, self.user_id)

    def test_classic_drop_creates_round_transaction_audit_and_vip_points(self):
        response = self.client.post(
            "/api/games/plinko/midnight-vault/drop",
            json={"bet": "5.00", "mode": "classic", "risk": "low", "rows": 8, "balls": 1},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["mode"], "classic")
        self.assertEqual(payload["ball_count"], 1)
        self.assertEqual(len(payload["pockets"]), 9)
        self.assertEqual(len(payload["balls"]), 1)
        self.assertEqual(len(payload["balls"][0]["path"]), 8)
        self.assertGreaterEqual(payload["balls"][0]["slot"], 0)
        self.assertLessEqual(payload["balls"][0]["slot"], 8)
        self.assertEqual(payload["net_cents"], payload["total_win_cents"] - payload["total_bet_cents"])

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "midnight-vault").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "midnight-vault").one()
            audit = db.query(AuditLog).filter(AuditLog.action == "game.plinko.drop").one()

            self.assertEqual(user.balance_cents, 100_000 + payload["net_cents"])
            self.assertEqual(user.vip_points, 5)
            self.assertEqual(round_item.total_bet_cents, 500)
            self.assertEqual(round_item.total_win_cents, payload["total_win_cents"])
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, payload["net_cents"])
            self.assertEqual(audit.amount_cents, payload["net_cents"])

    def test_drop_idempotency_replays_same_round_once(self):
        headers = {"Idempotency-Key": "plinko-drop-once"}
        body = {"bet": "5.00", "mode": "classic", "risk": "low", "rows": 8, "balls": 1}

        first = self.client.post("/api/games/plinko/midnight-vault/drop", json=body, headers=headers)
        second = self.client.post("/api/games/plinko/midnight-vault/drop", json=body, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["round_id"], second.json()["round_id"])
        self.assertEqual(first.json()["transaction"]["id"], second.json()["transaction"]["id"])
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Transaction).filter_by(method_id="midnight-vault").count(), 1)
            self.assertEqual(db.query(GameRound).filter_by(game_id="midnight-vault").count(), 1)

    def test_multi_drop_uses_total_bet_once(self):
        response = self.client.post(
            "/api/games/plinko/midnight-vault/drop",
            json={"bet": "10.00", "mode": "multi", "risk": "high", "rows": 16, "balls": 5},
        )
        payload = response.json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["ball_count"], 5)
        self.assertEqual(sum(ball["bet_cents"] for ball in payload["balls"]), 1_000)
        self.assertEqual(sum(ball["win_cents"] for ball in payload["balls"]), payload["total_win_cents"])

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.vip_points, 10)

    def test_rejects_invalid_inputs_and_insufficient_balance(self):
        cases = [
            ({"bet": "1.00", "mode": "classic", "risk": "low", "rows": 8, "balls": 1}, "err_plinko_bet_invalid"),
            ({"bet": "5.00", "mode": "turbo", "risk": "low", "rows": 8, "balls": 1}, "err_plinko_mode_invalid"),
            ({"bet": "5.00", "mode": "classic", "risk": "wild", "rows": 8, "balls": 1}, "err_plinko_risk_invalid"),
            ({"bet": "5.00", "mode": "classic", "risk": "low", "rows": 10, "balls": 1}, "err_plinko_rows_invalid"),
            ({"bet": "5.00", "mode": "multi", "risk": "low", "rows": 8, "balls": 4}, "err_plinko_balls_invalid"),
        ]
        for payload, code in cases:
            with self.subTest(code=code):
                response = self.client.post("/api/games/plinko/midnight-vault/drop", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["detail"]["code"], code)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.add(user)
            db.commit()

        response = self.client.post(
            "/api/games/plinko/midnight-vault/drop",
            json={"bet": "5.00", "mode": "classic", "risk": "low", "rows": 8, "balls": 1},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_plinko_balance")


if __name__ == "__main__":
    unittest.main()
