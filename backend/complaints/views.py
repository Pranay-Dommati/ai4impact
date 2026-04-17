from django.db.models import Case, IntegerField, Value, When
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Complaint
from .serializers import ComplaintSerializer
from .service import process_complaint
from .utils import get_cluster_insights


class ComplaintListCreateView(APIView):
	def get(self, request):
		priority_order = Case(
			When(priority="high", then=Value(3)),
			When(priority="medium", then=Value(2)),
			default=Value(1),
			output_field=IntegerField(),
		)
		complaints = Complaint.objects.all().annotate(priority_rank=priority_order).order_by(
			"-priority_rank", "-score", "-created_at"
		)
		serializer = ComplaintSerializer(complaints, many=True)
		return Response(serializer.data)

	def post(self, request):
		serializer = ComplaintSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			complaint, _ = process_complaint(**serializer.validated_data)
		except ValueError as exc:
			return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
		return Response(ComplaintSerializer(complaint).data, status=status.HTTP_201_CREATED)


class ClusterListView(APIView):
	def get(self, request):
		return Response(get_cluster_insights())
