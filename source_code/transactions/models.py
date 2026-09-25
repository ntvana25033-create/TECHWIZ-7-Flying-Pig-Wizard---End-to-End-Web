from django.db import models
from django.conf import settings

class Category(models.Model):
    TYPE_CHOICES = (
        ('income', 'Thu nhập'),
        ('expense', 'Chi phí'),
    )
    
    name = models.CharField(max_length=255, verbose_name="Tên danh mục")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Loại")

    def __str__(self):
        return self.name

class Transaction(models.Model):
    TYPE_CHOICES = (
        ('income', 'Thu nhập'),
        ('expense', 'Chi phí'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Người dùng")    
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, verbose_name="Danh mục")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Số tiền")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name="Loại giao dịch")
    description = models.TextField(blank=True, null=True, verbose_name="Mô tả")
    

    ai_suggested_category = models.ForeignKey(
        Category, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='ai_suggested_transactions',
        verbose_name="AI gợi ý danh mục"
    )
    
    date = models.DateField(verbose_name="Ngày giao dịch")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
            return f"{self.user.email} - {self.amount} - {self.date}"