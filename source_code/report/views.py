from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render
from django.views import View

from transactions.models import Transaction
from transactions.mixins import StudentRequiredMixin


PERIODS = {
    "day": "Hôm nay",
    "week": "7 ngày",
    "month": "Tháng",
    "3m": "3 tháng",
    "6m": "6 tháng",
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

        # Build chart buckets from the real Transaction.date value.
        # This avoids database-specific TruncDate/TruncMonth returning NULL.
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
                    "label": cursor.strftime("%m/%Y"),
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
                    "label": cursor.strftime("%d/%m"),
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
            "transaction_count": qs.count(),
        })
