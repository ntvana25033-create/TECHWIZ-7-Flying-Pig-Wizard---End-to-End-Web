from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View

from transactions.models import Transaction
from transactions.mixins import StudentRequiredMixin

PERIODS = {
    "day": "Today",
    "week": "Last 7 days",
    "month": "This month",
    "3m": "3 months",
    "6m": "6 months",
}


def _bounds(period, reference):
    if period == "day":
        return reference, reference
    if period == "week":
        return reference - timedelta(days=6), reference
    if period == "month":
        return reference.replace(day=1), reference
    months = 3 if period == "3m" else 6
    start_month = reference.replace(day=1)
    month_index = start_month.year * 12 + start_month.month - 1 - (months - 1)
    start = date(month_index // 12, month_index % 12 + 1, 1)
    return start, reference


def _money(value):
    return float(value or Decimal("0"))


class ReportDashboardView(StudentRequiredMixin, View):
    def get(self, request):
        period = request.GET.get("period", "month")
        if period not in PERIODS:
            period = "month"

        try:
            reference = date.fromisoformat(request.GET.get("date", ""))
        except ValueError:
            reference = date.today()

        start, end = _bounds(period, reference)
        qs = Transaction.objects.filter(
            user=request.user, date__gte=start, date__lte=end
        ).select_related("category")

        totals = qs.values("type").annotate(total=Sum("amount"))
        total_income = next((_money(x["total"]) for x in totals if x["type"] == "income"), 0)
        total_expense = next((_money(x["total"]) for x in totals if x["type"] == "expense"), 0)

        category_rows = list(
            qs.values("type", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("type", "-total")
        )
        income_categories = [x for x in category_rows if x["type"] == "income"]
        expense_categories = [x for x in category_rows if x["type"] == "expense"]

        income_categories_json = [
            {"name": row["category__name"] or "Uncategorized", "total": float(row["total"])}
            for row in income_categories
        ]

        expense_categories_json = [
            {"name": row["category__name"] or "Uncategorized", "total": float(row["total"])}
            for row in expense_categories
        ]

        transactions_json = [
            {
                "date": t.date.isoformat() if t.date else "",
                "amount": _money(t.amount),
                "type": t.type,
                "category": t.category.name if t.category else "Uncategorized",
                "description": t.description if t.description else ""
            }
            for t in qs
        ]

        rows = (
            qs.exclude(date__isnull=True)
            .values("date", "type")
            .annotate(total=Sum("amount"))
            .order_by("date", "type")
        )

        if period in {"3m", "6m"}:
            bucket_map = {}
            cursor = start.replace(day=1)
            while cursor <= end:
                key = cursor.isoformat()
                bucket_map[key] = {
                    "label": cursor.strftime("%b %Y"),
                    "income": 0,
                    "expense": 0,
                }
                next_month = cursor.month + 1
                cursor = date(
                    cursor.year + (next_month - 1) // 12,
                    (next_month - 1) % 12 + 1,
                    1,
                )

            for row in rows:
                transaction_date = row["date"]
                if transaction_date is None:
                    continue
                key = transaction_date.replace(day=1).isoformat()
                if key in bucket_map:
                    bucket_map[key][row["type"]] += _money(row["total"])
        else:
            bucket_map = {}
            cursor = start
            while cursor <= end:
                bucket_map[cursor.isoformat()] = {
                    "label": cursor.strftime("%b %d"),
                    "income": 0,
                    "expense": 0,
                }
                cursor += timedelta(days=1)

            for row in rows:
                transaction_date = row["date"]
                if transaction_date is None:
                    continue
                key = transaction_date.isoformat()
                if key in bucket_map:
                    bucket_map[key][row["type"]] += _money(row["total"])

        chart_data = list(bucket_map.values())
        return render(request, "report/dashboard.html", {
            "period": period,
            "periods": PERIODS,
            "reference": reference.isoformat(),
            "start": start,
            "end": end,
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": total_income - total_expense,
            "income_categories": income_categories,
            "expense_categories": expense_categories,
            "chart_data": chart_data,
            "income_categories_json": income_categories_json,
            "expense_categories_json": expense_categories_json,
            "transactions_json": transactions_json,
            "transaction_count": qs.count(),
        })

    def post(self, request):
        # Lấy tham số trực tiếp từ form POST thay vì URL GET
        period = request.POST.get("period", "month")
        if period not in PERIODS:
            period = "month"

        try:
            reference = date.fromisoformat(request.POST.get("date", ""))
        except ValueError:
            reference = date.today()

        start, end = _bounds(period, reference)
        qs = Transaction.objects.filter(
            user=request.user, date__gte=start, date__lte=end
        ).select_related("category")

        # Tính toán tổng số
        totals = qs.values("type").annotate(total=Sum("amount"))
        total_income = next((_money(x["total"]) for x in totals if x["type"] == "income"), 0)
        total_expense = next((_money(x["total"]) for x in totals if x["type"] == "expense"), 0)
        balance = total_income - total_expense

        # Chi tiết danh mục
        category_rows = list(
            qs.values("type", "category__name").annotate(total=Sum("amount")).order_by("type", "-total"))
        currency = getattr(request.user.profile, "currency_code", "VND")

        # Định dạng URL đính kèm trong email
        base_url = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
        if not base_url:
            base_url = f"{request.scheme}://{request.get_host()}"

        action_path = reverse("report:dashboard")
        # Chủ động tạo query string mới dựa trên thông tin vừa được yêu cầu
        query_string = f"period={period}&date={reference.isoformat()}"
        full_url = f"{base_url}{action_path}?{query_string}"

        body_lines = [
            f"Your Financial Report: {PERIODS.get(period)} ({start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')})",
            "--------------------------------------------------",
            f"Total Income:   {total_income:,.0f} {currency}",
            f"Total Expenses: {total_expense:,.0f} {currency}",
            f"Balance:        {balance:,.0f} {currency}",
            "--------------------------------------------------",
            "\nEXPENSES BY CATEGORY:"
        ]

        for row in [x for x in category_rows if x["type"] == "expense"]:
            cat_name = row["category__name"] or "Uncategorized"
            body_lines.append(f"- {cat_name}: {float(row['total']):,.0f} {currency}")

        body_lines.append("\nINCOME BY CATEGORY:")
        for row in [x for x in category_rows if x["type"] == "income"]:
            cat_name = row["category__name"] or "Uncategorized"
            body_lines.append(f"- {cat_name}: {float(row['total']):,.0f} {currency}")

        body_lines.append(f"\nView full interactive charts and transaction details here:\n{full_url}")

        # Gửi email
        try:
            send_mail(
                subject=f"Campus Coin - Financial Report ({PERIODS.get(period)})",
                message="\n".join(body_lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
            messages.success(request, f"Report successfully sent to {request.user.email}")
        except Exception as exc:
            messages.error(request, f"Failed to send email: {str(exc)}")

        # Trả người dùng về đúng trang báo cáo họ vừa ra lệnh gửi mail
        return redirect(f"{action_path}?{query_string}")