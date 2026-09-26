from django.core.management.base import BaseCommand

from accounts.models import Role, User


class Command(BaseCommand):
    help = "Create demo accounts for Campus Coin"

    def handle(self, *args, **options):
        admin_role, _ = Role.objects.get_or_create(
            role_name=Role.Name.ADMIN,
            defaults={"description": "Administrator account"},
        )
        student_role, _ = Role.objects.get_or_create(
            role_name=Role.Name.STUDENT,
            defaults={"description": "Student account"},
        )

        admin = User.objects.filter(email="admin@campuscoin.local").first()
        if not admin:
            admin = User.objects.create_user(
                email="admin@campuscoin.local",
                password="Admin@123456",
                role=admin_role,
            )
        admin.profile.full_name = "Campus Coin Admin"
        admin.profile.save()

        student = User.objects.filter(email="student@campuscoin.local").first()
        if not student:
            student = User.objects.create_user(
                email="student@campuscoin.local",
                password="Student@123456",
                role=student_role,
            )
        student.profile.full_name = "Demo Student"
        student.profile.academic_year = "Year 2"
        student.profile.monthly_allowance = 5000000
        student.profile.monthly_savings_goal = 1000000
        student.profile.save()

        self.stdout.write(self.style.SUCCESS("Demo accounts created or verified"))
        self.stdout.write("Admin: admin@campuscoin.local / Admin@123456")
        self.stdout.write("Student: student@campuscoin.local / Student@123456")
