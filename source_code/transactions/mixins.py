from django.contrib import messages
from django.shortcuts import redirect

from accounts.models import Role


class RoleRequiredMixin:
    required_role = None
    login_url_name = "accounts:login"

    def dispatch(self, request, *args, **kwargs):
        user = request.user

        if not user.is_authenticated:
            return redirect(self.login_url_name)

        if not user.is_active or user.role.role_name != self.required_role:
            messages.error(request, "You do not have permission to access this feature")
            if user.role.role_name == Role.Name.ADMIN:
                return redirect("accounts:admin_dashboard")
            return redirect("transactions:transaction-list")

        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(RoleRequiredMixin):
    required_role = Role.Name.STUDENT
    login_url_name = "accounts:login"


class AdminRequiredMixin(RoleRequiredMixin):
    required_role = Role.Name.ADMIN
    login_url_name = "accounts:admin_login"
