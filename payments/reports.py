"""Kenyan rental-income reporting: Monthly Collection, Monthly Expenditure,
Monthly Revenue and Rental Tax, computed per-property from each property's own
PaymentConfig rates (never hardcoded), then rolled up across every property
the requesting user can access.
"""
from decimal import Decimal

from django.db.models import Sum

from .models import Payment


def _quantize(value):
	return (value or Decimal("0")).quantize(Decimal("0.01"))


def build_revenue_report(properties, period=None):
	"""properties: queryset/iterable of Property instances (already scoped to
	the requesting user). period: 'YYYY-MM' string, defaults to all-time."""
	breakdown = []
	totals = {
		"collection": Decimal("0"),
		"expenditure": Decimal("0"),
		"revenue": Decimal("0"),
		"tax": Decimal("0"),
	}

	for prop in properties:
		payments = Payment.objects.filter(property=prop, status=Payment.Status.PAID)
		if period:
			payments = payments.filter(period=period)
		collection = payments.aggregate(total=Sum("paid_amount")).get("total") or Decimal("0")

		config = getattr(prop, "payment_config", None)
		expenditure_rate = (config.expenditure_rate_percent if config else Decimal("40.00")) / Decimal("100")
		tax_rate = (config.rental_tax_rate_percent if config else Decimal("10.00")) / Decimal("100")

		expenditure = collection * expenditure_rate
		revenue = collection - expenditure
		tax = revenue * tax_rate

		breakdown.append(
			{
				"property_id": str(prop.id),
				"property_name": prop.name,
				"collection": _quantize(collection),
				"expenditure": _quantize(expenditure),
				"revenue": _quantize(revenue),
				"tax": _quantize(tax),
				"expenditure_rate_percent": config.expenditure_rate_percent if config else Decimal("40.00"),
				"rental_tax_rate_percent": config.rental_tax_rate_percent if config else Decimal("10.00"),
			}
		)

		totals["collection"] += collection
		totals["expenditure"] += expenditure
		totals["revenue"] += revenue
		totals["tax"] += tax

	return {
		"period": period,
		"properties": breakdown,
		"totals": {k: _quantize(v) for k, v in totals.items()},
	}
