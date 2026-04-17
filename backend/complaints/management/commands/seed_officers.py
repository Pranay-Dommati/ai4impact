from django.core.management.base import BaseCommand

from complaints.models import Department, Location, Officer


class Command(BaseCommand):
    help = "Seed dummy officer profiles with credentials for workflow MVP"

    def handle(self, *args, **options):
        officer_rows = [
            {
                "name": "Aarav Reddy",
                "username": "roads_kokapet_1",
                "password": "demo123",
                "department": "Road Maintenance",
                "city": "Hyderabad",
                "area": "Kokapet",
            },
            {
                "name": "Nisha Verma",
                "username": "roads_gachibowli_1",
                "password": "demo123",
                "department": "Road Maintenance",
                "city": "Hyderabad",
                "area": "Gachibowli",
            },
            {
                "name": "Ishaan Patel",
                "username": "water_hyd_1",
                "password": "demo123",
                "department": "Water Department",
                "city": "Hyderabad",
                "area": "Kokapet",
            },
            {
                "name": "Meera Singh",
                "username": "electricity_hyd_1",
                "password": "demo123",
                "department": "Electricity Department",
                "city": "Hyderabad",
                "area": "Gachibowli",
            },
            {
                "name": "Rahul Kumar",
                "username": "sanitation_hyd_1",
                "password": "demo123",
                "department": "Sanitation Department",
                "city": "Hyderabad",
                "area": "Gachibowli",
            },
        ]

        created = 0
        for row in officer_rows:
            department = Department.objects.filter(name=row["department"]).first()
            location = Location.objects.filter(city=row["city"], area=row["area"]).first()
            if not department:
                self.stdout.write(self.style.WARNING(f"Skipping {row['username']}: department not found"))
                continue

            _, was_created = Officer.objects.update_or_create(
                username=row["username"],
                defaults={
                    "name": row["name"],
                    "password": row["password"],
                    "department": department,
                    "location_ref": location,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f"Officers seeded/updated. Newly created: {created}"))
