from django.contrib import admin
from .models import AITrainingExample, Category, Transaction

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type")
    list_filter = ("type",)
    search_fields = ("name",)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "date", "type", "category", "amount", "ai_prediction_correct")
    list_filter = ("type", "category", "ai_prediction_correct")
    search_fields = ("description", "user__email")

@admin.register(AITrainingExample)
class AITrainingExampleAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "source", "source_direction", "created_at", "text")
    list_filter = ("source", "category")
    search_fields = ("text",)
