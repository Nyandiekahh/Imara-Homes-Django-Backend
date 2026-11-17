import csv
import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from communications.notify import notify_user
from communications.phone import normalize_kenyan_phone
from properties.scoping import accessible_properties, accessible_property_ids
from tenancies.models import Tenancy
from users.models import User

from . import mpesa
from .charges import build_charges_breakdown, charges_total
from .models import MpesaTransaction, Payment
from .receipts import build_receipt_pdf
from .reports import build_revenue_report
from .serializers import PaymentSerializer

logger = logging.getLogger(__name__)


def _payments_for_user(user):
	qs = Payment.objects.select_related("tenancy", "tenancy__user", "unit", "property")
	if user.role in (User.Role.OWNER, User.Role.AGENT, User.Role.ADMIN):
		qs = qs.filter(property_id__in=accessible_property_ids(user, permission="can_manage_payments" if user.role == User.Role.AGENT else None))
	elif user.role == User.Role.TENANT:
		qs = qs.filter(tenancy__user=user)
	return qs


def _notify_payment_success(payment):
	"""Send a receipt notification (SMS + email) once a payment is confirmed."""
	try:
		tenant = payment.tenancy.user
		message = (
			f"Payment of KES {payment.paid_amount:,.2f} received for {payment.unit.name if payment.unit else payment.property.name} "
			f"({payment.period}). Receipt No: {payment.receipt_number}. Thank you."
		)
		notify_user(tenant, subject=f"{settings.APP_NAME} Payment Receipt", message=message)
	except Exception:  # noqa: BLE001 - never let a notification failure break payment processing
		logger.exception("Failed to send payment confirmation notification for payment %s", payment.id)


class PaymentListView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def get(self, request):
		qs = _payments_for_user(request.user)
		status_filter = request.query_params.get("status")
		property_id = request.query_params.get("property_id")
		period = request.query_params.get("period")
		search = request.query_params.get("search")
		ordering = request.query_params.get("ordering")

		if status_filter:
			qs = qs.filter(status=status_filter)
		if property_id:
			qs = qs.filter(property_id=property_id)
		if period:
			qs = qs.filter(period=period)
		if search:
			qs = qs.filter(tenancy__user__full_name__icontains=search) | qs.filter(unit__name__icontains=search)
		if ordering:
			qs = qs.order_by(ordering)

		return Response(PaymentSerializer(qs, many=True).data)


