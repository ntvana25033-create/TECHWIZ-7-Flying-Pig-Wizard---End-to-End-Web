from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .managers import UserManager


class Role(models.Model):
    class Name(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        ADMIN = "ADMIN", "Administrators"

    role_id = models.SmallAutoField(primary_key=True)
    role_name = models.CharField(max_length=30, unique=True, choices=Name.choices)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "roles"
        ordering = ["role_id"]

    def __str__(self):
        return self.get_role_name_display()


class User(AbstractBaseUser):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending verification"
        ACTIVE = "ACTIVE", "Active"
        DISABLED = "DISABLED", "Disabled"
        LOCKED = "LOCKED", "Locked"

    user_id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    email = models.EmailField(max_length=190, unique=True)
    password = models.CharField(max_length=255, db_column="password_hash")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    last_login = models.DateTimeField(blank=True, null=True, db_column="last_login_at")
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["role", "status"], name="idx_users_role_status"),
            models.Index(fields=["created_at"], name="idx_users_created_at"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(failed_login_attempts__lte=100),
                name="chk_users_failed_login",
            )
        ]

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE and self.deleted_at is None

    @property
    def is_staff(self):
        return self.is_active and self.role.role_name == Role.Name.ADMIN

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff

    def get_full_name(self):
        try:
            return self.profile.full_name or self.email
        except UserProfile.DoesNotExist:
            return self.email

    def get_short_name(self):
        return self.get_full_name()

    def __str__(self):
        return self.email


class UserProfile(models.Model):
    profile_id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150)
    academic_year = models.CharField(max_length=50, blank=True, null=True)
    monthly_allowance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monthly_savings_goal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    avatar_path = models.ImageField(
        upload_to="avatars/%Y/%m/",
        max_length=500,
        blank=True,
        null=True,
    )
    currency_code = models.CharField(max_length=3, default="VND")
    timezone = models.CharField(max_length=64, default="Asia/Ho_Chi_Minh")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"
        constraints = [
            models.CheckConstraint(
                condition=Q(monthly_allowance__gte=0),
                name="chk_profiles_allowance",
            ),
            models.CheckConstraint(
                condition=Q(monthly_savings_goal__gte=0),
                name="chk_profiles_savings_goal",
            ),
        ]

    def __str__(self):
        return self.full_name or self.user.email


class UserSession(models.Model):
    session_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_sessions")
    session_token_hash = models.CharField(max_length=64, unique=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_activity_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "user_sessions"
        indexes = [
            models.Index(
                fields=["user", "revoked_at", "expires_at"],
                name="idx_sessions_user_active",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="chk_session_expiry",
            )
        ]

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()

    def revoke(self):
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"{self.user.email} - {self.created_at:%d/%m/%Y %H:%M}"


class PasswordResetToken(models.Model):
    reset_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "password_reset_tokens"
        indexes = [
            models.Index(
                fields=["user", "expires_at", "used_at"],
                name="idx_reset_user_expiry",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__gt=F("created_at")),
                name="chk_reset_expiry",
            )
        ]

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"Reset token - {self.user.email}"
