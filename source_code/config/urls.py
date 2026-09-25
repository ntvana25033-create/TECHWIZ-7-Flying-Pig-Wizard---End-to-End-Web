from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views.auth_views import home_view

urlpatterns = [
    path("", home_view, name="home"),
    #path("account/admin-account/finance/", include("transactions.admin_urls")),
    path("account/", include("accounts.urls")),
    path("transactions/", include("transactions.urls")),
    path("django-admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)