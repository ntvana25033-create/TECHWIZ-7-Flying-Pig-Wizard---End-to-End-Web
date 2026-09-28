from django.contrib import admin

from .models import ChatMessage, ChatSession


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "intent", "rating", "created_at")
    fields = readonly_fields
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "last_message_at")
    search_fields = ("user__email", "title")
    list_filter = ("created_at", "last_message_at")
    readonly_fields = ("created_at", "updated_at", "last_message_at")
    inlines = [ChatMessageInline]


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "intent", "rating", "created_at")
    search_fields = ("content", "session__user__email")
    list_filter = ("role", "intent", "rating", "created_at")
    readonly_fields = ("created_at",)
