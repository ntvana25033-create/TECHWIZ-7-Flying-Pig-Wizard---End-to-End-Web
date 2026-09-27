from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserProfile
from transactions.models import Category, Transaction

from .models import ChatMessage, ChatSession
from .services import (
    CampusCoinAssistant,
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
        profile.currency_code = "USD"
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

    def test_usd_amount_parser_preserves_cents_and_thousands(self):
        self.assertEqual(parse_requested_amount("Can I afford a $30.50 purchase?"), Decimal("30.50"))
        self.assertEqual(parse_requested_amount("Can I afford a $1,200.50 purchase?"), Decimal("1200.50"))
        self.assertEqual(parse_requested_amount("Can I afford USD 75.25?"), Decimal("75.25"))
        self.assertEqual(parse_requested_amount("Can I afford 1.5k?"), Decimal("1500.0"))
        self.assertEqual(parse_requested_amount("Can I afford 2 tickets at $30 each?"), Decimal("30"))

    def test_month_comparison_uses_same_period_not_full_previous_month(self):
        food = Category.objects.get(name="Food", type="expense")
        Transaction.objects.create(
            user=self.user, category=food, amount=Decimal("600000"),
            type="expense", description="Previous comparable", date=date(2026, 8, 10),
        )
        Transaction.objects.create(
            user=self.user, category=food, amount=Decimal("900000"),
            type="expense", description="Previous late month", date=date(2026, 8, 28),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.assertEqual(snapshot.previous_month_expense, Decimal("1500000"))
        self.assertEqual(snapshot.current_period_expense, Decimal("1200000"))
        self.assertEqual(snapshot.previous_period_expense, Decimal("600000"))
        self.assertEqual(snapshot.expense_change_percent, Decimal("100"))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Compare my spending with last month", snapshot, "compare_month"
        )
        self.assertIn("through the same day", answer)
        self.assertIn("100.0% higher", answer)

    def test_common_typo_can_still_match_supported_intent(self):
        router = IntentRouter()
        self.assertEqual(router.detect("how much did i spnd this mnth"), "monthly_expense")

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

    def test_smart_coach_intents_are_detected_locally(self):
        router = IntentRouter()
        self.assertEqual(router.detect("Analyze my finances and give me smart insights"), "smart_insights")
        self.assertEqual(router.detect("Am I overspending this month?"), "spending_risk")
        self.assertEqual(router.detect("Make me a plan for the rest of the month"), "rest_of_month_plan")

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
        self.assertIn("only **1 transaction**", answer)
        self.assertIn("$2.00", answer)

    def test_category_spending_answer_is_calculated_from_current_month(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Tôi đã chi bao nhiêu cho Food?", snapshot, "category_spending"
        )
        self.assertIn("$1,200,000.00", answer)
        self.assertIn("Food", answer)

    def test_week_comparison_zero_delta_says_unchanged(self):
        Transaction.objects.filter(user=self.user, type="expense").delete()
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "7 ngày gần đây tôi chi bao nhiêu?", snapshot, "week_spending"
        )
        self.assertIn("no change", answer)


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
        self.assertIn("$1,111,111.00", answer)
        self.assertIn("$0.00/day", answer)

    def test_smart_insights_explain_budget_savings_and_action(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Analyze my finances", snapshot, "smart_insights"
        )
        self.assertIn("Smart insights", answer)
        self.assertIn("Budget use", answer)
        self.assertIn("Savings", answer)
        self.assertIn("Action now", answer)

    def test_rest_of_month_plan_uses_safe_daily_budget(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Make me a plan for the rest of the month", snapshot, "rest_of_month_plan"
        )
        self.assertIn("Rest-of-month action plan", answer)
        self.assertIn("Daily guardrail", answer)
        self.assertIn("Best place to review", answer)

    def test_spending_risk_returns_explained_level(self):
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = DeterministicFinanceAssistant().answer(
            self.user, "Am I overspending?", snapshot, "spending_risk"
        )
        self.assertIn("Current overspending risk", answer)
        self.assertIn("practical guardrail", answer)


    def test_greeting_explains_capabilities_and_scope(self):
        assistant = CampusCoinAssistant()
        result = assistant.reply(self.user, "hello")
        self.assertEqual(result["intent"], "greeting")
        self.assertEqual(result["source"], "assistant_capabilities")
        self.assertIn("Campus Coin AI", result["answer"])
        self.assertIn("outside my scope", result["answer"])
        self.assertEqual(result["snapshot"], {})

    def test_unrelated_question_is_rejected_as_out_of_scope(self):
        assistant = CampusCoinAssistant()
        result = assistant.reply(self.user, "Tell me a joke about cats")
        self.assertEqual(result["intent"], "out_of_scope")
        self.assertEqual(result["source"], "scope_guard")
        self.assertIn("outside my scope", result["answer"])
        self.assertEqual(result["snapshot"], {})

    def test_finance_question_not_supported_by_campus_coin_is_not_guessed(self):
        assistant = CampusCoinAssistant()
        result = assistant.reply(self.user, "Can my Campus Coin budget tell me which stock to buy?")
        self.assertEqual(result["intent"], "unsupported_finance")
        self.assertIn("cannot answer it reliably", result["answer"])

    def test_data_scope_question_does_not_expose_external_data(self):
        assistant = CampusCoinAssistant()
        result = assistant.reply(self.user, "What data can you access?")
        self.assertEqual(result["intent"], "data_scope")
        self.assertIn("signed-in Campus Coin account", result["answer"])
        self.assertIn("do **not** have live access", result["answer"])

    def test_short_follow_up_uses_previous_supported_context(self):
        assistant = CampusCoinAssistant()
        history = [
            {"role": "user", "content": "Can I afford a 500k purchase?"},
            {"role": "assistant", "content": "Previous answer"},
        ]
        intent, resolved = assistant._resolve_contextual_intent("what about 700k?", history)
        self.assertEqual(intent, "affordability")
        self.assertIn("700k", resolved)


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
        self.assertIn("$0.00", payload["assistant_message"]["content"])
        self.assertIn("$1,111,111.00", payload["assistant_message"]["content"])


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
        self.assertIn("1 transaction", payload["assistant_message"]["content"])


    def test_external_wallet_balance_is_not_confused_with_campus_coin_balance(self):
        response = self.client.post(
            reverse("finance_assistant:api-chat"),
            data='{"message":"Số dư Momo của tôi còn bao nhiêu?"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant_message"]["intent"], "external_balance")
        self.assertEqual(payload["source"], "scope_guard")
        self.assertIn("cannot access live", payload["assistant_message"]["content"])

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
        self.assertIn("$300,000.00", expense_response.json()["assistant_message"]["content"] )
        self.assertEqual(income_response.json()["assistant_message"]["intent"], "monthly_income")
        self.assertEqual(income_response.json()["source"], "campus_coin_data")
        self.assertIn("$700,000.00", income_response.json()["assistant_message"]["content"] )



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

    def test_assistant_page_uses_preset_questions_without_free_text_input(self):
        response = self.client.get(reverse("finance_assistant:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preset questions only")
        self.assertNotContains(response, "data-chat-form")
        self.assertNotContains(response, "<textarea")
        self.assertContains(response, 'data-prompt="What can you do?"')

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
        self.assertIn("$5,000,000.00", first["assistant_message"]["content"])
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
        self.assertIn("$4,900,000.00", second["assistant_message"]["content"])

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
        self.assertIn("$500,000.00", payload["assistant_message"]["content"])


class FinanceAssistantFullFunctionAuditTests(TestCase):
    """Audit every data-backed assistant feature against known database rows.

    These tests deliberately use small USD values so a wrong query or formula is
    easy to spot during `py manage.py test finance_assistant`.
    """

    def setUp(self):
        role = Role.objects.get(role_name=Role.Name.STUDENT)
        self.user = User.objects.create_user(
            email="audit@example.com",
            password="StrongPass123!",
            role=role,
        )
        profile, _ = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={"full_name": "Audit Student"},
        )
        profile.monthly_allowance = Decimal("1000.00")
        profile.monthly_savings_goal = Decimal("200.00")
        profile.currency_code = "USD"
        profile.timezone = "Asia/Ho_Chi_Minh"
        profile.save()

        self.allowance = Category.objects.create(name="Allowance Audit", type="income")
        # Use the exact canonical Allowance name as well, because only canonical
        # allowance categories are excluded from counted extra income.
        self.allowance_canonical = Category.objects.create(name="Allowance", type="income")
        self.job = Category.objects.create(name="Part-time Audit", type="income")
        self.food = Category.objects.create(name="Food Audit", type="expense")
        self.transport = Category.objects.create(name="Transport Audit", type="expense")

        Transaction.objects.create(
            user=self.user,
            category=self.allowance_canonical,
            amount=Decimal("1000.00"),
            type="income",
            description="Monthly allowance",
            date=date(2026, 9, 1),
        )
        Transaction.objects.create(
            user=self.user,
            category=self.job,
            amount=Decimal("100.00"),
            type="income",
            description="Part-time pay",
            date=date(2026, 9, 5),
        )
        Transaction.objects.create(
            user=self.user,
            category=self.food,
            amount=Decimal("100.00"),
            type="expense",
            description="Groceries",
            date=date(2026, 9, 10),
        )
        Transaction.objects.create(
            user=self.user,
            category=self.food,
            amount=Decimal("20.00"),
            type="expense",
            description="Lunch",
            date=date(2026, 9, 15),
        )
        Transaction.objects.create(
            user=self.user,
            category=self.transport,
            amount=Decimal("80.00"),
            type="expense",
            description="Transport pass",
            date=date(2026, 9, 25),
        )

        # Previous-month same-period data plus a late-month row. Only the first
        # row belongs in the like-for-like percentage; both belong in the full
        # previous-month total.
        Transaction.objects.create(
            user=self.user,
            category=self.food,
            amount=Decimal("100.00"),
            type="expense",
            description="Previous comparable",
            date=date(2026, 8, 10),
        )
        Transaction.objects.create(
            user=self.user,
            category=self.food,
            amount=Decimal("50.00"),
            type="expense",
            description="Previous late month",
            date=date(2026, 8, 28),
        )

        self.snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        self.answerer = DeterministicFinanceAssistant()

    def _answer(self, intent, text):
        return self.answerer.answer(self.user, text, self.snapshot, intent)

    def test_snapshot_exact_source_values_and_formulas(self):
        s = self.snapshot
        self.assertEqual(s.monthly_allowance, Decimal("1000.00"))
        self.assertEqual(s.savings_goal, Decimal("200.00"))
        self.assertEqual(s.month_income, Decimal("1100.00"))
        self.assertEqual(s.recorded_allowance_income, Decimal("1000.00"))
        self.assertEqual(s.counted_income, Decimal("100.00"))
        self.assertEqual(s.month_expense, Decimal("200.00"))
        self.assertEqual(s.available_funds, Decimal("1100.00"))
        self.assertEqual(s.remaining_funds, Decimal("900.00"))
        self.assertEqual(s.safe_to_spend_now, Decimal("700.00"))
        self.assertEqual(s.days_remaining, 6)
        self.assertEqual(s.safe_daily_budget.quantize(Decimal("0.01")), Decimal("116.67"))
        self.assertEqual(s.avg_daily_expense, Decimal("8.00"))
        self.assertEqual(s.projected_expense, Decimal("240.00"))
        self.assertEqual(s.projected_remaining, Decimal("860.00"))
        self.assertEqual(s.previous_month_expense, Decimal("150.00"))
        self.assertEqual(s.current_period_expense, Decimal("200.00"))
        self.assertEqual(s.previous_period_expense, Decimal("100.00"))
        self.assertEqual(s.expense_change_percent, Decimal("100"))
        self.assertEqual(s.last_7_days_expense, Decimal("80.00"))
        self.assertEqual(s.previous_7_days_expense, Decimal("20.00"))
        self.assertEqual(s.month_transaction_count, 5)
        self.assertEqual(s.expense_transaction_count, 3)
        self.assertEqual(s.expense_days_count, 3)
        self.assertEqual(s.top_expense_categories[0]["category"], "Food Audit")
        self.assertEqual(Decimal(s.top_expense_categories[0]["amount"]), Decimal("120.00"))

    def test_every_advertised_data_feature_is_grounded_in_expected_values(self):
        cases = {
            "monthly_expense": ("How much did I spend this month?", ["$200.00"]),
            "monthly_income": ("How much income this month?", ["$1,100.00", "$1,000.00", "$100.00"]),
            "category_spending": ("How much did I spend on Food Audit?", ["$120.00", "60.0%"]),
            "balance": ("How much do I have left?", ["$900.00", "$1,000.00", "$100.00", "$200.00"]),
            "spendable": ("How much can I safely spend?", ["$900.00", "$200.00", "$700.00"]),
            "daily_budget": ("What is my daily budget?", ["$116.67/day", "6 days"]),
            "savings_goal": ("How is my savings goal?", ["$200.00", "$700.00 above"]),
            "affordability": ("Can I afford a $50 purchase?", ["$50.00", "$650.00"]),
            "top_categories": ("What are my top categories?", ["Food Audit", "$120.00", "Transport Audit", "$80.00"]),
            "recent_transactions": ("Show my 5 recent transactions", ["Transport pass", "$80.00"]),
            "largest_expenses": ("What are my largest expenses?", ["Groceries", "$100.00"]),
            "compare_month": ("Compare with last month", ["$200.00", "$100.00", "100.0% higher", "$150.00"]),
            "forecast": ("Forecast my month end", ["$240.00", "$860.00", "$8.00/day", "25 elapsed calendar days"]),
            "week_spending": ("How much did I spend in the last 7 days?", ["$80.00", "$20.00", "$60.00 increase"]),
            "today_spending": ("How much did I spend today?", ["$80.00"]),
            "smart_insights": ("Analyze my finances", ["$1,000.00", "$100.00", "$200.00", "$900.00"]),
            "spending_risk": ("Am I overspending?", ["Current overspending risk: LOW", "$900.00", "$200.00"]),
            "rest_of_month_plan": ("Make me a plan for the rest of the month", ["$900.00", "$700.00", "$116.67/day", "Food Audit", "60.0%"]),
            "saving_advice": ("Give me saving advice", ["$1,000.00", "$100.00", "$200.00", "Food Audit", "60.0%"]),
            "summary": ("Summarize my finances", ["$1,000.00", "$100.00", "$200.00", "$900.00", "$860.00"]),
        }
        for intent, (text, expected_fragments) in cases.items():
            with self.subTest(intent=intent):
                answer = self._answer(intent, text)
                self.assertIsNotNone(answer)
                for fragment in expected_fragments:
                    self.assertIn(fragment, answer)

    def test_all_data_intents_have_declared_sources(self):
        from .services import INTENT_DATA_SOURCES

        expected_intents = {
            "monthly_expense", "monthly_income", "category_spending", "balance",
            "spendable", "daily_budget", "savings_goal", "affordability",
            "top_categories", "recent_transactions", "largest_expenses",
            "compare_month", "forecast", "week_spending", "today_spending",
            "smart_insights", "spending_risk", "rest_of_month_plan",
            "saving_advice", "summary",
        }
        self.assertEqual(set(INTENT_DATA_SOURCES), expected_intents)
        for intent in expected_intents:
            self.assertTrue(INTENT_DATA_SOURCES[intent], intent)

    def test_forecast_refuses_to_fake_confidence_without_expense_data(self):
        Transaction.objects.filter(user=self.user, date__year=2026, date__month=9, type="expense").delete()
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = self.answerer.answer(self.user, "Forecast my month end", snapshot, "forecast")
        self.assertIn("no recorded expense transactions", answer)
        self.assertIn("will not present", answer)

    def test_forecast_marks_sparse_data_as_limited(self):
        Transaction.objects.filter(user=self.user, date__year=2026, date__month=9, type="expense").delete()
        Transaction.objects.create(
            user=self.user,
            category=self.food,
            amount=Decimal("25.00"),
            type="expense",
            description="One expense only",
            date=date(2026, 9, 25),
        )
        snapshot = FinanceContextService().build(self.user, date(2026, 9, 25))
        answer = self.answerer.answer(self.user, "Forecast my month end", snapshot, "forecast")
        self.assertIn("limited-data projection", answer)
        self.assertIn("1 expense transaction", answer)

    def test_risk_level_does_not_change_only_because_weekly_percentage_is_large(self):
        # The 7-day rise is 300%, but current and projected balances still protect
        # the savings goal. Trend is context, not an arbitrary risk trigger.
        answer = self._answer("spending_risk", "Am I overspending?")
        self.assertIn("Current overspending risk: LOW", answer)
        self.assertIn("300.0% higher", answer)
        self.assertIn("Risk levels are rule-based", answer)
