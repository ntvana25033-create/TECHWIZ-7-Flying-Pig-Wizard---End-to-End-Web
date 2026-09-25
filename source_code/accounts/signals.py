from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Role, User, UserProfile


@receiver(post_migrate)
def ensure_default_roles(sender, **kwargs):
    if sender.label != "accounts":
        return

    Role.objects.get_or_create(
        role_name=Role.Name.STUDENT,
        defaults={"description": "Tài khoản sinh viên"},
    )
    Role.objects.get_or_create(
        role_name=Role.Name.ADMIN,
        defaults={"description": "Tài khoản quản trị"},
    )


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"full_name": instance.email.split("@")[0]},
        )
