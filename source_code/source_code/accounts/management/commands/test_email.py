from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send a test email using the current SMTP configuration"

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Recipient email address for testing")

    def handle(self, *args, **options):
        recipient = options["recipient"]
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is not configured in .env")

        sent = send_mail(
            "Campus Coin - SMTP Test",
            "Campus Coin SMTP email has been configured successfully.",
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        if sent:
            self.stdout.write(self.style.SUCCESS("EMAIL SENT OK"))
        else:
            raise CommandError("The email was not sent")
