from rest_framework import serializers

from .models import Complaint
from .service import process_complaint


class ComplaintSerializer(serializers.ModelSerializer):
    assigned_department_name = serializers.SerializerMethodField()
    routing = serializers.SerializerMethodField()
    reasoning = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            "id",
            "text",
            "category",
            "location",
            "source",
            "priority",
            "score",
            "impact_score",
            "severity",
            "urgency",
            "risk_type",
            "affected_population_estimate",
            "duration_hint",
            "issue_type",
            "cluster_id",
            "ai_confidence",
            "assigned_department_name",
            "routing",
            "reasoning",
            "status",
            "created_at",
        ]
        read_only_fields = [
            "priority",
            "score",
            "impact_score",
            "severity",
            "urgency",
            "risk_type",
            "affected_population_estimate",
            "duration_hint",
            "issue_type",
            "cluster_id",
            "ai_confidence",
            "assigned_department_name",
            "routing",
            "reasoning",
            "created_at",
        ]

    def create(self, validated_data):
        complaint, _ = process_complaint(
            text=validated_data.get("text", ""),
            source=validated_data.get("source", "portal"),
            category=validated_data.get("category", "other"),
            location=validated_data.get("location", ""),
            status=validated_data.get("status", "pending"),
        )
        return complaint

    def get_assigned_department_name(self, obj):
        if obj.assigned_department:
            return obj.assigned_department.name
        return "Unassigned"

    def get_routing(self, obj):
        return obj.ai_analysis.get("routing", {})

    def get_reasoning(self, obj):
        return obj.ai_analysis.get("priority", {}).get("reasoning", [])
