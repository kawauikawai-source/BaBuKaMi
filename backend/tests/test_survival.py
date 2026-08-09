import json
import random
import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.survival import (
    CATEGORY_DATA,
    CONTENT_ERRORS,
    SCENARIO_BANK,
    SURVIVAL_GAME_ID,
    choice_explanation,
    correct_choice_id,
    create_round_plan,
    evaluate_choice,
    public_question,
    resolution_parameter_values,
)
from app.db.session import Base, get_db
from app.deps import get_current_user
from app.main import create_app
from app.models import AuditLog, GameRound, Transaction, User


class ArcticProtocolContentTest(unittest.TestCase):
    def test_bank_has_exact_content_contract(self):
        self.assertEqual(CONTENT_ERRORS, [])
        self.assertEqual(len(CATEGORY_DATA), 8)
        self.assertEqual(len(SCENARIO_BANK), 120)
        self.assertEqual(sum(len(item["choices"]) for item in SCENARIO_BANK), 360)
        self.assertEqual(len({item["id"] for item in SCENARIO_BANK}), 120)
        for item in SCENARIO_BANK:
            self.assertEqual(len(item["choices"]), 3)
            self.assertEqual(len(item["profiles"]), 3)
            self.assertEqual({profile["correct"] for profile in item["profiles"]}, {0, 1, 2})
            for lang in ("ru", "en"):
                self.assertTrue(item["title"][lang])
                self.assertTrue(item["prompt"][lang])

    def test_every_category_has_fifteen_distinct_decision_sets(self):
        for category in CATEGORY_DATA:
            scenarios = [item for item in SCENARIO_BANK if item["category"] == category["key"]]
            answer_sets = {
                tuple(choice["text"]["ru"] for choice in scenario["choices"])
                for scenario in scenarios
            }
            self.assertEqual(len(scenarios), 15)
            self.assertEqual(len(answer_sets), 15)

    def test_each_dossier_profile_changes_data_and_correct_protocol(self):
        for scenario in SCENARIO_BANK:
            signatures = set()
            for profile in scenario["profiles"]:
                selection = {
                    "scenario_id": scenario["id"],
                    "profile_id": profile["id"],
                    "choice_order": [2, 0, 1],
                }
                question = public_question(selection, "ru")
                signature = tuple(
                    (parameter["key"], parameter["label"], parameter["value"])
                    for parameter in question["parameters"]
                )
                signatures.add(signature)
                answer_id = correct_choice_id(selection)
                self.assertTrue(evaluate_choice(selection, answer_id))
                self.assertTrue(choice_explanation(selection, answer_id, "ru", correct=True))
                wrong_id = next(item for item in ("a", "b", "c") if item != answer_id)
                wrong_explanation = choice_explanation(selection, wrong_id, "ru", correct=False)
                self.assertIn("Верный протокол:", wrong_explanation)
                updates = resolution_parameter_values(selection, "ru")
                self.assertTrue(updates)
                self.assertTrue(set(updates).issubset({parameter["key"] for parameter in question["parameters"]}))
            self.assertEqual(len(signatures), 3)

    def test_power_overload_resolves_to_visible_safe_load(self):
        scenario = next(
            item
            for item in SCENARIO_BANK
            if any(profile["id"] == "power_external" for profile in item["profiles"])
        )
        selection = {
            "scenario_id": scenario["id"],
            "profile_id": "power_external",
            "choice_order": [0, 1, 2],
        }
        question = public_question(selection, "ru")
        self.assertEqual(
            next(item["value"] for item in question["parameters"] if item["key"] == "load"),
            "134%",
        )
        self.assertEqual(resolution_parameter_values(selection, "ru")["load"], "68%")

    def test_round_plan_avoids_recent_scenario_and_profile_pair(self):
        first = create_round_plan(
            rng=random.Random(41),
            category_key="nuclear_winter",
        )
        recent = []
        for selection in first["selections"]:
            recent.extend(
                [
                    selection["scenario_id"],
                    f"{selection['scenario_id']}::{selection['profile_id']}",
                ]
            )
        second = create_round_plan(
            recent_ids=recent,
            rng=random.Random(42),
            category_key="nuclear_winter",
        )
        first_scenarios = {selection["scenario_id"] for selection in first["selections"]}
        second_scenarios = {selection["scenario_id"] for selection in second["selections"]}
        self.assertTrue(first_scenarios.isdisjoint(second_scenarios))

    def test_answer_order_is_shuffled_without_changing_logic(self):
        orders = set()
        correct_bases = set()
        for seed in range(30):
            plan = create_round_plan(
                rng=random.Random(seed),
                category_key="solar_storm",
            )
            selection = plan["selections"][0]
            orders.add(tuple(selection["choice_order"]))
            question = public_question(selection, "en")
            self.assertEqual(len(question["choices"]), 3)
            answer_id = correct_choice_id(selection)
            self.assertTrue(evaluate_choice(selection, answer_id))
            correct_bases.add(selection["choice_order"][("a", "b", "c").index(answer_id)])
        self.assertEqual(len(orders), 6)
        self.assertEqual(correct_bases, {0, 1, 2})

    def test_legacy_active_round_profile_remains_playable(self):
        scenario = SCENARIO_BANK[0]
        selection = {
            "scenario_id": scenario["id"],
            "profile_id": "legacy-profile-before-content-v2",
            "choice_order": [1, 2, 0],
        }
        question = public_question(selection, "ru")
        self.assertEqual(len(question["parameters"]), 3)
        answer_id = correct_choice_id(selection)
        self.assertTrue(evaluate_choice(selection, answer_id))


