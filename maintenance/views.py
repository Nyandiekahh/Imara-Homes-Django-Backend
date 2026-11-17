from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from properties.scoping import accessible_property_ids
from users.models import User

from .models import MaintenanceAttachment, MaintenanceRequest
from .serializers import MaintenanceAttachmentSerializer, MaintenanceRequestSerializer


def _maintenance_queryset_for_user(user):
	qs = MaintenanceRequest.objects.select_related(
		"tenancy", "tenancy__user", "tenancy__property", "unit", "assigned_to"
	)
	if user.role in (User.Role.OWNER, User.Role.ADMIN, User.Role.AGENT):
		qs = qs.filter(
			tenancy__property_id__in=accessible_property_ids(
				user, permission="can_manage_maintenance" if user.role == User.Role.AGENT else None
			)
		)
	elif user.role == User.Role.TENANT:
		qs = qs.filter(tenancy__user=user)
	else:
		qs = qs.none()
	return qs


class MaintenanceListView(APIView):
	"""Owner/agent view across all properties they manage — the tenant-facing
	create/list endpoints live under /tenants/<id>/maintenance/."""

	permission_classes = [permissions.IsAuthenticated]

	def get(self, request):
		if request.user.role == User.Role.TENANT:
			return Response({"detail": "Use /tenants/me/maintenance/ instead."}, status=status.HTTP_403_FORBIDDEN)

		qs = _maintenance_queryset_for_user(request.user)
		status_filter = request.query_params.get("status")
		priority_filter = request.query_params.get("priority")
		property_id = request.query_params.get("property_id")
		if status_filter:
			qs = qs.filter(status=status_filter)
		if priority_filter:
			qs = qs.filter(priority=priority_filter)
		if property_id:
			qs = qs.filter(tenancy__property_id=property_id)
		return Response(MaintenanceRequestSerializer(qs, many=True, context={"request": request}).data)


class MaintenanceDetailView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def get_object(self, request, request_id):
		return _maintenance_queryset_for_user(request.user).filter(id=request_id).first()

	def get(self, request, request_id):
		obj = self.get_object(request, request_id)
		if not obj:
			return Response({"detail": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
		return Response(MaintenanceRequestSerializer(obj, context={"request": request}).data)

	def patch(self, request, request_id):
		obj = self.get_object(request, request_id)
		if not obj:
			return Response({"detail": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

		allowed_fields = ["status", "priority", "notes", "assigned_to"]
		if request.user.role == User.Role.TENANT:
			allowed_fields = ["description"]

		data = {k: v for k, v in request.data.items() if k in allowed_fields}
		serializer = MaintenanceRequestSerializer(obj, data=data, partial=True, context={"request": request})
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class MaintenanceAttachmentUploadView(APIView):
	"""Upload a photo to a maintenance request. Reachable by the tenant who
	filed it, or the owner/agent managing the property."""

	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def post(self, request, request_id):
		obj = _maintenance_queryset_for_user(request.user).filter(id=request_id).first()
		if not obj:
			return Response({"detail": "Request not found."}, status=status.HTTP_404_NOT_FOUND)

		image = request.FILES.get("image")
		if not image:
			return Response({"detail": "image is required."}, status=status.HTTP_400_BAD_REQUEST)

		attachment = MaintenanceAttachment.objects.create(
			request=obj,
			image=image,
			caption=request.data.get("caption", ""),
			uploaded_by=request.user,
		)
		return Response(MaintenanceAttachmentSerializer(attachment, context={"request": request}).data, status=status.HTTP_201_CREATED)

	def delete(self, request, request_id, attachment_id):
		obj = _maintenance_queryset_for_user(request.user).filter(id=request_id).first()
		if not obj:
			return Response({"detail": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
		attachment = obj.attachments.filter(id=attachment_id).first()
		if not attachment:
			return Response({"detail": "Attachment not found."}, status=status.HTTP_404_NOT_FOUND)
		attachment.delete()
		return Response({"success": True})
