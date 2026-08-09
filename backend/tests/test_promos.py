import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, PromoCode, PromoRedemption, Transaction, User
from app.core.rate_limit import limiter


class PromoCodesApiTest(unittest.TestCase):
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
                email="promo-player@example.com",
                name="Promo Player",
                provider="local",
                email_verified=True,
                created_at=datetime.now(UTC),
            )
            self.other_user = User(
                email="promo-other@example.com",
                name="Other Player",
                provider="local",
                email_verified=True,
                created_at=datetime.now(UTC),
            )
            self.admin = User(
                email="promo-admin@example.com",
                name="Promo Admin",
                provider="local",
                email_verified=True,
                is_admin=True,
                created_at=datetime.now(UTC),
            )
            db.add_all([self.user, self.other_user, self.admin])
            db.commit()
            db.refresh(self.user)
            db.refresh(self.other_user)
            db.refresh(self.admin)
            self.user_id = self.user.id
            self.other_user_id = self.other_user.id
            self.admin_id = self.admin.id

        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
        self.current_user_id = self.admin_id
        self.app.dependency_overrides[get_current_user] = self.override_current_user
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

    def create_fixed_promo(self, code="START50", amount="50.00", **overrides):
        self.current_user_id = self.admin_id
        payload = {
            "code": code,
            "title": code,
            "reward_type": "fixed",
            "amount": amount,
            "usage_limit": 100,
            "per_user_limit": 1,
            "is_active": True,
        }
        payload.update(overrides)
        response = self.client.post("/api/admin/promos", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_percent_promo(self, code="RELOAD10", **overrides):
        self.current_user_id = self.admin_id
        payload = {
            "code": code,
            "title": code,
            "reward_type": "percent",
            "percent": "10.00",
            "max_bonus": "75.00",
            "min_deposit": "20.00",
            "usage_limit": 100,
            "per_user_limit": 1,
            "is_active": True,
        }
        payload.update(overrides)
        response = self.client.post("/api/admin/promos", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def redeem(self, code, amount=None, user_id=None):
        self.current_user_id = user_id or self.user_id
        payload = {"method_id": "promo", "promo_code": code}
        if amount is not None:
            payload["amount"] = amount
        return self.client.post("/api/cashier/deposit", json=payload)

    def test_fixed_promo_redeem_creates_transaction_redemption_and_audit(self):
        promo = self.create_fixed_promo()

        response = self.redeem("start50")
        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()

        self.assertEqual(payload["wallet"]["balance_cents"], 5_000)
        self.assertEqual(payload["transaction"]["amount_cents"], 5_000)
        self.assertEqual(payload["transaction"]["method_id"], "promo")

        with self.SessionLocal() as db:
            redemption = db.query(PromoRedemption).one()
            self.assertEqual(redemption.promo_code_id, promo["id"])
            self.assertEqual(redemption.bonus_cents, 5_000)
            self.assertEqual(db.query(AuditLog).filter(AuditLog.action == "cashier.promo.redeem").count(), 1)

    def test_admin_create_normalizes_promo_code_to_uppercase(self):
        promo = self.create_fixed_promo(code="night-gift")

        self.assertEqual(promo["code"], "NIGHT-GIFT")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(PromoCode).one().code, "NIGHT-GIFT")

    def test_percent_promo_uses_deposit_amount_and_cap(self):
        self.create_percent_promo()

        response = self.redeem("RELOAD10", amount="1000.00")
        self.assertEqual(response.status_code, 201, response.text)

        payload = response.json()
        self.assertEqual(payload["wallet"]["balance_cents"], 7_500)
        self.assertEqual(payload["transaction"]["amount_cents"], 7_500)

        with self.SessionLocal() as db:
            redemption = db.query(PromoRedemption).one()
            self.assertEqual(redemption.deposit_cents, 100_000)
            self.assertEqual(redemption.bonus_cents, 7_500)

    def test_percent_promo_enforces_min_deposit(self):
        self.create_percent_promo()

        response = self.redeem("RELOAD10", amount="10.00")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_promo_min_deposit")

    def test_promo_limits_prevent_extra_redemptions(self):
        self.create_fixed_promo(code="ONCE", usage_limit=1, per_user_limit=1)

        first = self.redeem("ONCE")
        self.assertEqual(first.status_code, 201)

        repeat = self.redeem("ONCE")
        self.assertEqual(repeat.status_code, 422)
        self.assertEqual(repeat.json()["detail"]["code"], "err_promo_usage_limit")

        other = self.redeem("ONCE", user_id=self.other_user_id)
        self.assertEqual(other.status_code, 422)
        self.assertEqual(other.json()["detail"]["code"], "err_promo_usage_limit")

    def test_promo_per_user_limit_prevents_repeat_when_global_limit_remains(self):
        self.create_fixed_promo(code="USERONCE", usage_limit=10, per_user_limit=1)

        first = self.redeem("USERONCE")
        self.assertEqual(first.status_code, 201)

        repeat = self.redeem("USERONCE")
        self.assertEqual(repeat.status_code, 422)
        self.assertEqual(repeat.json()["detail"]["code"], "err_promo_already_used")

    def test_inactive_and_expired_promos_are_rejected(self):
        self.create_fixed_promo(code="OFF", is_active=False)
        self.create_fixed_promo(
            code="OLD",
            starts_at=(datetime.now(UTC) - timedelta(days=3)).isoformat(),
            expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )

        inactive = self.redeem("OFF")
        expired = self.redeem("OLD")

        self.assertEqual(inactive.status_code, 422)
        self.assertEqual(inactive.json()["detail"]["code"], "err_promo_inactive")
        self.assertEqual(expired.status_code, 422)
        self.assertEqual(expired.json()["detail"]["code"], "err_promo_expired")

    def test_non_admin_cannot_manage_promos(self):
        self.current_user_id = self.user_id

        response = self.client.post(
            "/api/admin/promos",
            json={"code": "NOPE", "reward_type": "fixed", "amount": "10.00"},
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_and_disable_promo(self):
        promo = self.create_fixed_promo(code="LISTME")

        listed = self.client.get("/api/admin/promos?status=active")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["code"], "LISTME")

        disabled = self.client.post(f"/api/admin/promos/{promo['id']}/disable")
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["is_active"])
        self.assertEqual(disabled.json()["status"], "inactive")

        with self.SessionLocal() as db:
            self.assertEqual(db.query(AuditLog).filter(AuditLog.action == "admin.promo.disable").count(), 1)

    def test_scheduled_promo_filters_and_redeem_is_blocked(self):
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        promo = self.create_fixed_promo(code="SOON", starts_at=future)

        active = self.client.get("/api/admin/promos?status=active")
        scheduled = self.client.get("/api/admin/promos?status=scheduled")
        redeem = self.redeem("SOON")

        self.assertEqual(active.status_code, 200)
        self.assertNotIn("SOON", [item["code"] for item in active.json()])
        self.assertEqual(scheduled.status_code, 200)
        self.assertEqual(scheduled.json()[0]["id"], promo["id"])
        self.assertEqual(scheduled.json()[0]["status"], "scheduled")
        self.assertEqual(redeem.status_code, 422)
        self.assertEqual(redeem.json()["detail"]["code"], "err_promo_not_started")

    def test_preview_fixed_and_percent_without_redemption(self):
        self.create_fixed_promo(code="PREVIEW50", amount="50.00")
        self.create_percent_promo(code="PREVIEW10")
        self.current_user_id = self.user_id

        fixed = self.client.get("/api/cashier/promos/preview?code=preview50")
        percent = self.client.get("/api/cashier/promos/preview?code=PREVIEW10&amount=1000.00")

        self.assertEqual(fixed.status_code, 200, fixed.text)
        self.assertEqual(fixed.json()["bonus_cents"], 5_000)
        self.assertEqual(percent.status_code, 200, percent.text)
        self.assertEqual(percent.json()["bonus_cents"], 7_500)
        self.assertEqual(percent.json()["deposit_cents"], 100_000)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(PromoRedemption).count(), 0)
            self.assertEqual(db.query(Transaction).count(), 0)

    def test_admin_can_update_promo_and_detail_contains_redemptions_and_audit(self):
        promo = self.create_fixed_promo(code="EDITME", amount="10.00")
        redeemed = self.redeem("EDITME")
        self.assertEqual(redeemed.status_code, 201)
        self.current_user_id = self.admin_id

        update = self.client.patch(
            f"/api/admin/promos/{promo['id']}",
            json={"title": "Edited Promo", "amount": "15.00", "usage_limit": 25},
        )
        detail = self.client.get(f"/api/admin/promos/{promo['id']}")
        redemptions = self.client.get(f"/api/admin/promos/{promo['id']}/redemptions")

        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(update.json()["title"], "Edited Promo")
        self.assertEqual(update.json()["amount_cents"], 1_500)
        self.assertEqual(update.json()["usage_limit"], 25)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["promo"]["id"], promo["id"])
        self.assertEqual(detail.json()["redemptions"][0]["promo_code"], "EDITME")
        self.assertTrue(any(item["action"] == "admin.promo.update" for item in detail.json()["audit"]))
        self.assertEqual(redemptions.status_code, 200)
        self.assertEqual(redemptions.json()[0]["user_id"], self.user_id)

    def test_promo_stats_and_config_error_codes(self):
        self.create_fixed_promo(code="STATSA")
        self.create_fixed_promo(code="STATSOFF", is_active=False)

        stats = self.client.get("/api/admin/promos/stats")
        invalid_type = self.client.post(
            "/api/admin/promos",
            json={"code": "BADTYPE", "reward_type": "mystery", "amount": "10.00"},
        )
        invalid_fixed = self.client.post(
            "/api/admin/promos",
            json={"code": "NOAMOUNT", "reward_type": "fixed"},
        )

        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total"], 2)
        self.assertEqual(stats.json()["active"], 1)
        self.assertEqual(stats.json()["inactive"], 1)
        self.assertEqual(invalid_type.status_code, 422)
        self.assertEqual(invalid_type.json()["detail"]["code"], "err_promo_reward_type")
        self.assertEqual(invalid_fixed.status_code, 422)
        self.assertEqual(invalid_fixed.json()["detail"]["code"], "err_promo_fixed_amount")


if __name__ == "__main__":
    unittest.main()
