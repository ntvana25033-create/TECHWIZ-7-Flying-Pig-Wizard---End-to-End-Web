from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from transactions.mixins import AdminRequiredMixin, StudentRequiredMixin

from .models import Notification


class NotificationListView(StudentRequiredMixin, ListView):
    model = Notification
    template_name = "notifications/list.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")


class AdminNotificationListView(AdminRequiredMixin, ListView):
    model = Notification
    template_name = "notifications/admin_list.html"
    context_object_name = "notifications"
    paginate_by = 50

    def get_queryset(self):
        queryset = Notification.objects.select_related("user").order_by("-created_at")
        kind = self.request.GET.get("kind", "").strip()
        status = self.request.GET.get("status", "").strip()
        if kind in Notification.Kind.values:
            queryset = queryset.filter(kind=kind)
        if status == "read":
            queryset = queryset.filter(is_read=True)
        elif status == "unread":
            queryset = queryset.filter(is_read=False)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["kinds"] = Notification.Kind.choices
        context["selected_kind"] = self.request.GET.get("kind", "")
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class NotificationMarkReadView(StudentRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return redirect("notifications:list")


class NotificationMarkAllReadView(StudentRequiredMixin, View):
    def post(self, request):
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        if updated:
            messages.success(request, f"Marked {updated} notification(s) as read.")
        return redirect("notifications:list")
