from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from accounts.models import Role, User
from accounts.services import (
    find_valid_reset_token,
    record_login_session,
    revoke_all_sessions,
    revoke_current_session,
    send_password_reset_email,
)


def home_view(request):
    if request.user.is_authenticated:
        if request.user.role.role_name == Role.Name.ADMIN:
            return redirect("accounts:admin_dashboard")
        return redirect("transactions:transaction-list")
    return redirect("accounts:login")


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def register_view(request):
    if request.user.is_authenticated:
        if request.user.role.role_name == Role.Name.ADMIN:
            return redirect("accounts:admin_dashboard")
        return redirect("transactions:transaction-list")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailAuthenticationBackend")
        record_login_session(request, user)
        messages.success(request, "Tạo tài khoản thành công. Chào mừng bạn đến Campus Coin!")
        return redirect("transactions:transaction-list")

    return render(request, "accounts/auth/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        if request.user.role.role_name == Role.Name.ADMIN:
            return redirect("accounts:admin_dashboard")
        return redirect("transactions:transaction-list")

    form = LoginForm(request, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role.role_name != Role.Name.STUDENT:
            form.add_error(None, "Tài khoản quản trị phải đăng nhập tại Cổng Admin")
        else:
            login(request, user)
            record_login_session(request, user)
            messages.success(request, "Đăng nhập thành công")
            return redirect(_safe_next_url(request) or "transactions:transaction-list")

    return render(
        request,
        "accounts/auth/login.html",
        {"form": form, "next": _safe_next_url(request)},
    )


def logout_view(request):
    admin_portal = bool(
        request.user.is_authenticated
        and request.user.role.role_name == Role.Name.ADMIN
    )
    if request.user.is_authenticated:
        revoke_current_session(request)
        logout(request)
    messages.success(request, "Đã đăng xuất")
    if admin_portal:
        return redirect("accounts:admin_login")
    return redirect("accounts:login")


def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = ForgotPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(
            email__iexact=email,
            role__role_name=Role.Name.STUDENT,
            status__in=[User.Status.ACTIVE, User.Status.LOCKED],
            deleted_at__isnull=True,
        ).first()
        if user:
            send_password_reset_email(request, user)

        messages.success(
            request,
            "Nếu email sinh viên tồn tại trong hệ thống, liên kết đặt lại mật khẩu đã được gửi",
        )
        return redirect("accounts:forgot_password")

    return render(request, "accounts/auth/forgot_password.html", {"form": form})


def reset_password_view(request, token):
    reset_token = find_valid_reset_token(token)
    if not reset_token:
        return render(request, "accounts/auth/reset_password_invalid.html", status=400)

    admin_portal = reset_token.user.role.role_name == Role.Name.ADMIN
    form = ResetPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = reset_token.user
        user.set_password(form.cleaned_data["new_password1"])
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == User.Status.LOCKED:
            user.status = User.Status.ACTIVE
        user.save(
            update_fields=[
                "password",
                "failed_login_attempts",
                "locked_until",
                "status",
                "updated_at",
            ]
        )
        reset_token.used_at = timezone.now()
        reset_token.save(update_fields=["used_at"])
        revoke_all_sessions(user)
        messages.success(request, "Đặt lại mật khẩu thành công. Hãy đăng nhập lại")
        if admin_portal:
            return redirect("accounts:admin_login")
        return redirect("accounts:login")

    return render(
        request,
        "accounts/auth/reset_password.html",
        {"form": form, "admin_portal": admin_portal},
    )