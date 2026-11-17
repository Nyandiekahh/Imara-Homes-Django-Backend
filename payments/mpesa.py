"""Safaricom Daraja (M-Pesa) integration: OAuth, STK Push, and status query.

Fully env-driven via settings.MPESA_* (see config/settings.py). When
MPESA_CONSUMER_KEY/SECRET are not set, `is_configured()` returns False and the
calling view falls back to a clearly-labelled development simulation instead
of pretending to move real money.
"""
import base64
import logging
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"


class DarajaError(Exception):
	pass


def is_configured():
	return bool(settings.MPESA_CONSUMER_KEY and settings.MPESA_CONSUMER_SECRET and settings.MPESA_PASSKEY)


def _base_url():
	return PRODUCTION_BASE_URL if settings.MPESA_ENV == "production" else SANDBOX_BASE_URL


def get_access_token():
	url = f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials"
	response = requests.get(
		url,
		auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
		timeout=15,
	)
	response.raise_for_status()
	return response.json()["access_token"]


def _password_and_timestamp():
	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
	password = base64.b64encode(raw.encode()).decode()
	return password, timestamp


def _callback_url():
	base = settings.MPESA_CALLBACK_BASE_URL.rstrip("/")
	secret = settings.MPESA_CALLBACK_SECRET
	url = f"{base}/api/payments/mpesa/callback/"
	if secret:
		url = f"{url}?secret={secret}"
	return url


def stk_push(phone, amount, account_reference=None, transaction_desc=None):
	"""Initiate an STK push. Returns the Daraja response dict on success or
	raises DarajaError with a human-readable message on failure."""
	if not settings.MPESA_CALLBACK_BASE_URL:
		raise DarajaError(
			"MPESA_CALLBACK_BASE_URL is not set — Safaricom needs a public HTTPS URL to call back."
		)

	token = get_access_token()
	password, timestamp = _password_and_timestamp()

	payload = {
		"BusinessShortCode": settings.MPESA_SHORTCODE,
		"Password": password,
		"Timestamp": timestamp,
		"TransactionType": "CustomerPayBillOnline",
		"Amount": int(round(float(amount))),
		"PartyA": phone,
		"PartyB": settings.MPESA_SHORTCODE,
		"PhoneNumber": phone,
		"CallBackURL": _callback_url(),
		"AccountReference": (account_reference or settings.MPESA_ACCOUNT_REFERENCE)[:12],
		"TransactionDesc": (transaction_desc or "Rent Payment")[:13],
	}

	response = requests.post(
		f"{_base_url()}/mpesa/stkpush/v1/processrequest",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=20,
	)
	data = response.json() if response.content else {}
	if response.status_code != 200 or data.get("ResponseCode") not in (None, "0"):
		message = data.get("errorMessage") or data.get("ResponseDescription") or "STK push request failed."
		raise DarajaError(message)
	return data


def query_stk_status(checkout_request_id):
	token = get_access_token()
	password, timestamp = _password_and_timestamp()
	payload = {
		"BusinessShortCode": settings.MPESA_SHORTCODE,
		"Password": password,
		"Timestamp": timestamp,
		"CheckoutRequestID": checkout_request_id,
	}
	response = requests.post(
		f"{_base_url()}/mpesa/stkpushquery/v1/query",
		json=payload,
		headers={"Authorization": f"Bearer {token}"},
		timeout=20,
	)
	return response.json() if response.content else {}
