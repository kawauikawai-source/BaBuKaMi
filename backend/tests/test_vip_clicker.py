import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, Transaction, User, VipClickerProgress
from app.services.money import apply_game_result


class VipClickerApiTest(unittest.TestCase):
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
                email="clicker@example.com",
                name="Clicker",
                provider="local",
                email_verified=True,
                balance_cents=20_000,
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

    def test_clicker_progress_starts_empty_and_increments_by_tier(self):
        initial = self.client.get("/api/vip/clicker")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["total_clicks"], 0)
        self.assertEqual(initial.json()["totals"]["gold"], 0)

        for _ in range(3):
            response = self.client.post("/api/vip/clicker/gold/click")
            self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/vip/clicker/bronze/click")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["totals"]["gold"], 3)
        self.assertEqual(payload["totals"]["bronze"], 1)
        self.assertEqual(payload["total_clicks"], 4)

        with self.SessionLocal() as db:
            rows = db.query(VipClickerProgress).all()
            self.assertEqual(len(rows), 2)

    def test_clicker_reset_clears_only_selected_tier(self):
        self.client.post("/api/vip/clicker/gold/click")
        self.client.post("/api/vip/clicker/gold/click")
        self.client.post("/api/vip/clicker/silver/click")

        response = self.client.post("/api/vip/clicker/gold/reset")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["totals"]["gold"], 0)
        self.assertEqual(payload["totals"]["silver"], 1)
        self.assertEqual(payload["total_clicks"], 1)

    def test_clicker_accepts_batched_clicks(self):
        response = self.client.post("/api/vip/clicker/silver/click", json={"count": 18})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totals"]["silver"], 18)

        invalid = self.client.post("/api/vip/clicker/silver/click", json={"count": 26})
        self.assertEqual(invalid.status_code, 422)

    def test_clicker_ignores_click_sent_before_latest_reset(self):
        old_click_time = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
        self.client.post("/api/vip/clicker/bronze/click", json={"client_action_at": old_click_time})

        response = self.client.post("/api/vip/clicker/bronze/reset")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totals"]["bronze"], 0)

        stale = self.client.post("/api/vip/clicker/bronze/click", json={"client_action_at": old_click_time})
        self.assertEqual(stale.status_code, 200)
        self.assertEqual(stale.json()["totals"]["bronze"], 0)

    def test_clicker_counts_click_sent_after_reset(self):
        self.client.post("/api/vip/clicker/bronze/reset")
        fresh_time = datetime.now(UTC).isoformat()

        response = self.client.post("/api/vip/clicker/bronze/click", json={"client_action_at": fresh_time})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totals"]["bronze"], 1)

    def test_clicker_rejects_invalid_tier(self):
        response = self.client.post("/api/vip/clicker/diamond/click")
        self.assertEqual(response.status_code, 422)

    def test_clicker_requires_authentication(self):
        self.app.dependency_overrides.pop(get_current_user)
        response = self.client.get("/api/vip/clicker")
        self.assertEqual(response.status_code, 401)

    def test_game_bet_points_are_capped_by_bought_tier(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_tier = "bronze"
            user.vip_points = 995
            user.balance_cents = 20_000
            apply_game_result(
                db,
                user=user,
                game_id="test-game",
                total_bet_cents=1_000,
                total_win_cents=0,
                net_cents=-1_000,
                action="game.test.spin",
            )
            db.commit()
            db.refresh(user)
            self.assertEqual(user.vip_points, 999)

    def test_existing_points_above_current_cap_are_not_reduced_by_bet(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_tier = "bronze"
            user.vip_points = 1840
            user.balance_cents = 20_000
            apply_game_result(
                db,
                user=user,
                game_id="test-game",
                total_bet_cents=1_000,
                total_win_cents=0,
                net_cents=-1_000,
                action="game.test.spin",
            )
            db.commit()
            db.refresh(user)
            self.assertEqual(user.vip_points, 1840)

    def test_purchase_silver_deducts_balance_and_unlocks_next_tier(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_points = 999
            user.balance_cents = 20_000
            db.commit()

        response = self.client.post("/api/vip/tiers/purchase", json={"tier": "silver"})
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["wallet"]["balance_cents"], 19_000)
        self.assertEqual(payload["wallet"]["vip_tier"], "silver")
        self.assertEqual(payload["wallet"]["vip_points"], 1000)
        self.assertEqual(payload["transaction"]["type"], "vip")
        self.assertEqual(payload["transaction"]["amount_cents"], -1000)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.vip_tier, "silver")
            self.assertEqual(user.vip_points, 1000)
            self.assertEqual(user.balance_cents, 19_000)
            self.assertEqual(db.query(Transaction).filter_by(type="vip").count(), 1)
            self.assertEqual(db.query(AuditLog).filter_by(action="vip.tier.purchase").count(), 1)

    def test_purchase_vip_tier_idempotency_replays_once(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_points = 999
            user.balance_cents = 20_000
            db.commit()

        headers = {"Idempotency-Key": "vip-silver-once"}
        body = {"tier": "silver"}
        first = self.client.post("/api/vip/tiers/purchase", json=body, headers=headers)
        second = self.client.post("/api/vip/tiers/purchase", json=body, headers=headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["transaction"]["id"], second.json()["transaction"]["id"])
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.vip_tier, "silver")
            self.assertEqual(user.balance_cents, 19_000)
            self.assertEqual(db.query(Transaction).filter_by(type="vip").count(), 1)

    def test_purchase_requires_enough_points_and_balance(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_points = 998
            user.balance_cents = 20_000
            db.commit()

        response = self.client.post("/api/vip/tiers/purchase", json={"tier": "silver"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_vip_not_enough_points")

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_points = 999
            user.balance_cents = 500
            db.commit()

        response = self.client.post("/api/vip/tiers/purchase", json={"tier": "silver"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_vip_balance")

    def test_purchase_rejects_skip_and_repeat(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            user.vip_tier = "bronze"
            user.vip_points = 20_000
            user.balance_cents = 20_000
            db.commit()

        skip = self.client.post("/api/vip/tiers/purchase", json={"tier": "gold"})
        self.assertEqual(skip.status_code, 409)
        self.assertEqual(skip.json()["detail"]["code"], "err_vip_not_next")

        self.client.post("/api/vip/tiers/purchase", json={"tier": "silver"})
        repeat = self.client.post("/api/vip/tiers/purchase", json={"tier": "silver"})
        self.assertEqual(repeat.status_code, 409)
        self.assertEqual(repeat.json()["detail"]["code"], "err_vip_already_unlocked")


if __name__ == "__main__":
    unittest.main()
