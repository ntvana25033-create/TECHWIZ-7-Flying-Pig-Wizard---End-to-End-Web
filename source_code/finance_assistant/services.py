from __future__ import annotations

import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q, Sum
from django.utils import timezone

from accounts.models import UserProfile
from transactions.models import Category, Transaction


ZERO = Decimal("0")
ALLOWANCE_CATEGORY_NAMES = (
    "Allowance",
    "Monthly Allowance",
    "Pocket Money",
    "Tro cap",
    "Trợ cấp",
)


INTENT_DATA_SOURCES = {
    "monthly_expense": (
        "transactions.Transaction.amount",
        "transactions.Transaction.type",
        "transactions.Transaction.date",
    ),
    "monthly_income": (
        "transactions.Transaction.amount",
        "transactions.Transaction.type",
        "transactions.Transaction.date",
        "accounts.UserProfile.monthly_allowance",
    ),
    "category_spending": (
        "transactions.Category.name",
        "transactions.Transaction.category",
        "transactions.Transaction.amount",
        "transactions.Transaction.type",
        "transactions.Transaction.date",
    ),
    "balance": (
        "accounts.UserProfile.monthly_allowance",
        "transactions.Transaction.amount/type/date/category",
    ),
    "spendable": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction.amount/type/date/category",
    ),
    "daily_budget": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction.amount/type/date/category",
        "calendar days remaining",
    ),
    "savings_goal": (
        "accounts.UserProfile.monthly_savings_goal",
        "accounts.UserProfile.monthly_allowance",
        "transactions.Transaction.amount/type/date/category",
    ),
    "affordability": (
        "user-entered purchase amount",
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction.amount/type/date/category",
    ),
    "top_categories": (
        "transactions.Transaction.category",
        "transactions.Transaction.amount/type/date",
    ),
    "recent_transactions": (
        "transactions.Transaction.date",
        "transactions.Transaction.amount",
        "transactions.Transaction.type",
        "transactions.Transaction.category",
        "transactions.Transaction.description",
    ),
    "largest_expenses": (
        "transactions.Transaction.date",
        "transactions.Transaction.amount",
        "transactions.Transaction.type",
        "transactions.Transaction.category",
        "transactions.Transaction.description",
    ),
    "compare_month": (
        "transactions.Transaction.amount/type/date",
        "calendar same-period comparison",
    ),
    "forecast": (
        "transactions.Transaction.amount/type/date",
        "accounts.UserProfile.monthly_allowance",
        "calendar days elapsed/in month",
    ),
    "week_spending": (
        "transactions.Transaction.amount/type/date",
        "calendar last-7-day windows",
    ),
    "today_spending": (
        "transactions.Transaction.amount/type/date",
        "accounts.UserProfile.timezone",
    ),
    "smart_insights": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction amount/type/date/category",
    ),
    "spending_risk": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction amount/type/date",
    ),
    "rest_of_month_plan": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction amount/type/date/category",
        "calendar days remaining",
    ),
    "saving_advice": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction amount/type/date/category",
    ),
    "summary": (
        "accounts.UserProfile.monthly_allowance",
        "accounts.UserProfile.monthly_savings_goal",
        "transactions.Transaction amount/type/date/category",
    ),
}


def _allowance_category_q() -> Q:
    query = Q()
    for name in ALLOWANCE_CATEGORY_NAMES:
        query |= Q(category__name__iexact=name)
    return query


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _sum_type(queryset, transaction_type: str) -> Decimal:
    return _dec(
        queryset.filter(type=transaction_type).aggregate(total=Sum("amount"))["total"]
    )


