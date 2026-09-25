from django import forms


class FormStyleMixin:
    """Gắn class/placeholder thống nhất cho toàn bộ form của accounts."""

    def apply_form_style(self):
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "auth-check")
                continue

            current = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"auth-input {current}".strip()
            field.widget.attrs.setdefault("placeholder", field.label or name.replace("_", " ").title())

            if isinstance(field.widget, forms.PasswordInput):
                field.widget.attrs.setdefault("autocomplete", "new-password")
