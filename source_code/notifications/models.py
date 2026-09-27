from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        WEEKLY_SUMMARY = "weekly_summary", "Weekly summary"
        MONTHLY_SUMMARY = "monthly_summary", "Monthly summary"
        SAVINGS_THRESHOLD = "savings_threshold", "Savings goal warning"
        LOW_BALANCE = "low_balance", "Low balance warning"

    class Severity(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.INFO,
    )
    title = models.CharField(max_length=180)
    message = models.TextField()
    period_start = models.DateField(blank=True, null=True)
    period_end = models.DateField(blank=True, null=True)
    income_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    expense_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    savings_goal = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    action_path = models.CharField(max_length=500, default="/notifications/")
    dedup_key = models.CharField(max_length=190, unique=True)
    is_read = models.BooleanField(default=False)
    emailed_at = models.DateTimeField(blank=True, null=True)
    email_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"], name="idx_notif_user_unread"),
            models.Index(fields=["kind", "created_at"], name="idx_notif_kind_created"),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.get_kind_display()} - {self.title}"