class ArcticProtocolApiTest(unittest.TestCase):
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
            user = User(
                email="protocol@example.com",
                name="Protocol Player",
                provider="local",
                email_verified=True,
                balance_cents=100_000,
                created_at=datetime.now(UTC),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            self.user_id = user.id

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

    def start(self, key="protocol-start"):
        return self.client.post(
            "/api/games/survival/arctic-protocol/start",
            json={"bet": "5.00", "lang": "ru"},
            headers={"Idempotency-Key": key},
        )

    def round_state(self):
        with self.SessionLocal() as db:
            round_item = db.query(GameRound).filter_by(game_id=SURVIVAL_GAME_ID).order_by(GameRound.id.desc()).first()
            return round_item, json.loads(round_item.result_json)

    def answer_correctly(self, round_id, key):
        round_item, result = self.round_state()
        selection = result["selections"][result["stage_index"]]
        answer = correct_choice_id(selection)
        return self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{round_id}/choice",
            json={"choice_id": answer, "lang": "ru"},
            headers={"Idempotency-Key": key},
        )

    def ready_round(self, round_id, key):
        return self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{round_id}/ready",
            json={"lang": "ru"},
            headers={"Idempotency-Key": key},
        )

    def continue_round(self, round_id, key):
        return self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{round_id}/continue",
            json={"lang": "ru"},
            headers={"Idempotency-Key": key},
        )

    def test_start_reserves_bet_and_hides_future_content(self):
        response = self.start()
        body = response.json()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["phase"], "briefing")
        self.assertEqual(body["stage"], 1)
        self.assertEqual(body["question"]["choices"], [])
        self.assertIsNone(body["deadline_at"])
        self.assertNotIn("selections", body)
        self.assertIsNone(body["correct_choice_id"])
        ready = self.ready_round(body["round_id"], "ready-start")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["phase"], "awaiting_choice")
        self.assertEqual(len(ready.json()["question"]["choices"]), 3)
        self.assertTrue(
            all(parameter["resolved_value"] is None for parameter in ready.json()["question"]["parameters"])
        )
        self.assertIsNotNone(ready.json()["deadline_at"])
        seconds_left = (datetime.fromisoformat(ready.json()["deadline_at"]) - datetime.now(UTC)).total_seconds()
        self.assertGreater(seconds_left, 28)
        self.assertLessEqual(seconds_left, 30)
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter_by(method_id=SURVIVAL_GAME_ID).one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(user.vip_points, 5)
            self.assertEqual(transaction.status, "pending")
            self.assertEqual(transaction.amount_cents, -500)

    def test_start_is_idempotent_and_second_active_round_conflicts(self):
        first = self.start("same-start")
        replay = self.start("same-start")
        conflict = self.start("different-start")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(first.json()["round_id"], replay.json()["round_id"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["detail"]["code"], "err_survival_active_round")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Transaction).filter_by(method_id=SURVIVAL_GAME_ID).count(), 1)

    def test_correct_answer_restores_resolved_phase_after_reload(self):
        started = self.start().json()
        self.ready_round(started["round_id"], "ready-1")
        answered = self.answer_correctly(started["round_id"], "answer-1")
        self.assertEqual(answered.status_code, 200)
        self.assertEqual(answered.json()["phase"], "resolved")
        self.assertTrue(answered.json()["explanation"])
        self.assertTrue(
            any(parameter["resolved_value"] for parameter in answered.json()["question"]["parameters"])
        )
        reloaded = self.client.get(
            f"/api/games/survival/arctic-protocol/rounds/{started['round_id']}",
            params={"lang": "en"},
        )
        self.assertEqual(reloaded.status_code, 200)
        self.assertEqual(reloaded.json()["phase"], "resolved")
        self.assertIsNone(reloaded.json()["deadline_at"])
        continued = self.continue_round(started["round_id"], "continue-1")
        self.assertEqual(continued.json()["phase"], "briefing")
        self.assertEqual(continued.json()["stage"], 2)
        self.assertIsNone(continued.json()["deadline_at"])

    def test_wrong_answer_settles_once_and_burns_bet(self):
        started = self.start().json()
        self.ready_round(started["round_id"], "ready-wrong")
        _, result = self.round_state()
        selection = result["selections"][0]
        correct = correct_choice_id(selection)
        wrong = next(item for item in ("a", "b", "c") if item != correct)
        response = self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{started['round_id']}/choice",
            json={"choice_id": wrong, "lang": "ru"},
            headers={"Idempotency-Key": "wrong-once"},
        )
        replay = self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{started['round_id']}/choice",
            json={"choice_id": wrong, "lang": "ru"},
            headers={"Idempotency-Key": "wrong-once"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "lost")
        self.assertEqual(response.json()["outcome"], "wrong_choice")
        self.assertEqual(response.json()["round_id"], replay.json()["round_id"])
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            transaction = db.query(Transaction).filter_by(method_id=SURVIVAL_GAME_ID).one()
            self.assertEqual(user.balance_cents, 99_500)
            self.assertEqual(transaction.status, "completed")
            self.assertEqual(transaction.amount_cents, -500)

    def test_expired_round_settles_on_active_reload(self):
        started = self.start().json()
        self.ready_round(started["round_id"], "ready-expired")
        with self.SessionLocal() as db:
            round_item = db.get(GameRound, started["round_id"])
            result = json.loads(round_item.result_json)
            result["deadline_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            round_item.result_json = json.dumps(result)
            db.commit()
        response = self.client.get("/api/games/survival/arctic-protocol/active", params={"lang": "ru"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "lost")
        self.assertEqual(response.json()["outcome"], "timeout")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(AuditLog).filter_by(action="game.survival.timeout").count(), 1)

    def test_six_correct_answers_pay_exactly_six_x(self):
        body = self.start().json()
        round_id = body["round_id"]
        for stage in range(6):
            self.ready_round(round_id, f"ready-{stage}")
            answered = self.answer_correctly(round_id, f"correct-{stage}").json()
            if stage < 5:
                self.assertEqual(answered["phase"], "resolved")
                body = self.continue_round(round_id, f"continue-{stage}").json()
                self.assertEqual(body["stage"], stage + 2)
                self.assertEqual(body["phase"], "briefing")
            else:
                self.assertEqual(answered["status"], "completed")
                self.assertEqual(answered["outcome"], "survived")
                self.assertEqual(answered["total_win_cents"], 3_000)
                self.assertEqual(answered["net_cents"], 2_500)
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            round_item = db.get(GameRound, round_id)
            transaction = db.query(Transaction).filter_by(method_id=SURVIVAL_GAME_ID).one()
            self.assertEqual(user.balance_cents, 102_500)
            self.assertEqual(round_item.total_win_cents, 3_000)
            self.assertEqual(transaction.amount_cents, 2_500)
            self.assertEqual(db.query(AuditLog).filter_by(action="game.survival.completed").count(), 1)

    def test_invalid_bet_and_early_timeout_are_readable(self):
        invalid = self.client.post(
            "/api/games/survival/arctic-protocol/start",
            json={"bet": "1.00", "lang": "ru"},
        )
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["detail"]["code"], "err_survival_bet_invalid")
        started = self.start("valid-after-invalid").json()
        self.ready_round(started["round_id"], "ready-timeout")
        early = self.client.post(
            f"/api/games/survival/arctic-protocol/rounds/{started['round_id']}/timeout",
            json={"lang": "ru"},
            headers={"Idempotency-Key": "early-timeout"},
        )
        self.assertEqual(early.status_code, 409)
        self.assertEqual(early.json()["detail"]["code"], "err_survival_timeout_not_due")


if __name__ == "__main__":
    unittest.main()
