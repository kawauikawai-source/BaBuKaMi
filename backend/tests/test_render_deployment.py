import unittest

from app.core.config import Settings


class RenderDeploymentSettingsTest(unittest.TestCase):
    def test_render_url_configures_same_origin_production(self):
        settings = Settings(
            _env_file=None,
            environment="production",
            secret_key="x" * 32,
            refresh_cookie_secure=True,
            bukamiku_client_secret="test-secret",
            render_external_url="https://bambiku-test.onrender.com/",
            bukamiku_public_url="https://bukamiku-test.onrender.com/",
        )

        self.assertEqual(settings.public_base_url, "https://bambiku-test.onrender.com")
        self.assertEqual(settings.api_base_url, "https://bambiku-test.onrender.com/api")
        self.assertEqual(settings.cors_origins, ["https://bambiku-test.onrender.com"])
        self.assertEqual(
            settings.google_redirect_uri,
            "https://bambiku-test.onrender.com/api/auth/google/callback",
        )
        self.assertEqual(
            settings.telegram_redirect_uri,
            "https://bambiku-test.onrender.com/api/auth/telegram/callback",
        )
        self.assertEqual(settings.google_success_redirect, "https://bambiku-test.onrender.com/index.html")
        self.assertEqual(settings.telegram_success_redirect, "https://bambiku-test.onrender.com/index.html")
        self.assertEqual(settings.bukamiku_redirect_uri, "https://bukamiku-test.onrender.com/auth/callback")

    def test_explicit_oauth_redirects_are_not_overwritten(self):
        settings = Settings(
            _env_file=None,
            environment="production",
            secret_key="x" * 32,
            refresh_cookie_secure=True,
            bukamiku_client_secret="test-secret",
            render_external_url="https://bambiku-test.onrender.com",
            google_redirect_uri="https://play.example.com/api/auth/google/callback",
            telegram_redirect_uri="https://play.example.com/api/auth/telegram/callback",
        )

        self.assertEqual(settings.google_redirect_uri, "https://play.example.com/api/auth/google/callback")
        self.assertEqual(settings.telegram_redirect_uri, "https://play.example.com/api/auth/telegram/callback")

    def test_render_url_must_be_https(self):
        with self.assertRaises(ValueError):
            Settings(
                _env_file=None,
                environment="production",
                secret_key="x" * 32,
                refresh_cookie_secure=True,
                bukamiku_client_secret="test-secret",
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
