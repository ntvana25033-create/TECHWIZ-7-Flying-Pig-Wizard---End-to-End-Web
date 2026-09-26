from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.forms import (
    AccountPasswordChangeForm,
    AdminProfileForm,
    AdminUserCreateForm,
    AdminUserEditForm,
    ForgotPasswordForm,
    LoginForm,
)
from accounts.models import Role, User, UserSession
from accounts.services import (
    hash_session_key,
    record_login_session,
    revoke_all_sessions,
    revoke_current_session,
    send_password_reset_email,
)


def admin_login_view(request):
    if request.user.is_authenticated:
        if request.user.role.role_name == Role.Name.ADMIN:
            return redirect("accounts:admin_dashboard")
        return redirect("transactions:transaction-list")

    form = LoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role.role_name != Role.Name.ADMIN:
            form.add_error(None, "This account does not have administrator privileges")
        else:
            login(request, user)
            record_login_session(request, user)
            messages.success(request, "Administrator login successful")
            return redirect("accounts:admin_dashboard")

    return render(
        request,
        "accounts/admin/login.html",
        {"form": form, "admin_portal": True},
    )


def admin_forgot_password_view(request):
    if request.user.is_authenticated:
        if request.user.role.role_name == Role.Name.ADMIN:
            return redirect("accounts:admin_dashboard")
        return redirect("transactions:transaction-list")

    form = ForgotPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(
            email__iexact=email,
            role__role_name=Role.Name.ADMIN,
            status__in=[User.Status.ACTIVE, User.Status.LOCKED],
            deleted_at__isnull=True,
        ).first()
        if user:
            send_password_reset_email(request, user)
        messages.success(
            request,
            "If the administrator email exists in the system, a password reset link has been sent",
        )
        return redirect("accounts:admin_forgot_password")

    return render(
        request,
        "accounts/admin/forgot_password.html",
        {"form": form, "admin_portal": True},
    )


@admin_required
def admin_logout_view(request):
    revoke_current_session(request)
    logout(request)
    messages.success(request, "Signed out of the Admin Portal")
    return redirect("accounts:admin_login")


@admin_required
def admin_dashboard_view(request):
    users = User.objects.filter(deleted_at__isnull=True)
    students = users.filter(role__role_name=Role.Name.STUDENT)
    context = {
        "total_students": students.count(),
        "active_students": students.filter(status=User.Status.ACTIVE).count(),
        "locked_students": students.filter(status=User.Status.LOCKED).count(),
        "disabled_students": students.filter(status=User.Status.DISABLED).count(),
        "total_admins": users.filter(role__role_name=Role.Name.ADMIN).count(),
        "recent_users": students.select_related("role", "profile").order_by("-created_at")[:8],
    }
    return render(request, "accounts/admin/dashboard.html", context)


@admin_required
def admin_user_list_view(request):
    keyword = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    role = request.GET.get("role", "").strip()
    users = User.objects.select_related("role", "profile").filter(
        deleted_at__isnull=True
    ).order_by("-created_at")

    if keyword:
        users = users.filter(
            Q(email__icontains=keyword) | Q(profile__full_name__icontains=keyword)
        )
    if status in User.Status.values:
        users = users.filter(status=status)
    if role in Role.Name.values:
        users = users.filter(role__role_name=role)

    return render(
        request,
        "accounts/admin/user_list.html",
        {
            "users": users,
            "keyword": keyword,
            "status": status,
            "role": role,
            "statuses": User.Status.choices,
            "roles": Role.Name.choices,
        },
    )


@admin_required
def admin_user_create_view(request):
    form = AdminUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Created account {user.email}")
        return redirect("accounts:admin_user_detail", user_id=user.pk)
    return render(request, "accounts/admin/user_form.html", {"form": form, "mode": "create"})


@admin_required
def admin_user_detail_view(request, user_id):
    target = get_object_or_404(
        User.objects.select_related("role", "profile").filter(deleted_at__isnull=True),
        pk=user_id,
    )
    sessions = target.login_sessions.order_by("-last_activity_at")[:10]
    return render(
        request,
        "accounts/admin/user_detail.html",
        {"target": target, "sessions": sessions},
    )


