from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserProfile
from transactions.models import Category, Transaction

from .models import ChatMessage, ChatSession
from .services import (
    DeterministicFinanceAssistant,
    FinanceContextService,
    IntentRouter,
    parse_requested_amount,
    parse_requested_count,
)


class FinanceAssistantServiceTests(TestCase):
    def setUp(self):
        role = Role.objects.get(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(email="student@example.com", password="StrongPass123!", role=role)
        profile, _ = UserProfile.objects.get_or_create(user=self.user, defaults={"full_name": "Student"})
        profile.monthly_allowance = Decimal("5000000")
        profile.monthly_savings_goal = Decimal("1000000")
        profile.currency_code = "VND"
        profile.save()
        food = Category.objects.create(name="Food", type="expense")
        income = Category.objects.create(name="Part-time", type="income")
        self.allowance_category = Category.objects.create(name="Allowance", type="income")
        Transaction.objects.create(
            user=self.user, category=food, amount=Decimal("1200000"),
            type="expense", description="Meals", date=date(2026, 9, 10),
        )
        Transaction.objects.create(
            user=self.user, category=income, amount=Decimal("500000"),
            type="income", description="Side job", date=date(2026, 9, 12),
        )

    def test_snapshot_uses_allowance_plus_income_minus_expense(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.assertEqual(snapshot.available_funds, Decimal("5500000"))
        self.assertEqual(snapshot.remaining_funds, Decimal("4300000"))
        self.assertEqual(snapshot.safe_to_spend_now, Decimal("3300000"))
        self.assertEqual(snapshot.counted_income, Decimal("500000"))
        self.assertEqual(snapshot.recorded_allowance_income, Decimal("0"))

    def test_allowance_transaction_is_not_double_counted_when_profile_allowance_exists(self):
        Transaction.objects.create(
            user=self.user, category=self.allowance_category, amount=Decimal("500000"),
            type="income", description="Monthly allowance received", date=date(2026, 9, 15),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.assertEqual(snapshot.month_income, Decimal("1000000"))
        self.assertEqual(snapshot.recorded_allowance_income, Decimal("500000"))
        self.assertEqual(snapshot.counted_income, Decimal("500000"))
        self.assertEqual(snapshot.available_funds, Decimal("5500000"))
        self.assertEqual(snapshot.remaining_funds, Decimal("4300000"))

    def test_allowance_transaction_counts_when_profile_allowance_is_zero(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.monthly_allowance = Decimal("0")
        profile.save(update_fields=["monthly_allowance"])
        Transaction.objects.create(
            user=self.user, category=self.allowance_category, amount=Decimal("700000"),
            type="income", description="Allowance received", date=date(2026, 9, 15),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.assertEqual(snapshot.month_income, Decimal("1200000"))
        self.assertEqual(snapshot.counted_income, Decimal("1200000"))
        self.assertEqual(snapshot.available_funds, Decimal("1200000"))
        self.assertEqual(snapshot.remaining_funds, Decimal("0"))

    def test_exact_profile_case_does_not_add_allowance_transaction_twice(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.monthly_allowance = Decimal("4444444")
        profile.monthly_savings_goal = Decimal("5555555")
        profile.save()
        # Remove the fixture income/expense so this matches the UI example exactly.
        Transaction.objects.filter(user=self.user).delete()
        Transaction.objects.create(
            user=self.user, category=self.allowance_category, amount=Decimal("2"),
            type="income", description="Allowance", date=date(2026, 9, 25),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.assertEqual(snapshot.month_income, Decimal("2"))
        self.assertEqual(snapshot.recorded_allowance_income, Decimal("2"))
        self.assertEqual(snapshot.counted_income, Decimal("0"))
        self.assertEqual(snapshot.remaining_funds, Decimal("4444444"))
        self.assertEqual(snapshot.safe_to_spend_now, Decimal("0"))
        self.assertEqual(snapshot.savings_goal - snapshot.remaining_funds, Decimal("1111111"))

    def test_spendable_intent_is_distinct_from_balance(self):
        router = IntentRouter()
        self.assertEqual(router.detect("Tôi còn bao nhiêu tiền để tiêu?"), "spendable")
        self.assertEqual(router.detect("Tôi còn bao nhiêu tiền?"), "balance")

    def test_intents_and_amount_parsing(self):
        router = IntentRouter()
        self.assertEqual(router.detect("Tháng này tôi còn bao nhiêu?"), "balance")
        self.assertEqual(router.detect("Mình có mua món 1,5 triệu được không?"), "affordability")
        self.assertEqual(parse_requested_amount("Mình có mua món 1,5 triệu được không?"), Decimal("1500000.0"))

    def test_recent_transaction_intent_variants_and_requested_count(self):
        router = IntentRouter()
        self.assertEqual(router.detect("Cho tôi xem 5 giao dịch gần nhất"), "recent_transactions")
        self.assertEqual(router.detect("3 giao dịch mới nhất"), "recent_transactions")
        self.assertEqual(router.detect("Show my 7 latest transactions"), "recent_transactions")
        self.assertEqual(parse_requested_count("Cho tôi xem 3 giao dịch gần nhất"), 3)
        self.assertEqual(parse_requested_count("Show my 99 latest transactions"), 10)

    def test_common_monthly_and_category_intents_are_local(self):
        router = IntentRouter()
        self.assertEqual(router.detect("Tháng này tôi đã chi bao nhiêu?"), "monthly_expense")
        self.assertEqual(router.detect("Tổng thu nhập tháng này của tôi là bao nhiêu?"), "monthly_income")
        self.assertEqual(router.detect("Tôi đã chi bao nhiêu cho Food?"), "category_spending")
        self.assertEqual(router.detect("Tôi tiêu nhiều nhất vào danh mục nào?"), "top_categories")
        self.assertEqual(router.detect("Số dư Momo của tôi còn bao nhiêu?"), "external_balance")
        self.assertEqual(router.detect("Vietcombank balance của tôi là bao nhiêu?"), "external_balance")

    def test_recent_answer_uses_actual_number_of_available_transactions(self):
        Transaction.objects.filter(user=self.user).delete()
        Transaction.objects.create(
            user=self.user, category=self.allowance_category, amount=Decimal("2"),
            type="income", description="Allowance", date=date(2026, 9, 25),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Cho tôi xem 5 giao dịch gần nhất", snapshot, "recent_transactions"
        )
        self.assertIn("chỉ có **1 giao dịch**", answer)
        self.assertIn("2 VND", answer)

    def test_category_spending_answer_is_calculated_from_current_month(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Tôi đã chi bao nhiêu cho Food?", snapshot, "category_spending"
        )
        self.assertIn("1,200,000 VND", answer)
        self.assertIn("Food", answer)

    def test_week_comparison_zero_delta_says_unchanged(self):
        Transaction.objects.filter(user=self.user, type="expense").delete()
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "7 ngày gần đây tôi chi bao nhiêu?", snapshot, "week_spending"
        )
        self.assertIn("không đổi", answer)


    def test_saving_advice_uses_exact_current_shortfall(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.monthly_allowance = Decimal("4444444")
        profile.monthly_savings_goal = Decimal("5555555")
        profile.save()
        Transaction.objects.filter(user=self.user).delete()
        Transaction.objects.create(
            user=self.user, category=self.allowance_category, amount=Decimal("2"),
            type="income", description="Allowance", date=date(2026, 9, 25),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Gợi ý tiết kiệm cho tôi", snapshot, "saving_advice"
        )
        self.assertIn("1,111,111 VND", answer)
        self.assertIn("0 VND/ngày", answer)


class FinanceAssistantAPITests(TestCase):
    def setUp(self):
        role = Role.objects.get(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(email="api@example.com", password="StrongPass123!", role=role)
        UserProfile.objects.get_or_create(user=self.user, defaults={"full_name": "API Student"})
        self.client.force_login(self.user, backend="accounts.backends.EmailAuthenticationBackend")

    def test_chat_creates_owned_session_and_messages(self):
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"How much do I have left?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatSession.objects.filter(user=self.user).count(), 1)
        self.assertEqual(ChatMessage.objects.filter(session__user=self.user).count(), 2)
        self.assertEqual(response.json()["assistant_message"]["intent"], "balance")

    def test_spendable_answer_respects_savings_goal(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.monthly_allowance = Decimal("4444444")
        profile.monthly_savings_goal = Decimal("5555555")
        profile.save()
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Tôi còn bao nhiêu tiền để tiêu?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"]["intent"], "spendable")
        self.assertIn("0 VND", payload["assistant_message"]["content"])
        self.assertIn("1,111,111 VND", payload["assistant_message"]["content"])


    def test_recent_transactions_with_one_row_does_not_fallback(self):
        category = Category.objects.create(name="Allowance API", type="income")
        Transaction.objects.create(
            user=self.user, category=category, amount=Decimal("2"),
            type="income", description="Tiny income", date=date(2026, 9, 25),
        )
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Cho tôi xem 5 giao dịch gần nhất"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"]["intent"], "recent_transactions")
        self.assertEqual(payload["source"], "campus_coin_data")
        self.assertIn("1 giao dịch", payload["assistant_message"]["content"])


    def test_external_wallet_balance_is_not_confused_with_campus_coin_balance(self):
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Số dư Momo của tôi còn bao nhiêu?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"]["intent"], "external_balance")
        self.assertEqual(payload["source"], "campus_coin_data")
        self.assertIn("không có quyền truy cập", payload["assistant_message"]["content"])

    def test_monthly_expense_and_income_do_not_need_openai(self):
        expense_category = Category.objects.create(name="Transport API", type="expense")
        income_category = Category.objects.create(name="Job API", type="income")
        Transaction.objects.create(
            user=self.user, category=expense_category, amount=Decimal("300000"),
            type="expense", description="Bus", date=date(2026, 9, 25),
        )
        Transaction.objects.create(
            user=self.user, category=income_category, amount=Decimal("700000"),
            type="income", description="Work", date=date(2026, 9, 25),
        )
        expense_response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Tháng này tôi đã chi bao nhiêu?"}',
            content_type="application/json",
        )
        income_response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Tổng thu nhập tháng này của tôi là bao nhiêu?"}',
            content_type="application/json",
        )
        self.assertEqual(expense_response.json()["assistant_message"]["intent"], "monthly_expense")
        self.assertEqual(expense_response.json()["source"], "campus_coin_data")
        self.assertIn("300,000 VND", expense_response.json()["assistant_message"]["content"] )
        self.assertEqual(income_response.json()["assistant_message"]["intent"], "monthly_income")
        self.assertEqual(income_response.json()["source"], "campus_coin_data")
        self.assertIn("700,000 VND", income_response.json()["assistant_message"]["content"] )



class FinanceAssistantPageAndPrivacyTests(TestCase):
    def setUp(self):
        role = Role.objects.get(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(email="owner@example.com", password="StrongPass123!", role=role)
        self.other = User.objects.create_user(email="other@example.com", password="StrongPass123!", role=role)
        self.client.force_login(self.user, backend="accounts.backends.EmailAuthenticationBackend")

    def test_assistant_page_renders(self):
        response = self.client.get(reverse("finance_assistant:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus Coin AI")
        self.assertContains(response, "AI Assistant")

    def test_user_cannot_post_into_another_users_chat(self):
        other_session = ChatSession.objects.create(user=self.other, title="Private chat")
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data=f'{{"message":"hello","session_id":{other_session.pk}}}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_session.messages.count(), 0)


    def test_balance_uses_only_logged_in_users_data_and_refreshes_after_new_transaction(self):
        owner_profile = UserProfile.objects.get(user=self.user)
        owner_profile.monthly_allowance = Decimal("5000000")
        owner_profile.monthly_savings_goal = Decimal("0")
        owner_profile.save()
        other_profile = UserProfile.objects.get(user=self.other)
        other_profile.monthly_allowance = Decimal("99000000")
        other_profile.save()
        food = Category.objects.create(name="Privacy Food", type="expense")
        Transaction.objects.create(
            user=self.other, category=food, amount=Decimal("88000000"),
            type="expense", description="Other private expense", date=date(2026, 9, 25),
        )
        first = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Tôi còn bao nhiêu tiền?"}',
            content_type="application/json",
        ).json()
        self.assertIn("5,000,000 VND", first["assistant_message"]["content"])
        self.assertNotIn("99,000,000", first["assistant_message"]["content"])
        Transaction.objects.create(
            user=self.user, category=food, amount=Decimal("100000"),
            type="expense", description="My expense", date=date(2026, 9, 25),
        )
        second = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Tôi còn bao nhiêu tiền?"}',
            content_type="application/json",
        ).json()
        self.assertIn("4,900,000 VND", second["assistant_message"]["content"])

    def test_affordability_uses_savings_buffer(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.monthly_allowance = Decimal("3000000")
        profile.monthly_savings_goal = Decimal("1000000")
        profile.save()
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Mình có mua món 500k được không?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"]["intent"], "affordability")
        self.assertIn("500,000 VND", payload["assistant_message"]["content"])
