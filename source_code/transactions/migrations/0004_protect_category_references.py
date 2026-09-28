from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0003_transaction_import_staging"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aitrainingexample",
            name="category",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="ai_training_examples",
                to="transactions.category",
                verbose_name="Training category",
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=models.PROTECT,
                to="transactions.category",
                verbose_name="Category",
            ),
        ),
        migrations.AlterField(
            model_name="transaction",
            name="ai_suggested_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="ai_suggested_transactions",
                to="transactions.category",
                verbose_name="AI suggested category",
            ),
        ),
        migrations.AlterField(
            model_name="transactionimportrow",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="csv_import_rows",
                to="transactions.category",
            ),
        ),
        migrations.AlterField(
            model_name="transactionimportrow",
            name="ai_suggested_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="ai_suggested_import_rows",
                to="transactions.category",
            ),
        ),
    ]
