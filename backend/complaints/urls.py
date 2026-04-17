from django.urls import path

from .telegram_views import telegram_webhook
from .views import ClusterListView, ComplaintListCreateView

urlpatterns = [
    path("complaints/", ComplaintListCreateView.as_view(), name="complaints-list-create"),
    path("clusters/", ClusterListView.as_view(), name="clusters-list"),
    path("telegram/webhook/", telegram_webhook, name="telegram-webhook"),
]
