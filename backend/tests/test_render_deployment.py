import unittest

from app.core.config import Settings


class RenderDeploymentSettingsTest(unittest.TestCase):
    def test_render_url_configures_same_origin_production(self):
        settings = Settings(
            _env_file=None,
            environment="production",
            secret_key="x" * 32,
            refresh_cookie_secure=True,
            render_external_url="https://bambiku-test.onrender.com/",
        )

        self.assertEqual(settings.public_base_url, "https://bambiku-test.onrender.com")
        self.assertEqual(settings.api_base_url, "https://bambiku-test.onrender.com/api")
        self.assertEqual(settings.cors_origins, ["https://bambiku-test.onrender.com"])

    def test_render_url_must_be_https(self):
        with self.assertRaises(ValueError):
            Settings(
                _env_file=None,
                environment="production",
                secret_key="x" * 32,
                refresh_cookie_secure=True,
                render_external_url="http://bambiku-test.onrender.com",
            )

    def test_neon_url_uses_installed_psycopg_driver(self):
        settings = Settings(
            _env_file=None,
            database_url="postgresql://user:password@example.neon.tech/neondb?sslmode=require",
        )

        self.assertEqual(
            settings.sqlalchemy_database_url,
            "postgresql+psycopg://user:password@example.neon.tech/neondb?sslmode=require",
        )


if __name__ == "__main__":
    unittest.main()
