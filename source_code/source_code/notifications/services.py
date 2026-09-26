from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from transactions.models import Transaction

from .models import Notification


ZERO = Decimal("0")
SAVINGS_WARNING_FACTOR = Decimal("1.15")
LOW_BALANCE_RATIO = Decimal("0.10")


def _money(value):
    return value if value is not None else ZERO


def _period_totals(user, start_date, end_date):
    rows = (
        Transaction.objects.filter(user=user, date__range=(start_date, end_date))
        .values("type")
        .annotate(total=Sum("amount"))
    )
    income = ZERO
    expense = ZERO
    for row in rows:
        if row["type"] == "income":
            income = _money(row["total"])
        elif row["type"] == "expense":
            expense = _money(row["total"])
    return income, expense, income - expense


def _month_bounds(reference_date):
    start = reference_date.replace(day=1)
    end = reference_date.replace(day=monthrange(reference_date.year, reference_date.month)[1])
    return start, end


def _absolute_url(path):
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"
    return f"{base}{path}"


def _format_money(value, currency):
    amount = _money(value)
    return f"{amount:,.0f} {currency}"


def _email_notification(notification):
    user = notification.user
    if not user.email:
        return

    currency = getattr(user.profile, "currency_code", "VND") or "VND"
    link = _absolute_url(notification.action_path)
    body = (
        f"{notification.title}\n\n"
        f"{notification.message}\n\n"
        f"Income: {_format_money(notification.income_total, currency)}\n"
        f"Expenses: {_format_money(notification.expense_total, currency)}\n"
        f"Remaining: {_format_money(notification.balance, currency)}\n"
        f"Open Campus Coin: {link}\n"
    )
    try:
        send_mail(
            subject=f"Campus Coin - {notification.title}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as exc:
        notification.email_error = str(exc)[:500]
        notification.save(update_fields=["email_error"])
        return

    notification.emailed_at = timezone.now()
    notification.email_error = ""
    notification.save(update_fields=["emailed_at", "email_error"])


def _create_notification(*, send_email=True, **values):
    dedup_key = values["dedup_key"]
    notification, created = Notification.objects.get_or_create(
        dedup_key=dedup_key,
        defaults=values,
    )
    if send_email and notification.emailed_at is None:
        _email_notification(notification)
    return notification, created


def create_weekly_summary(user, reference_date=None, *, send_email=True, force=False):
    reference_date = reference_date or timezone.localdate()
    if not force and reference_date.weekday() != 6:  # Sunday
        return None, False

    start_date = reference_date - timedelta(days=6)
    end_date = reference_date
    income, expense, balance = _period_totals(user, start_date, end_date)
    action_path = reverse("report:dashboard") + f"?period=week&date={end_date.isoformat()}"
    return _create_notification(
        user=user,
        kind=Notification.Kind.WEEKLY_SUMMARY,
        severity=Notification.Severity.INFO,
        title="Weekly finance summary",
        message=(
            f"Your weekly summary for {start_date:%b %d} - {end_date:%b %d, %Y} is ready. "
            "Review your income, spending, and remaining balance."
        ),
        period_start=start_date,
        period_end=end_date,
        income_total=income,
        expense_total=expense,
        balance=balance,
        savings_goal=getattr(user.profile, "monthly_savings_goal", None),
        action_path=action_path,
        dedup_key=f"weekly:{user.pk}:{end_date.isoformat()}",
        send_email=send_email,
    )


def create_monthly_summary(user, reference_date=None, *, send_email=True, force=False):
    reference_date = reference_date or timezone.localdate()
    start_date, month_end = _month_bounds(reference_date)
    if not force and reference_date != month_end:
        return None, False

    income, expense, balance = _period_totals(user, start_date, reference_date)
    action_path = reverse("report:dashboard") + f"?period=month&date={reference_date.isoformat()}"
    return _create_notification(
        user=user,
        kind=Notification.Kind.MONTHLY_SUMMARY,
        severity=Notification.Severity.INFO,
        title="Monthly finance summary",
        message=(
            f"Your {reference_date:%B %Y} summary is ready. "
            "Review your total income, expenses, and remaining balance for the month."
        ),
        period_start=start_date,
        period_end=reference_date,
        income_total=income,
        expense_total=expense,
        balance=balance,
        savings_goal=getattr(user.profile, "monthly_savings_goal", None),
        action_path=action_path,
        dedup_key=f"monthly:{user.pk}:{reference_date:%Y-%m}",
        send_email=send_email,
    )


def create_threshold_notifications(user, reference_date=None, *, send_email=True):
    reference_date = reference_date or timezone.localdate()
    start_date, _ = _month_bounds(reference_date)
    income, expense, transaction_balance = _period_totals(user, start_date, reference_date)

    profile = user.profile
    allowance = _money(profile.monthly_allowance)
    savings_goal = _money(profile.monthly_savings_goal)

    # The allowance is the planned monthly base. Recorded income is added on top of it.
    # If no allowance is configured, the calculation naturally falls back to recorded income.
    available_funds = allowance + income
    budget_remaining = available_funds - expense
    action_path = reverse("report:dashboard") + f"?period=month&date={reference_date.isoformat()}"
    created = []
    low_balance = False
    if available_funds > ZERO:
        low_balance_limit = available_funds * LOW_BALANCE_RATIO
        low_balance = budget_remaining <= low_balance_limit

    if savings_goal > ZERO and available_funds > ZERO:
        near_savings = budget_remaining <= savings_goal * SAVINGS_WARNING_FACTOR
        # If the balance is already critically low, send only the stronger low-balance
        # alert. A savings warning that was created earlier in the month remains stored.
        if near_savings and not low_balance:
            notification, was_created = _create_notification(
                user=user,
                kind=Notification.Kind.SAVINGS_THRESHOLD,
                severity=Notification.Severity.WARNING,
                title="Spending is close to your savings goal",
                message=(
                    "Your remaining monthly funds are close to or below the amount you planned to save. "
                    "Review upcoming expenses before spending more."
                ),
                period_start=start_date,
                period_end=reference_date,
                income_total=income,
                expense_total=expense,
                balance=budget_remaining,
                savings_goal=savings_goal,
                action_path=action_path,
                dedup_key=f"savings:{user.pk}:{reference_date:%Y-%m}",
                send_email=send_email,
            )
            if was_created:
                created.append(notification)

    if low_balance:
        notification, was_created = _create_notification(
            user=user,
            kind=Notification.Kind.LOW_BALANCE,
            severity=Notification.Severity.CRITICAL,
            title="Your remaining balance is running low",
            message=(
                "Your estimated remaining funds for this month are at or below 10% of your available monthly funds. "
                "Check your spending and planned payments."
            ),
            period_start=start_date,
            period_end=reference_date,
            income_total=income,
            expense_total=expense,
            balance=budget_remaining,
            savings_goal=savings_goal or None,
            action_path=action_path,
            dedup_key=f"low-balance:{user.pk}:{reference_date:%Y-%m}",
            send_email=send_email,
        )
        if was_created:
            created.append(notification)

    return created


def process_user_notifications(
    user,
    reference_date=None,
    *,
    send_email=True,
    force_weekly=False,
    force_monthly=False,
):
    reference_date = reference_date or timezone.localdate()
    results = []
    weekly, created = create_weekly_summary(
        user,
        reference_date,
        send_email=send_email,
        force=force_weekly,
    )
    if created:
        results.append(weekly)

    monthly, created = create_monthly_summary(
        user,
        reference_date,
        send_email=send_email,
        force=force_monthly,
    )
    if created:
        results.append(monthly)

    results.extend(create_threshold_notifications(user, reference_date, send_email=send_email))
    return results


def process_all_users(
    reference_date=None,
    *,
    send_email=True,
    force_weekly=False,
    force_monthly=False,
):
    reference_date = reference_date or timezone.localdate()
    users = User.objects.filter(
        status=User.Status.ACTIVE,
        deleted_at__isnull=True,
        role__role_name=Role.Name.STUDENT,
    ).select_related("profile")

    created = []
    for user in users:
        created.extend(
            process_user_notifications(
                user,
                reference_date,
                send_email=send_email,
                force_weekly=force_weekly,
                force_monthly=force_monthly,
            )
        )
    return created
