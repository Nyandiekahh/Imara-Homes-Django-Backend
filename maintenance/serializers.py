from rest_framework import serializers

from .models import MaintenanceAttachment, MaintenanceRequest


class MaintenanceAttachmentSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)

    class Meta:
        model = MaintenanceAttachment
        fields = ["id", "request", "image", "image_url", "caption", "uploaded_by_name", "created_at"]
        read_only_fields = ["id", "image_url", "uploaded_by_name", "created_at"]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class MaintenanceRequestSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenancy.user.full_name", read_only=True)
    tenant_phone = serializers.CharField(source="tenancy.user.phone", read_only=True)
    property_id = serializers.UUIDField(source="tenancy.property.id", read_only=True)
    property_name = serializers.CharField(source="tenancy.property.name", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True)
    attachments = MaintenanceAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceRequest
        fields = [
            "id",
            "tenancy",
            "tenant_name",
            "tenant_phone",
            "property_id",
            "property_name",
            "unit",
            "unit_name",
            "title",
            "description",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "notes",
            "attachments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenancy", "unit", "created_at", "updated_at"]
