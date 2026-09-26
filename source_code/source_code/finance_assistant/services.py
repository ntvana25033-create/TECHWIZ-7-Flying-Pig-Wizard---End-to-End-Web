from __future__ import annotations

import random
import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher

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


def _is_vietnamese_query(text: str) -> bool:
    q = f" {_normalize_for_intent(text)} "
    markers = (
        " toi ", " minh ", " thang ", " tuan ", " ngay ",
        " bao nhieu ", " giao dich ", " tiet kiem ", " thu nhap ",
        " so du ", " gan nhat ", " moi nhat ", " duoc khong ",
        " chi ", " tieu ", " danh muc ", " con lai ", " mua mon ",
        " goi y ", " hom nay ", " tong ",
    )
    return any(marker in q for marker in markers)


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


def format_money(value: Decimal, currency: str = "VND") -> str:
    amount = _dec(value)
    if currency.upper() == "VND":
        quantized = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{quantized:,.0f} VND"
    return f"{amount:,.2f} {currency.upper()}"


def parse_requested_amount(text: str) -> Decimal | None:
    normalized = _normalize(text)
    matches = re.findall(
        r"(?<!\w)(\d[\d., ]*)(?:\s*)(million|mil|m|thousand|k|trieu|tr|nghin|ngan)?(?!\w)",
        normalized,
    )
    if not matches:
        return None

    for raw_number, suffix in reversed(matches):
        raw_number = raw_number.strip().replace(" ", "")
        if not raw_number:
            continue

        multiplier = Decimal("1")
        if suffix in {"million", "mil", "m", "trieu", "tr"}:
            multiplier = Decimal("1000000")
        elif suffix in {"thousand", "k", "nghin", "ngan"}:
            multiplier = Decimal("1000")

        try:
            if multiplier != 1:
                separators = raw_number.count(",") + raw_number.count(".")
                if separators == 1:
                    number = Decimal(raw_number.replace(",", "."))
                else:
                    number = Decimal(
                        raw_number.replace(",", "").replace(".", "")
                    )
            else:
                number = Decimal(
                    raw_number.replace(",", "").replace(".", "")
                )
        except Exception:
            continue

        amount = number * multiplier
        if amount > 0:
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

