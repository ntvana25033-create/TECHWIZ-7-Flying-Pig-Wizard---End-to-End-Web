from django.urls import path
from .views import ReportDashboardView

app_name = "report"

urlpatterns = [
    path("", ReportDashboardView.as_view(), name="dashboard"),
]
