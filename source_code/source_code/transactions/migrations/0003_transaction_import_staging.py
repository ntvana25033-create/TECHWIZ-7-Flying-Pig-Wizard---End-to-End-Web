from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("transactions", "0002_ai_feedback"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransactionImportBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_filename", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("confirmed", "Confirmed")], default="draft", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transaction_import_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TransactionImportRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField()),
                ("type", models.CharField(blank=True, max_length=10)),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("description", models.TextField(blank=True)),
                ("date", models.DateField(blank=True, null=True)),
                ("ai_prediction_confidence", models.FloatField(blank=True, null=True)),
                ("validation_errors", models.JSONField(blank=True, default=list)),
                ("review_note", models.CharField(blank=True, max_length=500)),
                ("source_row", models.JSONField(blank=True, default=dict)),
                ("ai_suggested_category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_suggested_import_rows", to="transactions.category")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="transactions.transactionimportbatch")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="csv_import_rows", to="transactions.category")),
            ],
            options={"ordering": ["row_number"]},
        ),
        migrations.AddConstraint(
            model_name="transactionimportrow",
            constraint=models.UniqueConstraint(fields=("batch", "row_number"), name="uniq_transaction_import_batch_row"),
        ),
    ]
