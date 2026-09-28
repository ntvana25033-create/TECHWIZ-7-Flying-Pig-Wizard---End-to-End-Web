from datetime import date

from django.core.management.base import BaseCommand, CommandError

from notifications.services import process_all_users


class Command(BaseCommand):
    help = "Generate scheduled Campus Coin notifications and send notification emails."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Reference date in YYYY-MM-DD format.")
        parser.add_argument("--force-weekly", action="store_true", help="Create a weekly summary even if the date is not Sunday.")
        parser.add_argument("--force-monthly", action="store_true", help="Create a monthly summary even if the date is not the last day of the month.")
        parser.add_argument("--no-email", action="store_true", help="Create in-app notifications without sending email.")

    def handle(self, *args, **options):
        reference_date = None
        if options["date"]:
            try:
                reference_date = date.fromisoformat(options["date"])
            except ValueError as exc:
                raise CommandError("--date must use YYYY-MM-DD.") from exc

        created = process_all_users(
            reference_date,
            send_email=not options["no_email"],
            force_weekly=options["force_weekly"],
            force_monthly=options["force_monthly"],
        )
        self.stdout.write(self.style.SUCCESS(f"Created {len(created)} notification(s)."))
