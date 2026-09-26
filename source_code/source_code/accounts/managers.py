from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _get_role(self, role_name):
        from .models import Role

        role, _ = Role.objects.get_or_create(
            role_name=role_name,
            defaults={"description": f"Role {role_name.lower()}"},
        )
        return role

    def create_user(self, email, password=None, role=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not password:
            raise ValueError("Password is required")

        email = self.normalize_email(email).lower()
        role = role or self._get_role("STUDENT")
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.pop("is_staff", None)
        extra_fields.pop("is_superuser", None)
        extra_fields.setdefault("status", "ACTIVE")
        role = self._get_role("ADMIN")
        return self.create_user(email=email, password=password, role=role, **extra_fields)
