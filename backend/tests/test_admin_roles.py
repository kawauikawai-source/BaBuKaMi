import unittest

from app.deps import apply_admin_email_role, settings
from app.models import User


class AdminEmailRoleTest(unittest.TestCase):
    def setUp(self):
        self.original_admin_emails = settings.admin_emails
        self.original_environment = settings.environment

    def tearDown(self):
        settings.admin_emails = self.original_admin_emails
        settings.environment = self.original_environment

    def test_configured_admin_list_grants_and_revokes_role(self):
        settings.admin_emails = "owner@example.com"
        owner = User(email="OWNER@example.com", name="Owner", is_admin=False)
        removed = User(email="removed@example.com", name="Removed", is_admin=True)

        apply_admin_email_role(owner)
        apply_admin_email_role(removed)

        self.assertTrue(owner.is_admin)
        self.assertFalse(removed.is_admin)

    def test_empty_admin_list_preserves_database_role_for_local_use(self):
        settings.environment = "development"
        settings.admin_emails = ""
        local_admin = User(email="local@example.com", name="Local", is_admin=True)

        apply_admin_email_role(local_admin)

        self.assertTrue(local_admin.is_admin)

    def test_empty_admin_list_revokes_database_role_in_production(self):
        settings.environment = "production"
        settings.admin_emails = ""
        removed = User(email="removed@example.com", name="Removed", is_admin=True)

        apply_admin_email_role(removed)

        self.assertFalse(removed.is_admin)


if __name__ == "__main__":
    unittest.main()
