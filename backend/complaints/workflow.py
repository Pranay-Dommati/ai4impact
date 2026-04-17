from __future__ import annotations

from datetime import timedelta

import requests
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import Complaint, Officer, ResolutionTask

DEFAULT_SLA_MINUTES = 120
REOPEN_SLA_MINUTES = 30

PRIORITY_RANK = {
    "high": 3,
    "medium": 2,
    "low": 1,
}

TRANSITIONS: dict[str, set[str]] = {
    "queued": {"assigned", "escalated"},
    "assigned": {"in_progress", "resolved_pending_verification", "escalated"},
    "in_progress": {"resolved_pending_verification", "escalated"},
    "resolved_pending_verification": {"closed", "in_progress", "escalated"},
    "escalated": {"in_progress", "resolved_pending_verification", "closed"},
    "closed": set(),
}


def _send_telegram_update(*, complaint: Complaint, text: str) -> None:
    if complaint.source != "telegram":
        return
    if not complaint.citizen_chat_id:
        return
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": complaint.citizen_chat_id, "text": text}, timeout=10)
    except Exception:
        # Telegram notification failures should never block workflow progression.
        return


def _officer_base_queryset(*, department_id: int):
    return Officer.objects.filter(department_id=department_id, is_active=True).annotate(
        active_task_count=Count("tasks", filter=~Q(tasks__state="closed")),
    )


def _pick_officer(*, complaint: Complaint) -> Officer | None:
    department = complaint.assigned_department
    if not department:
        return None

    # Include all active officers for regular assignment so idle managers can absorb load.
    candidates = _officer_base_queryset(department_id=department.id)
    if not candidates.exists():
        return None

    # Capacity-aware assignment: officers at/above max_active_tasks are considered full.
    candidates = [
        officer for officer in candidates if officer.active_task_count < max(1, officer.max_active_tasks)
    ]
    if not candidates:
        return None

    if complaint.location_ref:
        location_matched = [officer for officer in candidates if officer.location_ref_id == complaint.location_ref_id]
        if location_matched:
            candidates = location_matched

    candidates.sort(key=lambda officer: (officer.active_task_count, officer.current_load, officer.id))
    return candidates[0]


def _pick_manager(*, complaint: Complaint) -> Officer | None:
    department = complaint.assigned_department
    if not department:
        return None

    managers = _officer_base_queryset(department_id=department.id).filter(is_manager=True)
    if not managers.exists():
        return None

    manager_list = list(managers)
    if complaint.location_ref:
        local = [officer for officer in manager_list if officer.location_ref_id == complaint.location_ref_id]
        if local:
            manager_list = local

    manager_list.sort(key=lambda officer: (officer.active_task_count, officer.current_load, officer.id))
    return manager_list[0]


def _assign_task_to_officer(*, task: ResolutionTask, officer: Officer, note: str) -> ResolutionTask:
    task.officer = officer
    task.state = "assigned"
    task.notes = f"{task.notes}\n[{timezone.now().isoformat()}] {note}".strip()
    task.save(update_fields=["officer", "state", "notes", "updated_at"])

    officer.current_load += 1
    officer.save(update_fields=["current_load"])

    _send_telegram_update(
        complaint=task.complaint,
        text=(
            f"Your complaint has been assigned to officer {officer.name} "
            f"({officer.username}) from {officer.department.name}."
        ),
    )
    return task


def _sorted_queued_tasks():
    queued = list(
        ResolutionTask.objects.select_related("complaint", "complaint__location_ref", "complaint__assigned_department")
        .filter(state="queued")
        .order_by("created_at")
    )

    queued.sort(
        key=lambda task: (
            -PRIORITY_RANK.get(task.complaint.priority, 1),
            -(task.complaint.score or 0),
            task.created_at,
        )
    )
    return queued


def assign_queued_tasks() -> int:
    assigned_count = 0
    for task in _sorted_queued_tasks():
        officer = _pick_officer(complaint=task.complaint)
        if not officer:
            continue
        _assign_task_to_officer(task=task, officer=officer, note="Assignment Agent: dequeued by priority")
        assigned_count += 1
    return assigned_count


def create_resolution_task_for_complaint(*, complaint: Complaint, sla_minutes: int = DEFAULT_SLA_MINUTES) -> ResolutionTask:
    existing = ResolutionTask.objects.filter(complaint=complaint).first()
    if existing:
        return existing

    officer = _pick_officer(complaint=complaint)
    state = "assigned" if officer else "queued"
    task = ResolutionTask.objects.create(
        complaint=complaint,
        officer=officer,
        state=state,
        sla_due_at=timezone.now() + timedelta(minutes=max(1, sla_minutes)),
        notes=(
            "Auto-assigned by Assignment Agent"
            if officer
            else "Queued by Assignment Agent: all officers at capacity"
        ),
    )

    if officer:
        officer.current_load += 1
        officer.save(update_fields=["current_load"])
        _send_telegram_update(
            complaint=complaint,
            text=(
                f"Complaint accepted and assigned to {officer.name} ({officer.username}). "
                f"Department: {officer.department.name}."
            ),
        )
    else:
        _send_telegram_update(
            complaint=complaint,
            text="Complaint accepted and queued by priority. You will get an update once an officer is assigned.",
        )

    # Try to assign any queued tasks that may now be assignable.
    assign_queued_tasks()
    return task


