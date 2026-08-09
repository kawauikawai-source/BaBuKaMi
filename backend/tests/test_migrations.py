import os
import tempfile
import unittest

from sqlalchemy import create_engine, inspect

from app.core.config import get_settings
from app.db.migrations import run_alembic_upgrade


class AlembicMigrationTest(unittest.TestCase):
    def test_alembic_upgrade_creates_production_demo_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "migration-test.db")
            original = os.environ.get("BAMBIKU_DATABASE_URL")
            os.environ["BAMBIKU_DATABASE_URL"] = f"sqlite:///{db_path}"
            get_settings.cache_clear()
            engine = None
            try:
                run_alembic_upgrade()
                engine = create_engine(f"sqlite:///{db_path}", future=True)
                inspector = inspect(engine)
                self.assertTrue(inspector.has_table("users"))
                self.assertTrue(inspector.has_table("transactions"))
                self.assertTrue(inspector.has_table("refresh_sessions"))
                self.assertTrue(inspector.has_table("game_rounds"))
                self.assertTrue(inspector.has_table("audit_logs"))
                self.assertTrue(inspector.has_table("vip_clicker_progress"))
                self.assertTrue(inspector.has_table("promo_codes"))
                self.assertTrue(inspector.has_table("promo_redemptions"))
                self.assertTrue(inspector.has_table("idempotency_keys"))
                self.assertTrue(inspector.has_table("abuse_events"))
                self.assertFalse(inspector.has_table("arctic_cash_boards"))
                self.assertTrue(inspector.has_table("alembic_version"))
                refresh_columns = {column["name"]: column for column in inspector.get_columns("refresh_sessions")}
                self.assertIn("last_used_at", refresh_columns)
                self.assertIn("rotated_at", refresh_columns)
                self.assertIn("revoked_reason", refresh_columns)
                self.assertIn("replaced_by_session_id", refresh_columns)
                user_columns = {column["name"]: column for column in inspector.get_columns("users")}
                self.assertIn("first_name", user_columns)
                self.assertIn("last_name", user_columns)
                self.assertIn("kyc_status", user_columns)
                game_round_columns = {column["name"]: column for column in inspector.get_columns("game_rounds")}
                self.assertIn("result_json", game_round_columns)
                self.assertIn("status", game_round_columns)
                self.assertIn("settled_at", game_round_columns)
                self.assertTrue(game_round_columns["result_number"]["nullable"])
                self.assertTrue(game_round_columns["result_color"]["nullable"])
            finally:
                if engine is not None:
                    engine.dispose()
                if original is None:
                    os.environ.pop("BAMBIKU_DATABASE_URL", None)
                else:
                    os.environ["BAMBIKU_DATABASE_URL"] = original
                get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
