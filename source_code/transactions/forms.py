from django import forms
from .models import Transaction

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        # Thứ tự các trường hiển thị trên form
        fields = ['type', 'category', 'amount', 'description', 'date']
        
        # Tùy chỉnh Widget để đổi sang thẻ <input type="date">
        widgets = {
            'date': forms.DateInput(attrs={
                'type': 'date', 
                'style': 'padding: 5px; cursor: pointer;' # Thêm chút CSS cho đẹp
            }),
        }