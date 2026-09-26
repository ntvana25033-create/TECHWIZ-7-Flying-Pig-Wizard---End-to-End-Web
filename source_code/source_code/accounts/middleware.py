from datetime import timedelta

from django.contrib.auth import logout
from django.utils import timezone

from .models import UserSession
from .services import hash_session_key, record_login_session


class ActiveSessionMiddleware:
    ACTIVITY_UPDATE_INTERVAL = timedelta(minutes=5)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if not user.is_active:
                logout(request)
            else:
                self._validate_session(request, user)
        return self.get_response(request)

    def _validate_session(self, request, user):
        if not request.session.session_key:
            request.session.save()

        token_hash = hash_session_key(request.session.session_key)
        tracked = UserSession.objects.filter(
            session_token_hash=token_hash,
            user=user,
        ).first()

        if tracked is None:
            record_login_session(request, user)
            return

        now = timezone.now()
        if tracked.revoked_at is not None or tracked.expires_at <= now:
            logout(request)
            return

        if now - tracked.last_activity_at >= self.ACTIVITY_UPDATE_INTERVAL:
            tracked.last_activity_at = now
            tracked.expires_at = request.session.get_expiry_date()
            tracked.save(update_fields=["last_activity_at", "expires_at"])
