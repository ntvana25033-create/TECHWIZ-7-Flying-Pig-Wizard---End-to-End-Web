from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import Role


def role_required(role_name, *, login_name, denied_redirect):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect(login_name)
            if user.is_active and user.role.role_name == role_name:
                return view_func(request, *args, **kwargs)

            messages.error(request, "You do not have permission to access this area")
            if user.role.role_name == Role.Name.ADMIN:
                return redirect("accounts:admin_dashboard")
            return redirect(denied_redirect)

        return wrapper

    return decorator


def student_required(view_func):
    return role_required(
        Role.Name.STUDENT,
        login_name="accounts:login",
        denied_redirect="accounts:profile",
    )(view_func)


def admin_required(view_func):
    return role_required(
        Role.Name.ADMIN,
        login_name="accounts:admin_login",
        denied_redirect="accounts:profile",
    )(view_func)
