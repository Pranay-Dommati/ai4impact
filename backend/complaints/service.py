from typing import Any
import logging

from django.db.utils import OperationalError, ProgrammingError

from .gemini_agent import call_gemini_structured
from .models import Complaint, Department, DepartmentAssignment, Location
from .workflow import create_resolution_task_for_complaint

logger = logging.getLogger(__name__)


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


def _severity_points(level: str) -> int:
    return {"low": 25, "medium": 65, "high": 100}.get(_normalize_priority(level), 65)


def _urgency_points(level: str) -> int:
    return {"low": 25, "medium": 65, "high": 100}.get(_normalize_priority(level), 65)


def _population_points(affected_population: int) -> int:
    population = max(0, affected_population)
    if population >= 100:
        return 100
    if population >= 50:
        return 80
    if population >= 20:
        return 60
    if population >= 5:
        return 40
    if population >= 1:
        return 25
    return 10


def _risk_points(risk_type: str) -> int:
    risk = (risk_type or "").strip().lower()
    if any(keyword in risk for keyword in ("electroc", "fire", "live wire", "collapse", "accident", "safety", "hazard")):
        return 100
    if any(keyword in risk for keyword in ("flood", "water loss", "contamination", "outage", "health")):
        return 75
    if any(keyword in risk for keyword in ("service disruption", "inconvenience", "delay")):
        return 45
    return 35


def _location_points(location_type: str) -> int:
    normalized = (location_type or "").strip().lower()
    return {
        "hospital": 100,
        "school": 95,
        "road": 75,
        "residential": 65,
        "other": 45,
    }.get(normalized, 45)


def _priority_from_score(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _compute_impact_matrix(
    *,
    severity: str,
    urgency: str,
    risk_type: str,
    affected_population_estimate: int,
    location_type: str,
) -> dict[str, Any]:
    sev_points = _severity_points(severity)
    urg_points = _urgency_points(urgency)
    pop_points = _population_points(affected_population_estimate)
    risk_points = _risk_points(risk_type)
    loc_points = _location_points(location_type)

    weighted_score = int(
        round(
            (0.35 * sev_points)
            + (0.25 * urg_points)
            + (0.15 * pop_points)
            + (0.15 * risk_points)
            + (0.10 * loc_points)
        )
    )
    weighted_score = max(0, min(100, weighted_score))

    # Policy guardrail: life/safety high risk in critical places should not drop below high.
    critical_place = location_type in {"school", "hospital"}
    high_safety_risk = risk_points >= 100 and sev_points >= 65
    if critical_place and high_safety_risk and weighted_score < 80:
        weighted_score = 80

    return {
        "score": weighted_score,
        "priority_level": _priority_from_score(weighted_score),
        "components": {
            "severity": sev_points,
            "urgency": urg_points,
            "population": pop_points,
            "risk": risk_points,
            "location": loc_points,
        },
        "weights": {
            "severity": 0.35,
            "urgency": 0.25,
            "population": 0.15,
            "risk": 0.15,
            "location": 0.10,
        },
    }


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


def _resolve_department(
    *,
    ai_department_name: str,
    resolved_category: str,
    location_ref: Location,
) -> Department | None:
    if ai_department_name:
        direct = Department.objects.filter(name__iexact=ai_department_name).first()
        if direct:
            return direct

    # Fallback 1: location + category assignment map.
    assignment = (
        DepartmentAssignment.objects.filter(
            location=location_ref,
            department__category__iexact=resolved_category,
        )
        .select_related("department")
        .first()
    )
    if assignment:
        return assignment.department

    # Fallback 2: any department for this category.
    return Department.objects.filter(category__iexact=resolved_category).first()


def process_complaint(
    *,
    text: str,
    source: str,
    category: str | None = None,
    location: str | None = None,
    citizen_chat_id: int | None = None,
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

    severity = _normalize_priority(impact.get("severity", "medium"))
    urgency = _normalize_priority(impact.get("urgency", "medium"))
    risk_type = str(impact.get("risk_type", "public_service"))[:80]
    affected_population_estimate = max(0, int(impact.get("affected_population_estimate", 0) or 0))
    location_type = str(extracted_location.get("location_type", "other")).strip().lower() or "other"

    matrix = _compute_impact_matrix(
        severity=severity,
        urgency=urgency,
        risk_type=risk_type,
        affected_population_estimate=affected_population_estimate,
        location_type=location_type,
    )

    score = int(matrix["score"])
    impact_score = score
    priority = str(matrix["priority_level"])

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
    assigned_department = _resolve_department(
        ai_department_name=ai_department,
        resolved_category=resolved_category,
        location_ref=location_ref,
    )
    routing.setdefault("department", assigned_department.name if assigned_department else "Unassigned")
    routing.setdefault("sub_department", "General")
    routing.setdefault("jurisdiction", f"{resolved_city} - {resolved_area}")

    # Keep Gemini output for transparency, but source-of-truth priority is matrix-based.
    priority_reasoning = ai_priority.get("reasoning") if isinstance(ai_priority.get("reasoning"), list) else []
    ai_payload["priority"] = {
        "level": priority,
        "score": score,
        "reasoning": [
            *[str(item).strip() for item in priority_reasoning if str(item).strip()],
            (
                f"Impact Matrix score={score} from severity={matrix['components']['severity']}, "
                f"urgency={matrix['components']['urgency']}, population={matrix['components']['population']}, "
                f"risk={matrix['components']['risk']}, location={matrix['components']['location']}"
            ),
        ],
    }
    ai_payload["impact_matrix"] = matrix

    complaint = Complaint.objects.create(
        text=text,
        category=resolved_category,
        location=resolved_location,
        source=source,
        priority=priority,
        score=score,
        impact_score=impact_score,
        severity=severity,
        urgency=urgency,
        risk_type=risk_type,
        affected_population_estimate=affected_population_estimate,
        duration_hint=str(impact.get("duration_hint", ""))[:80],
        issue_type=issue_type[:100],
        cluster_id=cluster_id,
        ai_confidence=max(0.0, min(1.0, confidence)),
        ai_analysis=ai_payload,
        citizen_chat_id=citizen_chat_id,
        location_ref=location_ref,
        assigned_department=assigned_department,
        status=status,
    )

    try:
        create_resolution_task_for_complaint(complaint=complaint)
    except (OperationalError, ProgrammingError) as exc:
        # Keep complaint creation alive if migrations are pending during demo setup.
        logger.warning("Workflow task creation skipped due to DB schema mismatch: %s", str(exc))

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