class PaymentDetailView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def get(self, request, payment_id):
		payment = _payments_for_user(request.user).filter(id=payment_id).first()
		if not payment:
			return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
		return Response(PaymentSerializer(payment).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def initiate_stk_push(request):
	amount = Decimal(str(request.data.get("amount", 0)))
	phone_raw = request.data.get("phone") or request.data.get("phone_number", "")
	phone = normalize_kenyan_phone(phone_raw)
	account_ref = request.data.get("account_ref") or request.data.get("account_reference", "RENT")
	description = request.data.get("description") or request.data.get("transaction_desc", "Rent payment")

	if amount <= 0 or not phone:
		return Response(
			{"detail": "A valid amount and Kenyan phone number are required."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	tenancy = Tenancy.objects.filter(user=request.user).first()
	if not tenancy and request.data.get("tenant_id"):
		tenancy = Tenancy.objects.filter(id=request.data.get("tenant_id")).first()
	if not tenancy:
		return Response({"detail": "Tenant profile not found."}, status=status.HTTP_400_BAD_REQUEST)

	charges = build_charges_breakdown(tenancy)

	if mpesa.is_configured():
		try:
			daraja_response = mpesa.stk_push(
				phone=phone,
				amount=amount,
				account_reference=account_ref,
				transaction_desc=description,
			)
		except mpesa.DarajaError as exc:
			return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
		except Exception:  # noqa: BLE001
			logger.exception("Unexpected error calling Daraja STK push")
			return Response({"detail": "Could not reach M-Pesa right now. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)

		checkout_id = daraja_response.get("CheckoutRequestID")
		merchant_id = daraja_response.get("MerchantRequestID", "")

		payment = Payment.objects.create(
			tenancy=tenancy,
			property=tenancy.property,
			unit=tenancy.unit,
			period=timezone.now().strftime("%Y-%m"),
			amount=amount,
			fine=0,
			charges=charges,
			paid_amount=0,
			status=Payment.Status.PENDING,
			payment_method=Payment.Method.MPESA,
			mpesa_checkout_request_id=checkout_id,
			metadata={"account_ref": account_ref, "description": description, "phone": phone},
		)
		MpesaTransaction.objects.create(
			payment=payment,
			merchant_request_id=merchant_id,
			checkout_request_id=checkout_id,
			result_code=0,
			result_desc="Pending customer authorization",
			phone_number=phone,
		)
		return Response(
			{
				"checkout_request_id": checkout_id,
				"merchant_request_id": merchant_id,
				"customer_message": daraja_response.get(
					"CustomerMessage", "STK push sent. Complete payment on your phone."
				),
			}
		)

	# --- Development-safe simulation (no MPESA_* credentials configured) ---
	checkout_id = f"ws_CO_DEV_{uuid.uuid4().hex[:20]}"
	payment = Payment.objects.create(
		tenancy=tenancy,
		property=tenancy.property,
		unit=tenancy.unit,
		period=timezone.now().strftime("%Y-%m"),
		amount=amount,
		fine=0,
		charges=charges,
		paid_amount=0,
		status=Payment.Status.PENDING,
		payment_method=Payment.Method.MPESA,
		mpesa_checkout_request_id=checkout_id,
		metadata={"account_ref": account_ref, "description": description, "phone": phone, "dev_mode": True},
	)
	MpesaTransaction.objects.create(
		payment=payment,
		merchant_request_id=f"mr_dev_{uuid.uuid4().hex[:16]}",
		checkout_request_id=checkout_id,
		result_code=0,
		result_desc="Pending customer authorization (dev simulation — set MPESA_* env vars for real Daraja)",
		phone_number=phone,
	)
	return Response(
		{
			"checkout_request_id": checkout_id,
			"merchant_request_id": payment.mpesa_transaction.merchant_request_id,
			"customer_message": "STK push sent. Complete payment on your phone.",
			"dev_mode": True,
		}
	)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def check_stk_status(request, checkout_request_id):
	transaction = MpesaTransaction.objects.select_related("payment").filter(
		checkout_request_id=checkout_request_id
	).first()
	if not transaction:
		return Response({"detail": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)

	payment = transaction.payment

	if payment.status == Payment.Status.PENDING and mpesa.is_configured() and not payment.metadata.get("dev_mode"):
		# Real credentials: proactively query Daraja in case the callback was missed,
		# but the callback endpoint remains the source of truth for completion.
		try:
			result = mpesa.query_stk_status(checkout_request_id)
			result_code = str(result.get("ResultCode", ""))
			if result_code == "0" and payment.status == Payment.Status.PENDING:
				receipt = f"NF{uuid.uuid4().hex[:8].upper()}"
				payment.status = Payment.Status.PAID
				payment.paid_amount = payment.total
				payment.receipt_number = receipt
				payment.paid_at = timezone.now()
				payment.save(update_fields=["status", "paid_amount", "receipt_number", "paid_at", "updated_at"])
				_notify_payment_success(payment)
		except Exception:  # noqa: BLE001 - query is best-effort; callback remains authoritative
			logger.info("Daraja status query failed for %s (will rely on callback)", checkout_request_id)

	elif payment.status == Payment.Status.PENDING and timezone.now() - payment.created_at > timedelta(seconds=8):
		# Development-safe simulation for local/dev parity with frontend polling.
		receipt = f"NFDEV{uuid.uuid4().hex[:8].upper()}"
		payment.status = Payment.Status.PAID
		payment.paid_amount = payment.total
		payment.receipt_number = receipt
		payment.paid_at = timezone.now()
		payment.save(update_fields=["status", "paid_amount", "receipt_number", "paid_at", "updated_at"])
		transaction.mpesa_receipt_number = receipt
		transaction.transaction_date = timezone.now().strftime("%Y%m%d%H%M%S")
		transaction.result_desc = "The service request is processed successfully."
		transaction.save(update_fields=["mpesa_receipt_number", "transaction_date", "result_desc", "updated_at"])
		_notify_payment_success(payment)

	if payment.status == Payment.Status.PAID:
		return Response(
			{
				"status": "completed",
				"receipt_number": payment.receipt_number,
				"amount": payment.paid_amount,
			}
		)

	if payment.status in [Payment.Status.OVERDUE, Payment.Status.WAIVED]:
		return Response({"status": "failed", "result_desc": "Payment not completed."})

	return Response({"status": "pending"})


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def mpesa_callback(request):
	"""Safaricom Daraja calls this endpoint directly (server-to-server) once
	the customer completes or cancels the STK push on their phone."""
	if settings.MPESA_CALLBACK_SECRET and request.query_params.get("secret") != settings.MPESA_CALLBACK_SECRET:
		return Response({"detail": "Invalid callback secret."}, status=status.HTTP_403_FORBIDDEN)

	body = request.data.get("Body", {})
	callback = body.get("stkCallback", {})
	checkout_request_id = callback.get("CheckoutRequestID")
	result_code = callback.get("ResultCode")
	result_desc = callback.get("ResultDesc", "")

	transaction = MpesaTransaction.objects.select_related("payment").filter(
		checkout_request_id=checkout_request_id
	).first()
	if not transaction:
		logger.warning("M-Pesa callback for unknown CheckoutRequestID: %s", checkout_request_id)
		# Always 200 the callback so Safaricom doesn't retry indefinitely.
		return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

	transaction.result_code = result_code or 0
	transaction.result_desc = result_desc
	transaction.raw_callback = request.data

	items = {}
	for item in callback.get("CallbackMetadata", {}).get("Item", []):
		items[item.get("Name")] = item.get("Value")

	transaction.mpesa_receipt_number = str(items.get("MpesaReceiptNumber", ""))
	transaction.transaction_date = str(items.get("TransactionDate", ""))
	transaction.phone_number = str(items.get("PhoneNumber", transaction.phone_number))
	transaction.save()

	payment = transaction.payment
	if result_code == 0:
		payment.status = Payment.Status.PAID
		payment.paid_amount = items.get("Amount", payment.total)
		payment.receipt_number = transaction.mpesa_receipt_number or payment.receipt_number
		payment.paid_at = timezone.now()
		payment.save(update_fields=["status", "paid_amount", "receipt_number", "paid_at", "updated_at"])
		_notify_payment_success(payment)
	else:
		payment.status = Payment.Status.OVERDUE if payment.status == Payment.Status.PENDING else payment.status
		payment.save(update_fields=["status", "updated_at"])

	return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def record_manual_payment(request):
	tenant_id = request.data.get("tenant_id")
	amount = Decimal(str(request.data.get("amount", 0)))
	if not tenant_id or amount <= 0:
		return Response(
			{"detail": "tenant_id and valid amount are required."},
			status=status.HTTP_400_BAD_REQUEST,
		)

	tenancy = Tenancy.objects.filter(
		id=tenant_id, property_id__in=accessible_property_ids(request.user)
	).first()
	if not tenancy:
		return Response({"detail": "Tenant not found."}, status=status.HTTP_404_NOT_FOUND)

	payment = Payment.objects.create(
		tenancy=tenancy,
		property=tenancy.property,
		unit=tenancy.unit,
		period=timezone.now().strftime("%Y-%m"),
		amount=amount,
		fine=0,
		charges=build_charges_breakdown(tenancy),
		paid_amount=amount,
		status=Payment.Status.PAID,
		payment_method=Payment.Method.MANUAL,
		receipt_number=request.data.get("receipt_number") or f"MN{uuid.uuid4().hex[:8].upper()}",
		paid_at=request.data.get("date") or timezone.now(),
		metadata={"notes": request.data.get("notes", ""), "recorded_by": str(request.user.id)},
	)
	_notify_payment_success(payment)
	return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_receipt(request, payment_id):
	payment = _payments_for_user(request.user).filter(id=payment_id).first()
	if not payment:
		return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
	return Response(
		{
			"receipt_number": payment.receipt_number,
			"date": payment.paid_at,
			"amount": payment.amount,
			"fine": payment.fine,
			"charges": payment.charges,
			"total": payment.total,
			"tenant_name": payment.tenancy.user.full_name or payment.tenancy.user.email,
			"unit_name": payment.unit.name if payment.unit else None,
			"period": payment.period,
			"payment_method": payment.payment_method,
		}
	)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_receipt_pdf(request, payment_id):
	payment = _payments_for_user(request.user).filter(id=payment_id).first()
	if not payment:
		return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
	if payment.status != Payment.Status.PAID:
		return Response({"detail": "Receipt is only available for paid payments."}, status=status.HTTP_400_BAD_REQUEST)

	buffer = build_receipt_pdf(payment)
	filename = f"receipt-{payment.receipt_number or payment.id}.pdf"
	return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def waive_fine(request, payment_id):
	payment = _payments_for_user(request.user).filter(id=payment_id).first()
	if not payment:
		return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)
	payment.fine = 0
	payment.status = Payment.Status.WAIVED
	payment.save(update_fields=["fine", "status", "updated_at"])
	return Response(PaymentSerializer(payment).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_payment_summary(request):
	payments = _payments_for_user(request.user)
	property_id = request.query_params.get("property_id")
	if property_id:
		payments = payments.filter(property_id=property_id)

	total_paid = payments.filter(status=Payment.Status.PAID).aggregate(total=Sum("paid_amount")).get("total") or Decimal("0")
	total_overdue = payments.filter(status=Payment.Status.OVERDUE).aggregate(total=Sum("total")).get("total") or Decimal("0")
	total_pending = payments.filter(status=Payment.Status.PENDING).aggregate(total=Sum("total")).get("total") or Decimal("0")

	return Response(
		{
			"total_paid": total_paid,
			"total_overdue": total_overdue,
			"total_pending": total_pending,
		}
	)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_overdue_payments(request):
	overdue = _payments_for_user(request.user).filter(status=Payment.Status.OVERDUE)
	return Response(PaymentSerializer(overdue, many=True).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_upcoming_payments(request):
	upcoming = _payments_for_user(request.user).filter(status=Payment.Status.PENDING).order_by("created_at")[:20]
	return Response(PaymentSerializer(upcoming, many=True).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def generate_statement(request):
	payments = _payments_for_user(request.user).order_by("-created_at")
	tenant_id = request.query_params.get("tenant_id")
	property_id = request.query_params.get("property_id")
	if tenant_id:
		payments = payments.filter(tenancy_id=tenant_id)
	if property_id:
		payments = payments.filter(property_id=property_id)

	response = HttpResponse(content_type="text/csv")
	response["Content-Disposition"] = "attachment; filename=payment_statement.csv"

	writer = csv.writer(response)
	writer.writerow(["Tenant", "Unit", "Period", "Rent", "Charges", "Fine", "Total", "Status", "Paid At", "Receipt"])
	for p in payments:
		writer.writerow(
			[
				p.tenancy.user.full_name or p.tenancy.user.email,
				p.unit.name if p.unit else "",
				p.period,
				p.amount,
				charges_total(p.charges),
				p.fine,
				p.total,
				p.status,
				p.paid_at,
				p.receipt_number,
			]
		)

	return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_revenue_report(request):
	"""Kenyan rental-income report: Monthly Collection, Monthly Expenditure,
	Monthly Revenue and Rental Tax — see payments/reports.py for the formula,
	which reads each property's own configurable rates rather than a hardcoded
	percentage."""
	if request.user.role == User.Role.TENANT:
		return Response({"detail": "Not available for tenants."}, status=status.HTTP_403_FORBIDDEN)

	properties = accessible_properties(request.user).select_related("payment_config")
	property_id = request.query_params.get("property_id")
	if property_id:
		properties = properties.filter(id=property_id)
	period = request.query_params.get("period")  # e.g. "2026-09"

	report = build_revenue_report(properties, period=period)
	return Response(report)
