import unittest
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.rate_limit import limiter
from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AbuseEvent, RefreshSession, Transaction, User


class SecurityGateTest(unittest.TestCase):
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
                email="security-player@example.com",
                name="Security Player",
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
        self.current_user_id = self.user_id
        self.limiter_enabled = limiter.enabled
        limiter.enabled = False
        self.client = TestClient(self.app)

    def tearDown(self):
        limiter.enabled = self.limiter_enabled
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

    def register(self, client=None, email="new-security@example.com"):
        active_client = client or self.client
        return active_client.post(
            "/api/auth/register",
            json={"name": "New Security", "email": email, "password": "password123"},
        )

    def test_refresh_rotates_token_and_reuse_revokes_all_sessions(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        old_cookie = self.client.cookies.get("bk_refresh_token")

        refreshed = self.client.post("/api/auth/refresh")
        self.assertEqual(refreshed.status_code, 200)
        new_cookie = self.client.cookies.get("bk_refresh_token")
        self.assertNotEqual(old_cookie, new_cookie)

        reuse_client = TestClient(self.app)
        reuse_client.cookies.set("bk_refresh_token", old_cookie)
        reuse = reuse_client.post("/api/auth/refresh")
        self.assertEqual(reuse.status_code, 401)
        self.assertEqual(reuse.json()["detail"]["code"], "err_refresh_reuse_detected")

        new_after_reuse = self.client.post("/api/auth/refresh")
        self.assertEqual(new_after_reuse.status_code, 401)

        with self.SessionLocal() as db:
            active_sessions = db.query(RefreshSession).filter(RefreshSession.revoked_at.is_(None)).count()
            self.assertEqual(active_sessions, 0)

    def test_logout_all_revokes_all_refresh_sessions(self):
        client_a = TestClient(self.app)
        client_b = TestClient(self.app)
        login_a = self.register(client_a, "logout-a@example.com")
        login_b = client_b.post(
            "/api/auth/login",
            json={"email": "logout-a@example.com", "password": "password123"},
        )
        self.assertEqual(login_a.status_code, 201)
        self.assertEqual(login_b.status_code, 200)

        access = login_a.json()["access_token"]
        logout_all = client_a.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {access}"})
        self.assertEqual(logout_all.status_code, 200)

        self.assertEqual(client_a.post("/api/auth/refresh").status_code, 401)
        self.assertEqual(client_b.post("/api/auth/refresh").status_code, 401)

    def test_production_settings_reject_unsafe_values(self):
        with self.assertRaises(ValueError):
            Settings(
                _env_file=None,
                environment="production",
                secret_key="change-me-to-a-long-random-secret",
                frontend_origins="https://casino.example.com",
                refresh_cookie_secure=True,
            )
        with self.assertRaises(ValueError):
            Settings(
                _env_file=None,
                environment="production",
                secret_key="x" * 32,
                frontend_origins="http://127.0.0.1:5500",
                refresh_cookie_secure=True,
            )
        with self.assertRaises(ValueError):
            Settings(
                _env_file=None,
                environment="production",
                secret_key="x" * 32,
                frontend_origins="https://casino.example.com",
                refresh_cookie_secure=False,
            )

    def test_promo_failed_attempts_trigger_temporary_block(self):
        self.app.dependency_overrides[get_current_user] = self.override_current_user
        for _ in range(10):
            response = self.client.post("/api/cashier/deposit", json={"method_id": "promo", "promo_code": "BADCODE"})
            self.assertEqual(response.status_code, 422)

        blocked = self.client.post("/api/cashier/deposit", json={"method_id": "promo", "promo_code": "BADCODE"})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["detail"]["code"], "err_abuse_promo_blocked")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(AbuseEvent).filter_by(action="promo.redeem.failed").count(), 10)

    def test_pending_withdraw_limit_blocks_fourth_request(self):
        self.app.dependency_overrides[get_current_user] = self.override_current_user
        for _ in range(3):
            response = self.client.post("/api/cashier/withdraw", json={"amount": "180.00", "method_id": "kawaui-studio"})
            self.assertEqual(response.status_code, 201)

        fourth = self.client.post("/api/cashier/withdraw", json={"amount": "180.00", "method_id": "kawaui-studio"})
        self.assertEqual(fourth.status_code, 409)
        self.assertEqual(fourth.json()["detail"]["code"], "err_withdraw_pending_limit")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Transaction).filter_by(type="withdraw", status="pending").count(), 3)

    def test_vip_clicker_too_fast_is_blocked(self):
        self.app.dependency_overrides[get_current_user] = self.override_current_user
        for _ in range(6):
            response = self.client.post("/api/vip/clicker/bronze/click")
            self.assertEqual(response.status_code, 200)

        blocked = self.client.post("/api/vip/clicker/bronze/click")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["detail"]["code"], "err_abuse_too_fast")

    def test_login_register_rate_limit_uses_json_error(self):
        limiter.enabled = True
        for index in range(5):
            response = self.register(email=f"rate-{index}@example.com")
            self.assertEqual(response.status_code, 201)

        limited = self.register(email="rate-limited@example.com")
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["detail"]["code"], "err_rate_limited")


if __name__ == "__main__":
    unittest.main()
