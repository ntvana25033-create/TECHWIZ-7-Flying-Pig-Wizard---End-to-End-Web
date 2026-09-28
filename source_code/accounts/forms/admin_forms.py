from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from accounts.models import Role, User

from .base import FormStyleMixin


class AdminUserCreateForm(FormStyleMixin, forms.Form):
    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Role", choices=Role.Name.choices)
    status = forms.ChoiceField(label="Status", choices=User.Status.choices, initial=User.Status.ACTIVE)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, deleted_at__isnull=True).exists():
            raise ValidationError("This email address is already in use")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The password confirmation does not match")
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
    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email")
    role = forms.ChoiceField(label="Role", choices=Role.Name.choices)
    status = forms.ChoiceField(label="Status", choices=User.Status.choices)

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
            raise ValidationError("This email address is already in use")
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
    full_name = forms.CharField(label="Full name", max_length=150)
    email = forms.EmailField(label="Email")
    avatar_path = forms.ImageField(
        label="Profile picture",
        required=False,
        widget=forms.FileInput(
            attrs={
                "accept": "image/jpeg,image/png,image/webp,image/gif",
                "data-avatar-input": "1",
            }
        ),
        help_text="Upload a JPG, PNG, WEBP, or GIF image up to 5 MB.",
    )
    remove_avatar = forms.BooleanField(
        label="Remove current profile picture",
        required=False,
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        initial = kwargs.setdefault("initial", {})
        initial.update(
            {
                "full_name": user.profile.full_name,
                "email": user.email,
            }
        )
        super().__init__(*args, **kwargs)
        self.apply_form_style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email, deleted_at__isnull=True).exclude(pk=self.user.pk).exists():
            raise ValidationError("This email address is already in use")
        return email

    def clean_avatar_path(self):
        avatar = self.cleaned_data.get("avatar_path")
        if not avatar:
            return avatar
        content_type = getattr(avatar, "content_type", None)
        size = getattr(avatar, "size", 0)
        allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if content_type and content_type not in allowed_types:
            raise ValidationError("Please upload a JPG, PNG, WEBP, or GIF image")
        if size and size > 5 * 1024 * 1024:
            raise ValidationError("Profile picture must be 5 MB or smaller")
        return avatar

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("remove_avatar") and self.files.get("avatar_path"):
            self.add_error("avatar_path", "Choose a new picture or remove the current picture, not both")
        return cleaned

    def save(self):
        self.user.email = self.cleaned_data["email"]
        self.user.save(update_fields=["email", "updated_at"])

        profile = self.user.profile
        profile.full_name = self.cleaned_data["full_name"].strip()
        if self.cleaned_data.get("remove_avatar"):
            if profile.avatar_path:
                profile.avatar_path.delete(save=False)
            profile.avatar_path = None
        elif self.cleaned_data.get("avatar_path"):
            if profile.avatar_path:
                profile.avatar_path.delete(save=False)
            profile.avatar_path = self.cleaned_data["avatar_path"]
        profile.save()
        return self.user
