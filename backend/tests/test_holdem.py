import json
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, GameRound, Transaction, User
from app.core.holdem import dealer_qualifies, evaluate_best


class TexasHoldemApiTest(unittest.TestCase):
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

    def audit_actions(self):
        with self.SessionLocal() as db:
            return [item.action for item in db.query(AuditLog).order_by(AuditLog.id).all()]

    def start_round(self, state=None):
        round_state = state or {
            "player_cards": ["AS", "AH"],
            "dealer_cards": ["KS", "KH"],
            "community_cards": ["2C", "7D", "9S"],
            "deck": ["3C", "4D"],
        }
        with patch("app.routers.games.deal_holdem_round", return_value=round_state):
            response = self.client.post("/api/games/holdem/texas-holdem/start", json={"ante": "5.00"})
        self.assertEqual(response.status_code, 201)
        return response

    def test_start_creates_active_round_and_hides_dealer_cards(self):
        response = self.start_round()
        payload = response.json()

        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["stage"], "decision")
        self.assertEqual(payload["player_cards"], ["AS", "AH"])
        self.assertEqual(payload["dealer_cards"], [])
        self.assertEqual(payload["dealer_hidden_count"], 2)
        self.assertEqual(payload["community_cards"], ["2C", "7D", "9S"])
        self.assertEqual(payload["available_actions"], ["call", "fold"])
        self.assertEqual(payload["total_bet_cents"], 500)
        self.assertEqual(payload["call_amount_cents"], 1000)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "texas-holdem").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "texas-holdem").one()
            stored = json.loads(round_item.result_json)
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(user.vip_points, 5)
            self.assertEqual(round_item.status, "active")
            self.assertEqual(stored["dealer_cards"], ["KS", "KH"])
            self.assertEqual(transaction.status, "pending")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.holdem.start", self.audit_actions())

    def test_rejects_second_active_round_and_insufficient_balance(self):
        first = self.start_round()
        second = self.client.post("/api/games/holdem/texas-holdem/start", json={"ante": "5.00"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_holdem_active_round")

        with self.SessionLocal() as db:
            db.query(GameRound).delete()
            db.query(Transaction).delete()
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.commit()

        low_balance = self.client.post("/api/games/holdem/texas-holdem/start", json={"ante": "5.00"})
        self.assertEqual(low_balance.status_code, 422)
        self.assertEqual(low_balance.json()["detail"]["code"], "err_holdem_balance")

    def test_fold_settles_loss_without_revealing_dealer_hand_value(self):
        start = self.start_round()
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "fold"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["outcome"], "fold")
        self.assertEqual(payload["net_cents"], -500)
        self.assertEqual(payload["dealer_cards"], ["KS", "KH"])

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "texas-holdem").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.holdem.fold", self.audit_actions())

    def test_call_settles_player_win_and_awards_call_vip_points(self):
        start = self.start_round()
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "call"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["outcome"], "win")
        self.assertEqual(payload["dealer_cards"], ["KS", "KH"])
        self.assertEqual(payload["community_cards"], ["2C", "7D", "9S", "4D", "3C"])
        self.assertEqual(payload["total_bet_cents"], 1500)
        self.assertEqual(payload["total_win_cents"], 3000)
        self.assertEqual(payload["net_cents"], 1500)
        self.assertEqual(payload["player_hand"]["name_key"], "holdem_hand_pair")

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "texas-holdem").one()
            self.assertEqual(user.balance_cents, 101_500)
            self.assertEqual(user.vip_points, 15)
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, 1500)

        actions = self.audit_actions()
        self.assertIn("game.holdem.call", actions)
        self.assertIn("game.holdem.settle", actions)

    def test_dealer_not_qualified_returns_call_and_pays_ante(self):
        start = self.start_round(
            {
                "player_cards": ["AS", "7H"],
                "dealer_cards": ["KD", "3C"],
                "community_cards": ["2C", "5D", "9S"],
                "deck": ["JC", "QD"],
            }
        )
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "call"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["outcome"], "dealer_not_qualified")
        self.assertFalse(payload["dealer_qualified"])
        self.assertEqual(payload["total_bet_cents"], 1500)
        self.assertEqual(payload["total_win_cents"], 2000)
        self.assertEqual(payload["net_cents"], 500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            self.assertEqual(user.balance_cents, 100_500)

    def test_call_settles_player_loss_when_dealer_qualifies(self):
        start = self.start_round(
            {
                "player_cards": ["AS", "7H"],
                "dealer_cards": ["KD", "KC"],
                "community_cards": ["2C", "5D", "9S"],
                "deck": ["JC", "QD"],
            }
        )
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "call"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["outcome"], "loss")
        self.assertTrue(payload["dealer_qualified"])
        self.assertEqual(payload["total_bet_cents"], 1500)
        self.assertEqual(payload["total_win_cents"], 0)
        self.assertEqual(payload["net_cents"], -1500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "texas-holdem").one()
            self.assertEqual(user.balance_cents, 98_500)
            self.assertEqual(transaction.amount_cents, -1500)

    def test_call_push_returns_full_stake_when_dealer_qualifies(self):
        start = self.start_round(
            {
                "player_cards": ["2S", "3H"],
                "dealer_cards": ["2D", "3C"],
                "community_cards": ["4C", "4D", "AS"],
                "deck": ["QH", "KD"],
            }
        )
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "call"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["outcome"], "push")
        self.assertTrue(payload["dealer_qualified"])
        self.assertEqual(payload["total_bet_cents"], 1500)
        self.assertEqual(payload["total_win_cents"], 1500)
        self.assertEqual(payload["net_cents"], 0)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "texas-holdem").one()
            self.assertEqual(user.balance_cents, 100_000)
            self.assertEqual(transaction.amount_cents, 0)

    def test_holdem_hand_ranking_and_dealer_qualification(self):
        straight_flush = evaluate_best(["AS", "KS", "QS", "JS", "TS", "2C", "3D"])
        full_house = evaluate_best(["AH", "AD", "AC", "KD", "KC", "2S", "3H"])
        flush_over_pair = evaluate_best(["AS", "2S", "3S", "7S", "9S", "KH", "KD"])

        self.assertEqual(straight_flush.name_key, "holdem_hand_straight_flush")
        self.assertEqual(full_house.name_key, "holdem_hand_full_house")
        self.assertEqual(flush_over_pair.name_key, "holdem_hand_flush")
        self.assertGreater(straight_flush.rank_value, full_house.rank_value)
        self.assertTrue(dealer_qualifies(["4C", "4D", "AS", "KD", "QH", "2D", "3C"]))
        self.assertFalse(dealer_qualifies(["3C", "3D", "AS", "KD", "QH", "2D", "5C"]))

    def test_call_reports_visible_flush_instead_of_hole_card_pair(self):
        start = self.start_round(
            {
                "player_cards": ["AS", "2S"],
                "dealer_cards": ["KH", "KD"],
                "community_cards": ["3S", "7S", "9S"],
                "deck": ["4D", "5C"],
            }
        )
        round_id = start.json()["round_id"]
        response = self.client.post(f"/api/games/holdem/texas-holdem/rounds/{round_id}/decision", json={"action": "call"})
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["outcome"], "win")
        self.assertEqual(payload["player_hand"]["name_key"], "holdem_hand_flush")
        self.assertEqual(payload["dealer_hand"]["name_key"], "holdem_hand_pair")


if __name__ == "__main__":
    unittest.main()
