import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.db.session import Base, get_db
from app.main import create_app
from app.models import RefreshSession, User


class AccountRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        Base.metadata.create_all(bind=self.engine)
        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
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

    def register(self, email="recovery@example.com"):
        return self.client.post(
            "/api/auth/register",
            json={"name": "Recovery User", "email": email, "password": "password123"},
        )

    @staticmethod
    def bearer(response):
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    @patch("app.routers.auth.send_verification_email")
    @patch("app.routers.auth.secrets.token_urlsafe", side_effect=["initial" * 8, "v" * 48])
    def test_email_verification_is_single_use(self, _token, _email):
        registered = self.register()
        self.assertEqual(registered.status_code, 201)
        headers = self.bearer(registered)

        requested = self.client.post("/api/auth/email-verification/request", headers=headers)
        self.assertEqual(requested.status_code, 200)
        confirmed = self.client.post(
            "/api/auth/email-verification/confirm",
            json={"token": "v" * 48},
        )
        self.assertEqual(confirmed.status_code, 200)
        repeated = self.client.post(
            "/api/auth/email-verification/confirm",
            json={"token": "v" * 48},
        )
        self.assertEqual(repeated.status_code, 422)
        with self.SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "recovery@example.com"))
            self.assertTrue(user.email_verified)

    @patch("app.routers.auth.send_password_reset_email")
    @patch("app.routers.auth.secrets.token_urlsafe", side_effect=["initial" * 8, "r" * 48])
    def test_password_reset_changes_password_and_revokes_sessions(self, _token, _email):
        registered = self.register()
        self.assertEqual(registered.status_code, 201)
        forgot = self.client.post("/api/auth/password/forgot", json={"email": "recovery@example.com"})
        self.assertEqual(forgot.status_code, 200)
        reset = self.client.post(
            "/api/auth/password/reset",
            json={"token": "r" * 48, "new_password": "new-password-456"},
        )
        self.assertEqual(reset.status_code, 200)
        old_login = self.client.post(
            "/api/auth/login", json={"email": "recovery@example.com", "password": "password123"}
        )
        self.assertEqual(old_login.status_code, 401)
        new_login = self.client.post(
            "/api/auth/login", json={"email": "recovery@example.com", "password": "new-password-456"}
        )
        self.assertEqual(new_login.status_code, 200)

    def test_change_password_requires_current_password(self):
        registered = self.register()
        headers = self.bearer(registered)
        denied = self.client.post(
            "/api/auth/password/change",
            headers=headers,
            json={"current_password": "wrong", "new_password": "new-password-456"},
        )
        self.assertEqual(denied.status_code, 422)
        self.assertEqual(denied.json()["detail"]["code"], "err_current_password")
        changed = self.client.post(
            "/api/auth/password/change",
            headers=headers,
            json={"current_password": "password123", "new_password": "new-password-456"},
        )
        self.assertEqual(changed.status_code, 200)

    def test_device_sessions_can_be_listed_and_revoked(self):
        registered = self.register()
        headers = self.bearer(registered)
        sessions = self.client.get("/api/auth/sessions", headers=headers)
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()), 1)
        session = sessions.json()[0]
        self.assertTrue(session["current"])
        revoked = self.client.delete(f"/api/auth/sessions/{session['id']}", headers=headers)
        self.assertEqual(revoked.status_code, 200)
        with self.SessionLocal() as db:
            stored = db.get(RefreshSession, session["id"])
            self.assertIsNotNone(stored.revoked_at)


if __name__ == "__main__":
    unittest.main()
