from rest_framework import status
from django.db.models import Count, Q
from django.db.utils import OperationalError, ProgrammingError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Officer, ResolutionTask
from .serializers import OfficerSerializer, ResolutionTaskSerializer
from .workflow import run_escalation_rules, submit_citizen_verification, transition_task_state


class OfficerListView(APIView):
    def get(self, request):
        try:
            officers = Officer.objects.select_related("department", "location_ref").annotate(
                active_task_count=Count("tasks", filter=~Q(tasks__state="closed")),
            )
            return Response(OfficerSerializer(officers, many=True).data)
        except (OperationalError, ProgrammingError):
            return Response([])


class ResolutionTaskListView(APIView):
    def get(self, request):
        try:
            tasks = ResolutionTask.objects.select_related("complaint", "officer", "manager").all()
            return Response(ResolutionTaskSerializer(tasks, many=True).data)
        except (OperationalError, ProgrammingError):
            return Response([])


class ResolutionTaskTransitionView(APIView):
    def post(self, request, task_id: int):
        to_state = str(request.data.get("state", "")).strip()
        actor = str(request.data.get("actor", "workflow_api")).strip() or "workflow_api"
        try:
            task = ResolutionTask.objects.select_related("officer", "manager").filter(id=task_id).first()
        except (OperationalError, ProgrammingError):
            return Response({"detail": "Workflow tables are not migrated yet"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not task:
            return Response({"detail": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            task = transition_task_state(task=task, to_state=to_state, actor=actor)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ResolutionTaskSerializer(task).data)


class ResolutionTaskVerifyView(APIView):
    def post(self, request, task_id: int):
        photo_url = str(request.data.get("photo_url", "")).strip()
        approved = bool(request.data.get("approved", False))
        try:
            task = ResolutionTask.objects.filter(id=task_id).first()
        except (OperationalError, ProgrammingError):
            return Response({"detail": "Workflow tables are not migrated yet"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not task:
            return Response({"detail": "Task not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            task = submit_citizen_verification(task=task, photo_url=photo_url, approved=approved)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ResolutionTaskSerializer(task).data)


class RunEscalationRulesView(APIView):
    def post(self, request):
        try:
            escalated_count = run_escalation_rules()
            return Response({"escalated": escalated_count})
        except (OperationalError, ProgrammingError):
            return Response({"detail": "Workflow tables are not migrated yet"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
