from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError

from accounts.models import User

from .base import FormStyleMixin


class RegisterForm(FormStyleMixin, forms.Form):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    email = forms.EmailField(label="Email")
    academic_year = forms.CharField(label="Năm học", max_length=50, required=False)
    monthly_allowance = forms.DecimalField(
        label="Trợ cấp hàng tháng", max_digits=15, decimal_places=2, min_value=0, required=False
    )
    monthly_savings_goal = forms.DecimalField(
        label="Mục tiêu tiết kiệm", max_digits=15, decimal_places=2, min_value=0, required=False
    )
    password1 = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput)
    accept_terms = forms.BooleanField(
        label="Tôi đồng ý với điều khoản sử dụng và chính sách bảo mật", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()
        self.fields["full_name"].widget.attrs.update({"placeholder": "Nguyễn Văn A", "autocomplete": "name"})
        self.fields["email"].widget.attrs.update({"placeholder": "student@example.com", "autocomplete": "email"})
        self.fields["academic_year"].widget.attrs.update({"placeholder": "Ví dụ: Năm 3"})
        self.fields["monthly_allowance"].widget.attrs.update({"placeholder": "3000000", "inputmode": "decimal"})
        self.fields["monthly_savings_goal"].widget.attrs.update({"placeholder": "500000", "inputmode": "decimal"})
        self.fields["password1"].widget.attrs.update({"autocomplete": "new-password", "data-password": "main"})
        self.fields["password2"].widget.attrs.update({"autocomplete": "new-password"})

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
        user = User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password1"],
        )
        profile = user.profile
        profile.full_name = self.cleaned_data["full_name"].strip()
        profile.academic_year = self.cleaned_data.get("academic_year") or None
        profile.monthly_allowance = self.cleaned_data.get("monthly_allowance") or 0
        profile.monthly_savings_goal = self.cleaned_data.get("monthly_savings_goal") or 0
        profile.save()
        return user


class LoginForm(FormStyleMixin, forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None
        self.apply_form_style()
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "student@example.com"})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            self.user_cache = authenticate(
                self.request, email=email.strip().lower(), password=password
            )
            if self.user_cache is None:
                raise ValidationError("Email hoặc mật khẩu không đúng, hoặc tài khoản đang bị khóa")
        return cleaned

    def get_user(self):
        return self.user_cache


class ForgotPasswordForm(FormStyleMixin, forms.Form):
    email = forms.EmailField(label="Email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()
        self.fields["email"].widget.attrs.update({"autocomplete": "email", "placeholder": "student@example.com"})


class ResetPasswordForm(FormStyleMixin, forms.Form):
    new_password1 = forms.CharField(label="Mật khẩu mới", widget=forms.PasswordInput)
    new_password2 = forms.CharField(label="Xác nhận mật khẩu mới", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("new_password1")
        password2 = cleaned.get("new_password2")
        if password1 and password2 and password1 != password2:
            self.add_error("new_password2", "Mật khẩu xác nhận không khớp")
        if password1:
            try:
                password_validation.validate_password(password1)
            except ValidationError as exc:
                self.add_error("new_password1", exc)
        return cleaned


class AccountPasswordChangeForm(FormStyleMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()
