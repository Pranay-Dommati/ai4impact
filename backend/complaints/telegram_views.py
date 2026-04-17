import requests
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .service import process_complaint


@api_view(["POST"])
def telegram_webhook(request):
    data = request.data

    message = data.get("message") or data.get("edited_message") or {}
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return Response({"status": "ignored"})

    try:
        complaint, meta = process_complaint(text=text, source="telegram")
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
