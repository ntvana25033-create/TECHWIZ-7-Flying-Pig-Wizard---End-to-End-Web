from django.contrib import admin

from .models import PasswordResetToken, Role, User, UserProfile, UserSession


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("role_id", "role_name", "description", "created_at")
    search_fields = ("role_name",)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "user_id",
        "email",
        "role",
        "status",
        "failed_login_attempts",
        "created_at",
    )
    list_filter = ("role", "status")
    search_fields = ("email", "profile__full_name")
    readonly_fields = (
        "password",
        "last_login",
        "created_at",
        "updated_at",
        "email_verified_at",
    )
    ordering = ("-created_at",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("profile_id", "full_name", "user", "academic_year", "currency_code")
    search_fields = ("full_name", "user__email")


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = (
        "session_id",
        "user",
        "ip_address",
        "created_at",
        "last_activity_at",
        "expires_at",
        "revoked_at",
    )
    search_fields = ("user__email", "session_token_hash", "ip_address")
    readonly_fields = ("session_token_hash", "created_at", "last_activity_at")


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("reset_id", "user", "expires_at", "used_at", "created_at")
    search_fields = ("user__email",)
    readonly_fields = ("token_hash", "created_at")
