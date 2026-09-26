from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "kind",
        "severity",
        "is_read",
        "emailed_at",
        "created_at",
    )
    list_filter = ("kind", "severity", "is_read")
    search_fields = ("user__email", "title", "message", "dedup_key")
    readonly_fields = ("created_at", "emailed_at", "email_error")
