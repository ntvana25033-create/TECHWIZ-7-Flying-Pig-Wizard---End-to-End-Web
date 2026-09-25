from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .models import Category, Transaction
from django.http import JsonResponse
from .forms import TransactionForm

class AdminCategoryListView(ListView):
    model = Category
    template_name = 'transaction/admin_category_list.html'
    context_object_name = 'categories'

class AdminCategoryCreateView(CreateView):
    model = Category
    template_name = 'transaction/admin_category_form.html'
    fields = ['name', 'type']
    success_url = reverse_lazy('transactions:admin-category-list')

class AdminCategoryUpdateView(UpdateView):
    model = Category
    template_name = 'transaction/admin_category_form.html'
    fields = ['name', 'type']
    success_url = reverse_lazy('transactions:admin-category-list')

class AdminCategoryDeleteView(DeleteView):
    model = Category
    template_name = 'transaction/admin_category_confirm_delete.html'
    success_url = reverse_lazy('transactions:admin-category-list')

class AdminTransactionListView(ListView):
    model = Transaction
    template_name = 'transaction/admin_transaction_list.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        return Transaction.objects.all().order_by('-date')

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'transaction/category_list.html'
    context_object_name = 'categories'

class TransactionListView(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = 'transaction/transaction_list.html'
    context_object_name = 'transactions'

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user).order_by('-date')

class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransactionForm    
    template_name = 'transaction/transaction_form.html'
    success_url = reverse_lazy('transactions:transaction-list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm    
    template_name = 'transaction/transaction_form.html'
    success_url = reverse_lazy('transactions:transaction-list')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

class TransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = Transaction
    template_name = 'transaction/transaction_confirm_delete.html'
    success_url = reverse_lazy('transactions:transaction-list')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)


def load_categories(request):
    txn_type = request.GET.get('type')
    categories = Category.objects.filter(type=txn_type).values('id', 'name')
    return JsonResponse(list(categories), safe=False)