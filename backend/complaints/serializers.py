from rest_framework import serializers

from .models import Complaint, Officer, ResolutionTask
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


class ResolutionTaskSerializer(serializers.ModelSerializer):
    complaint_text = serializers.CharField(source="complaint.text", read_only=True)
    complaint_location = serializers.CharField(source="complaint.location", read_only=True)
    complaint_priority = serializers.CharField(source="complaint.priority", read_only=True)
    officer_name = serializers.CharField(source="officer.name", read_only=True, default="")
    officer_username = serializers.CharField(source="officer.username", read_only=True, default="")
    manager_name = serializers.CharField(source="manager.name", read_only=True, default="")
    manager_username = serializers.CharField(source="manager.username", read_only=True, default="")

    class Meta:
        model = ResolutionTask
        fields = [
            "id",
            "complaint",
            "complaint_text",
            "complaint_location",
            "complaint_priority",
            "officer",
            "officer_name",
            "officer_username",
            "manager",
            "manager_name",
            "manager_username",
            "state",
            "sla_due_at",
            "assigned_at",
            "resolved_at",
            "closed_at",
            "ttr_minutes",
            "escalated_count",
            "last_escalated_at",
            "escalated_to_manager_at",
            "verification_status",
            "verification_requested_at",
            "verification_photo_url",
            "verified_at",
            "notes",
        ]
        read_only_fields = fields


class OfficerSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    location_display = serializers.SerializerMethodField()
    active_task_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Officer
        fields = [
            "id",
            "name",
            "username",
            "password",
            "is_active",
            "is_manager",
            "max_active_tasks",
            "current_load",
            "department",
            "department_name",
            "location_ref",
            "location_display",
            "active_task_count",
        ]
        read_only_fields = fields

    def get_location_display(self, obj):
        if not obj.location_ref:
            return "Unassigned"
        return f"{obj.location_ref.city} - {obj.location_ref.area}"
