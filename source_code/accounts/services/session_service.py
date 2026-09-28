import hashlib

from django.utils import timezone

from accounts.models import UserSession


def hash_session_key(session_key):
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record_login_session(request, user):
    if not request.session.session_key:
        request.session.save()

    token_hash = hash_session_key(request.session.session_key)
    return UserSession.objects.update_or_create(
        session_token_hash=token_hash,
        defaults={
            "user": user,
            "ip_address": get_client_ip(request),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:500] or None,
            "expires_at": request.session.get_expiry_date(),
            "last_activity_at": timezone.now(),
            "revoked_at": None,
        },
    )[0]


def revoke_current_session(request):
    session_key = request.session.session_key
    if not session_key:
        return
    UserSession.objects.filter(
        session_token_hash=hash_session_key(session_key), revoked_at__isnull=True
    ).update(revoked_at=timezone.now())


def revoke_all_sessions(user):
    return user.login_sessions.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
