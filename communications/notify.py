"""Unified notification helper: sends email and/or SMS to a user according to
their notification preferences, and returns both log objects. Used anywhere
the app needs to reach a user (invitations, reminders, receipts, agent
assignments) without duplicating the "which channel(s)" decision.
"""
from .email_service import send_email
from .sms_service import send_sms


def notify_user(user, subject, message, sms_message=None, announcement=None, force=False):
	"""Send `message` by email and/or SMS depending on the user's saved
	preferences (notify_by_email / notify_by_sms). Pass force=True to ignore
	preferences (used for security-critical messages like OTPs)."""
	results = {"email": None, "sms": None}

	if user.email and (force or getattr(user, "notify_by_email", True)):
		results["email"] = send_email(user.email, subject, message, announcement=announcement)

	if user.phone and (force or getattr(user, "notify_by_sms", True)):
		results["sms"] = send_sms(user.phone, sms_message or message, announcement=announcement)

	return results
