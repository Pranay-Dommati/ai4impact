from typing import Any

from .gemini_agent import call_gemini_structured
from .models import Complaint, Department, Location


def _normalize_level(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"city", "village"}:
        return normalized
    return "city"


def _normalize_category(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"water", "electricity", "roads", "sanitation", "other"}:
        return normalized
    return "other"


def _normalize_priority(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return "medium"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_location_hint(location_hint: str | None) -> tuple[str, str]:
    raw = (location_hint or "").strip()
    if not raw:
        return "Unknown City", "Unspecified Area"

    if " - " in raw:
        city_part, area_part = [part.strip() for part in raw.split(" - ", 1)]
        return city_part or "Unknown City", area_part or "Unspecified Area"

    if "," in raw:
        area_part, city_part = [part.strip() for part in raw.split(",", 1)]
        return city_part or "Unknown City", area_part or "Unspecified Area"

    return "Unknown City", raw


def process_complaint(
    *,
    text: str,
    source: str,
    category: str | None = None,
    location: str | None = None,
    status: str = "pending",
) -> tuple[Complaint, dict[str, Any]]:
    hinted_city, hinted_area = _split_location_hint(location)
    hinted_category = _normalize_category(category or "other")

    ai_input = (
        f"Complaint: {text}\n"
        f"Category Hint: {hinted_category}\n"
        f"Location Hint: {hinted_city} - {hinted_area}"
    )
    ai_payload = call_gemini_structured(user_input=ai_input, source=source)
    if not ai_payload:
        raise ValueError("AI analysis unavailable. Complaint not created.")

    extracted = ai_payload.get("extracted", {})
    extracted_location = extracted.get("location", {})

    resolved_category = _normalize_category(extracted.get("category") or hinted_category)
    resolved_city = (extracted_location.get("city") or hinted_city or "Unknown City").strip().title()
    resolved_area = (extracted_location.get("area") or hinted_area or "Unspecified Area").strip().title()
    resolved_location = f"{resolved_city} - {resolved_area}"

    impact = ai_payload.get("impact", {})
    ai_priority = ai_payload.get("priority", {})
    confidence = float(ai_payload.get("meta", {}).get("confidence", 0) or 0)
    priority = _normalize_priority(ai_priority.get("level", ""))
    score = max(0, min(100, _safe_int(ai_priority.get("score"), 50)))
    impact_score = max(0, _safe_int(ai_priority.get("score"), score))

    issue_type = str(extracted.get("issue_type", "")).strip().lower().replace(" ", "_") or "general_issue"
    cluster_id = str(ai_payload.get("clustering", {}).get("cluster_id", "")).strip() or "unclustered"

    location_level = _normalize_level(extracted_location.get("level", "city"))
    location_ref, _ = Location.objects.get_or_create(
        city=resolved_city,
        area=resolved_area,
        defaults={"level": location_level},
    )
    if location_ref.level != location_level and location_level in {"city", "village"}:
        location_ref.level = location_level
        location_ref.save(update_fields=["level"])

    routing = ai_payload.setdefault("routing", {})
    ai_department = str(routing.get("department", "")).strip()
    assigned_department = Department.objects.filter(name__iexact=ai_department).first() if ai_department else None
    routing.setdefault("department", assigned_department.name if assigned_department else "Unassigned")
    routing.setdefault("sub_department", "General")
    routing.setdefault("jurisdiction", f"{resolved_city} - {resolved_area}")

    complaint = Complaint.objects.create(
        text=text,
        category=resolved_category,
        location=resolved_location,
        source=source,
        priority=priority,
        score=score,
        impact_score=impact_score,
        severity=_normalize_priority(impact.get("severity", "medium")),
        urgency=_normalize_priority(impact.get("urgency", "medium")),
        risk_type=str(impact.get("risk_type", "public_service"))[:80],
        affected_population_estimate=max(0, int(impact.get("affected_population_estimate", 0) or 0)),
        duration_hint=str(impact.get("duration_hint", ""))[:80],
        issue_type=issue_type[:100],
        cluster_id=cluster_id,
        ai_confidence=max(0.0, min(1.0, confidence)),
        ai_analysis=ai_payload,
        location_ref=location_ref,
        assigned_department=assigned_department,
        status=status,
    )

    meta = {
        "category": resolved_category,
        "location": resolved_location,
        "city": resolved_city,
        "area": resolved_area,
        "score": score,
        "priority": priority,
        "impact_score": impact_score,
        "cluster_id": cluster_id,
        "severity": complaint.severity,
        "urgency": complaint.urgency,
        "department": routing.get("department", "Unassigned"),
        "ai_confidence": complaint.ai_confidence,
    }

    return complaint, meta
