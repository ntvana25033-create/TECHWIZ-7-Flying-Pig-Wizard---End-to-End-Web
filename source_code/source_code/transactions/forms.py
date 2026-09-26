from django import forms

from .models import Category, Transaction


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["type", "category", "amount", "description", "date"]
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Example: lunch at cafeteria, fuel, part-time salary...",
                }
            ),
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        transaction_type = cleaned_data.get("type")
        category = cleaned_data.get("category")

        if category and transaction_type and category.type != transaction_type:
            self.add_error(
                "category",
                "The selected category does not match the transaction type.",
            )

        return cleaned_data


class CSVTransactionImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        help_text="UTF-8 CSV. Supported columns: type, category, amount, description, date.",
    )

    def clean_csv_file(self):
        uploaded = self.cleaned_data["csv_file"]
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("Please select a .csv file.")
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("The CSV file must be 5 MB or smaller.")
        return uploaded
