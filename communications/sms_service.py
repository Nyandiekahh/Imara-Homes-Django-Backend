"""Africa's Talking SMS integration.

Fully env-driven (AFRICASTALKING_USERNAME / AFRICASTALKING_API_KEY /
AFRICASTALKING_SENDER_ID / AFRICASTALKING_ENV in settings). When credentials
are not configured the send is recorded as a failed SMSLog instead of raising,
so the rest of the app keeps working in local/dev environments without SMS
set up.
"""
import logging

import requests
from django.conf import settings
from django.utils import timezone

from .phone import normalize_kenyan_phone

logger = logging.getLogger(__name__)

SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
PRODUCTION_URL = "https://api.africastalking.com/version1/messaging"


def is_configured():
	return bool(settings.AFRICASTALKING_USERNAME and settings.AFRICASTALKING_API_KEY)


def send_sms(phone, message, announcement=None):
	"""Send an SMS and return the created SMSLog instance."""
	from .models import SMSLog  # local import to avoid app-loading order issues

	normalized = normalize_kenyan_phone(phone)
	if not normalized:
		return SMSLog.objects.create(
			announcement=announcement,
			recipient_phone=phone or "",
			message=message,
			status=SMSLog.Status.FAILED,
			error_message="Invalid or missing Kenyan phone number.",
		)

	if not is_configured():
		return SMSLog.objects.create(
			announcement=announcement,
			recipient_phone=normalized,
			message=message,
			status=SMSLog.Status.FAILED,
			error_message="SMS is not configured (set AFRICASTALKING_USERNAME/AFRICASTALKING_API_KEY).",
		)

	url = SANDBOX_URL if settings.AFRICASTALKING_ENV == "sandbox" else PRODUCTION_URL
	payload = {
		"username": settings.AFRICASTALKING_USERNAME,
		"to": f"+{normalized}",
		"message": message,
	}
	if settings.AFRICASTALKING_SENDER_ID:
		payload["from"] = settings.AFRICASTALKING_SENDER_ID

	headers = {
		"apiKey": settings.AFRICASTALKING_API_KEY,
		"Content-Type": "application/x-www-form-urlencoded",
		"Accept": "application/json",
	}

	try:
		response = requests.post(url, data=payload, headers=headers, timeout=15)
		response.raise_for_status()
		data = response.json()
		recipients = data.get("SMSMessageData", {}).get("Recipients", [])
		recipient = recipients[0] if recipients else {}
		status_text = recipient.get("status", "")
		success = status_text.lower().startswith("success") or str(recipient.get("statusCode")) == "101"
		return SMSLog.objects.create(
			announcement=announcement,
			recipient_phone=normalized,
			message=message,
			status=SMSLog.Status.SENT if success else SMSLog.Status.FAILED,
			provider_message_id=recipient.get("messageId", ""),
			provider_status=status_text,
			error_message="" if success else status_text,
			sent_at=timezone.now() if success else None,
		)
	except Exception as exc:  # noqa: BLE001 - external API, log and degrade gracefully
		logger.warning("SMS send failed for %s: %s", normalized, exc)
		return SMSLog.objects.create(
			announcement=announcement,
			recipient_phone=normalized,
			message=message,
			status=SMSLog.Status.FAILED,
			error_message=str(exc),
		)
