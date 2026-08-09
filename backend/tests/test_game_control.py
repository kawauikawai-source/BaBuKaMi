import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, GameControlSettings, User
from app.services.money import apply_game_result, reserve_bet


class GameControlTest(unittest.TestCase):
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
            user = User(email="control@example.com", name="Control", balance_cents=100_000, email_verified=True)
            db.add(user)
            db.commit()
            db.refresh(user)
            self.user_id = user.id
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
            return db.get(User, self.user_id)

    def test_settings_persist_and_audit(self):
        response = self.client.put(
            "/api/game-control/settings",
            json={"daily_bet_limit_cents": 5000, "reminder_minutes": 15},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["daily_bet_limit_cents"], 5000)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(GameControlSettings).filter_by(user_id=self.user_id).one().reminder_minutes, 15)
            self.assertEqual(db.query(AuditLog).filter_by(action="game.control.update").count(), 1)

    def test_daily_limit_blocks_instant_and_reserved_bets(self):
        self.client.put("/api/game-control/settings", json={"daily_bet_limit_cents": 1000, "reminder_minutes": 30})
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            apply_game_result(db, user=user, game_id="instant", total_bet_cents=700, total_win_cents=0, net_cents=-700)
            db.commit()

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            with self.assertRaises(Exception) as raised:
                reserve_bet(db, user=user, amount_cents=400, game_id="active", method_id="active",
                            title="Active", title_key="tx_active", action="game.active.start", balance_error_code="err_game_balance")
            self.assertEqual(getattr(raised.exception, "status_code", None), 409)
            db.rollback()
            self.assertEqual(db.get(User, self.user_id).balance_cents, 99_300)

    def test_pause_blocks_new_bet_and_resume_unlocks_it(self):
        paused = self.client.post("/api/game-control/pause", json={"duration_minutes": 60})
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["is_paused"])
        with self.SessionLocal() as db:
            with self.assertRaises(Exception) as raised:
                apply_game_result(db, user=db.get(User, self.user_id), game_id="instant", total_bet_cents=500,
                                  total_win_cents=0, net_cents=-500)
            self.assertEqual(getattr(raised.exception, "status_code", None), 409)

        resumed = self.client.post("/api/game-control/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertFalse(resumed.json()["is_paused"])

    def test_requires_authentication(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get("/api/game-control").status_code, 401)


if __name__ == "__main__":
    unittest.main()
