from django import forms
from django.core.exceptions import ValidationError

from accounts.models import User, UserProfile

from .base import FormStyleMixin


class ProfileForm(FormStyleMixin, forms.ModelForm):
    email = forms.EmailField(label="Email")

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
            "full_name": "Họ và tên",
            "academic_year": "Năm học",
            "monthly_allowance": "Trợ cấp hàng tháng",
            "monthly_savings_goal": "Mục tiêu tiết kiệm hàng tháng",
            "avatar_path": "Ảnh đại diện",
            "currency_code": "Đơn vị tiền tệ",
            "timezone": "Múi giờ",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_form_style()
        if self.instance and self.instance.user_id:
            self.fields["email"].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        query = User.objects.filter(email__iexact=email, deleted_at__isnull=True)
        if self.instance and self.instance.user_id:
            query = query.exclude(pk=self.instance.user_id)
        if query.exists():
            raise ValidationError("Email này đã được sử dụng")
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user.email = self.cleaned_data["email"]
        if commit:
            profile.user.save(update_fields=["email", "updated_at"])
            profile.save()
            self.save_m2m()
        return profile
