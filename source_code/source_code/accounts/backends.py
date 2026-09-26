from datetime import timedelta

from django.contrib.auth.backends import BaseBackend
from django.utils import timezone

from .models import User


class EmailAuthenticationBackend(BaseBackend):
    MAX_FAILED_ATTEMPTS = 5
    LOCK_MINUTES = 15

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        login_email = (email or username or "").strip().lower()
        if not login_email or not password:
            return None

        user = User.objects.select_related("role").filter(
            email__iexact=login_email,
            deleted_at__isnull=True,
        ).first()
        if user is None:
            return None

        now = timezone.now()
        if user.status == User.Status.LOCKED:
            if user.locked_until and user.locked_until > now:
                return None
            user.status = User.Status.ACTIVE
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(
                update_fields=[
                    "status",
                    "failed_login_attempts",
                    "locked_until",
                    "updated_at",
                ]
            )

        if user.status != User.Status.ACTIVE:
            return None

        if user.check_password(password):
            if user.failed_login_attempts or user.locked_until:
                user.failed_login_attempts = 0
                user.locked_until = None
                user.save(
                    update_fields=[
                        "failed_login_attempts",
                        "locked_until",
                        "updated_at",
                    ]
                )
            return user

        user.failed_login_attempts = min(user.failed_login_attempts + 1, 100)
        update_fields = ["failed_login_attempts", "updated_at"]
        if user.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS:
            user.status = User.Status.LOCKED
            user.locked_until = now + timedelta(minutes=self.LOCK_MINUTES)
            update_fields.extend(["status", "locked_until"])
        user.save(update_fields=update_fields)
        return None

    def get_user(self, user_id):
        return User.objects.select_related("role").filter(
            pk=user_id,
            deleted_at__isnull=True,
        ).first()
