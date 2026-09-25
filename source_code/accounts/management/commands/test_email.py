from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Gửi email kiểm tra qua cấu hình SMTP hiện tại"

    def add_arguments(self, parser):
        parser.add_argument("recipient", help="Địa chỉ email nhận để kiểm tra")

    def handle(self, *args, **options):
        recipient = options["recipient"]
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("Chưa cấu hình EMAIL_HOST_USER hoặc EMAIL_HOST_PASSWORD trong .env")

        sent = send_mail(
            "Campus Coin - Kiểm tra SMTP",
            "Email SMTP của Campus Coin đã được cấu hình thành công.",
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
        if sent:
            self.stdout.write(self.style.SUCCESS("EMAIL SENT OK"))
        else:
            raise CommandError("Email không được gửi")
