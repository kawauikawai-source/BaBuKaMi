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
from app.core.blocks import (
    can_place,
    empty_board,
    has_valid_x,
    multiplier_after_clear,
    pressure_level_for,
    shape_cells,
    tick_ms_for,
)


class NeonPyramidsApiTest(unittest.TestCase):
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

    def start_round(self, difficulty="level1"):
        queue = ["I", "I", "O", "T", "S", "Z", "J", "L", "I", "O", "T", "S", "Z", "J"]
        with patch("app.routers.games.generate_piece_queue", return_value=queue):
            response = self.client.post(
                "/api/games/blocks/neon-pyramids/start",
                json={"bet": "5.00", "difficulty": difficulty},
            )
        self.assertEqual(response.status_code, 201)
        return response

    def test_start_creates_active_round_and_pending_transaction(self):
        response = self.start_round()
        payload = response.json()

        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["current_piece"]["id"], 1)
        self.assertEqual(payload["current_piece"]["type"], "I")
        self.assertEqual(payload["total_bet_cents"], 500)
        self.assertEqual(payload["difficulty"], "level1")
        self.assertEqual(payload["board_height"], 15)
        self.assertEqual(payload["tick_ms"], 650)
        self.assertEqual(payload["pressure_level"], 0)
        self.assertFalse(payload["cashout_available"])
        self.assertEqual(payload["current_multiplier"], "0.1")
        self.assertEqual(payload["potential_win_cents"], 50)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.query(GameRound).filter(GameRound.game_id == "neon-pyramids").one()
            transaction = db.query(Transaction).filter(Transaction.method_id == "neon-pyramids").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(round_item.status, "active")
            self.assertIn('"difficulty":"level1"', round_item.result_json)
            self.assertIn('"current_piece":{"id":1,"type":"I"}', round_item.result_json)
            self.assertEqual(transaction.status, "pending")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.blocks.start", self.audit_actions())

    def test_rejects_second_active_round_and_insufficient_balance(self):
        first = self.start_round()
        second = self.client.post("/api/games/blocks/neon-pyramids/start", json={"bet": "5.00"})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_blocks_active_round")

        with self.SessionLocal() as db:
            db.query(GameRound).delete()
            db.query(Transaction).delete()
            user = db.get(User, self.user_id)
            user.balance_cents = 100
            db.add(user)
            db.commit()

        response = self.client.post("/api/games/blocks/neon-pyramids/start", json={"bet": "5.00"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_blocks_balance")

    def test_difficulty_levels_and_invalid_difficulty(self):
        invalid = self.client.post(
            "/api/games/blocks/neon-pyramids/start",
            json={"bet": "5.00", "difficulty": "nightmare"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["detail"]["code"], "err_blocks_difficulty_invalid")

        level2 = self.start_round("level2").json()
        self.assertEqual(level2["difficulty"], "level2")
        self.assertEqual(level2["board_height"], 15)
        self.assertEqual(level2["tick_ms"], 520)
        self.assertEqual(level2["pressure_level"], 0)
        self.assertEqual(level2["current_multiplier"], "0.25")

        with self.SessionLocal() as db:
            db.query(GameRound).delete()
            db.query(Transaction).delete()
            db.commit()

        level3 = self.start_round("level3").json()
        self.assertEqual(level3["difficulty"], "level3")
        self.assertEqual(level3["board_height"], 15)
        self.assertEqual(level3["tick_ms"], 430)
        self.assertEqual(level3["pressure_level"], 0)
        self.assertEqual(level3["current_multiplier"], "0.4")

    def test_pressure_increases_drop_speed_during_round(self):
        self.assertEqual(pressure_level_for("level1", 0), 0)
        self.assertEqual(pressure_level_for("level1", 7), 0)
        self.assertEqual(pressure_level_for("level1", 8), 1)
        self.assertEqual(tick_ms_for("level1", 0), 650)
        self.assertEqual(tick_ms_for("level1", 8), 615)
        self.assertEqual(tick_ms_for("level2", 14), 450)
        self.assertEqual(tick_ms_for("level3", 12), 360)
        self.assertEqual(tick_ms_for("level3", 999), 240)

    def test_active_round_recovers_after_page_refresh(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        active = self.client.get("/api/games/blocks/neon-pyramids/active")

        self.assertEqual(active.status_code, 200)
        payload = active.json()
        self.assertEqual(payload["round_id"], round_id)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["current_piece"]["type"], "I")
        self.assertEqual(len(payload["board"]), 15)

    def test_place_clears_line_and_cashout_locks_until_one_x(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        no_lines = self.client.post(f"/api/games/blocks/neon-pyramids/rounds/{round_id}/cashout")
        self.assertEqual(no_lines.status_code, 409)
        self.assertEqual(no_lines.json()["detail"]["code"], "err_blocks_no_lines")

        first = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 1, "x": 0},
        )
        second = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 2, "rotation": 1, "x": 4},
        )
        third = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 3, "rotation": 0, "x": 8},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.json()["status"], "active")
        self.assertEqual(third.json()["lines_cleared"], 1)
        self.assertEqual(third.json()["current_multiplier"], "0.22")
        self.assertFalse(third.json()["cashout_available"])

        cashout = self.client.post(f"/api/games/blocks/neon-pyramids/rounds/{round_id}/cashout")
        self.assertEqual(cashout.status_code, 409)
        self.assertEqual(cashout.json()["detail"]["code"], "err_blocks_no_lines")

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            result = json.loads(round_item.result_json)
            result["lines_cleared"] = 4
            result["multiplier_cents"] = 170
            result["summary"]["lines"] = 4
            result["summary"]["multiplier"] = "1.7"
            round_item.result_json = json.dumps(result, separators=(",", ":"))
            db.add(round_item)
            db.commit()

        cashout = self.client.post(f"/api/games/blocks/neon-pyramids/rounds/{round_id}/cashout")
        self.assertEqual(cashout.status_code, 200)
        payload = cashout.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["total_win_cents"], 850)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "neon-pyramids").one()
            self.assertEqual(user.balance_cents, 99_500 + payload["total_win_cents"])
            self.assertEqual(user.games_played, 1)
            self.assertEqual(round_item.status, "completed")
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, payload["net_cents"])

        actions = self.audit_actions()
        self.assertIn("game.blocks.place", actions)
        self.assertIn("game.blocks.cashout", actions)

    def test_line_clear_multiplier_table_rewards_four_lines_most(self):
        self.assertEqual(multiplier_after_clear(10, 1, 1, 1, "level1"), 22)
        self.assertEqual(multiplier_after_clear(10, 2, 1, 1, "level1"), 44)
        self.assertEqual(multiplier_after_clear(10, 3, 1, 1, "level1"), 90)
        self.assertEqual(multiplier_after_clear(10, 4, 1, 1, "level1"), 170)
        self.assertEqual(multiplier_after_clear(25, 4, 1, 1, "level2"), 245)
        self.assertEqual(multiplier_after_clear(40, 4, 1, 1, "level3"), 360)

    def test_left_edge_is_valid_for_all_normalized_rotations(self):
        for piece in ("I", "J", "L", "O", "S", "T", "Z"):
            for rotation in range(4):
                with self.subTest(piece=piece, rotation=rotation):
                    cells = shape_cells(piece, rotation)
                    self.assertEqual(min(x for x, _ in cells), 0)
                    self.assertEqual(min(y for _, y in cells), 0)
                    self.assertTrue(has_valid_x(piece, rotation, 0))
                    self.assertTrue(can_place(empty_board("level1"), piece, rotation, 0, 0))

    def test_invalid_placement_and_stale_piece_are_rejected(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        invalid = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 1, "x": 9},
        )
        stale = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 99, "rotation": 0, "x": 0},
        )

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["detail"]["code"], "err_blocks_placement_invalid")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["detail"]["code"], "err_blocks_piece_invalid")

    def test_top_out_settles_loss(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            result = json.loads(round_item.result_json)
            result["board"] = [["Z" for _ in range(10)] for _ in range(15)]
            round_item.result_json = json.dumps(result, separators=(",", ":"))
            db.add(round_item)
            db.commit()

        response = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 0, "x": 0},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["net_cents"], -500)

        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "neon-pyramids").one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(user.games_played, 1)
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, -500)

        self.assertIn("game.blocks.lost", self.audit_actions())

    def test_active_round_endpoint_settles_impossible_top_out(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            result = json.loads(round_item.result_json)
            result["board"] = [["Z" for _ in range(10)] for _ in range(15)]
            round_item.result_json = json.dumps(result, separators=(",", ":"))
            db.add(round_item)
            db.commit()

        response = self.client.get("/api/games/blocks/neon-pyramids/active")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["loss_reason"], "top_out")

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter(Transaction.method_id == "neon-pyramids").one()
            self.assertEqual(round_item.status, "lost")
            self.assertEqual(transaction.status, "completed")

    def test_overloaded_stack_invalid_placement_settles_loss(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            result = json.loads(round_item.result_json)
            board = [["" for _ in range(10)] for _ in range(15)]
            board[0][4] = "Z"
            board[0][5] = "Z"
            result["board"] = board
            result["current_piece"] = {"id": 1, "type": "O"}
            round_item.result_json = json.dumps(result, separators=(",", ":"))
            db.add(round_item)
            db.commit()

        response = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 0, "x": 4, "y": 0},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "lost")
        self.assertEqual(payload["loss_reason"], "top_out")
        self.assertIn("game.blocks.lost", self.audit_actions())

    def test_exact_y_placement_allows_late_tuck_when_spawn_column_is_blocked(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        with self.SessionLocal() as db:
            round_item = db.get(GameRound, round_id)
            result = json.loads(round_item.result_json)
            board = [["" for _ in range(10)] for _ in range(15)]
            board[0][0] = "Z"
            result["board"] = board
            round_item.result_json = json.dumps(result, separators=(",", ":"))
            db.add(round_item)
            db.commit()

        response = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 0, "x": 0, "y": 11},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["last_drop_y"], 11)

    def test_exact_y_placement_rejects_piece_that_is_not_locked(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        response = self.client.post(
            f"/api/games/blocks/neon-pyramids/rounds/{round_id}/place",
            json={"piece_id": 1, "rotation": 0, "x": 0, "y": 1},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "err_blocks_placement_invalid")

    def test_forfeit_closes_round_and_repeated_actions_conflict(self):
        start = self.start_round()
        round_id = start.json()["round_id"]

        first = self.client.post(f"/api/games/blocks/neon-pyramids/rounds/{round_id}/forfeit")
        second = self.client.post(f"/api/games/blocks/neon-pyramids/rounds/{round_id}/forfeit")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "lost")
        self.assertEqual(first.json()["loss_reason"], "forfeit")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "err_blocks_round_settled")
        self.assertIn("game.blocks.forfeit", self.audit_actions())


if __name__ == "__main__":
    unittest.main()
