import csv
import logging
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction as db_transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models import Role
from notifications.services import create_threshold_notifications

from .ai_service import classifier
from .csv_import_service import (
    CSV_HEADERS,
    build_import_row,
    category_lookup,
    read_csv_rows,
    validate_edited_row,
)
from .forms import CSVTransactionImportForm, TransactionForm
from .mixins import AdminRequiredMixin, StudentRequiredMixin
logger = logging.getLogger(__name__)


TRANSACTION_SEARCH_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _parse_search_date(value):
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in TRANSACTION_SEARCH_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_search_amount(value):
    raw = (value or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("$", "").replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _apply_transaction_filters(queryset, params, *, include_user=False):
    keyword = (params.get("q") or "").strip()
    transaction_type = (params.get("type") or "").strip()
    category_id = (params.get("category") or "").strip()
    date_from_raw = (params.get("date_from") or "").strip()
    date_to_raw = (params.get("date_to") or "").strip()

    if keyword:
        search = (
            Q(description__icontains=keyword)
            | Q(category__name__icontains=keyword)
            | Q(type__icontains=keyword)
        )
        if include_user:
            search |= Q(user__email__icontains=keyword) | Q(user__profile__full_name__icontains=keyword)

        amount = _parse_search_amount(keyword)
        if amount is not None:
            search |= Q(amount=amount)

        search_date = _parse_search_date(keyword)
        if search_date is not None:
            search |= Q(date=search_date)

        if keyword.isdigit():
            search |= Q(pk=int(keyword))

        queryset = queryset.filter(search)

    if transaction_type in {"income", "expense"}:
        queryset = queryset.filter(type=transaction_type)

    if category_id.isdigit():
        queryset = queryset.filter(category_id=int(category_id))

    date_from = _parse_search_date(date_from_raw)
    date_to = _parse_search_date(date_to_raw)
    if date_from is not None:
        queryset = queryset.filter(date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(date__lte=date_to)

    return queryset


def _transaction_filter_context(params):
    return {
        "search_query": (params.get("q") or "").strip(),
        "selected_type": (params.get("type") or "").strip(),
        "selected_category": (params.get("category") or "").strip(),
        "date_from": (params.get("date_from") or "").strip(),
        "date_to": (params.get("date_to") or "").strip(),
        "search_categories": Category.objects.order_by("type", "name"),
    }


from .models import (
    Category,
    Transaction,
    TransactionImportBatch,
    TransactionImportRow,
)


class AdminCategoryListView(AdminRequiredMixin, ListView):
    model = Category
    template_name = "transaction/admin_category_list.html"
    context_object_name = "categories"


class AdminCategoryCreateView(AdminRequiredMixin, CreateView):
    model = Category
    template_name = "transaction/admin_category_form.html"
    fields = ["name", "type"]
    success_url = reverse_lazy("transactions:admin-category-list")


class AdminCategoryUpdateView(AdminRequiredMixin, UpdateView):
    model = Category
    template_name = "transaction/admin_category_form.html"
    fields = ["name", "type"]
    success_url = reverse_lazy("transactions:admin-category-list")


class AdminCategoryDeleteView(AdminRequiredMixin, DeleteView):
    model = Category
    template_name = "transaction/admin_category_confirm_delete.html"
    success_url = reverse_lazy("transactions:admin-category-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usage = self.object.reference_counts()
        context["category_usage"] = usage
        context["category_usage_total"] = sum(usage.values())
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        usage = self.object.reference_counts()
        usage_total = sum(usage.values())
        if usage_total:
            details = ", ".join(
                f"{label}: {count}" for label, count in usage.items() if count
            )
            messages.error(
                request,
                f"Category '{self.object.name}' cannot be deleted because it is still in use ({details}).",
            )
            return redirect(self.success_url)

        category_name = self.object.name
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Category '{category_name}' cannot be deleted because another record is using it.",
            )
        else:
            messages.success(request, f"Category '{category_name}' was deleted.")
        return redirect(self.success_url)


class AdminTransactionListView(AdminRequiredMixin, ListView):
    model = Transaction
    template_name = "transaction/admin_transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        queryset = Transaction.objects.select_related(
            "user", "user__profile", "category"
        ).all()
        return _apply_transaction_filters(
            queryset, self.request.GET, include_user=True
        ).order_by("-date", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_transaction_filter_context(self.request.GET))
        return context


class CategoryListView(StudentRequiredMixin, ListView):
    model = Category
    template_name = "transaction/category_list.html"
    context_object_name = "categories"


class TransactionListView(StudentRequiredMixin, ListView):
    model = Transaction
    template_name = "transaction/transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        queryset = Transaction.objects.select_related("category").filter(
            user=self.request.user
        )
        return _apply_transaction_filters(queryset, self.request.GET).order_by(
            "-date", "-created_at"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_transaction_filter_context(self.request.GET))
        return context


