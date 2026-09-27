from django.urls import path

from .views import profile_views
from .views import admin_views
from .views import auth_views

app_name = "accounts"

urlpatterns = [
    # User authentication
    path("register/", auth_views.register_view, name="register"),
    path("login/", auth_views.login_view, name="login"),
    path("logout/", auth_views.logout_view, name="logout"),
    path("forgot-password/", auth_views.forgot_password_view, name="forgot_password"),
    path("reset-password/<str:token>/", auth_views.reset_password_view, name="reset_password"),

    # User account
    path("profile/", profile_views.profile_view, name="profile"),
    path("change-password/", profile_views.change_password_view, name="change_password"),
    path("sessions/", profile_views.sessions_view, name="sessions"),
    path("sessions/<int:session_id>/revoke/", profile_views.revoke_session_view, name="revoke_session"),

    # Admin portal
    path("admin-account/login/", admin_views.admin_login_view, name="admin_login"),
    path("admin-account/logout/", admin_views.admin_logout_view, name="admin_logout"),
    path("admin-account/", admin_views.admin_dashboard_view, name="admin_dashboard"),
    path("admin-account/profile/", admin_views.admin_profile_view, name="admin_profile"),
    path("admin-account/change-password/", admin_views.admin_change_password_view, name="admin_change_password"),
    path("admin-account/sessions/", admin_views.admin_sessions_view, name="admin_sessions"),
    path("admin-account/sessions/<int:session_id>/revoke/", admin_views.admin_revoke_session_view, name="admin_revoke_session"),
    path("admin-account/users/", admin_views.admin_user_list_view, name="admin_user_list"),
    path("admin-account/users/add/", admin_views.admin_user_create_view, name="admin_user_create"),
    path("admin-account/users/<int:user_id>/", admin_views.admin_user_detail_view, name="admin_user_detail"),
    path("admin-account/users/<int:user_id>/edit/", admin_views.admin_user_edit_view, name="admin_user_edit"),
    path("admin-account/users/<int:user_id>/toggle-status/", admin_views.admin_user_toggle_status_view, name="admin_user_toggle_status"),
    path("admin-account/users/<int:user_id>/send-reset/", admin_views.admin_user_send_reset_view, name="admin_user_send_reset"),
    path("admin-account/users/<int:user_id>/delete/", admin_views.admin_user_delete_view, name="admin_user_delete"),
]