@admin_required
def admin_user_edit_view(request, user_id):
    target = get_object_or_404(
        User.objects.select_related("role", "profile").filter(deleted_at__isnull=True),
        pk=user_id,
    )
    form = AdminUserEditForm(request.POST or None, user=target)
    if request.method == "POST" and form.is_valid():
        if target.pk == request.user.pk:
            if form.cleaned_data["role"] != Role.Name.ADMIN:
                form.add_error("role", "You cannot downgrade the role of the account you are currently using")
            if form.cleaned_data["status"] != User.Status.ACTIVE:
                form.add_error("status", "You cannot lock or disable the account you are currently using")
        if not form.errors:
            previous_status = target.status
            previous_role = target.role.role_name
            user = form.save()
            if previous_role != user.role.role_name or (
                previous_status == User.Status.ACTIVE and user.status != User.Status.ACTIVE
            ):
                revoke_all_sessions(user)
            messages.success(request, "Account updated successfully")
            return redirect("accounts:admin_user_detail", user_id=user.pk)

    return render(
        request,
        "accounts/admin/user_form.html",
        {"form": form, "mode": "edit", "target": target},
    )


@admin_required
def admin_user_toggle_status_view(request, user_id):
    if request.method != "POST":
        return redirect("accounts:admin_user_detail", user_id=user_id)

    target = get_object_or_404(User, pk=user_id, deleted_at__isnull=True)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot disable your own account")
        return redirect("accounts:admin_user_detail", user_id=user_id)

    if target.status == User.Status.ACTIVE:
        target.status = User.Status.DISABLED
        revoke_all_sessions(target)
        messages.success(request, "Account disabled successfully")
    else:
        target.status = User.Status.ACTIVE
        target.failed_login_attempts = 0
        target.locked_until = None
        messages.success(request, "Account activated successfully")

    target.save(
        update_fields=[
            "status",
            "failed_login_attempts",
            "locked_until",
            "updated_at",
        ]
    )
    return redirect("accounts:admin_user_detail", user_id=user_id)


@admin_required
def admin_user_send_reset_view(request, user_id):
    if request.method != "POST":
        return redirect("accounts:admin_user_detail", user_id=user_id)
    target = get_object_or_404(User, pk=user_id, deleted_at__isnull=True)
    if target.status == User.Status.DISABLED:
        messages.error(request, "This account is disabled. Activate it before sending a reset link")
        return redirect("accounts:admin_user_detail", user_id=user_id)
    if send_password_reset_email(request, target):
        messages.success(request, "Password reset link created and sent")
    else:
        messages.error(request, "Unable to send the reset email. Check the EMAIL configuration in .env")
    return redirect("accounts:admin_user_detail", user_id=user_id)


@admin_required
def admin_user_delete_view(request, user_id):
    if request.method != "POST":
        return redirect("accounts:admin_user_detail", user_id=user_id)
    target = get_object_or_404(User, pk=user_id, deleted_at__isnull=True)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot delete the account you are currently using")
        return redirect("accounts:admin_user_detail", user_id=user_id)
    target.deleted_at = timezone.now()
    target.status = User.Status.DISABLED
    target.save(update_fields=["deleted_at", "status", "updated_at"])
    revoke_all_sessions(target)
    messages.success(request, "Account soft-deleted from the system")
    return redirect("accounts:admin_user_list")


@admin_required
def admin_profile_view(request):
    form = AdminProfileForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Administrator profile updated successfully")
        return redirect("accounts:admin_profile")
    return render(request, "accounts/admin/profile.html", {"form": form})


@admin_required
def admin_change_password_view(request):
    form = AccountPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        revoke_all_sessions(user)
        update_session_auth_hash(request, user)
        record_login_session(request, user)
        messages.success(request, "Password changed successfully. Other administrator sessions have been signed out")
        return redirect("accounts:admin_profile")
    return render(request, "accounts/admin/change_password.html", {"form": form})


@admin_required
def admin_sessions_view(request):
    current_hash = None
    if request.session.session_key:
        current_hash = hash_session_key(request.session.session_key)
    sessions = request.user.login_sessions.order_by("-last_activity_at")
    return render(
        request,
        "accounts/admin/sessions.html",
        {"sessions": sessions, "current_hash": current_hash},
    )


@admin_required
def admin_revoke_session_view(request, session_id):
    tracked = get_object_or_404(UserSession, pk=session_id, user=request.user)
    if request.method != "POST":
        return redirect("accounts:admin_sessions")
    is_current = bool(
        request.session.session_key
        and tracked.session_token_hash == hash_session_key(request.session.session_key)
    )
    tracked.revoke()
    messages.success(request, "Administrator session revoked")
    if is_current:
        logout(request)
        return redirect("accounts:admin_login")
    return redirect("accounts:admin_sessions")