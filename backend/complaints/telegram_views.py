import requests
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ResolutionTask
from .service import process_complaint
from .workflow import submit_citizen_verification


def _extract_task_id(command_text: str, prefix: str) -> int | None:
    lowered = (command_text or "").strip().lower()
    if not lowered.startswith(prefix):
        return None
    parts = lowered.split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


@api_view(["POST"])
def telegram_webhook(request):
    data = request.data

    message = data.get("message") or data.get("edited_message") or {}
    text = message.get("text", "")
    caption = message.get("caption", "")
    photos = message.get("photo") or []
    chat_id = message.get("chat", {}).get("id")

    if not chat_id:
        return Response({"status": "ignored"})

    # Citizen verification via Telegram image upload + caption: verify <task_id>
    verify_task_id = _extract_task_id(caption, "verify")
    if photos and verify_task_id is not None:
        task = ResolutionTask.objects.filter(id=verify_task_id).first()
        if not task:
            send_telegram_reply(chat_id, f"Task #{verify_task_id} not found")
            return Response({"status": "verify_task_not_found"}, status=404)

        largest = photos[-1] if photos else {}
        file_id = str(largest.get("file_id", "")).strip()
        if not file_id:
            send_telegram_reply(chat_id, "Photo missing file identifier. Please retry.")
            return Response({"status": "verify_missing_photo"}, status=400)

        try:
            submit_citizen_verification(task=task, photo_url=f"tg://{file_id}", approved=True)
            send_telegram_reply(chat_id, f"Verification received for Task #{task.id}. Complaint closed.")
        except ValueError as exc:
            send_telegram_reply(chat_id, str(exc))
            return Response({"status": "verify_failed", "detail": str(exc)}, status=400)

        return Response({"status": "verify_processed"})

    # Optional citizen rejection command: /reject <task_id>
    reject_task_id = _extract_task_id(text, "/reject")
    if reject_task_id is not None:
        task = ResolutionTask.objects.filter(id=reject_task_id).first()
        if not task:
            send_telegram_reply(chat_id, f"Task #{reject_task_id} not found")
            return Response({"status": "reject_task_not_found"}, status=404)
        try:
            submit_citizen_verification(task=task, photo_url="tg://rejected", approved=False)
            send_telegram_reply(chat_id, f"Task #{task.id} marked not solved. Escalated to manager.")
        except ValueError as exc:
            send_telegram_reply(chat_id, str(exc))
            return Response({"status": "reject_failed", "detail": str(exc)}, status=400)
        return Response({"status": "reject_processed"})

    status_task_id = _extract_task_id(text, "/status")
    if status_task_id is not None:
        task = ResolutionTask.objects.select_related("officer", "manager").filter(id=status_task_id).first()
        if not task:
            send_telegram_reply(chat_id, f"Task #{status_task_id} not found")
            return Response({"status": "status_task_not_found"}, status=404)
        send_telegram_reply(
            chat_id,
            (
                f"Task #{task.id}\n"
                f"State: {task.state}\n"
                f"Officer: {task.officer.name if task.officer else 'Unassigned'}\n"
                f"Manager: {task.manager.name if task.manager else 'Unassigned'}\n"
                f"SLA: {task.sla_due_at}"
            ),
        )
        return Response({"status": "status_processed"})

    if not text:
        send_telegram_reply(chat_id, "Send a complaint text, or verify using a photo captioned: verify <task_id>")
        return Response({"status": "ignored_empty_text"})

    try:
        complaint, meta = process_complaint(text=text, source="telegram", citizen_chat_id=int(chat_id))
    except ValueError:
        send_telegram_reply(
            chat_id,
            "Complaint received, but AI analysis is temporarily unavailable. Please try again in a minute.",
        )
        return Response({"status": "ai_unavailable"}, status=503)

    reply = (
        "Complaint received\n\n"
        f"{text}\n\n"
        f"Priority: {complaint.priority.upper()} (score: {complaint.score})\n"
        f"Severity/Urgency: {complaint.severity.upper()}/{complaint.urgency.upper()}\n"
        f"Cluster: {complaint.cluster_id}\n"
        f"Impact: {getattr(complaint, 'impact_score', '-')}\n"
        f"Category: {meta.get('category')} | Location: {meta.get('location')}\n"
        f"Department: {meta.get('department', 'Unassigned')}"
    )
    send_telegram_reply(chat_id, reply)

    return Response({"status": "processed"})


def send_telegram_reply(chat_id, text):
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
