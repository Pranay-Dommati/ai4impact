from django.db.models import Avg, Count, Sum

from .models import Complaint


def _cluster_impact_level(impact_score: int) -> str:
    if impact_score >= 30:
        return "HIGH"
    if impact_score >= 12:
        return "MEDIUM"
    return "LOW"


def get_cluster_insights() -> list[dict]:
    grouped = (
        Complaint.objects.values("category", "location", "cluster_id")
        .annotate(
            total_complaints=Count("id"),
            total_impact_score=Sum("impact_score"),
            avg_ai_score=Avg("score"),
        )
        .order_by("-total_complaints", "location")
    )

    results = []
    for row in grouped:
        location = row["location"]
        category = row["category"]
        cluster_id = row["cluster_id"]
        cluster_items = Complaint.objects.filter(cluster_id=cluster_id)

        high_count = cluster_items.filter(priority="high").count()
        medium_count = cluster_items.filter(priority="medium").count()
        low_count = cluster_items.filter(priority="low").count()
        severe_count = cluster_items.filter(severity="high").count()
        top_department = (
            cluster_items.exclude(assigned_department__isnull=True)
            .values_list("assigned_department__name", flat=True)
            .first()
        )

        total_count = row["total_complaints"]
        impact_score = int(row.get("total_impact_score") or 0)
        avg_ai_score = int(round(row.get("avg_ai_score") or 0))
        estimated_people = cluster_items.aggregate(total=Sum("affected_population_estimate")).get("total") or 0

        results.append(
            {
                "cluster_id": cluster_id,
                "total_complaints": total_count,
                "count": total_count,
                "category": category,
                "location": location,
                "impact": _cluster_impact_level(impact_score),
                "impact_score": impact_score,
                "avg_ai_score": avg_ai_score,
                "estimated_people": estimated_people,
                "estimated_affected_population": estimated_people,
                "priority_breakdown": {
                    "high": high_count,
                    "medium": medium_count,
                    "low": low_count,
                },
                "severity_breakdown": {
                    "high": severe_count,
                    "medium": cluster_items.filter(severity="medium").count(),
                    "low": cluster_items.filter(severity="low").count(),
                },
                "assigned_department": top_department or "Unassigned",
                "insight": f"Cluster detected from AI-prioritized complaints in {location}",
            }
        )

    return results
