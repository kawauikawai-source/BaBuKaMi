import unittest

from app.main import static_cache_control


class StaticResourcePolicyTest(unittest.TestCase):
    def test_html_and_runtime_config_are_not_cached(self):
        self.assertEqual(static_cache_control("/"), "no-store")
        self.assertEqual(static_cache_control("/pages/profile.html", True), "no-store")
        self.assertEqual(static_cache_control("/js/config/runtime.js", True), "no-store")

    def test_versioned_assets_and_fonts_are_immutable(self):
        immutable = "public, max-age=31536000, immutable"
        self.assertEqual(static_cache_control("/css/core/base.css", True), immutable)
        self.assertEqual(static_cache_control("/assets/images/sticker.webp", True), immutable)
        self.assertEqual(static_cache_control("/assets/fonts/nunito.woff2"), immutable)

    def test_unversioned_assets_can_revalidate(self):
        self.assertEqual(
            static_cache_control("/assets/images/sticker.webp"),
            "public, max-age=604800, stale-while-revalidate=86400",
        )
        self.assertIsNone(static_cache_control("/api/health"))


if __name__ == "__main__":
    unittest.main()
