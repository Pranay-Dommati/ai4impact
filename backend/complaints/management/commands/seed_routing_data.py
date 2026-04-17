from django.core.management.base import BaseCommand

from complaints.models import Department, DepartmentAssignment, Location


class Command(BaseCommand):
    help = "Seed base locations, departments, and assignments"

    def handle(self, *args, **options):
        location_rows = [
            {"city": "Hyderabad", "area": "Kokapet", "level": "city"},
            {"city": "Hyderabad", "area": "Gachibowli", "level": "city"},
            {"city": "Village X", "area": "Area A", "level": "village"},
        ]

        department_rows = [
            {"name": "Electricity Department", "category": "electricity"},
            {"name": "Water Department", "category": "water"},
            {"name": "Road Maintenance", "category": "roads"},
            {"name": "Sanitation Department", "category": "sanitation"},
        ]

        created_locations = {}
        for row in location_rows:
            location, _ = Location.objects.get_or_create(
                city=row["city"],
                area=row["area"],
                defaults={"level": row["level"]},
            )
            if location.level != row["level"]:
                location.level = row["level"]
                location.save(update_fields=["level"])
            created_locations[(row["city"], row["area"])] = location

        created_departments = {}
        for row in department_rows:
            department, _ = Department.objects.get_or_create(
                name=row["name"],
                defaults={"category": row["category"]},
            )
            if department.category != row["category"]:
                department.category = row["category"]
                department.save(update_fields=["category"])
            created_departments[row["category"]] = department

        assignment_map = {
            ("Hyderabad", "Kokapet"): ["electricity", "water", "roads"],
            ("Hyderabad", "Gachibowli"): ["electricity", "water", "roads", "sanitation"],
            ("Village X", "Area A"): ["water", "roads", "sanitation"],
        }

        total_assignments = 0
        for loc_key, categories in assignment_map.items():
            location = created_locations[loc_key]
            for category in categories:
                department = created_departments[category]
                DepartmentAssignment.objects.get_or_create(location=location, department=department)
                total_assignments += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(created_locations)} locations, {len(created_departments)} departments, and {total_assignments} assignments."
            )
        )
