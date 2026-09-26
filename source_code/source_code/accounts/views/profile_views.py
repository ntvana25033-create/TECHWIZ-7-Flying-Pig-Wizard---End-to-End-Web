from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.shortcuts import get_object_or_404, redirect, render

# Removed 'source_code.' from the four import lines below
from accounts.decorators import student_required
from accounts.forms import AccountPasswordChangeForm, ProfileForm
from accounts.models import UserSession
from accounts.services import hash_session_key, record_login_session, revoke_all_sessions


@student_required
def profile_view(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user.profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated successfully")
        return redirect("accounts:profile")
    return render(request, "accounts/profile/profile.html", {"form": form})


@student_required
def change_password_view(request):
    form = AccountPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        revoke_all_sessions(user)
        update_session_auth_hash(request, user)
        record_login_session(request, user)
        messages.success(request, "Password changed successfully. Other sessions have been signed out")
        return redirect("accounts:profile")
    return render(request, "accounts/profile/change_password.html", {"form": form})


@student_required
def sessions_view(request):
    current_hash = None
    if request.session.session_key:
        current_hash = hash_session_key(request.session.session_key)
    sessions = request.user.login_sessions.order_by("-last_activity_at")
    return render(
        request,
        "accounts/profile/sessions.html",
        {"sessions": sessions, "current_hash": current_hash},
    )


@student_required
def revoke_session_view(request, session_id):
    tracked = get_object_or_404(UserSession, pk=session_id, user=request.user)
    if request.method != "POST":
        return redirect("accounts:sessions")

    is_current = bool(
        request.session.session_key
        and tracked.session_token_hash == hash_session_key(request.session.session_key)
    )
    tracked.revoke()
    messages.success(request, "Login session revoked")
    if is_current:
        logout(request)
        return redirect("accounts:login")
    return redirect("accounts:sessions")