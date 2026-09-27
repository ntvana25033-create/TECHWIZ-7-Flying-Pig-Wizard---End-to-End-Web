from django.urls import path

from .views import AdminNotificationListView, NotificationListView, NotificationMarkAllReadView, NotificationMarkReadView


app_name = "notifications"

urlpatterns = [
    path("manage/", AdminNotificationListView.as_view(), name="admin-list"),
    path("", NotificationListView.as_view(), name="list"),
    path("<int:pk>/read/", NotificationMarkReadView.as_view(), name="mark-read"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark-all-read"),
]
