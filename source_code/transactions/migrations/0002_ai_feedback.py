from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("transactions", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="AITrainingExample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.TextField(verbose_name="Training text")),
                ("source", models.CharField(default="excel", max_length=30, verbose_name="Data source")),
                ("source_direction", models.CharField(blank=True, max_length=20, null=True, verbose_name="Excel In / Out")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_training_examples", to="transactions.category", verbose_name="Training category")),
            ],
        ),
        migrations.AddIndex(model_name="aitrainingexample", index=models.Index(fields=["category"], name="idx_ai_training_category")),
        migrations.AddField(model_name="transaction", name="ai_prediction_confidence", field=models.FloatField(blank=True, null=True, verbose_name="AI confidence")),
        migrations.AddField(model_name="transaction", name="ai_prediction_correct", field=models.BooleanField(blank=True, null=True, verbose_name="AI prediction correct")),
        migrations.AddField(model_name="transaction", name="ai_feedback_at", field=models.DateTimeField(blank=True, null=True, verbose_name="AI feedback time")),
    ]
