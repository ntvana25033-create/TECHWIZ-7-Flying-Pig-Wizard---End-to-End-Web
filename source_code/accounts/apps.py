from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    label = "accounts"
    verbose_name = "Tài khoản và bảo mật"

    def ready(self):
        from . import signals  # noqa: F401