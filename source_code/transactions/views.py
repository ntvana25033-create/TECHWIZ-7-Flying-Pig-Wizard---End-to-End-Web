import csv
from collections import Counter
from decimal import Decimal

from django.contrib import messages
from django.db import transaction as db_transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models import Role

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


class AdminTransactionListView(AdminRequiredMixin, ListView):
    model = Transaction
    template_name = "transaction/admin_transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        return (
            Transaction.objects.select_related("user", "category")
            .all()
            .order_by("-date", "-created_at")
        )


class CategoryListView(StudentRequiredMixin, ListView):
    model = Category
    template_name = "transaction/category_list.html"
    context_object_name = "categories"


class TransactionListView(StudentRequiredMixin, ListView):
    model = Transaction
    template_name = "transaction/transaction_list.html"
    context_object_name = "transactions"

    def get_queryset(self):
        return (
            Transaction.objects.select_related("category")
            .filter(user=self.request.user)
            .order_by("-date", "-created_at")
        )


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
            messages.success(request, f"AI dự đoán đúng: {selected_category.name}.")
        elif prediction:
            messages.info(
                request,
                f"Đã ghi nhận phản hồi: AI đoán ‘{prediction['category_name']}’, "
                f"bạn chọn ‘{selected_category.name}’. AI đã học dữ liệu mới.",
            )
        else:
            messages.success(
                request,
                f"Đã ghi nhận ‘{selected_category.name}’ làm dữ liệu mới để AI học.",
            )


class TransactionCreateView(StudentRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transaction/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        _apply_ai_feedback(form, self.request)
        return super().form_valid(form)


class TransactionUpdateView(StudentRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transaction/transaction_form.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def form_valid(self, form):
        ai_relevant_fields = {"description", "category", "type"}
        should_learn = bool(ai_relevant_fields.intersection(form.changed_data))
        _apply_ai_feedback(form, self.request, learn=should_learn)
        return super().form_valid(form)

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


class TransactionDeleteView(StudentRequiredMixin, DeleteView):
    model = Transaction
    template_name = "transaction/transaction_confirm_delete.html"
    success_url = reverse_lazy("transactions:transaction-list")

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


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
                f"Đã đọc {len(import_rows)} dòng. Có {invalid_count} dòng cần kiểm tra/sửa trước khi xác nhận.",
            )
        else:
            messages.success(
                request,
                f"AI đã phân loại {len(import_rows)} giao dịch. Hãy kiểm tra lại trước khi xác nhận.",
            )
        return redirect("transactions:csv-import-preview", batch_id=batch.pk)


class TransactionCSVTemplateView(StudentRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="campuscoin_transactions_template.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(CSV_HEADERS)
        writer.writerow(["expense", "", "45000", "Mua cơm trưa", "2026-09-25"])
        writer.writerow(["income", "", "1500000", "Nhận lương làm thêm", "2026-09-24"])
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
            messages.info(request, "Lô CSV này đã được xác nhận trước đó.")
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
            messages.warning(request, "Đã lưu thay đổi, nhưng vẫn còn dòng chưa hợp lệ.")
            return redirect("transactions:csv-import-preview", batch_id=batch.pk)

        if action == "continue":
            messages.success(request, "Dữ liệu đã hợp lệ. Kiểm tra tóm tắt và xác nhận lần cuối.")
            return redirect("transactions:csv-import-confirm", batch_id=batch.pk)

        messages.success(request, "Đã lưu các chỉnh sửa trong bảng tạm.")
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
            messages.warning(request, "Hãy sửa hết các dòng lỗi trước khi xác nhận.")
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
                messages.info(request, "Lô CSV này đã được nhập trước đó, hệ thống không nhập lại.")
                return redirect("transactions:transaction-list")

            rows = self._rows(batch)
            if not rows:
                messages.error(request, "Lô CSV không còn dữ liệu để xác nhận.")
                return redirect("transactions:csv-import-preview", batch_id=batch.pk)
            if any(row.validation_errors for row in rows):
                messages.warning(request, "Dữ liệu đã thay đổi và có lỗi. Hãy kiểm tra lại.")
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
                messages.error(request, "Có dòng thiếu hoặc không hợp lệ. Hãy quay lại bảng xem trước.")
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
            f"Đã nhập {len(transactions_to_create)} giao dịch vào SQL và bổ sung {learned_count} mẫu mới cho AI.",
        )
        return redirect("transactions:transaction-list")


class TransactionCSVImportCancelView(StudentRequiredMixin, View):
    def post(self, request, batch_id):
        batch = _student_batch_or_404(request, batch_id, draft_only=True)
        batch.delete()
        messages.info(request, "Đã hủy lô CSV. Chưa có Transaction nào được thêm vào hệ thống.")
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
