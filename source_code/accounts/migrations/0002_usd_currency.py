from django.db import migrations, models


def set_profiles_to_usd(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.exclude(currency_code="USD").update(currency_code="USD")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="currency_code",
            field=models.CharField(default="USD", max_length=3),
        ),
        migrations.RunPython(set_profiles_to_usd, migrations.RunPython.noop),
    ]
