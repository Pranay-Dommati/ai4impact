from django.core.management.base import BaseCommand
from django.core.management import call_command

from complaints.models import Complaint
from complaints.serializers import ComplaintSerializer


class Command(BaseCommand):
    help = "Seed demo complaints data for Civix-Pulse phase demo"

    def handle(self, *args, **options):
        Complaint.objects.all().delete()
        call_command("seed_routing_data")

        payloads = [
            {
                "text": "No water since morning in Area A housing block",
                "category": "water",
                "location": "Village X - Area A",
                "source": "portal",
            },
            {
                "text": "Water leak near main valve in Kokapet",
                "category": "water",
                "location": "Hyderabad - Kokapet",
                "source": "telegram",
            },
            {
                "text": "No water in Gachibowli school building",
                "category": "water",
                "location": "Hyderabad - Gachibowli",
                "source": "portal",
            },
            {
                "text": "Burst pipe and no water in Kokapet",
                "category": "water",
                "location": "Hyderabad - Kokapet",
                "source": "portal",
            },
            {
                "text": "Area A residents report water outage",
                "category": "water",
                "location": "Village X - Area A",
                "source": "telegram",
            },
            {
                "text": "Streetlight not working at Junction 5",
                "category": "electricity",
                "location": "Hyderabad - Kokapet",
                "source": "portal",
            },
            {
                "text": "Dark road due to failed streetlight in Gachibowli",
                "category": "electricity",
                "location": "Hyderabad - Gachibowli",
                "source": "telegram",
            },
            {
                "text": "Live wire hanging near bus stop in Kokapet",
                "category": "electricity",
                "location": "Hyderabad - Kokapet",
                "source": "telegram",
            },
        ]

        for payload in payloads:
            serializer = ComplaintSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            serializer.save()

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(payloads)} demo complaints."))
