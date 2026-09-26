from django import forms
from django.core.exceptions import ValidationError

from accounts.models import User, UserProfile

from .base import FormStyleMixin


MAX_AVATAR_SIZE = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ProfileForm(FormStyleMixin, forms.ModelForm):
    email = forms.EmailField(label="Email")
    remove_avatar = forms.BooleanField(label="Remove current profile picture", required=False)

    class Meta:
        model = UserProfile
        fields = [
            "full_name",
            "academic_year",
            "monthly_allowance",
            "monthly_savings_goal",
            "avatar_path",
            "currency_code",
            "timezone",
        ]
        labels = {
            "full_name": "Full name",
            "academic_year": "Academic year",
            "monthly_allowance": "Monthly allowance",
            "monthly_savings_goal": "Monthly savings goal",
            "avatar_path": "Profile picture",
            "currency_code": "Currency",
            "timezone": "Time zone",
        }
        widgets = {
            "avatar_path": forms.FileInput(
                attrs={
                    "accept": "image/jpeg,image/png,image/webp,image/gif",
                    "data-avatar-input": "1",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()
        if self.instance and self.instance.user_id:
            self.fields["email"].initial = self.instance.user.email
        self.fields["avatar_path"].help_text = (
            "Upload a JPG, PNG, WEBP, or GIF image up to 5 MB."
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        query = User.objects.filter(email__iexact=email, deleted_at__isnull=True)
        if self.instance and self.instance.user_id:
            query = query.exclude(pk=self.instance.user_id)
        if query.exists():
            raise ValidationError("This email address is already in use")
        return email

    def clean_avatar_path(self):
        avatar = self.cleaned_data.get("avatar_path")
        if not avatar:
            return avatar

        content_type = getattr(avatar, "content_type", None)
        if content_type:
            if content_type not in ALLOWED_AVATAR_TYPES:
                raise ValidationError("Please upload a JPG, PNG, WEBP, or GIF image")
            if getattr(avatar, "size", 0) > MAX_AVATAR_SIZE:
                raise ValidationError("Profile picture must be 5 MB or smaller")
        return avatar

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("remove_avatar") and self.files.get("avatar_path"):
            self.add_error("avatar_path", "Choose a new picture or remove the current picture, not both")
        return cleaned

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.email = self.cleaned_data["email"]
        if self.cleaned_data.get("remove_avatar"):
            if profile.avatar_path:
                profile.avatar_path.delete(save=False)
            profile.avatar_path = None
        if commit:
            profile.user.save(update_fields=["email", "updated_at"])
            profile.save()
            self.save_m2m()
        return profile
