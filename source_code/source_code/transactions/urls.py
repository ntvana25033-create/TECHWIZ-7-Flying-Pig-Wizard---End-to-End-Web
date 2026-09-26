from django.urls import path
from . import views

app_name = 'transactions'

urlpatterns = [
    path('categories/', views.CategoryListView.as_view(), name='category-list'),
    path('transactions/', views.TransactionListView.as_view(), name='transaction-list'),
    path('transactions/', views.TransactionListView.as_view(), name='list'),
    path('transactions/new/', views.TransactionCreateView.as_view(), name='transaction-create'),
    path('transactions/<int:pk>/edit/', views.TransactionUpdateView.as_view(), name='transaction-update'),
    path('transactions/<int:pk>/delete/', views.TransactionDeleteView.as_view(), name='transaction-delete'),

    path('import/csv/', views.TransactionCSVImportView.as_view(), name='csv-import'),
    path('import/csv/template/', views.TransactionCSVTemplateView.as_view(), name='csv-import-template'),
    path('import/csv/<int:batch_id>/preview/', views.TransactionCSVImportPreviewView.as_view(), name='csv-import-preview'),
    path('import/csv/<int:batch_id>/confirm/', views.TransactionCSVImportConfirmView.as_view(), name='csv-import-confirm'),
    path('import/csv/<int:batch_id>/cancel/', views.TransactionCSVImportCancelView.as_view(), name='csv-import-cancel'),

    path('ajax/load-categories/', views.load_categories, name='ajax_load_categories'),
    path('ajax/ai-predict/', views.ai_predict_category, name='ajax_ai_predict'),
    path('manage/categories/', views.AdminCategoryListView.as_view(), name='admin-category-list'),
    path('manage/categories/new/', views.AdminCategoryCreateView.as_view(), name='admin-category-create'),
    path('manage/categories/<int:pk>/edit/', views.AdminCategoryUpdateView.as_view(), name='admin-category-update'),
    path('manage/categories/<int:pk>/delete/', views.AdminCategoryDeleteView.as_view(), name='admin-category-delete'),
    path('manage/transactions/', views.AdminTransactionListView.as_view(), name='admin-transaction-list'),
]
