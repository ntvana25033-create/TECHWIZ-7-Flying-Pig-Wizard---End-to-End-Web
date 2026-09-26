import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from accounts.models import PasswordResetToken

logger = logging.getLogger(__name__)


def create_password_reset_token(user, lifetime_minutes=30):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = timezone.now()

    PasswordResetToken.objects.filter(
        user=user,
        used_at__isnull=True,
        expires_at__gt=now,
    ).update(used_at=now)

    PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=lifetime_minutes),
    )
    return raw_token


def find_valid_reset_token(raw_token):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return PasswordResetToken.objects.select_related("user", "user__role").filter(
        token_hash=token_hash,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
        user__deleted_at__isnull=True,
    ).first()


def send_password_reset_email(request, user):
    raw_token = create_password_reset_token(user)
    path = reverse("accounts:reset_password", kwargs={"token": raw_token})
    if settings.PUBLIC_BASE_URL:
        reset_url = f"{settings.PUBLIC_BASE_URL}{path}"
    else:
        reset_url = request.build_absolute_uri(path)

    subject = "Campus Coin - Reset Password"
    display_name = user.get_full_name() or user.email
    safe_display_name = escape(display_name)
    safe_reset_url = escape(reset_url)
    text_body = (
        f"Hello {display_name},\n\n"
        "You recently requested a password reset for Campus Coin.\n"
        f"Open the following link to create a new password:\n{reset_url}\n\n"
        "This link is valid for 30 minutes.\n"
        "If you did not request this action, you can ignore this email."
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#1f2937">
      <h2 style="margin-bottom:8px">Reset your Campus Coin password</h2>
      <p>Hello <strong>{safe_display_name}</strong>,</p>
      <p>You recently requested a password reset for Campus Coin.</p>
      <p style="margin:24px 0">
        <a href="{safe_reset_url}" style="background:#2563eb;color:white;padding:12px 18px;text-decoration:none;border-radius:8px;display:inline-block">
          Reset Password
        </a>
      </p>
      <p>This link is valid for <strong>30 minutes</strong>.</p>
      <p>If you did not request this action, you can ignore this email.</p>
      <p style="font-size:12px;color:#6b7280">If the button does not work, open this link: {safe_reset_url}</p>
    </div>
    """

    try:
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_body, "text/html")
        return email.send(fail_silently=False) > 0
    except Exception:
        logger.exception("Unable to send password reset email for user_id=%s", user.pk)
        return False
