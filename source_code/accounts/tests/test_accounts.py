from unittest.mock import patch
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.models import Role, User
from accounts.services import create_password_reset_token, find_valid_reset_token


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountTests(TestCase):
    def setUp(self):
        self.student_role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        self.admin_role, _ = Role.objects.get_or_create(role_name=Role.Name.ADMIN)
        self.student = User.objects.create_user(
            email="student@example.com",
            password="StrongPass123!",
            role=self.student_role,
        )
        self.student.profile.full_name = "Student Demo"
        self.student.profile.save()
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            role=self.admin_role,
        )
        self.admin.profile.full_name = "Admin Demo"
        self.admin.profile.save()

    def test_create_user_creates_profile(self):
        user = User.objects.create_user(
            email="new@example.com",
            password="StrongPass123!",
            role=self.student_role,
        )
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(hasattr(user, "profile"))

    def test_user_login_rejects_admin_account(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"email": self.admin.email, "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Portal")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_admin_login_rejects_student_account(self):
        response = self.client.post(
            reverse("accounts:admin_login"),
            {"email": self.student.email, "password": "StrongPass123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have administrator privileges")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_student_cannot_open_admin_dashboard(self):
        self.client.force_login(self.student, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertRedirects(response, reverse("accounts:profile"))

    def test_admin_cannot_open_student_transactions(self):
        self.client.force_login(self.admin, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.get(reverse("transactions:list"))
        self.assertRedirects(response, reverse("accounts:admin_dashboard"))

    def test_admin_dashboard_is_available_to_admin(self):
        self.client.force_login(self.admin, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administration Overview")

    def test_student_forgot_password_sends_email(self):
        response = self.client.post(
            reverse("accounts:forgot_password"),
            {"email": self.student.email},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Reset Password", mail.outbox[0].subject)


    @override_settings(PUBLIC_BASE_URL="auto")
    @patch("config.public_url.detect_lan_ip", return_value="192.168.1.55")
    def test_reset_email_uses_server_lan_ip_and_request_port(self, _detect_ip):
        self.client.post(
            reverse("accounts:forgot_password"),
            {"email": self.student.email},
            HTTP_HOST="127.0.0.1:8000",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("http://192.168.1.55:8000/", mail.outbox[0].body)

    @override_settings(PUBLIC_BASE_URL="auto")
    @patch("config.public_url.detect_lan_ip", return_value="192.168.1.77")
    def test_reset_email_does_not_trust_request_host(self, _detect_ip):
        self.client.post(
            reverse("accounts:forgot_password"),
            {"email": self.student.email},
            HTTP_HOST="203.0.113.99:8000",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("http://192.168.1.77:8000/", mail.outbox[0].body)
        self.assertNotIn("203.0.113.99", mail.outbox[0].body)

    @override_settings(PUBLIC_BASE_URL="https://campuscoin.example.com")
    def test_reset_email_can_use_manual_public_base_url(self):
        self.client.post(
            reverse("accounts:forgot_password"),
            {"email": self.student.email},
            HTTP_HOST="192.168.1.55:8000",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://campuscoin.example.com/", mail.outbox[0].body)

    def test_student_forgot_password_does_not_send_for_admin(self):
        self.client.post(reverse("accounts:forgot_password"), {"email": self.admin.email})
        self.assertEqual(len(mail.outbox), 0)

    def test_admin_forgot_password_route_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("accounts:admin_forgot_password")
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_token_is_hashed(self):
        raw_token = create_password_reset_token(self.student)
        saved = self.student.password_reset_tokens.latest("created_at")
        self.assertNotEqual(raw_token, saved.token_hash)
        self.assertEqual(find_valid_reset_token(raw_token).pk, saved.pk)

    def test_admin_can_disable_student_and_sessions_are_revoked(self):
        self.client.force_login(self.admin, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.post(
            reverse("accounts:admin_user_toggle_status", args=[self.student.pk])
        )
        self.assertRedirects(
            response,
            reverse("accounts:admin_user_detail", args=[self.student.pk]),
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.DISABLED)

    def test_admin_cannot_disable_self(self):
        self.client.force_login(self.admin, backend="accounts.backends.EmailAuthenticationBackend")
        self.client.post(reverse("accounts:admin_user_toggle_status", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.status, User.Status.ACTIVE)
