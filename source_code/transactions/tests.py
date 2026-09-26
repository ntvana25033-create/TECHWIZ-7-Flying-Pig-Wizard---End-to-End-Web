from datetime import date

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

from .models import AITrainingExample, Category, Transaction


class TransactionPermissionTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(role_name=Role.Name.ADMIN)
        self.student_role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)

        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="AdminTest123!",
            role=self.admin_role,
        )
        self.student = User.objects.create_user(
            email="student@example.com",
            password="StudentTest123!",
            role=self.student_role,
        )
        self.other_student = User.objects.create_user(
            email="other@example.com",
            password="OtherTest123!",
            role=self.student_role,
        )
        self.category = Category.objects.create(name="Food and dining", type="expense")
        self.other_transaction = Transaction.objects.create(
            user=self.other_student,
            category=self.category,
            amount=50000,
            type="expense",
            description="Another user's transaction",
            date=date.today(),
        )

    def test_guest_is_redirected_to_admin_login(self):
        response = self.client.get(reverse("transactions:admin-category-list"))
        self.assertRedirects(
            response,
            reverse("accounts:admin_login"),
            fetch_redirect_response=False,
        )

    def test_student_cannot_access_admin_transaction_pages(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("transactions:admin-category-list"))
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access_admin_transaction_pages(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("transactions:admin-category-list"))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_use_student_transaction_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("transactions:transaction-list"))
        self.assertRedirects(
            response,
            reverse("accounts:admin_dashboard"),
            fetch_redirect_response=False,
        )

    def test_student_cannot_edit_another_students_transaction(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse(
                "transactions:transaction-update",
                args=[self.other_transaction.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_ajax_categories_requires_student_role(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("transactions:ajax_load_categories"),
            {"type": "expense"},
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.student)
        response = self.client.get(
            reverse("transactions:ajax_load_categories"),
            {"type": "expense"},
        )
        self.assertEqual(response.status_code, 200)


class TransactionAIFeedbackTests(TestCase):
    def setUp(self):
        self.student_role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        self.student = User.objects.create_user(
            email="ai-student@example.com",
            password="StudentTest123!",
            role=self.student_role,
        )
        self.food = Category.objects.create(name="Food", type="expense")
        self.salary = Category.objects.create(name="Part-time Job", type="income")
        AITrainingExample.objects.create(
            text="coffee lunch cafeteria",
            category=self.food,
            source="excel",
        )
        self.client.force_login(self.student)

    def test_ai_prediction_does_not_train_model(self):
        before = AITrainingExample.objects.count()
        response = self.client.get(
            reverse("transactions:ajax_ai_predict"),
            {"type": "expense", "description": "coffee lunch"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["prediction"]["category_id"], self.food.id)
        self.assertEqual(AITrainingExample.objects.count(), before)

    def test_submit_transaction_adds_feedback_training_example(self):
        before = AITrainingExample.objects.count()
        response = self.client.post(
            reverse("transactions:transaction-create"),
            {
                "type": "expense",
                "category": self.food.id,
                "amount": "45000.00",
                "description": "coffee lunch",
                "date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AITrainingExample.objects.count(), before + 1)
        self.assertTrue(
            AITrainingExample.objects.filter(
                text="coffee lunch",
                category=self.food,
                source="user_feedback",
            ).exists()
        )

    def test_submit_learns_even_when_ai_has_no_prediction_yet(self):
        before = AITrainingExample.objects.count()
        response = self.client.post(
            reverse("transactions:transaction-create"),
            {
                "type": "income",
                "category": self.salary.id,
                "amount": "120000.00",
                "description": "translation freelance payment",
                "date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AITrainingExample.objects.count(), before + 1)
        self.assertTrue(
            AITrainingExample.objects.filter(
                text="translation freelance payment",
                category=self.salary,
                source="user_feedback",
            ).exists()
        )

    def test_category_type_must_match_transaction_type(self):
        response = self.client.post(
            reverse("transactions:transaction-create"),
            {
                "type": "expense",
                "category": self.salary.id,
                "amount": "45000.00",
                "description": "coffee lunch",
                "date": date.today().isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Category không phù hợp")
        self.assertFalse(
            Transaction.objects.filter(
                user=self.student,
                description="coffee lunch",
            ).exists()
        )


class TransactionCSVImportTests(TestCase):
    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .ai_service import classifier

        self.SimpleUploadedFile = SimpleUploadedFile
        classifier.invalidate()
        self.student_role, _ = Role.objects.get_or_create(role_name=Role.Name.STUDENT)
        self.student = User.objects.create_user(
            email="csv-student@example.com",
            password="StudentTest123!",
            role=self.student_role,
        )
        self.other_student = User.objects.create_user(
            email="csv-other@example.com",
            password="StudentTest123!",
            role=self.student_role,
        )
        self.food = Category.objects.create(name="Food", type="expense")
        self.salary = Category.objects.create(name="Part-time Job", type="income")
        AITrainingExample.objects.create(
            text="mua com trua cafeteria",
            category=self.food,
            source="test",
        )
        AITrainingExample.objects.create(
            text="nhan luong lam them",
            category=self.salary,
            source="test",
        )
        self.client.force_login(self.student)

    def _upload(self):
        content = (
            "type,category,amount,description,date\n"
            "expense,,45000,mua com trua cafeteria,2026-09-25\n"
            "income,,1500000,nhan luong lam them,2026-09-24\n"
        )
        upload = self.SimpleUploadedFile(
            "transactions.csv",
            content.encode("utf-8"),
            content_type="text/csv",
        )
        return self.client.post(reverse("transactions:csv-import"), {"csv_file": upload})

    def test_upload_creates_staging_only(self):
        from .models import TransactionImportBatch

        response = self._upload()
        self.assertEqual(response.status_code, 302)
        batch = TransactionImportBatch.objects.get(user=self.student)
        self.assertEqual(batch.rows.count(), 2)
        self.assertEqual(Transaction.objects.filter(user=self.student).count(), 0)
        self.assertTrue(all(row.category_id for row in batch.rows.all()))

    def test_confirm_creates_transactions_and_marks_batch(self):
        from .models import TransactionImportBatch

        self._upload()
        batch = TransactionImportBatch.objects.get(user=self.student)
        post_data = {"action": "continue"}
        for row in batch.rows.all():
            prefix = f"row-{row.pk}"
            post_data[f"{prefix}-type"] = row.type
            post_data[f"{prefix}-amount"] = str(row.amount)
            post_data[f"{prefix}-description"] = row.description
            post_data[f"{prefix}-date"] = row.date.isoformat()
            post_data[f"{prefix}-category"] = str(row.category_id)

        response = self.client.post(
            reverse("transactions:csv-import-preview", args=[batch.pk]),
            post_data,
        )
        self.assertRedirects(
            response,
            reverse("transactions:csv-import-confirm", args=[batch.pk]),
            fetch_redirect_response=False,
        )
        response = self.client.post(
            reverse("transactions:csv-import-confirm", args=[batch.pk])
        )
        self.assertRedirects(
            response,
            reverse("transactions:transaction-list"),
            fetch_redirect_response=False,
        )
        batch.refresh_from_db()
        self.assertEqual(batch.status, TransactionImportBatch.Status.CONFIRMED)
        self.assertEqual(Transaction.objects.filter(user=self.student).count(), 2)

    def test_student_cannot_open_another_students_batch(self):
        from .models import TransactionImportBatch

        other_batch = TransactionImportBatch.objects.create(
            user=self.other_student,
            original_filename="other.csv",
        )
        response = self.client.get(
            reverse("transactions:csv-import-preview", args=[other_batch.pk])
        )
        self.assertEqual(response.status_code, 404)
