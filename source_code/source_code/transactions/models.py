from django.conf import settings
from django.db import models


class Category(models.Model):
    TYPE_CHOICES = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    name = models.CharField(max_length=255, verbose_name="Category name")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Type")

    def __str__(self):
        return self.name


class AITrainingExample(models.Model):
    text = models.TextField(verbose_name="Training text")
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name="ai_training_examples", verbose_name="Training category"
    )
    source = models.CharField(max_length=30, default="excel", verbose_name="Data source")
    source_direction = models.CharField(max_length=20, blank=True, null=True, verbose_name="Excel In / Out")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["category"], name="idx_ai_training_category")]

    def __str__(self):
        return f"{self.category.name}: {self.text[:60]}"


class Transaction(models.Model):
    TYPE_CHOICES = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="User")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, verbose_name="Category")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Amount")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Transaction type")
    description = models.TextField(blank=True, null=True, verbose_name="Description")

    ai_suggested_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_suggested_transactions',
        verbose_name="AI suggested category"
    )

    date = models.DateField(verbose_name="Transaction date")
    ai_prediction_confidence = models.FloatField(null=True, blank=True, verbose_name="AI confidence")
    ai_prediction_correct = models.BooleanField(null=True, blank=True, verbose_name="AI prediction correct")
    ai_feedback_at = models.DateTimeField(null=True, blank=True, verbose_name="AI feedback time")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.amount} - {self.date}"


class TransactionImportBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transaction_import_batches",
    )
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} - {self.original_filename} - {self.status}"


class TransactionImportRow(models.Model):
    batch = models.ForeignKey(
        TransactionImportBatch,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_number = models.PositiveIntegerField()
    type = models.CharField(max_length=10, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="csv_import_rows",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    description = models.TextField(blank=True)
    date = models.DateField(blank=True, null=True)
    ai_suggested_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="ai_suggested_import_rows",
    )
    ai_prediction_confidence = models.FloatField(blank=True, null=True)
    validation_errors = models.JSONField(default=list, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    source_row = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"],
                name="uniq_transaction_import_batch_row",
            )
        ]

    @property
    def is_valid(self):
        return not self.validation_errors

    def __str__(self):
        return f"Batch {self.batch_id} - row {self.row_number}"
