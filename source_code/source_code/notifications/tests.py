from datetime import date
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User
from transactions.models import Category, Transaction

from .models import Notification
from .services import (
    create_monthly_summary,
    create_threshold_notifications,
    create_weekly_summary,
)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationServiceTests(TestCase):
    def setUp(self):
        role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(
            email="notify-student@example.com",
            password="StudentTest123!",
            role=role,
        )
        self.user.profile.monthly_allowance = Decimal("1000000")
        self.user.profile.monthly_savings_goal = Decimal("300000")
        self.user.profile.currency_code = "VND"
        self.user.profile.save()
        self.expense_category = Category.objects.create(name="Food", type="expense")
        self.income_category = Category.objects.create(name="Part-time Job", type="income")

    def _transaction(self, *, amount, transaction_type, when):
        category = self.income_category if transaction_type == "income" else self.expense_category
        return Transaction.objects.create(
            user=self.user,
            category=category,
            amount=Decimal(str(amount)),
            type=transaction_type,
            description="test transaction",
            date=when,
        )

    def test_weekly_summary_is_stored_and_emailed(self):
        sunday = date(2026, 9, 27)
        self._transaction(amount="250000", transaction_type="income", when=date(2026, 9, 25))
        self._transaction(amount="90000", transaction_type="expense", when=date(2026, 9, 26))

        notification, created = create_weekly_summary(self.user, sunday)

        self.assertTrue(created)
        self.assertEqual(notification.kind, Notification.Kind.WEEKLY_SUMMARY)
        self.assertEqual(notification.income_total, Decimal("250000"))
        self.assertEqual(notification.expense_total, Decimal("90000"))
        self.assertEqual(notification.balance, Decimal("160000"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Income:", mail.outbox[0].body)
        self.assertIn("Open Campus Coin:", mail.outbox[0].body)

    def test_monthly_summary_only_creates_once(self):
        month_end = date(2026, 9, 30)
        self._transaction(amount="400000", transaction_type="income", when=date(2026, 9, 12))
        self._transaction(amount="100000", transaction_type="expense", when=date(2026, 9, 18))

        _, first_created = create_monthly_summary(self.user, month_end)
        _, second_created = create_monthly_summary(self.user, month_end)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(
            Notification.objects.filter(user=self.user, kind=Notification.Kind.MONTHLY_SUMMARY).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_savings_goal_warning_uses_profile_goal(self):
        reference = date(2026, 9, 25)
        self._transaction(amount="660000", transaction_type="expense", when=reference)

        created = create_threshold_notifications(self.user, reference)

        kinds = {item.kind for item in created}
        self.assertIn(Notification.Kind.SAVINGS_THRESHOLD, kinds)
        savings = Notification.objects.get(user=self.user, kind=Notification.Kind.SAVINGS_THRESHOLD)
        self.assertEqual(savings.balance, Decimal("340000"))
        self.assertEqual(savings.savings_goal, Decimal("300000"))

    def test_low_balance_warning_is_deduplicated_per_month(self):
        reference = date(2026, 9, 25)
        self._transaction(amount="920000", transaction_type="expense", when=reference)

        create_threshold_notifications(self.user, reference)
        create_threshold_notifications(self.user, reference)

        self.assertEqual(
            Notification.objects.filter(user=self.user, kind=Notification.Kind.LOW_BALANCE).count(),
            1,
        )


class NotificationViewTests(TestCase):
    def setUp(self):
        role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(
            email="notification-view@example.com",
            password="StudentTest123!",
            role=role,
        )
        self.other = User.objects.create_user(
            email="notification-other@example.com",
            password="StudentTest123!",
            role=role,
        )
        self.item = Notification.objects.create(
            user=self.user,
            kind=Notification.Kind.WEEKLY_SUMMARY,
            severity=Notification.Severity.INFO,
            title="Weekly finance summary",
            message="Summary",
            dedup_key="view-own",
        )
        Notification.objects.create(
            user=self.other,
            kind=Notification.Kind.WEEKLY_SUMMARY,
            severity=Notification.Severity.INFO,
            title="Other user's notification",
            message="Private",
            dedup_key="view-other",
        )
        self.client.force_login(self.user)

    def test_list_only_shows_current_users_notifications(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "Weekly finance summary")
        self.assertNotContains(response, "Other user's notification")

    def test_mark_read_updates_notification(self):
        response = self.client.post(reverse("notifications:mark-read", args=[self.item.pk]))
        self.assertRedirects(response, reverse("notifications:list"))
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_read)


class AdminNotificationViewTests(TestCase):
    def setUp(self):
        student_role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        admin_role, _ = Role.objects.get_or_create(role_name=Role.Name.ADMIN)
        self.student = User.objects.create_user(email="student-admin-notify@example.com", password="StudentTest123!", role=student_role)
        self.admin = User.objects.create_user(email="admin-notify@example.com", password="AdminTest123!", role=admin_role)
        Notification.objects.create(
            user=self.student, kind=Notification.Kind.MONTHLY_SUMMARY, severity=Notification.Severity.INFO,
            title="September summary", message="Summary", dedup_key="admin-list-test"
        )

    def test_admin_can_open_notification_management(self):
        self.client.force_login(self.admin, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.get(reverse("notifications:admin-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "September summary")

    def test_student_is_redirected_from_notification_management(self):
        self.client.force_login(self.student, backend="accounts.backends.EmailAuthenticationBackend")
        response = self.client.get(reverse("notifications:admin-list"))
        self.assertRedirects(response, reverse("transactions:transaction-list"), fetch_redirect_response=False)
