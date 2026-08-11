import hashlib
import base64
import unittest
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import IdentityAppSession, SoulAppraisal, StudioTransaction, StudioWallet, Transaction, User


class StudioIntegrationTest(unittest.TestCase):
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
                email="studio-player@example.com",
                name="Studio Player",
                first_name="Studio",
                last_name="Player",
                dob="2000-01-01",
                country="PL",
                phone="+48123456789",
                provider="local",
                email_verified=True,
                balance_cents=1_000_000,
                created_at=datetime.now(UTC),
            )
            admin = User(
                email="studio-admin@example.com",
                name="Studio Admin",
                provider="local",
                email_verified=True,
                is_admin=True,
                created_at=datetime.now(UTC),
            )
            db.add_all([player, admin])
            db.commit()
            self.player_id = player.id
            self.admin_id = admin.id

        self.current_user_id = self.player_id
        self.app = create_app()
        self.app.dependency_overrides[get_db] = self.override_db
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

    def identity_headers(self):
        raw_token = "studio-identity-test-token"
        with self.SessionLocal() as db:
            if not db.query(IdentityAppSession).count():
                db.add(
                    IdentityAppSession(
                        user_id=self.player_id,
                        client_id="bukamiku-bank",
                        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                        scope="birthdate country email profile",
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                    )
                )
                db.commit()
        return {"Authorization": f"Bearer {raw_token}"}

    def test_casino_transfer_approve_credits_studio_once(self):
        response = self.client.post(
            "/api/cashier/withdraw",
            json={"amount": "200.00", "method_id": "kawaui-studio"},
            headers={"Idempotency-Key": "studio-transfer-once"},
        )
        self.assertEqual(response.status_code, 201)
        transaction_id = response.json()["transaction"]["id"]
        with self.SessionLocal() as db:
            pending = db.query(StudioTransaction).one()
            self.assertEqual(pending.status, "pending")
            self.assertEqual(pending.net_cents, 10_000)

        self.current_user_id = self.admin_id
        approved = self.client.post(f"/api/admin/withdrawals/{transaction_id}/approve")
        self.assertEqual(approved.status_code, 200)
        repeated = self.client.post(f"/api/admin/withdrawals/{transaction_id}/approve")
        self.assertEqual(repeated.status_code, 409)
        with self.SessionLocal() as db:
            wallet = db.query(StudioWallet).filter_by(user_id=self.player_id).one()
            self.assertEqual(wallet.balance_cents, 10_000)
            self.assertEqual(db.query(StudioTransaction).one().status, "completed")

    def test_casino_transfer_reject_refunds_full_reserve(self):
        response = self.client.post(
            "/api/cashier/withdraw",
            json={"amount": "200.00", "method_id": "kawaui-studio"},
        )
        transaction_id = response.json()["transaction"]["id"]
        self.current_user_id = self.admin_id
        rejected = self.client.post(f"/api/admin/withdrawals/{transaction_id}/reject")
        self.assertEqual(rejected.status_code, 200)
        with self.SessionLocal() as db:
            player = db.get(User, self.player_id)
            self.assertEqual(player.balance_cents, 1_000_000)
            self.assertEqual(db.query(StudioTransaction).one().status, "rejected")
            self.assertEqual(db.query(StudioWallet).count(), 0)

    def test_studio_deposit_moves_balance_to_casino_once(self):
        with self.SessionLocal() as db:
            db.add(StudioWallet(user_id=self.player_id, currency="EUR", balance_cents=30_000, version=0))
            db.commit()

        headers = {"Idempotency-Key": "studio-deposit-once"}
        response = self.client.post(
            "/api/cashier/deposit",
            json={"amount": "100.00", "method_id": "kawaui-studio"},
            headers=headers,
        )
        repeated = self.client.post(
            "/api/cashier/deposit",
            json={"amount": "100.00", "method_id": "kawaui-studio"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(repeated.status_code, 201)
        self.assertEqual(response.json()["transaction"]["id"], repeated.json()["transaction"]["id"])
        self.assertEqual(response.json()["wallet"]["balance_cents"], repeated.json()["wallet"]["balance_cents"])

        with self.SessionLocal() as db:
            player = db.get(User, self.player_id)
            wallet = db.query(StudioWallet).filter_by(user_id=self.player_id).one()
            studio_transaction = db.query(StudioTransaction).one()
            self.assertEqual(player.balance_cents, 1_010_000)
            self.assertEqual(wallet.balance_cents, 20_000)
            self.assertEqual(studio_transaction.type, "casino_deposit")
            self.assertEqual(studio_transaction.net_cents, -10_000)
            self.assertEqual(db.query(Transaction).filter_by(method_id="kawaui-studio").count(), 1)

    def test_studio_deposit_rejects_insufficient_studio_balance(self):
        response = self.client.post(
            "/api/cashier/deposit",
            json={"amount": "100.00", "method_id": "kawaui-studio"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_studio_insufficient_balance")

    def test_three_soul_sales_credit_studio_and_fourth_is_blocked(self):
        headers = self.identity_headers()
        body = {"fatigue": "fresh", "debt": "none", "compromise": "minor"}
        decay = []
        payouts = []
        for number in range(1, 4):
            sale_headers = {**headers, "Idempotency-Key": f"soul-sale-{number}"}
            response = self.client.post("/api/apps/bukamiku/appraisals", json=body, headers=sale_headers)
            self.assertEqual(response.status_code, 201)
            decay.append(response.json()["appraisal"]["decay_bps"])
            payouts.append(response.json()["appraisal"]["payout_cents"])
        self.assertEqual(decay, [10_000, 2_500, 500])
        self.assertGreater(payouts[0], payouts[1])
        self.assertGreater(payouts[1], payouts[2])

        fourth = self.client.post(
            "/api/apps/bukamiku/appraisals",
            json=body,
            headers={**headers, "Idempotency-Key": "soul-sale-4"},
        )
        self.assertEqual(fourth.status_code, 409)
        self.assertEqual(fourth.json()["detail"]["code"], "err_soul_sale_limit")
        preview = self.client.post("/api/apps/bukamiku/appraisals/preview", json=body, headers=headers)
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["next_sale_number"], 4)
        self.assertEqual(preview.json()["payout_cents"], 0)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(SoulAppraisal).count(), 3)
            wallet = db.query(StudioWallet).filter_by(user_id=self.player_id).one()
            self.assertEqual(wallet.balance_cents, sum(payouts))

    def test_userinfo_exposes_only_allowed_identity_fields(self):
        response = self.client.get("/api/id/userinfo", headers=self.identity_headers())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"sub", "name", "given_name", "family_name", "email", "birthdate", "country"})
        self.assertNotIn("phone", payload)
        self.assertNotIn("balance", payload)
        self.assertNotIn("is_admin", payload)

    def test_authorization_code_requires_pkce_and_is_single_use(self):
        verifier = "kawaui-studio-verifier-that-is-long-enough-for-pkce-2026"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        response = self.client.get(
            "/api/id/authorize",
            params={
                "client_id": "bukamiku-bank",
                "redirect_uri": "http://127.0.0.1:5600/auth/callback",
                "state": "state-value-that-is-long-enough",
                "scope": "profile email birthdate country",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        self.assertEqual(response.status_code, 200)
        code = parse_qs(urlparse(response.json()["authorization_url"]).query)["code"][0]
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:5600/auth/callback",
            "client_id": "bukamiku-bank",
            "client_secret": "local-bukamiku-secret-change-me",
            "code_verifier": verifier,
        }
        exchanged = self.client.post("/api/id/token", json=payload)
        self.assertEqual(exchanged.status_code, 200)
        self.assertNotIn("refresh_token", exchanged.json())
        replay = self.client.post("/api/id/token", json=payload)
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(replay.json()["detail"]["code"], "err_identity_code")


if __name__ == "__main__":
    unittest.main()
