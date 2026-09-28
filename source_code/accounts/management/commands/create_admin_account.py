from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.models import Role, User


class Command(BaseCommand):
    help = "Create a Campus Coin administrator account"

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Administrator account email")
        parser.add_argument("--password", help="Administrator password")
        parser.add_argument("--name", default="Campus Coin Admin", help="Administrator full name")

    def handle(self, *args, **options):
        email = (options.get("email") or input("Email admin: ")).strip().lower()
        password = options.get("password")
        name = (options.get("name") or "Campus Coin Admin").strip()

        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("Invalid email address") from exc

        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("This email address already exists in the system")

        if not password:
            password = getpass("Password: ")
            confirm_password = getpass("Confirm password: ")
            if password != confirm_password:
                raise CommandError("The passwords do not match")

        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("Password does not meet the requirements: " + " ".join(exc.messages)) from exc

        admin_role, _ = Role.objects.get_or_create(
            role_name=Role.Name.ADMIN,
            defaults={"description": "Administrator account"},
        )

        user = User.objects.create_user(
            email=email,
            password=password,
            role=admin_role,
            status=User.Status.ACTIVE,
        )
        user.profile.full_name = name
        user.profile.save(update_fields=["full_name", "updated_at"])

        self.stdout.write(self.style.SUCCESS(f"Created administrator: {user.email}"))