def _kha_easter_egg(text: str) -> str | None:
    q = _normalize(text)
    secret_keywords = {
        "huu kha",
        "anh kha",
        "kha mode",
        "mai huu kha",
        "campus coin kha",
    }
    if q not in secret_keywords:
        return None

    messages = [
        "🔥 **KHA MODE ACTIVATED** — Campus Coin has detected legendary developer energy.",
        "👑 **ACHIEVEMENT UNLOCKED:** Huu Kha has entered the system. Difficulty level: unfair.",
        "⚡ **SYSTEM ALERT:** Huu Kha detected. Coolness level has exceeded the safe limit.",
        "💻 `STATUS: KHA IS COOKING...` Nobody knows what he is building, but it already looks serious.",
        "😎 **HUU KHA STAYS ON TOP.** This is not an opinion. It is a system message.",
        "🧠 AI checked 999,999 possibilities and reached one conclusion: **Kha is still built different.**",
        "✨ **LEGEND DETECTED:** Huu Kha appeared. Campus Coin gained +200% style.",
        "📡 Connecting to Kha Server...\n✅ Connected.\n✅ Talent detected.\n✅ Aura detected.\n🔥 **ABSOLUTE CINEMA.**",
        "🎮 **SECRET CHARACTER UNLOCKED:** Huu Kha — Class: Developer | Level: ??? | Aura: MAX.",
    ]
    return random.choice(messages)


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
    avg_daily_expense: Decimal
    projected_expense: Decimal
    projected_remaining: Decimal
    previous_month_expense: Decimal
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
        reference_date = reference_date or timezone.localdate()
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

        profile = UserProfile.objects.filter(user=user).first()
        if profile is not None:
            allowance = _dec(profile.monthly_allowance)
            savings_goal = _dec(profile.monthly_savings_goal)
            currency = (profile.currency_code or "VND").upper()
        else:
            allowance = ZERO
            savings_goal = ZERO
            currency = "VND"

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

        expense_change = None
        if previous_expense > ZERO:
            expense_change = (
                (expense - previous_expense)
                / previous_expense
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
            avg_daily_expense=avg_daily,
            projected_expense=projected_expense,
            projected_remaining=projected_remaining,
            previous_month_expense=previous_expense,
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

        return "general"

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
        snapshot: FinancialSnapshot,
        intent: str,
    ) -> str | None:
        currency = snapshot.currency
        money = lambda value: format_money(value, currency)
        vi = _is_vietnamese_query(text)

        if intent == "greeting":
            return (
                "Hi! I’m Campus Coin AI. I can check your remaining budget, "
                "analyze spending, review transactions, protect your savings goal, "
                "and help you make safer spending decisions."
            )

        if intent == "help":
            return (
                "I’m your Campus Coin finance assistant. I can:\n\n"
                "• Check your remaining monthly budget.\n"
                "• Calculate how much you can safely spend.\n"
                "• Calculate your daily spending limit through month-end.\n"
                "• Show this month’s income and expenses.\n"
                "• Analyze spending by category.\n"
                "• Show your top spending categories.\n"
                "• Show your largest expenses.\n"
                "• Show your recent transactions.\n"
                "• Check today’s spending.\n"
                "• Check spending from the last 7 days.\n"
                "• Compare your spending with last month.\n"
                "• Forecast month-end spending and remaining funds.\n"
                "• Check whether a purchase fits your budget and savings goal.\n"
                "• Summarize your financial situation.\n"
                "• Give personalized saving suggestions based on your Campus Coin data.\n\n"
                "Try asking: “How much money do I have left?”, "
                "“How much can I safely spend?”, "
                "“How much did I spend on Food this month?”, "
                "“Show my 5 latest transactions”, or "
                "“Can I afford a 500,000 VND purchase?”"
            )

        if intent == "external_balance":
            if vi:
                return (
                    "Mình **không có quyền truy cập** số dư trực tiếp của ngân hàng hoặc ví điện tử. "
                    "Mình chỉ có thể tính từ dữ liệu đã lưu trong Campus Coin. "
                    "Bạn có thể hỏi: **“Tôi còn bao nhiêu tiền trong Campus Coin?”**"
                )
            return (
                "I cannot access live bank-account or e-wallet balances. "
                "I can only calculate from records saved in Campus Coin. "
                "Try asking: **“How much do I have left in Campus Coin?”**"
            )

        if intent == "monthly_expense":
            if snapshot.month_expense <= ZERO:
                return (
                    "You have **no recorded expenses this month**, "
                    "so your current monthly spending is **0 VND**."
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
                    "budget is **0 VND**. Update your Profile or add transactions "
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
                    f"spending is currently 0 VND**, and you are "
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
                        f"0 VND/day** if you want to preserve the "
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
                    "**“Can I afford a 750,000 VND purchase?”**"
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
                if vi:
                    return (
                        "Bạn chưa có giao dịch nào trong Campus Coin. "
                        "Hãy thêm giao dịch trước để mình có thể hiển thị lịch sử gần đây."
                    )
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
            if vi:
                if shown < requested:
                    intro = f"Bạn hiện chỉ có **{shown} giao dịch**; đây là lịch sử gần nhất:\n"
                else:
                    intro = f"**{shown} giao dịch gần nhất** của bạn:\n"
            elif shown < requested:
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
            if snapshot.previous_month_expense <= ZERO:
                return (
                    f"You have spent {money(snapshot.month_expense)} this month. "
                    "There is not enough previous-month spending data for a "
                    "percentage comparison."
                )

            pct = snapshot.expense_change_percent or ZERO
            if pct == ZERO:
                return (
                    f"You have spent **{money(snapshot.month_expense)}** this "
                    f"month versus **{money(snapshot.previous_month_expense)}** "
                    "last month. Spending is currently **unchanged**. The current "
                    "month is not finished, so this is not yet a full-month comparison."
                )

            direction = "higher" if pct > 0 else "lower"
            return (
                f"You have spent **{money(snapshot.month_expense)}** this month "
                f"versus **{money(snapshot.previous_month_expense)}** last month, "
                f"currently about **{abs(pct):.1f}% {direction}**. The current "
                "month is not finished, so this is not yet a like-for-like "
                "full-month comparison."
            )

        if intent == "forecast":
            return (
                f"If your current average spending pace continues, projected "
                f"month spending is about **{money(snapshot.projected_expense)}**, "
                f"leaving roughly **{money(snapshot.projected_remaining)}** by "
                f"month-end. This is a simple projection from your "
                f"{money(snapshot.avg_daily_expense)}/day average, not a "
                "guaranteed outcome."
            )

        if intent == "week_spending":
            delta = (
                snapshot.last_7_days_expense
                - snapshot.previous_7_days_expense
            )

            if delta == ZERO:
                if vi:
                    return (
                        f"Bạn đã chi **{money(snapshot.last_7_days_expense)}** trong 7 ngày gần đây, "
                        "bằng đúng 7 ngày trước đó — **không đổi**."
                    )
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

        if intent == "saving_advice":
            top = (
                snapshot.top_expense_categories[0]
                if snapshot.top_expense_categories
                else None
            )
            advice = []

            if top:
                top_amount = Decimal(top["amount"])
                ten_pct = top_amount * Decimal("0.10")
                advice.append(
                    f"Your largest category is **{top['category']} "
                    f"({money(top_amount)})**; trimming just 10% there would "
                    f"keep about {money(ten_pct)}."
                )

            if snapshot.savings_goal > ZERO:
                if (
                    snapshot.remaining_funds
                    >= snapshot.savings_goal
                ):
                    advice.append(
                        f"You have a "
                        f"{money(snapshot.remaining_funds - snapshot.savings_goal)} "
                        "buffer above your savings goal; do not treat the full "
                        "remaining budget as spendable cash."
                    )
                else:
                    advice.append(
                        f"You are "
                        f"{money(snapshot.savings_goal - snapshot.remaining_funds)} "
                        "below your savings target, so prioritize optional expenses first."
                    )

            if vi:
                vi_advice = []
                if top:
                    top_amount = Decimal(top["amount"])
                    ten_pct = top_amount * Decimal("0.10")
                    vi_advice.append(
                        f"Danh mục chi nhiều nhất là **{top['category']} ({money(top_amount)})**; "
                        f"giảm khoảng 10% ở đây có thể giữ lại khoảng {money(ten_pct)}."
                    )
                if snapshot.savings_goal > ZERO:
                    if snapshot.remaining_funds >= snapshot.savings_goal:
                        vi_advice.append(
                            f"Bạn đang có khoảng đệm {money(snapshot.remaining_funds - snapshot.savings_goal)} "
                            "cao hơn mục tiêu tiết kiệm; không nên xem toàn bộ số dư còn lại là tiền có thể tiêu."
                        )
                    else:
                        vi_advice.append(
                            f"Bạn đang thiếu {money(snapshot.savings_goal - snapshot.remaining_funds)} so với "
                            "mục tiêu tiết kiệm, nên ưu tiên cắt giảm các khoản không thiết yếu trước."
                        )
                vi_advice.append(
                    f"Mức chi an toàn hiện tại khoảng **{money(snapshot.safe_daily_budget)}/ngày** cho phần còn lại của tháng."
                )
                return " ".join(vi_advice)

            advice.append(
                f"Your current safe spending pace is about "
                f"**{money(snapshot.safe_daily_budget)}/day** for the rest "
                "of the month."
            )
            return " ".join(advice)

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
    def __init__(self):
        self.context_service = FinanceContextService()
        self.intent_router = IntentRouter()
        self.deterministic = DeterministicFinanceAssistant()

    def reply(self, user, text: str, history: list[dict] | None = None) -> dict:
        kha_reply = _kha_easter_egg(text)

        if kha_reply:
            return {
                "answer": kha_reply,
                "intent": "kha_easter_egg",
                "source": "easter_egg",
                "snapshot": {},
            }

        snapshot = self.context_service.build(user)
        intent = self.intent_router.detect(text)

        core_answer = self.deterministic.answer(
            user,
            text,
            snapshot,
            intent,
        )

        if core_answer is not None:
            return {
                "answer": core_answer,
                "intent": intent,
                "source": "campus_coin_data",
                "snapshot": self._response_snapshot(snapshot),
            }

        fallback = (
            "I’m not sure what you mean yet. Ask me about remaining funds, "
            "safe-to-spend money, daily spending limits, savings goals, "
            "monthly income or expenses, category spending, recent transactions, "
            "largest expenses, month comparisons, month-end forecasts, "
            "saving suggestions, or whether a specific purchase fits your budget."
        )

        return {
            "answer": fallback,
            "intent": "fallback",
            "source": "local_fallback",
            "snapshot": self._response_snapshot(snapshot),
        }

    @staticmethod
    def _response_snapshot(snapshot: FinancialSnapshot) -> dict:
        return {
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