def _refresh_spending_notifications(user):
    try:
        create_threshold_notifications(user)
    except Exception:
        logger.exception("Could not refresh spending notifications for user %s", user.pk)


def _apply_ai_feedback(form, request, learn=True):
    description = (form.cleaned_data.get("description") or "").strip()
    selected_category = form.cleaned_data.get("category")
    transaction_type = form.cleaned_data.get("type")
    prediction = classifier.predict(description, transaction_type) if description else None

    if prediction:
        predicted_category = Category.objects.filter(pk=prediction["category_id"]).first()
        form.instance.ai_suggested_category = predicted_category
        form.instance.ai_prediction_confidence = prediction["confidence"]
        form.instance.ai_prediction_correct = bool(
            selected_category and selected_category.id == prediction["category_id"]
        )

    if selected_category and description and learn:
        classifier.learn(description, selected_category)
        form.instance.ai_feedback_at = timezone.now()

        if prediction and form.instance.ai_prediction_correct:
            messages.success(request, f"AI prediction confirmed: {selected_category.name}.")
        elif prediction:
            messages.info(
                request,
                f"Feedback saved: the AI suggested ‘{prediction['category_name']}’, "
                f"you selected ‘{selected_category.name}’. The AI learned from the final choice.",
            )
        else:
            messages.success(
                request,
                f"Saved ‘{selected_category.name}’ as new training feedback for the AI.",
            )


