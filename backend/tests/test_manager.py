import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, ManagerAction, ManagerBetPreset, ManagerMessage, ManagerTicket, User


class ManagerOperatorTest(unittest.TestCase):
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
            player = User(
                email="silver@example.com",
                name="Silver Player",
                balance_cents=200_000,
                vip_tier="bronze",
                vip_points=4_999,
                email_verified=True,
            )
            admin = User(
                email="manager-admin@example.com",
                name="Manager Admin",
                balance_cents=0,
                is_admin=True,
                email_verified=True,
            )
            db.add_all([player, admin])
            db.commit()
            db.refresh(player)
            db.refresh(admin)
            self.player_id = player.id
            self.admin_id = admin.id
        self.current_user_id = self.player_id
        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
        self.app.dependency_overrides[get_current_user] = self.override_user
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

    def override_user(self):
        with self.SessionLocal() as db:
            return db.get(User, self.current_user_id)

    def set_player_tier(self, tier: str) -> None:
        with self.SessionLocal() as db:
            player = db.get(User, self.player_id)
            player.vip_tier = tier
            db.commit()

    def test_bronze_cannot_open_operator(self):
        response = self.client.get("/api/manager")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "err_manager_vip_required")

    def test_silver_can_confirm_personal_chip_once(self):
        self.set_player_tier("silver")
        created = self.client.post(
            "/api/manager/messages",
            json={
                "text": "Поставь 150 евро в Удаче Кавая",
                "language": "ru",
                "intent": "set_bet",
                "payload": {"game_id": "dragons-fortune", "amount_cents": 15_000},
            },
        )
        self.assertEqual(created.status_code, 200)
        action_id = created.json()["action"]["id"]

        headers = {"Idempotency-Key": "manager-action-confirm-once"}
        confirmed = self.client.post(f"/api/manager/actions/{action_id}/confirm", headers=headers)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.json()["action"]["status"], "completed")
        self.assertEqual(confirmed.json()["state"]["bet_presets"][0]["bet_cents"], 15_000)

        replayed = self.client.post(f"/api/manager/actions/{action_id}/confirm", headers=headers)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.json()["operator_message"]["id"], confirmed.json()["operator_message"]["id"])

        repeated = self.client.post(f"/api/manager/actions/{action_id}/confirm")
        self.assertEqual(repeated.status_code, 409)
        with self.SessionLocal() as db:
            preset = db.query(ManagerBetPreset).filter_by(user_id=self.player_id, game_id="dragons-fortune").one()
            self.assertEqual(preset.bet_cents, 15_000)
            self.assertEqual(db.query(AuditLog).filter_by(action="manager.bet_preset.update").count(), 1)

    def test_custom_chip_is_accepted_by_game_start(self):
        self.set_player_tier("silver")
        with self.SessionLocal() as db:
            db.add(ManagerBetPreset(user_id=self.player_id, game_id="dragons-fortune", bet_cents=15_000))
            db.commit()
        response = self.client.post(
            "/api/games/crash/dragons-fortune/start",
            headers={"Idempotency-Key": "manager-custom-crash-start"},
            json={"bet": 150},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["total_bet_cents"], 15_000)

    def test_exception_ticket_can_be_approved_for_24_hours(self):
        self.set_player_tier("silver")
        requested = self.client.post(
            "/api/manager/messages",
            json={
                "text": "Хочу 200 евро в рулетке",
                "language": "ru",
                "intent": "set_bet",
                "payload": {"game_id": "roulette", "amount_cents": 20_000},
            },
        )
        self.assertEqual(requested.status_code, 200)
        ticket_id = requested.json()["ticket"]["id"]

        self.current_user_id = self.admin_id
        approved = self.client.patch(
            f"/api/admin/manager/tickets/{ticket_id}",
            json={
                "status": "resolved",
                "response": "Начальство одобрило временный номинал.",
                "approved_bet_cents": 20_000,
                "game_id": "roulette",
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "resolved")
        with self.SessionLocal() as db:
            preset = db.query(ManagerBetPreset).filter_by(user_id=self.player_id, game_id="roulette").one()
            self.assertEqual(preset.bet_cents, 20_000)
            self.assertEqual(preset.source, "admin_exception")
            self.assertIsNotNone(preset.expires_at)
            expires = preset.expires_at.replace(tzinfo=UTC) if preset.expires_at.tzinfo is None else preset.expires_at
            self.assertGreater((expires - datetime.now(UTC)).total_seconds(), 23 * 60 * 60)
            self.assertEqual(db.query(ManagerMessage).filter_by(user_id=self.player_id, role="admin").count(), 1)
            self.assertEqual(db.query(ManagerTicket).filter_by(id=ticket_id, status="resolved").count(), 1)


if __name__ == "__main__":
    unittest.main()
