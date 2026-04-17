from django.urls import path

from .telegram_views import telegram_webhook
from .views import ClusterListView, ComplaintListCreateView
from .workflow_views import (
    OfficerListView,
    ResolutionTaskListView,
    ResolutionTaskTransitionView,
    ResolutionTaskVerifyView,
    RunEscalationRulesView,
)

urlpatterns = [
    path("complaints/", ComplaintListCreateView.as_view(), name="complaints-list-create"),
    path("clusters/", ClusterListView.as_view(), name="clusters-list"),
    path("telegram/webhook/", telegram_webhook, name="telegram-webhook"),
    path("workflow/tasks/", ResolutionTaskListView.as_view(), name="workflow-task-list"),
    path("workflow/officers/", OfficerListView.as_view(), name="workflow-officer-list"),
    path("workflow/tasks/<int:task_id>/transition/", ResolutionTaskTransitionView.as_view(), name="workflow-task-transition"),
    path("workflow/tasks/<int:task_id>/verify/", ResolutionTaskVerifyView.as_view(), name="workflow-task-verify"),
    path("workflow/escalate/", RunEscalationRulesView.as_view(), name="workflow-escalate"),
]
