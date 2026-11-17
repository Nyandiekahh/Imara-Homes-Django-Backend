"""Kenyan phone number normalisation shared by SMS and M-Pesa."""
import re


def normalize_kenyan_phone(raw):
	"""Return a phone number in 2547XXXXXXXX / 2541XXXXXXXX format, or None
	if it doesn't look like a valid Kenyan mobile number."""
	if not raw:
		return None
	digits = re.sub(r"\D", "", str(raw))

	if digits.startswith("254") and len(digits) == 12:
		normalized = digits
	elif digits.startswith("0") and len(digits) == 10:
		normalized = "254" + digits[1:]
	elif digits.startswith("7") and len(digits) == 9:
		normalized = "254" + digits
	elif digits.startswith("1") and len(digits) == 9:
		normalized = "254" + digits
	else:
		return None

	if not re.match(r"^254[17]\d{8}$", normalized):
		return None
	return normalized


def to_international(raw):
	normalized = normalize_kenyan_phone(raw)
	return f"+{normalized}" if normalized else None
