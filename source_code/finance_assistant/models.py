from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="finance_chat_sessions",
    )
    title = models.CharField(max_length=120, default="New finance chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_sessions"
        ordering = ["-last_message_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-last_message_at"], name="idx_chat_user_recent"),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.title}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    class Rating(models.IntegerChoices):
        HELPFUL = 1, "Helpful"
        NONE = 0, "Not rated"
        NOT_HELPFUL = -1, "Not helpful"

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    intent = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    rating = models.SmallIntegerField(choices=Rating.choices, default=Rating.NONE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="idx_chat_msg_session"),
        ]

    def __str__(self):
        return f"{self.session_id} - {self.role} - {self.created_at:%Y-%m-%d %H:%M}"