class TransactionCreateView(StudentRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transaction/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        _apply_ai_feedback(form, self.request)
        response = super().form_valid(form)
        _refresh_spending_notifications(self.request.user)
        return response


class TransactionUpdateView(StudentRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transaction/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def form_valid(self, form):
        ai_relevant_fields = {"description", "category", "type"}
        should_learn = bool(ai_relevant_fields.intersection(form.changed_data))
        _apply_ai_feedback(form, self.request, learn=should_learn)
        response = super().form_valid(form)
        _refresh_spending_notifications(self.request.user)
        return response

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class TransactionDeleteView(StudentRequiredMixin, DeleteView):
    model = Transaction
    template_name = "transaction/transaction_confirm_delete.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        _refresh_spending_notifications(self.request.user)
        return response


class TransactionCSVImportView(StudentRequiredMixin, View):
    template_name = "transaction/csv_import_upload.html"

    def get(self, request):
        return render(request, self.template_name, {"form": CSVTransactionImportForm()})

    def post(self, request):
        form = CSVTransactionImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        uploaded = form.cleaned_data["csv_file"]
        try:
            source_rows = read_csv_rows(uploaded)
        except ValueError as exc:
            form.add_error("csv_file", str(exc))
            return render(request, self.template_name, {"form": form})

        batch = TransactionImportBatch.objects.create(
            user=request.user,
            original_filename=uploaded.name[:255],
        )
        categories = category_lookup()
        import_rows = [
            build_import_row(batch, row_number, source_row, categories)
            for row_number, source_row in source_rows
        ]
        TransactionImportRow.objects.bulk_create(import_rows)

        invalid_count = sum(bool(row.validation_errors) for row in import_rows)
        if invalid_count:
            messages.warning(
                request,
                f"Read {len(import_rows)} row(s). {invalid_count} row(s) need review before confirmation.",
            )
        else:
            messages.success(
                request,
                f"AI classified {len(import_rows)} transaction(s). Review the staging table before confirmation.",
            )
        return redirect("transactions:csv-import-preview", batch_id=batch.pk)


class TransactionCSVTemplateView(StudentRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="campuscoin_transactions_template.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(CSV_HEADERS)
        writer.writerow(["expense", "", "45000", "Lunch at cafeteria", "2026-09-25"])
        writer.writerow(["income", "", "1500000", "Part-time job payment", "2026-09-24"])
        return response


def _student_batch_or_404(request, batch_id, *, draft_only=False):
    queryset = TransactionImportBatch.objects.filter(user=request.user)
    if draft_only:
        queryset = queryset.filter(status=TransactionImportBatch.Status.DRAFT)
    return get_object_or_404(queryset, pk=batch_id)


class TransactionCSVImportPreviewView(StudentRequiredMixin, View):
    template_name = "transaction/csv_import_preview.html"

    def _context(self, batch):
        rows = list(
            batch.rows.select_related("category", "ai_suggested_category").order_by("row_number")
        )
        categories = list(Category.objects.order_by("type", "name"))
        return {
            "batch": batch,
            "rows": rows,
            "categories": categories,
            "invalid_count": sum(bool(row.validation_errors) for row in rows),
            "category_data": [
                {"id": item.id, "name": item.name, "type": item.type}
                for item in categories
            ],
        }

    def get(self, request, batch_id):
        batch = _student_batch_or_404(request, batch_id)
        if batch.status == TransactionImportBatch.Status.CONFIRMED:
            messages.info(request, "This CSV batch has already been confirmed.")
            return redirect("transactions:transaction-list")
        return render(request, self.template_name, self._context(batch))

    def post(self, request, batch_id):
        batch = _student_batch_or_404(request, batch_id, draft_only=True)
        rows = list(batch.rows.select_related("category", "ai_suggested_category"))
        category_map = {str(item.pk): item for item in Category.objects.all()}
        any_errors = False

        for row in rows:
            prefix = f"row-{row.pk}"
            category = category_map.get(request.POST.get(f"{prefix}-category", ""))
            result = validate_edited_row(
                transaction_type=request.POST.get(f"{prefix}-type", ""),
                category=category,
                amount_text=request.POST.get(f"{prefix}-amount", ""),
                description=request.POST.get(f"{prefix}-description", ""),
                date_text=request.POST.get(f"{prefix}-date", ""),
            )

            prediction = result["prediction"]
            predicted_category = None
            confidence = None
            if prediction:
                predicted_category = category_map.get(str(prediction["category_id"]))
                confidence = prediction["confidence"]

            row.type = result["type"]
            row.category = result["category"]
            row.amount = result["amount"]
            row.description = result["description"]
            row.date = result["date"]
            row.ai_suggested_category = predicted_category
            row.ai_prediction_confidence = confidence
            row.validation_errors = result["errors"]
            row.review_note = ""
            row.save(
                update_fields=[
                    "type",
                    "category",
                    "amount",
                    "description",
                    "date",
                    "ai_suggested_category",
                    "ai_prediction_confidence",
                    "validation_errors",
                    "review_note",
                ]
            )
            any_errors = any_errors or bool(result["errors"])

        batch.save(update_fields=["updated_at"])
        action = request.POST.get("action", "save")
        if any_errors:
            messages.warning(request, "Changes were saved, but some rows are still invalid.")
            return redirect("transactions:csv-import-preview", batch_id=batch.pk)

        if action == "continue":
            messages.success(request, "All rows are valid. Review the summary and confirm the import.")
            return redirect("transactions:csv-import-confirm", batch_id=batch.pk)

        messages.success(request, "Your staging-table edits were saved.")
        return redirect("transactions:csv-import-preview", batch_id=batch.pk)


class TransactionCSVImportConfirmView(StudentRequiredMixin, View):
    template_name = "transaction/csv_import_confirm.html"

    def _rows(self, batch):
        return list(
            batch.rows.select_related("category", "ai_suggested_category").order_by("row_number")
        )

    def _summary(self, rows):
        income_total = sum(
            (row.amount or Decimal("0")) for row in rows if row.type == "income"
        )
        expense_total = sum(
            (row.amount or Decimal("0")) for row in rows if row.type == "expense"
        )
        counts = Counter(row.category.name for row in rows if row.category)
        return {
            "row_count": len(rows),
            "income_total": income_total,
            "expense_total": expense_total,
            "category_counts": sorted(counts.items(), key=lambda item: (-item[1], item[0])),
        }

    def get(self, request, batch_id):
        batch = _student_batch_or_404(request, batch_id, draft_only=True)
        rows = self._rows(batch)
        if any(row.validation_errors for row in rows):
            messages.warning(request, "Fix all invalid rows before confirming the import.")
            return redirect("transactions:csv-import-preview", batch_id=batch.pk)
        return render(
            request,
            self.template_name,
            {"batch": batch, "rows": rows, **self._summary(rows)},
        )

    def post(self, request, batch_id):
        with db_transaction.atomic():
            batch = get_object_or_404(
                TransactionImportBatch.objects.select_for_update(),
                pk=batch_id,
                user=request.user,
            )
            if batch.status == TransactionImportBatch.Status.CONFIRMED:
                messages.info(request, "This CSV batch was already imported and will not be imported again.")
                return redirect("transactions:transaction-list")

            rows = self._rows(batch)
            if not rows:
                messages.error(request, "This CSV batch has no rows left to confirm.")
                return redirect("transactions:csv-import-preview", batch_id=batch.pk)
            if any(row.validation_errors for row in rows):
                messages.warning(request, "The staging data changed and now contains validation errors. Review it again.")
                return redirect("transactions:csv-import-preview", batch_id=batch.pk)
            if any(
                not row.type
                or row.type not in {"income", "expense"}
                or not row.category_id
                or row.category.type != row.type
                or row.amount is None
                or row.amount <= 0
                or row.date is None
                for row in rows
            ):
                messages.error(request, "One or more rows are incomplete or invalid. Return to the staging table.")
                return redirect("transactions:csv-import-preview", batch_id=batch.pk)

            now = timezone.now()
            transactions_to_create = []
            training_examples = []
            for row in rows:
                predicted_id = row.ai_suggested_category_id
                transactions_to_create.append(
                    Transaction(
                        user=request.user,
                        type=row.type,
                        category=row.category,
                        amount=row.amount,
                        description=row.description or None,
                        date=row.date,
                        ai_suggested_category=row.ai_suggested_category,
                        ai_prediction_confidence=row.ai_prediction_confidence,
                        ai_prediction_correct=(
                            row.category_id == predicted_id if predicted_id else None
                        ),
                        ai_feedback_at=now if row.description and row.category_id else None,
                    )
                )
                if row.description and row.category_id:
                    training_examples.append((row.description, row.category))

            Transaction.objects.bulk_create(transactions_to_create)
            learned_count = classifier.learn_many(training_examples, source="csv_import")

            batch.status = TransactionImportBatch.Status.CONFIRMED
            batch.confirmed_at = now
            batch.save(update_fields=["status", "confirmed_at", "updated_at"])

        messages.success(
            request,
            f"Imported {len(transactions_to_create)} transaction(s) into SQL and added {learned_count} new AI training example(s).",
        )
        _refresh_spending_notifications(request.user)
        return redirect("transactions:transaction-list")


class TransactionCSVImportCancelView(StudentRequiredMixin, View):
    def post(self, request, batch_id):
        batch = _student_batch_or_404(request, batch_id, draft_only=True)
        batch.delete()
        messages.info(request, "The CSV batch was cancelled. No final transactions were added.")
        return redirect("transactions:csv-import")


def ai_predict_category(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)
    if not request.user.is_active or request.user.role.role_name != Role.Name.STUDENT:
        return JsonResponse({"detail": "Permission denied"}, status=403)

    description = (request.GET.get("description") or "").strip()
    txn_type = request.GET.get("type")
    if txn_type not in {"income", "expense"} or not description:
        return JsonResponse({"prediction": None})

    return JsonResponse({"prediction": classifier.predict(description, txn_type)})


def load_categories(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"detail": "Authentication required"}, status=401)

    if not user.is_active or user.role.role_name != Role.Name.STUDENT:
        return JsonResponse({"detail": "Permission denied"}, status=403)

    txn_type = request.GET.get("type")
    if txn_type not in {"income", "expense"}:
        return JsonResponse([], safe=False)

    categories = Category.objects.filter(type=txn_type).values("id", "name")
    return JsonResponse(list(categories), safe=False)