def _previous_month(reference: date) -> tuple[date, date]:
    first = reference.replace(day=1)
    previous_end = first - timedelta(days=1)
    return previous_end.replace(day=1), previous_end


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    normalized = "".join(
        ch for ch in normalized if unicodedata.category(ch) != "Mn"
    )
    normalized = normalized.replace("đ", "d")
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_for_intent(text: str) -> str:
    q = _normalize(text).replace("’", "'")
    contraction_replacements = {
        r"\bwhat's\b": "what is",
        r"\bwhats\b": "what is",
        r"\bhow's\b": "how is",
        r"\bhows\b": "how is",
        r"\bi'm\b": "i am",
        r"\bcan't\b": "cannot",
        r"\bcant\b": "cannot",
        r"\bdon't\b": "do not",
        r"\bdont\b": "do not",
        r"\bwon't\b": "will not",
        r"\bwont\b": "will not",
    }
    for pattern, replacement in contraction_replacements.items():
        q = re.sub(pattern, replacement, q)

    q = re.sub(r"[^a-z0-9\s]", " ", q)
    token_replacements = {
        "im": "i am",
        "u": "you",
        "ur": "your",
        "pls": "please",
        "plz": "please",
        "thx": "thanks",
        "wanna": "want",
        "gonna": "going",
    }
    tokens = [token_replacements.get(token, token) for token in q.split()]
    return " ".join(tokens)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _contains_any(text: str, phrases: tuple[str, ...] | list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _is_help_request(text: str) -> bool:
    q = _normalize_for_intent(text)
    if not q:
        return False

    if q in {"can i help you", "may i help you", "how can i help you"}:
        return False

    finance_terms = {
        "save",
        "saving",
        "savings",
        "money",
        "budget",
        "spend",
        "spending",
        "expense",
        "expenses",
        "income",
        "transaction",
        "transactions",
        "purchase",
        "afford",
        "balance",
        "food",
        "transport",
        "shopping",
    }
    words = set(q.split())
    if len(words) >= 4 and words.intersection(finance_terms):
        return False

    help_examples = (
        "help",
        "help me",
        "help please",
        "please help",
        "can you help",
        "can you help me",
        "could you help me",
        "will you help me",
        "how can you help",
        "how can you help me",
        "what can you do",
        "what do you do",
        "what can i ask",
        "what can i ask you",
        "what should i ask you",
        "show me what you can do",
        "tell me what you can do",
        "what can you help me with",
        "what can you help with",
        "what are your capabilities",
        "what are your features",
        "show your features",
        "show your capabilities",
        "capabilities",
        "features",
    )

    if q in help_examples:
        return True

    if len(q.split()) <= 9:
        best_score = max(_similarity(q, example) for example in help_examples)
        if best_score >= 0.72:
            return True

    return False


DATA_SCOPE_EXAMPLES = (
    "what data can you access",
    "what data do you use",
    "what can you see",
    "where do your answers come from",
    "do you access my bank",
    "can you access my bank",
    "do you use live bank data",
    "what is your scope",
    "what are your limits",
    "what can you answer",
    "what can you not answer",
)

IN_SCOPE_TERMS = (
    "campus coin",
    "transaction", "transactions",
    "expense", "expenses",
    "income",
    "budget",
    "allowance",
    "saving", "savings",
    "spend", "spending",
    "purchase",
    "category", "categories",
    "balance",
    "money left",
    "remaining funds",
    "daily limit",
    "monthly summary",
    "forecast",
    "giao dich", "chi tieu", "thu nhap", "ngan sach", "tiet kiem",
    "so du", "danh muc", "tro cap", "con bao nhieu tien",
)


def _is_data_scope_request(text: str) -> bool:
    q = _normalize_for_intent(text)
    if q in DATA_SCOPE_EXAMPLES:
        return True
    if len(q.split()) <= 10:
        return max((_similarity(q, example) for example in DATA_SCOPE_EXAMPLES), default=0) >= 0.76
    return False


def _looks_in_scope_but_unsupported(text: str) -> bool:
    q = _normalize_for_intent(text)
    return _contains_any(q, IN_SCOPE_TERMS)


FUZZY_INTENT_EXAMPLES = {
    "balance": (
        "how much money do i have left",
        "what is my remaining balance",
        "how much budget is left this month",
    ),
    "monthly_expense": (
        "how much did i spend this month",
        "total expenses this month",
        "monthly spending",
    ),
    "monthly_income": (
        "how much income this month",
        "total income this month",
        "how much did i earn this month",
    ),
    "recent_transactions": (
        "show my recent transactions",
        "show latest transactions",
        "transaction history",
    ),
    "daily_budget": (
        "what is my daily budget",
        "how much can i spend per day",
        "daily spending limit",
    ),
    "savings_goal": (
        "how is my savings goal",
        "am i on track with my savings",
        "how much more do i need to save",
    ),
    "forecast": (
        "forecast my month end balance",
        "how much will i have left at month end",
        "project my spending",
    ),
    "summary": (
        "summarize my finances",
        "financial summary",
        "give me a budget overview",
    ),
    "smart_insights": (
        "analyze my finances",
        "give me smart insights",
        "what should i notice about my spending",
        "what is important in my finances",
    ),
    "rest_of_month_plan": (
        "make me a plan for the rest of the month",
        "make me a spending plan",
        "how should i manage the rest of this month",
        "what should i do for the rest of the month",
    ),
    "spending_risk": (
        "am i overspending",
        "is my spending risky",
        "check my spending risk",
        "do i need to slow down spending",
    ),
}


def _fuzzy_supported_intent(text: str) -> str | None:
    q = _normalize_for_intent(text)
    words = q.split()
    if not q or len(words) > 12:
        return None

    best_intent = None
    best_score = 0.0
    for intent, examples in FUZZY_INTENT_EXAMPLES.items():
        for example in examples:
            score = _similarity(q, example)
            if score > best_score:
                best_score = score
                best_intent = intent

    # A high threshold helps recover common typos without turning the assistant
    # into a general-purpose chatbot.
    return best_intent if best_score >= 0.80 else None


def format_money(value: Decimal, currency: str = "USD") -> str:
    amount = _dec(value)
    code = (currency or "USD").upper()
    if code == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {code}"


def _parse_money_number(raw_number: str) -> Decimal | None:
    """Parse a user-entered money number without silently dropping cents.

    Campus Coin is USD-based, but users may type either 1,234.56 or 1234,56.
    A single separator followed by exactly three digits is treated as a thousands
    separator; one or two trailing digits are treated as decimals.
    """
    raw = (raw_number or "").strip().replace(" ", "")
    if not raw or not re.search(r"\d", raw):
        return None

    # Keep digits and separators only. Currency symbols/words are handled by the caller.
    raw = re.sub(r"[^0-9.,]", "", raw)
    if not raw:
        return None

    try:
        if "," in raw and "." in raw:
            # Whichever separator appears last is the decimal mark when it has
            # one or two trailing digits (1,234.56 / 1.234,56).
            last_comma = raw.rfind(",")
            last_dot = raw.rfind(".")
            decimal_sep = "," if last_comma > last_dot else "."
            thousands_sep = "." if decimal_sep == "," else ","
            tail = raw.rsplit(decimal_sep, 1)[1]
            if 1 <= len(tail) <= 2:
                normalized = raw.replace(thousands_sep, "").replace(decimal_sep, ".")
            else:
                normalized = raw.replace(",", "").replace(".", "")
        elif "," in raw or "." in raw:
            sep = "," if "," in raw else "."
            parts = raw.split(sep)
            if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
                normalized = parts[0] + "." + parts[1]
            elif len(parts) > 2 and 1 <= len(parts[-1]) <= 2:
                normalized = "".join(parts[:-1]) + "." + parts[-1]
            else:
                normalized = "".join(parts)
        else:
            normalized = raw

        return Decimal(normalized)
    except Exception:
        return None


def parse_requested_amount(text: str) -> Decimal | None:
    normalized = _normalize(text)

    # Prefer amounts explicitly marked as USD/$ or using k/m suffixes. This avoids
    # accidentally treating unrelated counts (e.g. "2 tickets") as the price.
    marked_pattern = re.compile(
        r"(?:(\$|usd)\s*)?(\d[\d., ]*)\s*"
        r"(million|mil|m|thousand|k|trieu|tr|nghin|ngan)?\s*(usd)?",
        re.IGNORECASE,
    )
    candidates = []
    for match in marked_pattern.finditer(normalized):
        prefix_currency, raw_number, suffix, usd_after = match.groups()
        explicitly_marked = bool(prefix_currency or suffix or usd_after)
        candidates.append((match.start(), raw_number, (suffix or "").lower(), explicitly_marked))

    if not candidates:
        return None

    marked = [item for item in candidates if item[3]]
    ordered = marked if marked else candidates

    # For an ordinary affordability question, the first price-like number is a
    # safer default than the last number (which may be a quantity or day count).
    for _, raw_number, suffix, _ in ordered:
        number = _parse_money_number(raw_number)
        if number is None:
            continue

        multiplier = Decimal("1")
        if suffix in {"million", "mil", "m", "trieu", "tr"}:
            multiplier = Decimal("1000000")
        elif suffix in {"thousand", "k", "nghin", "ngan"}:
            multiplier = Decimal("1000")

        amount = number * multiplier
        if amount > ZERO:
            return amount

    return None


def parse_requested_count(text: str, default: int = 5, maximum: int = 10) -> int:
    q = _normalize_for_intent(text)
    if not _contains_any(q, ("transaction", "transactions", "giao dich")):
        return default

    match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", q)
    if not match:
        return default

    try:
        return max(1, min(int(match.group(1)), maximum))
    except (TypeError, ValueError):
        return default

@dataclass
class FinancialSnapshot:
    reference_date: date
    currency: str
    monthly_allowance: Decimal
    savings_goal: Decimal
    month_income: Decimal
    counted_income: Decimal
    recorded_allowance_income: Decimal
    month_expense: Decimal
    available_funds: Decimal
    remaining_funds: Decimal
    protected_savings_buffer: Decimal
    safe_to_spend_now: Decimal
    safe_daily_budget: Decimal
    days_remaining: int
    days_in_month: int
    days_elapsed: int
    month_transaction_count: int
    expense_transaction_count: int
    expense_days_count: int
    avg_daily_expense: Decimal
    projected_expense: Decimal
    projected_remaining: Decimal
    previous_month_expense: Decimal
    current_period_expense: Decimal
    previous_period_expense: Decimal
    comparison_day: int
    expense_change_percent: Decimal | None
    last_7_days_expense: Decimal
    previous_7_days_expense: Decimal
    top_expense_categories: list[dict]
    recent_transactions: list[dict]
    largest_expenses: list[dict]

    def as_dict(self) -> dict:
        def money(value):
            return str(_dec(value).quantize(Decimal("0.01")))

        return {
            "reference_date": self.reference_date.isoformat(),
            "currency": self.currency,
            "monthly_allowance": money(self.monthly_allowance),
            "monthly_income": money(self.month_income),
            "counted_extra_income": money(self.counted_income),
            "recorded_allowance_income": money(
                self.recorded_allowance_income
            ),
            "monthly_expense": money(self.month_expense),
            "available_funds": money(self.available_funds),
            "remaining_funds": money(self.remaining_funds),
            "savings_goal": money(self.savings_goal),
            "amount_above_savings_goal": money(
                self.protected_savings_buffer
            ),
            "savings_goal_shortfall": money(
                max(-self.protected_savings_buffer, ZERO)
            ),
            "safe_to_spend_while_preserving_goal": money(
                self.safe_to_spend_now
            ),
            "safe_daily_budget_to_preserve_goal": money(
                self.safe_daily_budget
            ),
            "days_remaining_in_month_including_today": self.days_remaining,
            "days_elapsed_in_month": self.days_elapsed,
            "month_transaction_count": self.month_transaction_count,
            "expense_transaction_count": self.expense_transaction_count,
            "expense_days_count": self.expense_days_count,
            "average_daily_expense_so_far": money(
                self.avg_daily_expense
            ),
            "projected_month_expense": money(self.projected_expense),
            "projected_month_remaining": money(
                self.projected_remaining
            ),
            "previous_month_expense": money(
                self.previous_month_expense
            ),
            "current_month_same_period_expense": money(
                self.current_period_expense
            ),
            "previous_month_same_period_expense": money(
                self.previous_period_expense
            ),
            "comparison_day": self.comparison_day,
            "expense_change_percent": (
                str(
                    self.expense_change_percent.quantize(
                        Decimal("0.1")
                    )
                )
                if self.expense_change_percent is not None
                else None
            ),
            "last_7_days_expense": money(self.last_7_days_expense),
            "previous_7_days_expense": money(
                self.previous_7_days_expense
            ),
            "top_expense_categories": self.top_expense_categories,
            "recent_transactions": self.recent_transactions,
            "largest_expenses": self.largest_expenses,
        }


class FinanceContextService:
    def build(
        self, user, reference_date: date | None = None
    ) -> FinancialSnapshot:
        profile = UserProfile.objects.filter(user=user).first()

        if reference_date is None:
            profile_timezone = getattr(profile, "timezone", "") if profile is not None else ""
            if profile_timezone:
                try:
                    reference_date = timezone.localdate(timezone=ZoneInfo(profile_timezone))
                except (ZoneInfoNotFoundError, ValueError):
                    reference_date = timezone.localdate()
            else:
                reference_date = timezone.localdate()

        month_start = reference_date.replace(day=1)
        month_end = reference_date.replace(
            day=monthrange(
                reference_date.year, reference_date.month
            )[1]
        )

        month_qs = Transaction.objects.filter(
            user=user,
            date__range=(month_start, reference_date),
        ).select_related("category")

        income = _sum_type(month_qs, "income")
        expense = _sum_type(month_qs, "expense")

        if profile is not None:
            allowance = _dec(profile.monthly_allowance)
            savings_goal = _dec(profile.monthly_savings_goal)
            currency = (profile.currency_code or "USD").upper()
        else:
            allowance = ZERO
            savings_goal = ZERO
            currency = "USD"

        recorded_allowance_income = _dec(
            month_qs.filter(type="income")
            .filter(_allowance_category_q())
            .aggregate(total=Sum("amount"))["total"]
        )

        counted_income = (
            max(income - recorded_allowance_income, ZERO)
            if allowance > ZERO
            else income
        )

        available = allowance + counted_income
        remaining = available - expense
        safe_to_spend = max(remaining - savings_goal, ZERO)

        days_remaining = max(
            (month_end - reference_date).days + 1, 1
        )
        safe_daily = safe_to_spend / Decimal(days_remaining)

        days_elapsed = max(reference_date.day, 1)
        month_transaction_count = month_qs.count()
        expense_transaction_count = month_qs.filter(type="expense").count()
        expense_days_count = (
            month_qs.filter(type="expense")
            .values("date")
            .distinct()
            .count()
        )
        avg_daily = expense / Decimal(days_elapsed)
        projected_expense = avg_daily * Decimal(month_end.day)
        projected_remaining = available - projected_expense

        previous_start, previous_end = _previous_month(
            reference_date
        )
        previous_expense = _dec(
            Transaction.objects.filter(
                user=user,
                type="expense",
                date__range=(previous_start, previous_end),
            ).aggregate(total=Sum("amount"))["total"]
        )

        # Compare the current partial month with the same number of calendar days
        # from the previous month. Comparing Sep 1-10 with the whole of August
        # would produce a mathematically correct percentage but a misleading one.
        comparable_day = min(reference_date.day, previous_end.day)
        current_period_end = month_start.replace(day=comparable_day)
        previous_period_end = previous_start.replace(day=comparable_day)
        current_period_expense = _dec(
            Transaction.objects.filter(
                user=user,
                type="expense",
                date__range=(month_start, current_period_end),
            ).aggregate(total=Sum("amount"))["total"]
        )
        previous_period_expense = _dec(
            Transaction.objects.filter(
                user=user,
                type="expense",
                date__range=(previous_start, previous_period_end),
            ).aggregate(total=Sum("amount"))["total"]
        )

        expense_change = None
        if previous_period_expense > ZERO:
            expense_change = (
                (current_period_expense - previous_period_expense)
                / previous_period_expense
                * Decimal("100")
            )

        week_start = reference_date - timedelta(days=6)
        previous_week_end = week_start - timedelta(days=1)
        previous_week_start = previous_week_end - timedelta(days=6)

        last_7 = _dec(
            Transaction.objects.filter(
                user=user,
                type="expense",
                date__range=(week_start, reference_date),
            ).aggregate(total=Sum("amount"))["total"]
        )

        previous_7 = _dec(
            Transaction.objects.filter(
                user=user,
                type="expense",
                date__range=(
                    previous_week_start,
                    previous_week_end,
                ),
            ).aggregate(total=Sum("amount"))["total"]
        )

        top_categories = [
            {
                "category": row["category__name"]
                or "Uncategorized",
                "amount": str(
                    _dec(row["total"]).quantize(
                        Decimal("0.01")
                    )
                ),
            }
            for row in (
                month_qs.filter(type="expense")
                .values("category__name")
                .annotate(total=Sum("amount"))
                .order_by("-total")[:5]
            )
        ]

        recent = [
            {
                "date": tx.date.isoformat(),
                "type": tx.type,
                "category": (
                    tx.category.name
                    if tx.category
                    else "Uncategorized"
                ),
                "amount": str(
                    _dec(tx.amount).quantize(
                        Decimal("0.01")
                    )
                ),
                "description": (tx.description or "")[:120],
            }
            for tx in Transaction.objects.filter(user=user)
            .select_related("category")
            .order_by("-date", "-created_at", "-id")[:10]
        ]

        largest = [
            {
                "date": tx.date.isoformat(),
                "category": (
                    tx.category.name
                    if tx.category
                    else "Uncategorized"
                ),
                "amount": str(
                    _dec(tx.amount).quantize(
                        Decimal("0.01")
                    )
                ),
                "description": (tx.description or "")[:120],
            }
            for tx in month_qs.filter(type="expense")
            .order_by("-amount", "-date")[:5]
        ]

        return FinancialSnapshot(
            reference_date=reference_date,
            currency=currency,
            monthly_allowance=allowance,
            savings_goal=savings_goal,
            month_income=income,
            counted_income=counted_income,
            recorded_allowance_income=recorded_allowance_income,
            month_expense=expense,
            available_funds=available,
            remaining_funds=remaining,
            protected_savings_buffer=remaining - savings_goal,
            safe_to_spend_now=safe_to_spend,
            safe_daily_budget=safe_daily,
            days_remaining=days_remaining,
            days_in_month=month_end.day,
            days_elapsed=days_elapsed,
            month_transaction_count=month_transaction_count,
            expense_transaction_count=expense_transaction_count,
            expense_days_count=expense_days_count,
            avg_daily_expense=avg_daily,
            projected_expense=projected_expense,
            projected_remaining=projected_remaining,
            previous_month_expense=previous_expense,
            current_period_expense=current_period_expense,
            previous_period_expense=previous_period_expense,
            comparison_day=comparable_day,
            expense_change_percent=expense_change,
            last_7_days_expense=last_7,
            previous_7_days_expense=previous_7,
            top_expense_categories=top_categories,
            recent_transactions=recent,
            largest_expenses=largest,
        )


class IntentRouter:
    def detect(self, text: str) -> str:
        q = _normalize_for_intent(text)

        if q in {
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "xin chao", "chao", "chao ban",
        } or q.startswith(("hi ", "hello ", "hey ", "xin chao ", "chao ban ")):
            return "greeting"

        if _is_help_request(text) or _contains_any(
            q, ("ban lam duoc gi", "ban co the lam gi", "giup toi", "huong dan toi")
        ):
            return "help"

        if _is_data_scope_request(text) or _contains_any(
            q, ("du lieu nao", "truy cap du lieu", "gioi han cua ban", "pham vi cua ban")
        ):
            return "data_scope"

        if _contains_any(q, (
            "daily budget", "daily spending budget", "daily spending limit", "daily limit",
            "per day", "per day budget", "spend each day", "spend per day", "spend a day",
            "how much should i spend daily", "how much should i spend each day",
            "how much can i spend each day", "how much can i spend per day",
            "what should my daily budget be",
            "ngan sach moi ngay", "ngan sach hang ngay", "moi ngay tieu bao nhieu",
            "mot ngay tieu bao nhieu", "gioi han chi moi ngay", "gioi han tieu moi ngay",
            "tieu bao nhieu moi ngay", "tieu bao nhieu mot ngay",
        )):
            return "daily_budget"

        if _contains_any(q, (
            "can i afford", "could i afford", "can i buy", "should i buy", "is it safe to buy",
            "is it safe to spend", "can i spend", "could i spend", "do i have enough for",
            "do i have enough money for", "does this fit my budget", "will this affect my savings",
            "will this hurt my savings", "purchase fit my budget", "purchase affect my savings",
            "purchase affects my savings", "buying this affect my savings",
            "co mua", "mua mon", "mua duoc khong", "co nen mua", "co du tien mua",
            "co du tien de mua", "chi duoc khong", "tieu duoc khong",
        )) and (
            parse_requested_amount(text) is not None
            or _contains_any(q, ("can i afford", "can i buy", "should i buy"))
        ):
            return "affordability"

        external_account_terms = (
            "vietcombank", "vietinbank", "bidv", "agribank", "techcombank", "mb bank", "mbbank",
            "acb", "sacombank", "vpbank", "tpbank", "momo", "zalopay", "zalo pay", "shopeepay",
            "bank account", "e wallet", "wallet balance", "vi dien tu", "tai khoan ngan hang",
        )
        if _contains_any(q, external_account_terms) and _contains_any(q, (
            "balance", "how much", "have left", "remaining", "money left",
            "so du", "bao nhieu", "con bao nhieu", "con lai", "con tien",
        )):
            return "external_balance"

        if _contains_any(q, (
            "safe to spend", "safely spend", "spendable", "how much can i spend",
            "how much can i still spend", "how much money can i spend",
            "how much money can i still spend", "what can i spend", "what can i safely spend",
            "available to spend", "money available to spend", "safe spending limit", "spending room",
            "spending allowance", "spend without affecting my savings", "spend without hurting my savings",
            "con bao nhieu tien de tieu", "con bao nhieu de tieu", "tien de tieu",
            "co the tieu bao nhieu", "tieu them bao nhieu", "chi them bao nhieu",
            "tieu ma van tiet kiem", "tieu an toan",
        )):
            return "spendable"

        if _contains_any(q, (
            "forecast", "projection", "projected", "month end", "month end balance", "end of month",
            "end of the month", "how much will i have left", "how much money will i have left",
            "what will i have left", "how much will remain", "project my spending", "project my balance",
            "forecast my spending", "forecast my balance", "du bao", "cuoi thang con bao nhieu",
            "du kien cuoi thang", "du kien chi tieu",
        )):
            return "forecast"

        if _contains_any(q, (
            "how much money do i have left", "how much do i have left", "how much have i got left",
            "how much is left", "how much money is left", "what is my balance", "what is my remaining balance",
            "remaining balance", "remaining budget", "budget left", "money left", "funds left",
            "available funds", "current balance", "how much do i have", "what do i have available",
            "how much budget is left", "how much is left this month", "what is left in my budget", "balance",
            "toi con bao nhieu tien", "minh con bao nhieu tien", "thang nay toi con bao nhieu",
            "thang nay con bao nhieu", "con bao nhieu tien", "con bao nhieu", "con lai bao nhieu",
            "so tien con lai", "ngan sach con lai",
        )):
            return "balance"

        if _contains_any(q, (
            "savings goal", "saving goal", "savings target", "saving target", "am i on track",
            "am i on track with my savings", "am i meeting my savings goal",
            "how far am i from my savings goal", "how much am i short of my savings goal",
            "how much more do i need to save", "protect my savings goal", "reach my savings goal",
            "muc tieu tiet kiem", "chi tieu tiet kiem", "con thieu bao nhieu de tiet kiem",
            "du muc tieu tiet kiem", "bao ve muc tieu tiet kiem",
        )):
            return "savings_goal"

        if _contains_any(q, (
            "recent transaction", "recent transactions", "latest transaction", "latest transactions",
            "last transaction", "last transactions", "transaction history", "show my transactions",
            "show me my transactions", "show recent activity", "recent activity", "transaction list",
            "giao dich gan nhat", "giao dich moi nhat", "xem giao dich", "lich su giao dich",
            "cho toi xem giao dich", "cac giao dich gan day", "giao dich gan day",
        )):
            return "recent_transactions"
        if re.search(r"\b\d{1,2}\s+(latest|recent|last)?\s*transactions?\b", q):
            return "recent_transactions"
        if re.search(r"\b\d{1,2}\s+giao dich\s+(gan nhat|moi nhat|gan day)\b", q):
            return "recent_transactions"

        if _contains_any(q, (
            "largest expense", "largest expenses", "biggest expense", "biggest expenses",
            "highest expense", "highest expenses", "most expensive transaction", "most expensive purchase",
            "largest purchase", "biggest purchase", "khoan chi lon nhat", "chi tieu lon nhat",
            "giao dich chi lon nhat", "mon mua dat nhat",
        )):
            return "largest_expenses"

        if _contains_any(q, (
            "top category", "top categories", "highest spending category", "highest spending categories",
            "spend the most", "spending the most", "where is my money going", "where does my money go",
            "where am i spending the most", "spending breakdown", "expense breakdown", "expenses by category",
            "spending by category", "which category", "most money on",
            "tieu nhieu nhat", "chi nhieu nhat", "danh muc nao", "danh muc chi nhieu nhat",
            "tieu vao danh muc nao", "chi vao danh muc nao",
        )):
            return "top_categories"

        if _contains_any(q, (
            "how much did i spend on", "how much have i spent on", "how much do i spend on",
            "how much am i spending on", "spent on", "spend on", "spending on", "expenses for",
            "expense for", "expenses on", "expense on",
            "chi bao nhieu cho", "tieu bao nhieu cho", "da chi bao nhieu cho", "da tieu bao nhieu cho",
            "chi cho", "tieu cho",
        )):
            return "category_spending"

        if _contains_any(q, (
            "how much have i spent this month", "how much did i spend this month",
            "how much am i spending this month", "what have i spent this month", "what did i spend this month",
            "monthly expenses", "monthly expense", "monthly spending", "total expenses this month",
            "total expense this month", "total spending this month", "spending this month", "expenses this month",
            "spent this month", "how much money have i spent this month",
            "thang nay toi da chi bao nhieu", "thang nay da chi bao nhieu", "thang nay toi chi bao nhieu",
            "chi bao nhieu thang nay", "tong chi thang nay", "tong chi tieu thang nay",
            "chi tieu thang nay", "tieu thang nay", "chi thang nay",
        )):
            return "monthly_expense"

        if _contains_any(q, (
            "monthly income", "income this month", "total income this month", "how much income",
            "how much have i earned", "how much did i earn", "how much have i earned this month",
            "how much did i earn this month", "how much money did i receive this month",
            "how much have i received this month", "money received this month", "earned this month",
            "received this month", "thu nhap thang nay", "tong thu nhap thang nay", "tong thu nhap",
            "thang nay thu nhap", "kiem duoc bao nhieu thang nay", "nhan duoc bao nhieu thang nay",
        )):
            return "monthly_income"

        if _contains_any(q, (
            "compare with last month", "compare to last month", "compare my spending with last month",
            "compare my spending to last month", "previous month", "last month comparison",
            "am i spending more than last month", "am i spending less than last month",
            "spending versus last month", "spending vs last month", "so voi thang truoc",
            "so sanh thang truoc", "thang nay voi thang truoc", "chi tieu so voi thang truoc",
        )):
            return "compare_month"

        if _contains_any(q, (
            "last 7 days", "past 7 days", "this week", "weekly spending", "spending this week",
            "spent this week", "how much did i spend this week", "how much have i spent this week",
            "7 ngay gan day", "7 ngay vua qua", "tuan nay", "chi tieu tuan nay", "chi tuan nay",
        )):
            return "week_spending"

        if _contains_any(q, (
            "today spending", "today expenses", "spending today", "expenses today", "spent today",
            "spend today", "how much did i spend today", "how much have i spent today",
            "hom nay chi bao nhieu", "hom nay tieu bao nhieu", "chi tieu hom nay", "chi hom nay",
        )):
            return "today_spending"

        if _contains_any(q, (
            "analyze my finances", "analyse my finances", "analyze my spending", "analyse my spending",
            "give me smart insights", "smart insights", "financial insights", "spending insights",
            "what should i notice", "what should i know about my finances", "what stands out",
            "tell me something useful about my spending", "analyze my money", "analyse my money",
            "phan tich tai chinh", "phan tich chi tieu", "phan tich tien cua toi", "cho toi insight",
            "co gi dang chu y", "chi tieu cua toi co gi dang chu y",
        )):
            return "smart_insights"

        if _contains_any(q, (
            "plan for the rest of the month", "plan the rest of the month", "rest of month plan",
            "make me a spending plan", "make a spending plan", "budget plan", "monthly action plan",
            "what should i do for the rest of the month", "how should i manage the rest of this month",
            "how should i spend for the rest of the month", "give me an action plan",
            "lap ke hoach chi tieu", "ke hoach phan con lai cua thang", "ke hoach cuoi thang",
            "toi nen chi tieu the nao den cuoi thang", "lap ke hoach cho toi",
        )):
            return "rest_of_month_plan"

        if _contains_any(q, (
            "am i overspending", "am i spending too fast", "am i spending too much",
            "is my spending risky", "spending risk", "check my spending risk", "risk of overspending",
            "do i need to slow down spending", "should i slow down spending", "spending warning",
            "overspending warning", "am i in danger of overspending", "budget risk",
            "toi co tieu qua tay khong", "toi co chi qua nhieu khong", "rui ro chi tieu",
            "canh bao chi tieu", "co nen giam chi tieu khong",
        )):
            return "spending_risk"

        if _contains_any(q, (
            "saving tips", "save money", "save more", "save smarter", "saving advice", "help me save",
            "help me save money", "help me save more", "how can i save", "how can i save more",
            "how do i save more", "how can i reduce spending", "help me reduce spending",
            "where can i cut spending", "what should i cut", "what should i reduce", "how can i spend less",
            "do i need to cut back", "am i spending too much", "personalized saving tips",
            "personalized savings advice", "goi y tiet kiem", "tu van tiet kiem", "lam sao de tiet kiem",
            "cach tiet kiem", "giup toi tiet kiem", "giam chi tieu", "cat giam chi tieu",
        )):
            return "saving_advice"

        if _contains_any(q, (
            "financial summary", "financial overview", "finance summary", "money summary", "budget summary",
            "summarize my finances", "summarize my financial situation", "how am i doing financially",
            "how are my finances", "financial health", "financial situation", "give me a summary",
            "give me an overview", "overview of my finances", "tom tat tai chinh", "tong quan tai chinh",
            "tinh hinh tai chinh", "tom tat chi tieu", "tong quan chi tieu",
        )):
            return "summary"

        fuzzy_intent = _fuzzy_supported_intent(text)
        if fuzzy_intent:
            return fuzzy_intent

        if _looks_in_scope_but_unsupported(text):
            return "unsupported_finance"

        return "out_of_scope"

def _match_user_expense_category(
    user, text: str
) -> str | None:
    q = _normalize_for_intent(text)
    names = list(
        Category.objects.filter(type="expense")
        .values_list("name", flat=True)
        .distinct()
    )
    names.sort(
        key=lambda name: len(_normalize_for_intent(name)),
        reverse=True,
    )

    for name in names:
        normalized_name = _normalize_for_intent(name)
        if not normalized_name:
            continue

        pattern = rf"(?<![a-z0-9]){re.escape(normalized_name)}(?![a-z0-9])"
        if re.search(pattern, q):
            return name

        tokens = [
            token
            for token in re.findall(
                r"[a-z0-9]+", normalized_name
            )
            if len(token) >= 2
        ]
        if tokens and all(
            re.search(rf"\b{re.escape(token)}\b", q)
            for token in tokens
        ):
            return name

    return None


class DeterministicFinanceAssistant:
    def answer(
        self,
        user,
        text: str,
        snapshot: FinancialSnapshot | None,
        intent: str,
    ) -> str | None:
        currency = snapshot.currency if snapshot is not None else "USD"
        money = lambda value: format_money(value, currency)

        if intent == "greeting":
            return (
                "Hi! I’m **Campus Coin AI**, a focused assistant for the finance data "
                "stored in this website. I can check your budget, income, expenses, "
                "transactions, spending categories, savings goal, safe spending limit, "
                "month-end forecast, and give **personalized money guidance based on your "
                "actual Campus Coin records**.\n\n"
                "For example, I can flag overspending risk, explain what is driving your "
                "spending, and build a practical plan for the rest of the month.\n\n"
                "Every finance answer is recalculated from your current Campus Coin Profile and "
                "Transaction records; I do not use hard-coded demo balances. "
                "I stay inside Campus Coin’s scope, so unrelated questions will be marked "
                "as outside my scope. Type **help** or **what can you do?** to see examples."
            )

        if intent == "help":
            return (
                "I’m **Campus Coin AI**. I answer questions using finance information "
                "available to your signed-in Campus Coin account.\n\n"
                "**I can help you with:**\n"
                "• Remaining monthly budget.\n"
                "• Safe-to-spend amount after protecting your savings goal.\n"
                "• Safe daily spending limit through month-end.\n"
                "• This month’s income and expenses.\n"
                "• Spending for a specific category.\n"
                "• Top spending categories and largest expenses.\n"
                "• Recent transactions.\n"
                "• Today’s spending and the last 7 days of spending.\n"
                "• Comparison with last month.\n"
                "• Month-end spending and remaining-funds forecast (a simple projection, not a guarantee).\n"
                "• Whether a specific purchase fits your current budget and savings goal.\n"
                "• A monthly financial summary and saving suggestions based on your data.\n"
                "• **Smart insights** that highlight important spending patterns from your recorded data.\n"
                "• **Overspending risk checks** using your remaining budget, savings goal, "
                "weekly trend, and projected month-end balance.\n"
                "• A **rest-of-month action plan** with a safe daily/weekly spending target.\n\n"
                "**My limits:** I do not answer unrelated general questions, jokes, coding, "
                "weather, entertainment, or other topics outside Campus Coin. I also cannot "
                "read live bank or e-wallet balances.\n\n"
                "Try: **“How much do I have left this month?”**, **“Show my 5 latest "
                "transactions”**, **“Analyze my finances”**, **“Am I overspending?”**, "
                "or **“Make me a plan for the rest of the month.”**\n\n"
                "For finance answers, I recalculate from the signed-in user's current Profile and "
                "Transaction rows each time; the buttons are not hard-coded demo responses."
            )

        if intent == "data_scope":
            return (
                "I use only the finance information available to your signed-in Campus Coin "
                "account, such as your Profile allowance and savings goal plus the transactions "
                "stored in Campus Coin. I do **not** have live access to bank accounts, e-wallets, "
                "other users’ private data, or unrelated external information."
            )

        if intent == "out_of_scope":
            return (
                "That question is **outside my scope**. I’m designed only for Campus Coin "
                "finance data and budget-related questions.\n\n"
                "You can ask me about your remaining budget, income, expenses, transactions, "
                "categories, savings goal, safe spending limit, recent activity, or month-end forecast. "
                "Type **help** to see everything I can do."
            )

        if intent == "unsupported_finance":
            return (
                "That sounds finance-related, but I cannot answer it reliably from the data "
                "Campus Coin currently stores. I only answer questions I can ground in your "
                "Campus Coin profile and transaction records.\n\n"
                "Try asking about your budget, income, expenses, categories, recent transactions, "
                "savings goal, safe-to-spend amount, or month-end forecast."
            )

        if intent == "external_balance":
            return (
                "I cannot access live bank-account or e-wallet balances. "
                "I can only calculate from records saved in Campus Coin. "
                "Try asking: **“How much do I have left in Campus Coin?”**"
            )

        if intent == "monthly_expense":
            if snapshot.month_expense <= ZERO:
                return (
                    "You have **no recorded expenses this month**, "
                    "so your current monthly spending is **$0.00**."
                )
            return (
                f"From the start of the month through "
                f"{snapshot.reference_date.isoformat()}, you have recorded "
                f"**{money(snapshot.month_expense)}** in expenses."
            )

        if intent == "monthly_income":
            if (
                snapshot.month_income <= ZERO
                and snapshot.monthly_allowance <= ZERO
            ):
                return (
                    "You have no recorded income this month, and your "
                    "Profile monthly allowance is currently 0."
                )

            parts = [
                "Recorded Transaction income this month is "
                f"**{money(snapshot.month_income)}**."
            ]
            if snapshot.monthly_allowance > ZERO:
                parts.append(
                    "Your Profile monthly allowance is "
                    f"**{money(snapshot.monthly_allowance)}**."
                )
                if snapshot.recorded_allowance_income > ZERO:
                    parts.append(
                        f"{money(snapshot.recorded_allowance_income)} in "
                        "Allowance transactions is not added a second time."
                    )
                parts.append(
                    "Extra income actually added above the allowance is "
                    f"**{money(snapshot.counted_income)}**."
                )
            return " ".join(parts)

        if intent == "category_spending":
            category_name = _match_user_expense_category(
                user, text
            )
            if not category_name:
                available_categories = list(
                    Category.objects.filter(type="expense")
                    .order_by("name")
                    .values_list("name", flat=True)[:8]
                )
                if available_categories:
                    return (
                        "I understand that you want spending for a specific "
                        "category, but I could not identify the category name. "
                        "Available examples include: **"
                        + ", ".join(available_categories)
                        + "**. Try: **“How much did I spend on Food this month?”**"
                    )
                return (
                    "There are no expense categories available to query yet."
                )

            month_start = snapshot.reference_date.replace(day=1)
            category_total = _dec(
                Transaction.objects.filter(
                    user=user,
                    type="expense",
                    category__name__iexact=category_name,
                    date__range=(
                        month_start,
                        snapshot.reference_date,
                    ),
                ).aggregate(total=Sum("amount"))["total"]
            )

            if category_total <= ZERO:
                return (
                    f"You have no recorded spending in "
                    f"**{category_name}** this month, so the current total "
                    f"for this category is **{money(ZERO)}**."
                )

            share = (
                category_total
                / snapshot.month_expense
                * Decimal("100")
                if snapshot.month_expense > ZERO
                else ZERO
            )
            return (
                f"This month you have spent **{money(category_total)}** "
                f"on **{category_name}**, about **{share:.1f}%** of your "
                "total monthly expenses."
            )

        if intent == "balance":
            if (
                snapshot.monthly_allowance <= ZERO
                and snapshot.month_income <= ZERO
                and snapshot.month_expense <= ZERO
            ):
                return (
                    "Campus Coin currently has no monthly allowance or "
                    "transactions for this month, so your estimated remaining "
                    "budget is **$0.00**. Update your Profile or add transactions "
                    "for a more useful calculation."
                )

            duplicate_note = ""
            if (
                snapshot.monthly_allowance > ZERO
                and snapshot.recorded_allowance_income > ZERO
            ):
                duplicate_note = (
                    f" Recorded Allowance transactions of "
                    f"{money(snapshot.recorded_allowance_income)} are not "
                    "added a second time because your Profile monthly allowance "
                    "already represents that monthly budget."
                )

            return (
                f"Your estimated remaining monthly budget is "
                f"**{money(snapshot.remaining_funds)}**. It is calculated as "
                f"monthly allowance {money(snapshot.monthly_allowance)} + "
                f"counted extra income {money(snapshot.counted_income)} − "
                f"expenses {money(snapshot.month_expense)}."
                f"{duplicate_note} This is Campus Coin data, not a live "
                "bank-account balance."
            )

        if intent == "spendable":
            if snapshot.remaining_funds <= ZERO:
                return (
                    "You currently have **no safe budget for additional spending**. "
                    f"Your monthly budget is at {money(snapshot.remaining_funds)}. "
                    "Prioritize pausing optional spending until income increases "
                    "or your plan changes."
                )

            if snapshot.savings_goal <= ZERO:
                return (
                    f"You have **{money(snapshot.remaining_funds)}** left to "
                    "allocate this month. You have no savings goal set, so no "
                    "savings reserve is being protected."
                )

            if snapshot.protected_savings_buffer <= ZERO:
                shortfall = (
                    snapshot.savings_goal - snapshot.remaining_funds
                )
                return (
                    f"You have **{money(snapshot.remaining_funds)}** left in "
                    f"the monthly budget, but your savings goal is "
                    f"**{money(snapshot.savings_goal)}**. Your **safe additional "
                    f"spending is currently $0.00**, and you are "
                    f"**{money(shortfall)} short** of fully protecting the goal."
                )

            return (
                f"You have **{money(snapshot.remaining_funds)}** left in the "
                f"monthly budget. After protecting your "
                f"**{money(snapshot.savings_goal)}** savings goal, you can "
                f"safely spend about **{money(snapshot.safe_to_spend_now)}** more."
            )

        if intent == "daily_budget":
            if snapshot.savings_goal > ZERO:
                if snapshot.protected_savings_buffer <= ZERO:
                    shortfall = (
                        snapshot.savings_goal
                        - snapshot.remaining_funds
                    )
                    return (
                        "Your **safe additional spending is currently "
                        f"$0.00/day** if you want to preserve the "
                        f"{money(snapshot.savings_goal)} savings goal. "
                        f"You are {money(shortfall)} short of that goal, so "
                        "prioritize pausing optional spending or adding income."
                    )

                return (
                    f"To preserve your **{money(snapshot.savings_goal)}** "
                    f"savings goal, keep spending near "
                    f"**{money(snapshot.safe_daily_budget)}/day** for the "
                    f"remaining {snapshot.days_remaining} days. You currently "
                    f"have {money(snapshot.safe_to_spend_now)} available to "
                    "spend above that goal."
                )

            even_daily = (
                max(snapshot.remaining_funds, ZERO)
                / Decimal(snapshot.days_remaining)
            )
            return (
                f"With {snapshot.days_remaining} days left and "
                f"{money(snapshot.remaining_funds)} remaining, an even daily "
                f"limit is about **{money(even_daily)}/day**. You have not "
                "set a monthly savings goal yet, so this does not reserve savings."
            )

        if intent == "savings_goal":
            gap = (
                snapshot.remaining_funds - snapshot.savings_goal
            )

            if snapshot.savings_goal <= ZERO:
                return (
                    "You have not set a monthly savings goal. Update "
                    "**Personal Profile → Monthly savings goal** so I can "
                    "calculate a safer budget."
                )

            if gap >= ZERO:
                return (
                    f"Your savings goal is "
                    f"**{money(snapshot.savings_goal)}**. Your remaining funds "
                    f"are currently **{money(gap)} above** that target, so the "
                    "goal is still protected if you avoid spending beyond that buffer."
                )

            return (
                f"Your savings goal is **{money(snapshot.savings_goal)}**, "
                f"but remaining funds are currently "
                f"**{money(abs(gap))} below** it. You would need to reduce "
                "spending or add income to get back on target."
            )

        if intent == "affordability":
            amount = parse_requested_amount(text)
            if amount is None:
                return (
                    "Please include the purchase price, for example: "
                    "**“Can I afford a $30 purchase?”**"
                )

            if amount <= snapshot.safe_to_spend_now:
                return (
                    f"Yes. **{money(amount)}** fits inside your current "
                    "safe-to-spend amount while preserving your savings goal. "
                    f"Your remaining buffer above the goal would be about "
                    f"**{money(snapshot.safe_to_spend_now - amount)}**."
                )

            if amount <= max(
                snapshot.remaining_funds, ZERO
            ):
                remaining_after = (
                    snapshot.remaining_funds - amount
                )
                goal_shortfall_after = max(
                    snapshot.savings_goal - remaining_after,
                    ZERO,
                )

                if snapshot.savings_goal > ZERO:
                    return (
                        f"You have enough Campus Coin budget to pay "
                        f"**{money(amount)}**, but it is **not safe for your "
                        f"current savings goal**. After the purchase, about "
                        f"{money(remaining_after)} would remain and you would be "
                        f"roughly **{money(goal_shortfall_after)} short** of the "
                        f"{money(snapshot.savings_goal)} goal. If the purchase is "
                        "optional, consider delaying it or choosing a lower price."
                    )

                return (
                    f"You have enough budget for **{money(amount)}** and would "
                    f"have about **{money(remaining_after)}** left. You have no "
                    "monthly savings goal set, so I cannot evaluate the purchase "
                    "against a savings target."
                )

            return (
                f"Not based on your current data: **{money(amount)}** is about "
                f"**{money(amount - snapshot.remaining_funds)}** above your "
                "estimated remaining funds."
            )

        if intent == "top_categories":
            rows = snapshot.top_expense_categories[:3]
            if not rows:
                return (
                    "There are no expenses to analyze this month yet."
                )

            parts = [
                f"{row['category']}: "
                f"{money(Decimal(row['amount']))}"
                for row in rows
            ]
            return (
                "Your highest spending categories this month are: "
                + "; ".join(parts)
                + "."
            )

        if intent == "recent_transactions":
            requested = parse_requested_count(text)
            rows = snapshot.recent_transactions[:requested]

            if not rows:
                return (
                    "You do not have any Campus Coin transactions yet. "
                    "Add a transaction first, then I can list your recent history."
                )

            lines = []
            for row in rows:
                sign = "+" if row["type"] == "income" else "−"
                label = row["description"] or row["category"]
                lines.append(
                    f"• {row['date']} — {label}: "
                    f"{sign}{money(Decimal(row['amount']))}"
                )

            shown = len(rows)
            if shown < requested:
                intro = (
                    f"You currently have only **{shown} "
                    f"transaction{'s' if shown != 1 else ''}**; "
                    "here is the recent history:\n"
                )
            else:
                intro = (
                    f"Your **{shown} most recent "
                    f"transaction{'s' if shown != 1 else ''}**:\n"
                )

            return intro + "\n".join(lines)

        if intent == "largest_expenses":
            rows = snapshot.largest_expenses[:5]
            if not rows:
                return "You have no expenses this month yet."

            lines = [
                f"• {row['date']} — "
                f"{row['description'] or row['category']}: "
                f"{money(Decimal(row['amount']))}"
                for row in rows
            ]
            return (
                "Your largest expenses this month:\n"
                + "\n".join(lines)
            )

        if intent == "compare_month":
            if snapshot.previous_period_expense <= ZERO:
                return (
                    f"You have spent {money(snapshot.current_period_expense)} through day "
                    f"{snapshot.comparison_day} this month. There is not enough spending data "
                    "from the same calendar period last month for a percentage comparison."
                )

            pct = snapshot.expense_change_percent or ZERO
            if pct == ZERO:
                return (
                    f"You have spent **{money(snapshot.current_period_expense)}** through day "
                    f"{snapshot.comparison_day} this month versus "
                    f"**{money(snapshot.previous_period_expense)}** through the same day "
                    "last month. Spending is currently **unchanged** for that like-for-like period."
                )

            direction = "higher" if pct > 0 else "lower"
            current_extra = ""
            if snapshot.reference_date.day > snapshot.comparison_day:
                current_extra = (
                    f" Current-month spending through day {snapshot.reference_date.day} is "
                    f"{money(snapshot.month_expense)}; those extra days are excluded from the percentage."
                )
            return (
                f"You have spent **{money(snapshot.current_period_expense)}** through day "
                f"{snapshot.comparison_day} this month versus "
                f"**{money(snapshot.previous_period_expense)}** through the same day "
                f"last month, about **{abs(pct):.1f}% {direction}**. "
                f"The full previous month total was {money(snapshot.previous_month_expense)}."
                f"{current_extra}"
            )

        if intent == "forecast":
            if snapshot.expense_transaction_count == 0:
                return (
                    "There are **no recorded expense transactions this month**, so Campus Coin "
                    "does not have enough spending data for a meaningful month-end forecast yet. "
                    f"The mechanical current average is {money(ZERO)}/day, but I will not present "
                    "that as a reliable prediction."
                )

            limited = snapshot.expense_transaction_count < 3 or snapshot.expense_days_count < 2
            qualifier = (
                "This is a **limited-data projection** because only "
                f"{snapshot.expense_transaction_count} expense transaction"
                f"{'s' if snapshot.expense_transaction_count != 1 else ''} across "
                f"{snapshot.expense_days_count} spending day"
                f"{'s' if snapshot.expense_days_count != 1 else ''} are recorded this month. "
                if limited
                else "This is a simple projection from recorded spending, not a guaranteed outcome. "
            )
            return (
                f"If your current recorded spending pace continues, projected month spending is "
                f"about **{money(snapshot.projected_expense)}**, leaving roughly "
                f"**{money(snapshot.projected_remaining)}** by month-end. "
                f"The calculation uses {money(snapshot.month_expense)} of expenses over "
                f"{snapshot.days_elapsed} elapsed calendar days = "
                f"{money(snapshot.avg_daily_expense)}/day, then multiplies that daily average by "
                f"{snapshot.days_in_month} days. {qualifier}"
            )

        if intent == "week_spending":
            delta = (
                snapshot.last_7_days_expense
                - snapshot.previous_7_days_expense
            )

            if delta == ZERO:
                return (
                    f"You spent **{money(snapshot.last_7_days_expense)}** in the "
                    "last 7 days, exactly the same as the previous 7 days — "
                    "**no change**."
                )

            direction = "increase" if delta > 0 else "decrease"
            return (
                f"You spent **{money(snapshot.last_7_days_expense)}** in the "
                f"last 7 days. The previous 7 days were "
                f"{money(snapshot.previous_7_days_expense)}, a "
                f"{money(abs(delta))} {direction}."
            )

        if intent == "today_spending":
            total = _dec(
                Transaction.objects.filter(
                    user=user,
                    type="expense",
                    date=snapshot.reference_date,
                ).aggregate(total=Sum("amount"))["total"]
            )
            return (
                f"You have recorded **{money(total)}** in expenses today."
            )

        if intent == "smart_insights":
            if (
                snapshot.monthly_allowance <= ZERO
                and snapshot.month_income <= ZERO
                and snapshot.month_expense <= ZERO
            ):
                return (
                    "I do not have enough Campus Coin data to generate useful insights yet. "
                    "Set your monthly allowance/savings goal and add a few transactions, then "
                    "ask me to **analyze my finances** again."
                )

            lines = ["**Smart insights from your Campus Coin data:**"]
            lines.append(
                f"• **Data basis:** As of {snapshot.reference_date.isoformat()}, Campus Coin is using "
                f"allowance {money(snapshot.monthly_allowance)} + counted extra income "
                f"{money(snapshot.counted_income)} − recorded expenses {money(snapshot.month_expense)}, "
                f"with a savings goal of {money(snapshot.savings_goal)}."
            )

            if snapshot.available_funds > ZERO:
                used_pct = snapshot.month_expense / snapshot.available_funds * Decimal("100")
                lines.append(
                    f"• **Budget use:** You have spent {money(snapshot.month_expense)} of "
                    f"{money(snapshot.available_funds)} available this month "
                    f"(**{used_pct:.1f}%**), leaving {money(snapshot.remaining_funds)}."
                )
            else:
                lines.append(
                    f"• **Budget use:** Campus Coin shows {money(snapshot.month_expense)} in "
                    "expenses but no monthly allowance or counted income to compare against."
                )

            if snapshot.savings_goal > ZERO:
                projected_goal_gap = snapshot.projected_remaining - snapshot.savings_goal
                if snapshot.remaining_funds < snapshot.savings_goal:
                    lines.append(
                        f"• **Savings pressure:** Your current remaining funds are "
                        f"{money(snapshot.savings_goal - snapshot.remaining_funds)} below the "
                        f"{money(snapshot.savings_goal)} savings goal."
                    )
                elif projected_goal_gap < ZERO:
                    lines.append(
                        f"• **Forecast warning:** The goal is protected right now, but at your "
                        f"current average pace the month-end projection is "
                        f"{money(-projected_goal_gap)} below the savings goal."
                    )
                else:
                    lines.append(
                        f"• **Savings outlook:** At the current average pace, the projection "
                        f"still finishes about {money(projected_goal_gap)} above your "
                        f"{money(snapshot.savings_goal)} savings goal."
                    )
            else:
                lines.append(
                    "• **Savings setup:** You have no monthly savings goal, so I can estimate "
                    "remaining money but cannot protect a target for you."
                )

            if snapshot.previous_7_days_expense > ZERO:
                weekly_delta = snapshot.last_7_days_expense - snapshot.previous_7_days_expense
                weekly_pct = abs(weekly_delta) / snapshot.previous_7_days_expense * Decimal("100")
                if weekly_delta == ZERO:
                    lines.append(
                        f"• **7-day trend:** Recent spending is {money(snapshot.last_7_days_expense)}, "
                        "the same as the previous 7 days."
                    )
                else:
                    direction = "higher" if weekly_delta > ZERO else "lower"
                    lines.append(
                        f"• **7-day trend:** Recent spending is {money(snapshot.last_7_days_expense)}, "
                        f"about **{weekly_pct:.1f}% {direction}** than the previous 7 days."
                    )
            elif snapshot.last_7_days_expense > ZERO:
                lines.append(
                    f"• **7-day trend:** You spent {money(snapshot.last_7_days_expense)} in the "
                    "last 7 days; there is not enough prior-week data for a reliable percentage comparison."
                )

            if snapshot.top_expense_categories and snapshot.month_expense > ZERO:
                top = snapshot.top_expense_categories[0]
                top_amount = Decimal(top["amount"])
                top_share = top_amount / snapshot.month_expense * Decimal("100")
                lines.append(
                    f"• **Main spending driver:** {top['category']} is your largest category at "
                    f"{money(top_amount)} (**{top_share:.1f}%** of this month's expenses)."
                )

            if snapshot.savings_goal > ZERO:
                lines.append(
                    f"• **Action now:** Keep optional spending near "
                    f"**{money(snapshot.safe_daily_budget)}/day** for the remaining "
                    f"{snapshot.days_remaining} days if you want to preserve the current savings target."
                )
            else:
                even_daily = max(snapshot.remaining_funds, ZERO) / Decimal(snapshot.days_remaining)
                lines.append(
                    f"• **Action now:** With no savings target set, an even remaining-budget pace "
                    f"would be about **{money(even_daily)}/day**."
                )

            return "\n".join(lines)

        if intent == "spending_risk":
            if (
                snapshot.monthly_allowance <= ZERO
                and snapshot.month_income <= ZERO
                and snapshot.month_expense <= ZERO
            ):
                return (
                    "I cannot rate spending risk yet because Campus Coin has no usable monthly "
                    "budget or transaction data for this month."
                )

            reasons = []
            high_risk = False
            watch_risk = False

            if snapshot.remaining_funds <= ZERO:
                high_risk = True
                reasons.append(
                    f"remaining monthly funds are {money(snapshot.remaining_funds)}"
                )

            if snapshot.projected_remaining < ZERO:
                high_risk = True
                reasons.append(
                    f"the current pace projects a month-end balance of {money(snapshot.projected_remaining)}"
                )

            if snapshot.savings_goal > ZERO:
                if snapshot.remaining_funds < snapshot.savings_goal:
                    high_risk = True
                    reasons.append(
                        f"you are already {money(snapshot.savings_goal - snapshot.remaining_funds)} "
                        "below the savings goal"
                    )
                elif snapshot.projected_remaining < snapshot.savings_goal:
                    watch_risk = True
                    reasons.append(
                        f"your projection would finish {money(snapshot.savings_goal - snapshot.projected_remaining)} "
                        "below the savings goal"
                    )

            weekly_context = None
            if snapshot.previous_7_days_expense > ZERO:
                weekly_delta = snapshot.last_7_days_expense - snapshot.previous_7_days_expense
                weekly_pct = weekly_delta / snapshot.previous_7_days_expense * Decimal("100")
                direction = "higher" if weekly_pct > ZERO else "lower" if weekly_pct < ZERO else "unchanged"
                if direction == "unchanged":
                    weekly_context = "last-7-day spending is unchanged from the previous 7 days"
                else:
                    weekly_context = (
                        f"last-7-day spending is {abs(weekly_pct):.1f}% {direction} than the previous 7 days"
                    )
            elif snapshot.last_7_days_expense > ZERO:
                weekly_context = (
                    "there is recent spending, but no prior 7-day spending is recorded for a percentage comparison"
                )

            if high_risk:
                level = "HIGH"
            elif watch_risk:
                level = "WATCH"
            else:
                level = "LOW"

            answer = [
                f"**Current overspending risk: {level}.**",
                f"Data used: allowance {money(snapshot.monthly_allowance)}, counted extra income "
                f"{money(snapshot.counted_income)}, expenses {money(snapshot.month_expense)}, "
                f"remaining funds {money(snapshot.remaining_funds)}, and savings goal "
                f"{money(snapshot.savings_goal)} as of {snapshot.reference_date.isoformat()}."
            ]
            if reasons:
                answer.append("Why: " + "; ".join(reasons) + ".")
            else:
                answer.append(
                    "Your current remaining funds and month-end projection do not breach the "
                    "budget or savings-goal rules used by this check."
                )
            if weekly_context:
                answer.append("Recent trend context: " + weekly_context + ".")
            answer.append(
                "Risk levels are rule-based: HIGH means the current/projected balance is negative "
                "or the savings goal is already not protected; WATCH means the current balance "
                "still protects the goal but the month-end projection does not; otherwise LOW."
            )

            if snapshot.savings_goal > ZERO:
                answer.append(
                    f"A practical guardrail is **{money(snapshot.safe_daily_budget)}/day** for "
                    f"the remaining {snapshot.days_remaining} days, with "
                    f"{money(snapshot.safe_to_spend_now)} total currently available above the savings goal."
                )
            else:
                answer.append(
                    "Set a monthly savings goal if you want this risk check to protect a specific amount."
                )
            return "\n\n".join(answer)

        if intent == "rest_of_month_plan":
            if (
                snapshot.monthly_allowance <= ZERO
                and snapshot.month_income <= ZERO
                and snapshot.month_expense <= ZERO
            ):
                return (
                    "I need a monthly allowance/income and some transaction data before I can build "
                    "a useful rest-of-month plan."
                )

            plan = [
                "**Rest-of-month action plan:**",
                f"• **Data basis:** {money(snapshot.remaining_funds)} remains from "
                f"{money(snapshot.available_funds)} available funds after "
                f"{money(snapshot.month_expense)} in recorded expenses as of "
                f"{snapshot.reference_date.isoformat()}."
            ]
            if snapshot.savings_goal > ZERO:
                plan.append(
                    f"• **Protect savings first:** Keep {money(snapshot.savings_goal)} reserved. "
                    f"That leaves **{money(snapshot.safe_to_spend_now)}** as your current safe-to-spend pool."
                )
                plan.append(
                    f"• **Daily guardrail:** Aim for no more than "
                    f"**{money(snapshot.safe_daily_budget)}/day** across the remaining "
                    f"{snapshot.days_remaining} days."
                )
                weekly_days = min(snapshot.days_remaining, 7)
                weekly_cap = snapshot.safe_daily_budget * Decimal(weekly_days)
                plan.append(
                    f"• **Next {weekly_days}-day cap:** Keep optional spending around "
                    f"**{money(weekly_cap)}** or less."
                )

                projected_gap = max(snapshot.savings_goal - snapshot.projected_remaining, ZERO)
                if projected_gap > ZERO:
                    daily_improvement = projected_gap / Decimal(snapshot.days_remaining)
                    plan.append(
                        f"• **Correct the current trajectory:** The present pace projects a "
                        f"{money(projected_gap)} gap versus your savings goal. Improve the outcome by "
                        f"about **{money(daily_improvement)}/day** through lower optional spending, "
                        "additional income, or a combination of both."
                    )
                else:
                    plan.append(
                        "• **Stay consistent:** Your current average projection still protects the "
                        "savings goal, so the main job is avoiding a late-month spending spike."
                    )
            else:
                even_daily = max(snapshot.remaining_funds, ZERO) / Decimal(snapshot.days_remaining)
                plan.append(
                    f"• **Set a daily ceiling:** About **{money(even_daily)}/day** would spread your "
                    f"remaining {money(snapshot.remaining_funds)} evenly across the final "
                    f"{snapshot.days_remaining} days."
                )
                plan.append(
                    "• **Add a savings target:** Without one, the plan can control spending but cannot "
                    "reserve money for a specific goal."
                )

            if snapshot.top_expense_categories and snapshot.month_expense > ZERO:
                top = snapshot.top_expense_categories[0]
                top_amount = Decimal(top["amount"])
                top_share = top_amount / snapshot.month_expense * Decimal("100")
                plan.append(
                    f"• **Largest category to review:** {top['category']} totals {money(top_amount)}, "
                    f"which is **{top_share:.1f}%** of this month's recorded expenses. Campus Coin "
                    "can identify the concentration, but it does not assume a made-up cut percentage; "
                    "only reduce transactions that are actually optional."
                )

            plan.append(
                "This plan is generated only from the records currently stored in Campus Coin and "
                "updates as you add new transactions."
            )
            return "\n".join(plan)

        if intent == "saving_advice":
            if (
                snapshot.monthly_allowance <= ZERO
                and snapshot.month_income <= ZERO
                and snapshot.month_expense <= ZERO
            ):
                return (
                    "I do not have enough Campus Coin data to give personalized saving advice yet. "
                    "Set your monthly allowance/savings goal and add transactions first; I will then "
                    "base the advice on those recorded values instead of guessing."
                )

            top = (
                snapshot.top_expense_categories[0]
                if snapshot.top_expense_categories
                else None
            )
            advice = [
                "**Personalized saving suggestions:**",
                f"• **Data basis:** allowance {money(snapshot.monthly_allowance)}, extra income "
                f"{money(snapshot.counted_income)}, expenses {money(snapshot.month_expense)}, "
                f"remaining {money(snapshot.remaining_funds)}, savings goal "
                f"{money(snapshot.savings_goal)}."
            ]

            if top and snapshot.month_expense > ZERO:
                top_amount = Decimal(top["amount"])
                top_share = top_amount / snapshot.month_expense * Decimal("100")
                advice.append(
                    f"• Your largest category is **{top['category']} ({money(top_amount)})**, "
                    f"representing **{top_share:.1f}%** of this month's recorded expenses. "
                    "That is a factual concentration to review; I do not invent a percentage cut "
                    "without transaction-level evidence that the spending is optional."
                )

            if snapshot.savings_goal > ZERO:
                if (
                    snapshot.remaining_funds
                    >= snapshot.savings_goal
                ):
                    advice.append(
                        f"• You have a "
                        f"{money(snapshot.remaining_funds - snapshot.savings_goal)} "
                        "buffer above your savings goal; do not treat the full "
                        "remaining budget as spendable cash."
                    )
                else:
                    advice.append(
                        f"• You are "
                        f"{money(snapshot.savings_goal - snapshot.remaining_funds)} "
                        "below your savings target, so prioritize optional expenses first."
                    )

                projected_gap = snapshot.projected_remaining - snapshot.savings_goal
                if projected_gap < ZERO:
                    improve_per_day = (-projected_gap) / Decimal(snapshot.days_remaining)
                    advice.append(
                        f"• At your current recorded pace, month-end would finish about "
                        f"{money(-projected_gap)} below the goal. That exact projected gap is the "
                        f"amount the plan needs to improve; spread across the remaining "
                        f"{snapshot.days_remaining} days, it is roughly {money(improve_per_day)}/day."
                    )
                else:
                    advice.append(
                        f"• Your current projection remains about {money(projected_gap)} above the "
                        "savings goal, so consistency matters more than aggressive cuts right now."
                    )
            else:
                advice.append(
                    "• Set a monthly savings goal in your profile if you want me to reserve a specific "
                    "amount before calculating what is safe to spend."
                )

            advice.append(
                f"• Your current safe spending pace is about "
                f"**{money(snapshot.safe_daily_budget)}/day** for the rest "
                "of the month."
            )

            if snapshot.previous_7_days_expense > ZERO:
                weekly_delta = snapshot.last_7_days_expense - snapshot.previous_7_days_expense
                weekly_pct = weekly_delta / snapshot.previous_7_days_expense * Decimal("100")
                if weekly_pct >= Decimal("20"):
                    advice.append(
                        f"• Spending in the last 7 days is **{weekly_pct:.1f}% higher** than the prior "
                        "7 days, so slowing the next few days would reduce the chance of a late-month squeeze."
                    )
                elif weekly_pct <= Decimal("-20"):
                    advice.append(
                        f"• Recent 7-day spending is **{abs(weekly_pct):.1f}% lower** than the previous "
                        "7 days; maintaining that pace supports your savings target."
                    )

            return "\n".join(advice)

        if intent == "summary":
            if snapshot.savings_goal > ZERO:
                if snapshot.protected_savings_buffer >= ZERO:
                    goal_text = (
                        f"Savings goal {money(snapshot.savings_goal)}; "
                        f"buffer above the goal "
                        f"{money(snapshot.protected_savings_buffer)}."
                    )
                else:
                    goal_text = (
                        f"Savings goal {money(snapshot.savings_goal)}; "
                        f"currently "
                        f"{money(-snapshot.protected_savings_buffer)} short "
                        "of fully protecting the goal."
                    )
            else:
                goal_text = (
                    "You have not set a monthly savings goal."
                )

            return (
                f"This month: monthly allowance "
                f"**{money(snapshot.monthly_allowance)}**, counted extra income "
                f"**{money(snapshot.counted_income)}**, expenses "
                f"**{money(snapshot.month_expense)}**, remaining "
                f"**{money(snapshot.remaining_funds)}**. {goal_text} "
                f"At the current pace, projected month-end remaining funds are "
                f"about {money(snapshot.projected_remaining)}."
            )

        return None


class CampusCoinAssistant:
    NON_DATA_INTENTS = {
        "greeting",
        "help",
        "data_scope",
        "out_of_scope",
        "unsupported_finance",
        "external_balance",
    }

    def __init__(self):
        self.context_service = FinanceContextService()
        self.intent_router = IntentRouter()
        self.deterministic = DeterministicFinanceAssistant()

    def _resolve_contextual_intent(
        self,
        text: str,
        history: list[dict] | None,
    ) -> tuple[str, str]:
        intent = self.intent_router.detect(text)
        if intent not in {"out_of_scope", "unsupported_finance"} or not history:
            return intent, text

        previous_user_text = next(
            (
                str(item.get("content", "")).strip()
                for item in reversed(history)
                if item.get("role") == "user" and str(item.get("content", "")).strip()
            ),
            "",
        )
        if not previous_user_text:
            return intent, text

        previous_intent = self.intent_router.detect(previous_user_text)
        q = _normalize_for_intent(text)

        spending_contexts = {
            "monthly_expense",
            "today_spending",
            "week_spending",
            "top_categories",
            "category_spending",
            "summary",
        }
        if previous_intent in spending_contexts:
            if q in {"today", "what about today", "and today", "today then", "hom nay", "hom nay thi sao"}:
                return "today_spending", "how much did i spend today"
            if q in {
                "this week",
                "what about this week",
                "and this week",
                "last 7 days",
                "what about the last 7 days",
                "tuan nay",
                "7 ngay gan day",
            }:
                return "week_spending", "how much did i spend in the last 7 days"
            if q in {"last month", "what about last month", "and last month", "thang truoc", "thang truoc thi sao"}:
                return "compare_month", "compare my spending with last month"

        if previous_intent in {"balance", "spendable", "daily_budget", "summary", "savings_goal"} and q in {
            "savings",
            "my savings",
            "and savings",
            "what about my savings",
            "savings goal",
            "tiet kiem",
            "muc tieu tiet kiem",
        }:
            return "savings_goal", "how is my savings goal"

        if previous_intent == "recent_transactions":
            count_match = re.fullmatch(r"(?:show )?(\d{1,2})(?: please)?", q)
            if count_match:
                return "recent_transactions", f"show my {count_match.group(1)} recent transactions"

        if previous_intent == "affordability" and parse_requested_amount(text) is not None:
            return "affordability", f"can i afford {text}"

        if previous_intent == "category_spending" and q.startswith(("what about ", "and ")):
            category_text = re.sub(r"^(?:what about|and)\s+", "", q).strip()
            if category_text:
                return "category_spending", f"how much did i spend on {category_text}"

        if previous_intent in {"smart_insights", "spending_risk", "summary", "saving_advice"} and q in {
            "what should i do",
            "what do i do",
            "what should i do now",
            "give me a plan",
            "make me a plan",
            "action plan",
            "toi nen lam gi",
            "gio toi nen lam gi",
            "lap ke hoach cho toi",
        }:
            return "rest_of_month_plan", "make me a plan for the rest of the month"

        if previous_intent in {"summary", "smart_insights", "spending_risk"} and q in {
            "any advice",
            "give me advice",
            "how can i improve",
            "how can i save more",
            "toi nen tiet kiem the nao",
            "co loi khuyen nao khong",
        }:
            return "saving_advice", "give me personalized saving tips"

        return intent, text

    def reply(self, user, text: str, history: list[dict] | None = None) -> dict:
        intent, resolved_text = self._resolve_contextual_intent(text, history)

        # Do not query finance tables for greetings, help, privacy/scope questions,
        # unsupported requests, or requests for live external-account data.
        if intent in self.NON_DATA_INTENTS:
            answer = self.deterministic.answer(user, resolved_text, None, intent)
            return {
                "answer": answer,
                "intent": intent,
                "source": "scope_guard" if intent in {"out_of_scope", "unsupported_finance", "external_balance"} else "assistant_capabilities",
                "data_sources": [],
                "snapshot": {},
            }

        snapshot = self.context_service.build(user)
        core_answer = self.deterministic.answer(
            user,
            resolved_text,
            snapshot,
            intent,
        )

        if core_answer is not None:
            return {
                "answer": core_answer,
                "intent": intent,
                "source": "campus_coin_data",
                "data_sources": list(INTENT_DATA_SOURCES.get(intent, ())),
                "snapshot": self._response_snapshot(snapshot),
            }

        # Defensive fallback: an unknown path must never become a general-purpose chatbot.
        return {
            "answer": (
                "I could not map that request to a supported Campus Coin finance action. "
                "Type **help** to see the questions I can answer."
            ),
            "intent": "out_of_scope",
            "source": "scope_guard",
            "data_sources": [],
            "snapshot": {},
        }

    @staticmethod
    def _response_snapshot(snapshot: FinancialSnapshot) -> dict:
        return {
            "reference_date": snapshot.reference_date.isoformat(),
            "month_transaction_count": snapshot.month_transaction_count,
            "expense_transaction_count": snapshot.expense_transaction_count,
            "remaining": str(
                snapshot.remaining_funds.quantize(Decimal("0.01"))
            ),
            "safe_to_spend": str(
                snapshot.safe_to_spend_now.quantize(Decimal("0.01"))
            ),
            "savings_shortfall": str(
                max(
                    snapshot.savings_goal - snapshot.remaining_funds,
                    ZERO,
                ).quantize(Decimal("0.01"))
            ),
            "expense": str(
                snapshot.month_expense.quantize(Decimal("0.01"))
            ),
            "safe_daily": str(
                snapshot.safe_daily_budget.quantize(Decimal("0.01"))
            ),
            "currency": snapshot.currency,
        }


assistant_engine = CampusCoinAssistant()
