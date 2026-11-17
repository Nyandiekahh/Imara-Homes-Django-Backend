from django.urls import path

from .views import MaintenanceAttachmentUploadView, MaintenanceDetailView, MaintenanceListView

urlpatterns = [
    path("maintenance/", MaintenanceListView.as_view()),
    path("maintenance/<uuid:request_id>/", MaintenanceDetailView.as_view()),
    path("maintenance/<uuid:request_id>/photos/", MaintenanceAttachmentUploadView.as_view()),
    path("maintenance/<uuid:request_id>/photos/<uuid:attachment_id>/", MaintenanceAttachmentUploadView.as_view()),
]
