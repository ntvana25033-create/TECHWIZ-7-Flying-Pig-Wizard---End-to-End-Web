from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from accounts.models import Role, User

from .base import FormStyleMixin


class AdminUserCreateForm(FormStyleMixin, forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Vai trò", choices=Role.Name.choices)
    status = forms.ChoiceField(label="Trạng thái", choices=User.Status.choices, initial=User.Status.ACTIVE)
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, deleted_at__isnull=True).exists():
            raise ValidationError("Email này đã được sử dụng")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Mật khẩu xác nhận không khớp")
        if password1:
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self):
        role, _ = Role.objects.get_or_create(role_name=self.cleaned_data["role"])
        user = User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
            role=role,
            status=self.cleaned_data["status"],
        )
        user.profile.full_name = self.cleaned_data["full_name"].strip()
        user.profile.save(update_fields=["full_name", "updated_at"])
        return user


class AdminUserEditForm(FormStyleMixin, forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Vai trò", choices=Role.Name.choices)
    status = forms.ChoiceField(label="Trạng thái", choices=User.Status.choices)

    def __init__(self, *args, user, **kwargs):
        self.target_user = user
        initial = kwargs.setdefault("initial", {})
        initial.update(
            {
                "full_name": user.profile.full_name,
                "email": user.email,
                "role": user.role.role_name,
                "status": user.status,
            }
        )
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, deleted_at__isnull=True).exclude(pk=self.target_user.pk).exists():
            raise ValidationError("Email này đã được sử dụng")
        return email

    def save(self):
        role, _ = Role.objects.get_or_create(role_name=self.cleaned_data["role"])
        user = self.target_user
        user.email = self.cleaned_data["email"]
        user.role = role
        user.status = self.cleaned_data["status"]
        if user.status != User.Status.LOCKED:
            user.locked_until = None
            if user.status == User.Status.ACTIVE:
                user.failed_login_attempts = 0
        user.save(
            update_fields=[
                "email",
                "role",
                "status",
                "locked_until",
                "failed_login_attempts",
                "updated_at",
            ]
        )
        user.profile.full_name = self.cleaned_data["full_name"].strip()
        user.profile.save(update_fields=["full_name", "updated_at"])
        return user


class AdminProfileForm(FormStyleMixin, forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    email = forms.EmailField(label="Email")

    def __init__(self, *args, user, **kwargs):
        self.user = user
        initial = kwargs.setdefault("initial", {})
        initial.update({"full_name": user.profile.full_name, "email": user.email})
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, deleted_at__isnull=True).exclude(pk=self.user.pk).exists():
            raise ValidationError("Email này đã được sử dụng")
        return email

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.save(update_fields=["email", "updated_at"])
        self.user.profile.full_name = self.cleaned_data["full_name"].strip()
        self.user.profile.save(update_fields=["full_name", "updated_at"])
        return self.user