def transition_task_state(*, task: ResolutionTask, to_state: str, actor: str = "system") -> ResolutionTask:
    from_state = task.state
    allowed = TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise ValueError(f"Invalid transition from {from_state} to {to_state}")

    now = timezone.now()
    task.state = to_state

    if to_state == "resolved_pending_verification":
        task.resolved_at = now
        task.verification_status = "pending"
        task.verification_requested_at = now
        task.notes = f"{task.notes}\n[{now.isoformat()}] {actor}: Awaiting citizen verification".strip()
        _send_telegram_update(
            complaint=task.complaint,
            text=(
                f"Task #{task.id} marked resolved by manager/officer. "
                f"Please upload a photo with caption: verify {task.id}"
            ),
        )

    if to_state == "closed":
        if task.verification_status != "approved" or not task.verification_photo_url:
            raise ValueError("Citizen photo verification is required before closure")
        task.closed_at = now
        delta = task.closed_at - task.assigned_at
        task.ttr_minutes = max(0, int(delta.total_seconds() // 60))
        task.notes = f"{task.notes}\n[{now.isoformat()}] {actor}: Case closed".strip()
        if task.officer and task.officer.current_load > 0:
            task.officer.current_load -= 1
            task.officer.save(update_fields=["current_load"])
        _send_telegram_update(
            complaint=task.complaint,
            text=f"Task #{task.id} is finalized as solved. Thank you for verification.",
        )

    if to_state == "escalated":
        task.escalated_count += 1
        task.last_escalated_at = now
        manager = _pick_manager(complaint=task.complaint)
        if manager:
            task.manager = manager
            task.escalated_to_manager_at = now
            if not task.officer:
                task.officer = manager
                manager.current_load += 1
                manager.save(update_fields=["current_load"])
            task.notes = (
                f"{task.notes}\n[{now.isoformat()}] {actor}: Escalated to manager {manager.name}"
            ).strip()
            _send_telegram_update(
                complaint=task.complaint,
                text=(
                    f"Task #{task.id} escalated and assigned to manager {manager.name} "
                    f"({manager.username}) due to SLA/verification conditions."
                ),
            )
        else:
            task.notes = f"{task.notes}\n[{now.isoformat()}] {actor}: Escalated (manager unavailable)".strip()
            _send_telegram_update(
                complaint=task.complaint,
                text=f"Task #{task.id} escalated, but manager assignment is pending.",
            )

    if to_state == "assigned":
        if not task.officer:
            officer = _pick_officer(complaint=task.complaint)
            if not officer:
                raise ValueError("No available officer to assign")
            _assign_task_to_officer(task=task, officer=officer, note=f"{actor}: assigned")

    if to_state == "in_progress":
        task.notes = f"{task.notes}\n[{now.isoformat()}] {actor}: Work in progress".strip()

    task.save()

    if to_state == "closed":
        assign_queued_tasks()

    return task


def run_escalation_rules() -> int:
    now = timezone.now()
    candidates = ResolutionTask.objects.select_related("complaint", "complaint__assigned_department", "complaint__location_ref").filter(
        ~Q(state="closed"),
        sla_due_at__lt=now,
    ).exclude(state="escalated")

    escalated = 0
    for task in candidates:
        transition_task_state(task=task, to_state="escalated", actor="SLA Agent")
        escalated += 1

    assign_queued_tasks()
    return escalated


def submit_citizen_verification(*, task: ResolutionTask, photo_url: str, approved: bool) -> ResolutionTask:
    if task.state != "resolved_pending_verification":
        raise ValueError("Verification can only be submitted for resolved pending verification tasks")
    if not photo_url.strip():
        raise ValueError("Photo URL is required")

    now = timezone.now()
    task.verification_photo_url = photo_url.strip()

    if approved:
        task.verification_status = "approved"
        task.verified_at = now
        task.save(update_fields=["verification_photo_url", "verification_status", "verified_at"])
        return transition_task_state(task=task, to_state="closed", actor="Citizen Verification Agent")

    task.verification_status = "rejected"
    task.save(update_fields=["verification_photo_url", "verification_status"])
    return transition_task_state(task=task, to_state="escalated", actor="Citizen Verification Agent")
