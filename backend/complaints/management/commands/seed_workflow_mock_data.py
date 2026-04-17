from django.core.management.base import BaseCommand
from django.db import transaction

from complaints.models import (
    Complaint,
    Department,
    DepartmentAssignment,
    Location,
    Officer,
    ResolutionTask,
)


class Command(BaseCommand):
    help = "Reset and seed workflow mock data: 2 locations, 3 departments, 2 officers per department per location"

    @transaction.atomic
    def handle(self, *args, **options):
        # Reset demo entities to keep the output deterministic for demos.
        ResolutionTask.objects.all().delete()
        Complaint.objects.all().delete()
        Officer.objects.all().delete()
        DepartmentAssignment.objects.all().delete()
        Department.objects.all().delete()
        Location.objects.all().delete()

        locations = [
            {"city": "Hyderabad", "area": "Kokapet", "level": "city"},
            {"city": "Hyderabad", "area": "Gachibowli", "level": "city"},
        ]
        departments = [
            {"name": "Road Maintenance", "category": "roads"},
            {"name": "Water Department", "category": "water"},
            {"name": "Electricity Department", "category": "electricity"},
        ]

        location_map: dict[str, Location] = {}
        for row in locations:
            obj = Location.objects.create(city=row["city"], area=row["area"], level=row["level"])
            location_map[row["area"].lower()] = obj

        department_map: dict[str, Department] = {}
        for row in departments:
            obj = Department.objects.create(name=row["name"], category=row["category"])
            department_map[row["category"]] = obj

        # Each location has exactly these 3 departments.
        for loc in location_map.values():
            for dept in department_map.values():
                DepartmentAssignment.objects.create(location=loc, department=dept)

        # 2 officers per department per location => 12 officers total.
        # Demo credentials are intentionally simple for MVP only.
        credentials = []
        for area_key, loc in location_map.items():
            for category, dept in department_map.items():
                for idx in range(1, 3):
                    username = f"{area_key}_{category}_{idx}"
                    password = "demo123"
                    name = f"{loc.area} {dept.category.title()} Officer {idx}"
                    Officer.objects.create(
                        name=name,
                        username=username,
                        password=password,
                        department=dept,
                        location_ref=loc,
                        is_active=True,
                        is_manager=(idx == 2),
                        max_active_tasks=2,
                        current_load=0,
                    )
                    credentials.append((username, password, dept.name, f"{loc.city} - {loc.area}"))

        self.stdout.write(self.style.SUCCESS("Seeded workflow mock data successfully."))
        self.stdout.write(self.style.SUCCESS("Locations: 2, Departments: 3, Officers: 12"))
        self.stdout.write("\nOfficer credentials (MVP demo):")
        for username, password, dept_name, location_name in credentials:
            self.stdout.write(f"- {username} / {password} | {dept_name} | {location_name}")
