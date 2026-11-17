"""Real outbound email, wrapping Django's send_mail so every call also leaves
an EmailLog audit trail (SENT or FAILED, never a false-positive SENT)."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def send_email(to_email, subject, body, announcement=None, html_body=None):
	from .models import EmailLog  # local import to avoid app-loading order issues

	try:
		send_mail(
			subject=subject,
			message=body,
			from_email=settings.DEFAULT_FROM_EMAIL,
			recipient_list=[to_email],
			html_message=html_body,
			fail_silently=False,
		)
		return EmailLog.objects.create(
			announcement=announcement,
			recipient_email=to_email,
			subject=subject,
			body=body,
			status=EmailLog.Status.SENT,
			sent_at=timezone.now(),
		)
	except Exception as exc:  # noqa: BLE001 - external SMTP, log and degrade gracefully
		logger.warning("Email send failed for %s: %s", to_email, exc)
		return EmailLog.objects.create(
			announcement=announcement,
			recipient_email=to_email,
			subject=subject,
			body=body,
			status=EmailLog.Status.FAILED,
			error_message=str(exc),
		)
