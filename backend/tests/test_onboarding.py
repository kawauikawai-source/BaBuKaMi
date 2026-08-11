import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.db.session import Base, get_db
from app.main import create_app
from app.models import User


class OnboardingTest(unittest.TestCase):
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

    def test_full_registration_persists_identity_and_kyc_choice(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "first_name": "Kawaui",
                "last_name": "Kawashi",
                "email": "onboarding@example.com",
                "password": "password123",
                "dob": "2000-04-15",
                "phone": "+48 555 010 203",
                "country": "Poland",
                "kyc_opt_in": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual(user["name"], "Kawaui Kawashi")
        self.assertEqual(user["first_name"], "Kawaui")
        self.assertEqual(user["last_name"], "Kawashi")
        self.assertEqual(user["kyc_status"], "pending")
        self.assertEqual(user["profile_completion"], 100)
        self.assertEqual(user["profile_missing_fields"], [])

        with self.SessionLocal() as db:
            stored = db.scalar(select(User).where(User.email == "onboarding@example.com"))
            self.assertEqual(stored.phone, "+48 555 010 203")
            self.assertEqual(stored.dob, "2000-04-15")

    def test_phone_and_kyc_can_be_skipped_without_restrictions(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "first_name": "Optional",
                "last_name": "Profile",
                "email": "optional@example.com",
                "password": "password123",
                "dob": "1998-02-20",
                "country": "Poland",
            },
        )
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual(user["kyc_status"], "not_started")
        self.assertIn("phone", user["profile_missing_fields"])
        self.assertFalse(user["onboarding_required"])

    def test_registration_rejects_underage_date(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "first_name": "Young",
                "last_name": "User",
                "email": "young@example.com",
                "password": "password123",
                "dob": "2012-01-01",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_legacy_name_registration_still_works(self):
        response = self.client.post(
            "/api/auth/register",
            json={"name": "Legacy User", "email": "legacy@example.com", "password": "password123"},
        )
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual(user["first_name"], "Legacy")
        self.assertEqual(user["last_name"], "User")


if __name__ == "__main__":
    unittest.main()
